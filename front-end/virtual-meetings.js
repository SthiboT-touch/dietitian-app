/* Google OAuth secrets and tokens never enter the browser. */
function virtualMeetingSlot(appointment) {
    if (appointment.consultation_type !== "VIRTUAL" || !["CONFIRMED", "SCHEDULED"].includes(appointment.status)) return "";
    return `<div class="virtual-meeting" data-virtual-appointment="${escapeHtml(appointment.appointment_id)}" aria-live="polite">Loading virtual meeting…</div>`;
}

async function mountVirtualMeetings(root) {
    await Promise.all([...root.querySelectorAll("[data-virtual-appointment]")].map(async slot => {
        const appointmentId = slot.dataset.virtualAppointment;
        const doctor = currentUser?.type === "dietitian";
        const endpoint = `/api/v1/appointments/${encodeURIComponent(appointmentId)}/meeting`;
        const render = async () => {
            try {
                const result = await request(endpoint);
                if (!slot.isConnected) return;
                const validLink = typeof result.meeting_url === "string" && /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(result.meeting_url);
                if (result.status === "READY" && validLink) {
                    slot.innerHTML = `<a class="button button-small button-primary" href="${escapeHtml(result.meeting_url)}" target="_blank" rel="noopener noreferrer">Join Google Meet</a>`;
                } else if (result.status === "UNAVAILABLE") {
                    slot.textContent = "A meeting link is available only for a confirmed virtual appointment.";
                } else {
                    slot.innerHTML = `<p>${escapeHtml(result.message || (doctor ? "Create a Google Meet link for this appointment. Connect Google in Settings first." : "Your dietitian will prepare the Google Meet link for this appointment."))}</p>${doctor ? '<button type="button" class="button button-small" data-create-meeting>Create / check Google Meet</button>' : '<button type="button" class="button button-small" data-check-meeting>Refresh meeting link</button>'}<p data-meeting-message role="status"></p>`;
                    slot.querySelector("[data-check-meeting]")?.addEventListener("click", render);
                    slot.querySelector("[data-create-meeting]")?.addEventListener("click", async event => {
                        const button = event.currentTarget;
                        button.disabled = true;
                        try {
                            await request(endpoint, {method: "POST"});
                            await render();
                        } catch(error) {
                            if (slot.isConnected) slot.querySelector("[data-meeting-message]").textContent = error.message;
                            button.disabled = false;
                        }
                    });
                }
            } catch(error) {
                if (slot.isConnected) slot.textContent = error.message;
            }
        };
        await render();
    }));
}

async function mountGoogleSettings(target) {
    const anchor = target.firstElementChild;
    const panel = document.createElement("section");
    panel.className = "content-panel google-meeting-settings";
    try {
        const status = await request("/api/v1/integrations/google");
        panel.innerHTML = `<h2>Google Meet &amp; Calendar</h2><p>${status.connected ? "Google is connected. Confirmed virtual appointments can have a Google Meet link." : "Connect your Google account to create virtual appointment links."}</p>
          <p>Only appointment time and a generic title are sent to Google. Patients join through their appointment page.</p>
          ${!status.configured ? '<p class="notice">Google meetings need to be configured by the app administrator before connecting.</p>' : `<button type="button" class="button button-primary" data-google-connect>${status.connected ? "Reconnect Google" : "Connect Google"}</button>`}
          ${status.connected ? `<form data-google-mode class="form-grid"><div class="form-field"><label>Virtual meeting format<select class="text-input" name="mode"><option value="calendar" ${status.mode === "calendar" ? "selected" : ""}>Calendar appointment with Google Meet</option><option value="meet" ${status.mode === "meet" ? "selected" : ""}>Google Meet link only</option></select></label></div><button type="submit" class="button quiet-button">Save meeting preference</button></form><button type="button" class="button quiet-button" data-google-disconnect>Disconnect Google</button>` : ""}
          <p data-google-message role="status" aria-live="polite"></p>`;
        panel.querySelector("[data-google-connect]")?.addEventListener("click", async event => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                const result = await request("/api/v1/integrations/google/connect", {method: "POST"});
                const url = new URL(result.authorization_url);
                if (url.protocol !== "https:" || url.hostname !== "accounts.google.com" || url.pathname !== "/o/oauth2/v2/auth") throw new Error("Google connection could not be started.");
                window.location.assign(url.href);
            } catch(error) {
                panel.querySelector("[data-google-message]").textContent = error.message;
                button.disabled = false;
            }
        });
        panel.querySelector("[data-google-mode]")?.addEventListener("submit", async event => {
            event.preventDefault();
            try {
                await request("/api/v1/integrations/google", {method: "PATCH", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))});
                panel.querySelector("[data-google-message]").textContent = "Meeting preference saved. Existing appointments keep their meeting format.";
            } catch(error) { panel.querySelector("[data-google-message]").textContent = error.message; }
        });
        panel.querySelector("[data-google-disconnect]")?.addEventListener("click", async event => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                await request("/api/v1/integrations/google/disconnect", {method: "POST"});
                if (!panel.isConnected) return;
                await mountGoogleSettings(target);
                panel.remove();
            } catch(error) {
                panel.querySelector("[data-google-message]").textContent = error.message;
                button.disabled = false;
            }
        });
    } catch(error) {
        panel.innerHTML = `<h2>Google Meet &amp; Calendar</h2><p class="notice">${escapeHtml(error.message)}</p>`;
    }
    if (target.isConnected && target.firstElementChild === anchor) target.append(panel);
}

window.addEventListener("load", () => {
    if (new URLSearchParams(window.location.search).get("google") === "connected") {
        window.history.replaceState({}, "", window.location.pathname);
        if (currentUser?.type === "dietitian") navTo("dietitian-settings");
    }
});
