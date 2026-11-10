/* Provider links open in a separate HTTPS tab, including from a local HTTP app. */
function isVirtualAppointment(appointment) {
    return appointment.appointment_type === "VIRTUAL" || appointment.consultation_type === "VIRTUAL";
}

function safeMeetingUrl(value) {
    try {
        const url = new URL(value);
        return url.protocol === "https:" && !url.username && !url.password ? url : null;
    } catch {
        return null;
    }
}

function appointmentMeetingMarkup(appointment, clinician = false) {
    if (!isVirtualAppointment(appointment)) return "";
    if (appointment.status === "PENDING") {
        return '<p class="appointment-note">The meeting link appears after your dietitian confirms the appointment.</p>';
    }
    if (!["CONFIRMED", "SCHEDULED"].includes(appointment.status)) return "";
    const url = safeMeetingUrl(appointment.meeting_link);
    if (!url) {
        return clinician
            ? `<div class="meeting-actions"><button type="button" class="button button-small" data-create-appointment-meeting="${escapeHtml(appointment.appointment_id)}">Create meeting link</button></div>`
            : '<p class="appointment-note">Your dietitian is preparing the meeting link. Refresh appointments to check again.</p>';
    }
    const instruction = url.hostname === "meet.jit.si"
        ? clinician ? "Open Jitsi and sign in to start the room before your patient joins." : "Your dietitian starts the Jitsi room first. If asked, wait for the host."
        : "Opens your meeting provider in a new tab.";
    return `<div class="meeting-actions"><a class="button button-small button-primary" data-join-appointment-meeting href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${clinician ? "Start virtual appointment" : "Join virtual appointment"}</a><p class="appointment-note">${instruction}</p></div>`;
}

function meetingChoiceMarkup(appointment) {
    if (!isVirtualAppointment(appointment)) return "";
    return `<div class="meeting-choice">
      <label>Meeting service<select class="text-input" data-meeting-mode><option value="manual">Use my own meeting link (recommended)</option><option value="jitsi">Automatic Jitsi link (host sign-in required)</option></select></label>
      <p class="appointment-note" data-jitsi-note hidden>Jitsi requires the host to sign in before the patient can join. Public service usage limits apply. <a href="https://jitsi.org/meet-jit-si-terms-of-service/" target="_blank" rel="noopener noreferrer">View limits</a></p>
      <label data-manual-meeting>HTTPS meeting link<input class="text-input" type="url" data-manual-meeting-link placeholder="https://meet.google.com/..." autocomplete="off"></label>
    </div>`;
}

function bindMeetingControls(root, refresh) {
    root.querySelectorAll("[data-meeting-mode]").forEach(select => {
        const choice = select.closest(".meeting-choice");
        const updateChoice = () => {
            choice.querySelector("[data-manual-meeting]").hidden = select.value !== "manual";
            choice.querySelector("[data-jitsi-note]").hidden = select.value === "manual";
        };
        select.addEventListener("change", updateChoice);
        updateChoice();
    });
    root.querySelectorAll("[data-create-appointment-meeting]").forEach(button => button.addEventListener("click", async () => {
        button.disabled = true;
        try {
            await request(`/api/v1/appointments/${encodeURIComponent(button.dataset.createAppointmentMeeting)}/meeting`, {method: "POST"});
            await refresh();
        } catch (error) {
            if (button.isConnected) button.disabled = false;
            showWorkspaceMessage(error.message, true);
        }
    }));
}
