/* Medical history and clinician care workflow, using existing authenticated request helpers. */
const medicalHistoryFields = {
    medications: "Medications and supplements",
    surgeries: "Surgeries and hospital admissions",
    family_history: "Family medical history",
    dietary_history: "Dietary history and preferences",
    lifestyle: "Lifestyle and activity",
    concerns: "Current concerns and consultation goals",
};

document.addEventListener("click", event => {
    const button = event.target.closest("[data-care-record]");
    if (!button) return;
    renderClientRecord(button.dataset.careRecord);
    loadClientProfile(button.dataset.careRecord);
});

async function mountMedicalHistoryForm(target, clientId) {
    const anchor = target.firstElementChild;
    const base = `/api/v1/clients/${encodeURIComponent(clientId)}/care`;
    const events = await request(base);
    const history = events.filter(event => event.kind === "HISTORY").at(-1);
    const panel = document.createElement("section");
    panel.className = "content-panel care-workflow";
        panel.innerHTML = `<h2>Medical history and care</h2><div data-care-message role="status" aria-live="polite"></div>
            <p class="appointment-note">${history ? `Last history update: ${escapeHtml(new Date(history.created_at).toLocaleString())}` : "No detailed medical history submitted yet."}</p>
      <form data-history class="form-grid">${Object.entries(medicalHistoryFields).map(([key, label]) => `<div class="form-field"><label for="care-${key}">${label}</label><textarea class="text-input" id="care-${key}" name="${key}" maxlength="4000">${escapeHtml(history?.payload[key] || "")}</textarea></div>`).join("")}<div class="form-actions"><button class="button button-primary">Save medical history</button></div></form>`;
    if (!target.isConnected || target.firstElementChild !== anchor) return;
    target.append(panel);
    panel.querySelector("[data-history]").addEventListener("submit", async event => {
        event.preventDefault();
        const button = event.currentTarget.querySelector("button");
        button.disabled = true;
        try {
            await request(`${base}/history`, {
                method: "POST",
                body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))),
            });
            if (!panel.isConnected) return;
            await mountMedicalHistoryForm(target, clientId);
            panel.remove();
        } catch (error) {
            panel.querySelector("[data-care-message]").textContent = error.message;
            button.disabled = false;
        }
    });
}

async function bindConsultationChoice(form, preferred = "") {
    const appointments = await request("/api/v1/appointments");
    const field = document.createElement("div");
    field.className = "form-field";
    field.innerHTML = '<label>Completed consultation<select class="text-input" name="appointment_id" required></select></label><p class="appointment-note">Care is created only after a completed consultation.</p>';
    form.prepend(field);
    const select = field.querySelector("select");
    const refresh = () => {
        const matches = appointments.filter(a => a.client_id === form.elements.client_id.value && a.status === "COMPLETED").sort((a,b) => new Date(b.appointment_date) - new Date(a.appointment_date));
        select.innerHTML = '<option value="">Choose a completed consultation</option>' + matches.map(a => `<option value="${escapeHtml(a.appointment_id)}">${escapeHtml(new Date(a.appointment_date).toLocaleString())} · ${escapeHtml(a.appointment_id)}</option>`).join("");
        if (matches.some(a => a.appointment_id === preferred)) select.value = preferred;
        else if (matches.length) select.value = matches[0].appointment_id;
        form.querySelector('button[type="submit"]').disabled = matches.length === 0;
    };
    form.elements.client_id.addEventListener("input", refresh);
    form.elements.client_id.addEventListener("change", refresh);
    refresh();
}

async function mountCarePanel(target, clientId, clinician) {
    const anchor = target.firstElementChild;
    const base = `/api/v1/clients/${encodeURIComponent(clientId)}/care`;
    const [events, progress, goals, appointments] = await Promise.all([
        request(base), request(`/api/v1/clients/${encodeURIComponent(clientId)}/progress`),
        request(`/api/v1/goals?client_id=${encodeURIComponent(clientId)}`),
        request(`/api/v1/appointments?client_id=${encodeURIComponent(clientId)}`),
    ]);
    const consultations = appointments.filter(a => a.status === "COMPLETED");
    const history = events.filter(e => e.kind === "HISTORY").at(-1);
    const panel = document.createElement("section");
    panel.className = "content-panel care-workflow";
    panel.innerHTML = `${clinician ? `<h2>Medical history and care</h2>` : ""}<div data-care-message role="status" aria-live="polite"></div>
      ${clinician ? `<section><h3>Consultation</h3><p>Complete the consultation before setting goals, assigning plans or sharing recommendations.</p>${appointments.filter(a => ["CONFIRMED", "SCHEDULED"].includes(a.status)).map(a => `<p>${escapeHtml(new Date(a.appointment_date).toLocaleString())} <button type="button" class="button quiet-button" data-complete-consultation="${escapeHtml(a.appointment_id)}" ${new Date(a.appointment_date).getTime() > Date.now() ? "disabled" : ""}>Mark consultation completed</button></p>`).join("")}<div class="form-field"><label>Care relates to completed appointment<select class="text-input" data-care-appointment required><option value="">Choose a completed consultation</option>${consultations.map(a => `<option value="${escapeHtml(a.appointment_id)}">${escapeHtml(new Date(a.appointment_date).toLocaleString())} · ${escapeHtml(a.appointment_id)}</option>`).join("")}</select></label></div>${consultations.length ? "" : '<p class="notice">No completed consultation yet. Care creation is unavailable until the appointment is completed.</p>'}</section>` : ""}
    ${clinician ? `<p class="appointment-note">${history ? `Last history update: ${escapeHtml(new Date(history.created_at).toLocaleString())}` : "No detailed medical history submitted yet."}</p>` : ""}
    ${clinician ? `<dl class="care-history">${Object.entries(medicalHistoryFields).map(([key, label]) => `<div><dt>${label}</dt><dd>${escapeHtml(history?.payload[key] || "Not provided")}</dd></div>`).join("")}</dl>` : ""}
      <h3>Progress review</h3><p>Each decision applies to the measurements reviewed. Updated measurements need a new review.</p>
      <div class="care-progress">${progress.length ? progress.map(entry => {
          const review = events.filter(e => e.kind === "PROGRESS_REVIEW" && e.payload.log_date === entry.log_date).at(-1);
          const same = review && Object.keys(entry).every(key => String(entry[key]) === String(review.payload.snapshot[key]));
          return `<article class="care-entry"><strong>${escapeHtml(entry.log_date)}</strong><p>${Object.entries(entry).filter(([key, value]) => key !== "log_date" && value != null).map(([key, value]) => `${escapeHtml(key.replaceAll("_", " "))}: ${escapeHtml(value)}`).join(" · ")}</p><span class="appointment-status">${same ? escapeHtml(review.payload.decision.replaceAll("_", " ")) : "PENDING REVIEW"}</span>${same ? `<p>${escapeHtml(review.payload.notes)}</p>` : ""}${clinician ? `<form data-progress-review class="form-grid"><input type="hidden" name="log_date" value="${escapeHtml(entry.log_date)}"><div class="form-field"><label>Decision<select class="text-input" name="decision"><option value="APPROVED">Approve</option><option value="CHANGES_REQUESTED">Request changes</option></select></label></div><div class="form-field"><label>Feedback<textarea class="text-input" name="notes" required maxlength="4000"></textarea></label></div><button class="button quiet-button">Save review</button></form>` : ""}</article>`;
      }).join("") : '<p class="empty-state">No progress submitted yet.</p>'}</div>
      <h3>Dietitian recommendations</h3>${events.filter(e => e.kind === "RECOMMENDATION").map(e => `<article class="care-entry"><small>${escapeHtml(new Date(e.created_at).toLocaleString())}</small><p>${escapeHtml(e.payload.content)}</p></article>`).join("") || '<p class="empty-state">No recommendations shared yet.</p>'}
      ${clinician ? '<form data-recommendation class="form-grid"><div class="form-field full-width"><label>Recommendation<textarea class="text-input" name="content" required maxlength="4000"></textarea></label></div><button class="button button-primary">Share recommendation</button></form>' : ""}
      ${clinician ? `<h3>Nutrition goals</h3>${goals.map(g => `<p>${escapeHtml(g.target_metric)}: target ${escapeHtml(g.target_value)}</p>`).join("") || '<p class="empty-state">No goals set.</p>'}<form data-care-goal class="form-grid"><div class="form-field"><label>Goal metric<input class="text-input" name="target_metric" required maxlength="150"></label></div><div class="form-field"><label>Target value<input class="text-input" name="target_value" type="number" step="any" required></label></div><button class="button quiet-button">Set patient goal</button></form><p><button type="button" class="button quiet-button" data-open-meals>Assign and review a meal plan</button></p>` : ""}`;
    // A request may finish after navigation; do not append into a different screen.
    if (!target.isConnected || target.firstElementChild !== anchor) return;
    target.append(panel);
    const appointmentSelect = panel.querySelector("[data-care-appointment]");
    if (appointmentSelect && consultations.length) appointmentSelect.value = consultations.at(-1).appointment_id;
    if (clinician && !consultations.length) panel.querySelectorAll("[data-progress-review] button, [data-recommendation] button, [data-care-goal] button, [data-open-meals]").forEach(button => button.disabled = true);
    panel.querySelectorAll("[data-complete-consultation]").forEach(button => button.addEventListener("click", async () => {
        button.disabled = true;
        try {
            await request(`/api/v1/appointments/${encodeURIComponent(button.dataset.completeConsultation)}/complete`, {method: "POST"});
            if (!panel.isConnected) return;
            await mountCarePanel(target, clientId, clinician);
            panel.remove();
        } catch(error) {
            panel.querySelector("[data-care-message]").textContent = error.message;
            button.disabled = false;
        }
    }));
    const bind = (selector, endpoint, transform = x => x) => panel.querySelectorAll(selector).forEach(form => form.addEventListener("submit", async event => {
        event.preventDefault();
        const button = form.querySelector("button");
        button.disabled = true;
        try {
            const values = transform(Object.fromEntries(new FormData(form)));
            if (clinician) {
                if (!appointmentSelect.value) throw new Error("Choose a completed consultation first.");
                values.appointment_id = appointmentSelect.value;
            }
            await request(endpoint, {method: "POST", body: JSON.stringify(values)});
            if (!panel.isConnected) return;
            // Build the replacement before removing the current panel so errors stay visible.
            await mountCarePanel(target, clientId, clinician);
            panel.remove();
        } catch (error) {
            panel.querySelector("[data-care-message]").textContent = error.message;
            button.disabled = false;
        }
    }));
    bind("[data-progress-review]", `${base}/progress-reviews`);
    bind("[data-recommendation]", `${base}/recommendations`);
    bind("[data-care-goal]", "/api/v1/goals", values => ({...values, client_id: clientId, target_value: Number(values.target_value)}));
    panel.querySelector("[data-open-meals]")?.addEventListener("click", () => {
        sessionStorage.setItem("meal-plan-client", clientId);
        sessionStorage.setItem("meal-plan-appointment", appointmentSelect.value);
        navTo("meal-plans");
    });
}
