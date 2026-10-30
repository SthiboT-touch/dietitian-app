const authScreen = document.querySelector("#authScreen");
const workspace = document.querySelector("#workspace");
const loginForm = document.querySelector("#loginForm");
const signupForm = document.querySelector("#signupForm");
const adminSetupForm = document.querySelector("#adminSetupForm");
const authMessage = document.querySelector("#authMessage");
const workspaceContent = document.querySelector("#workspaceContent");
const sessionKey = "nutrition-practice-session";
const adminTokenKey = "nutrition-practice-admin-token";
const dietitianTokenKey = "nutrition-practice-dietitian-token";
const clientTokenKey = "nutrition-practice-client-token";
const staffTokenKey = "nutrition-practice-staff-token";
const staffRoleNames = {
    reception: "Reception Staff",
    branch_manager: "Branch Manager",
    compliance_officer: "Compliance Officer",
    executive: "Executive",
    content_manager: "Content Manager",
};

let currentUser = null;

async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    const token =
        sessionStorage.getItem(adminTokenKey) ||
        sessionStorage.getItem(dietitianTokenKey) ||
        sessionStorage.getItem(clientTokenKey) ||
        sessionStorage.getItem(staffTokenKey);
    if (token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    let response;
    try {
        response = await fetch(url, { ...options, headers });
    } catch (error) {
        markConnectionUnavailable();
        // Never expose fetch internals or user-supplied URLs in the UI.
        throw new Error("Cannot reach NutriCare right now. Check your connection and try again.");
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
        const detail = payload && (payload.detail || payload.message);
        const message =
            typeof detail === "string"
                ? detail
                : Array.isArray(detail)
                  ? "Please review the highlighted form details."
                  : `Request failed (${response.status}).`;
        const requestId = response.headers.get("X-Request-ID") || (payload && payload.request_id);
        // Include the reference only when a server error occurs; 4xx validation
        // messages remain concise for patients and staff.
        const reference = response.status >= 500 && requestId ? ` Reference: ${requestId}.` : "";
        throw new Error(message + reference);
    }
    return payload;
}

// The health indicator reflects the real API/database result, not a hardcoded
// "connected" badge. It doesn't display connection strings or patient details.
function setConnectionState(state, label) {
    const container = document.querySelector("#connectionStatus");
    const text = document.querySelector("#connectionStatusText");
    if (!container || !text) return;
    container.dataset.state = state;
    text.textContent = label;
}

function markConnectionUnavailable() {
    setConnectionState("offline", "Connection unavailable");
}

async function refreshConnectionStatus() {
    setConnectionState("checking", "Checking connection…");
    try {
        const response = await fetch("/health", { cache: "no-store" });
        if (!response.ok) throw new Error("Health check failed");
        const status = await response.json();
        if (status.database === "offline" || status.status === "degraded") {
            setConnectionState("degraded", "Database unavailable");
        } else {
            setConnectionState("online", "Workspace connected");
        }
    } catch (_) {
        markConnectionUnavailable();
    }
}

window.addEventListener("online", refreshConnectionStatus);
window.addEventListener("offline", markConnectionUnavailable);
document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !document.querySelector("#workspace")?.hidden) {
        refreshConnectionStatus();
    }
});

// Medical documents are protected API resources, not public file links.
// A regular <a href> navigation does not send the bearer token.
async function openPrivateMedicalDocument(url) {
    const token =
        sessionStorage.getItem(adminTokenKey) ||
        sessionStorage.getItem(dietitianTokenKey) ||
        sessionStorage.getItem(clientTokenKey) ||
        sessionStorage.getItem(staffTokenKey);
    if (!token) throw new Error("Please sign in before opening medical documents.");

    const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
        throw new Error(
            response.status === 403
                ? "You do not have access to this document."
                : `Could not open document (${response.status}).`,
        );
    }
    const file = await response.blob();
    const blobUrl = URL.createObjectURL(file);
    const temporaryLink = document.createElement("a");
    temporaryLink.href = blobUrl;
    temporaryLink.download = "medical-document";
    document.body.appendChild(temporaryLink);
    temporaryLink.click();
    temporaryLink.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}

workspaceContent.addEventListener("click", async (event) => {
    const link = event.target.closest("[data-private-medical-document]");
    if (!link || !workspaceContent.contains(link)) return;
    event.preventDefault();
    const originalLabel = link.textContent;
    link.setAttribute("aria-busy", "true");
    try {
        await openPrivateMedicalDocument(link.dataset.privateMedicalDocument);
    } catch (error) {
        window.alert(error.message);
    } finally {
        link.removeAttribute("aria-busy");
        link.textContent = originalLabel;
    }
});

function showAuthMessage(message, kind = "error") {
    authMessage.textContent = message;
    authMessage.className = kind === "success" ? "form-message success" : "form-message";
    authMessage.hidden = false;
}

function showWorkspace(user, initialView = "overview") {
    currentUser = user;
    refreshConnectionStatus();
    sessionStorage.setItem(sessionKey, JSON.stringify(user));
    authScreen.hidden = true;
    workspace.hidden = false;
    const firstName = user.full_name.split(" ")[0];
    document.querySelector("#profileName").textContent = firstName;
    document.querySelector("#profileInitials").textContent = user.full_name
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part[0].toUpperCase())
        .join("");
    document.querySelector("#headerDate").textContent = new Intl.DateTimeFormat(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
    }).format(new Date());
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.classList.toggle("is-current", item.dataset.view === initialView);
    });
    const isClient = user.type === "client";
    const isAdmin = user.type === "admin";
    const isDietitian = user.type === "dietitian";
    const isStaff = Object.hasOwn(staffRoleNames, user.type);
    document.querySelectorAll("[data-staff-only]").forEach((item) => {
        item.hidden = !isStaff;
    });
    document.querySelectorAll("[data-reception-only]").forEach((item) => {
        item.hidden = !["reception", "branch_manager"].includes(user.type);
    });
    document.querySelectorAll("[data-compliance-only]").forEach((item) => {
        item.hidden = user.type !== "compliance_officer";
    });
    document.querySelectorAll("[data-standard-only]").forEach((item) => {
        item.hidden = isAdmin || isStaff;
    });
    document.querySelectorAll("[data-client-only]").forEach((item) => {
        item.hidden = !isClient;
    });
    const isMaleClient = isClient && String(user.gender || "").toLowerCase() === "male";
    document.querySelectorAll("[data-maternal-only]").forEach((item) => {
        item.hidden = !isClient || isMaleClient;
    });
    document.querySelectorAll("[data-dietitian-only]").forEach((item) => {
        item.hidden = !isDietitian;
    });
    document.querySelectorAll("[data-admin-only]").forEach((item) => {
        item.hidden = !isAdmin;
    });
    document.querySelector('[data-view="overview"]').innerHTML =
        '<span class="nav-glyph">&#9633;</span>Dashboard';
    document.querySelector('[data-view="clients"]').innerHTML =
        '<span class="nav-glyph">&#9787;</span>My Patients';
    document.querySelector("#signOutButton").lastChild.textContent = isAdmin
        ? "Logout"
        : "Sign out";
    document.querySelector("#mobileSignOutButton").textContent = isAdmin ? "Logout" : "Sign out";
    loadView(initialView);
    if (isAdmin) {
        document.querySelector("#reviewCount").textContent = "0";
        refreshAdminApprovalCount();
    } else if (isClient || isStaff) {
        document.querySelector("#reviewCount").textContent = "0";
    } else {
        refreshReviewCount();
    }
}

function signOut() {
    sessionStorage.removeItem(sessionKey);
    sessionStorage.removeItem(adminTokenKey);
    sessionStorage.removeItem(dietitianTokenKey);
    sessionStorage.removeItem(clientTokenKey);
    sessionStorage.removeItem(staffTokenKey);
    currentUser = null;
    workspace.hidden = true;
    authScreen.hidden = false;
    loginForm.reset();
    setAuthMode("login");
    updateAdminSetupTab();
}

function showWorkspaceMessage(message, isError = false) {
    const region = workspaceContent.querySelector("[data-message]");
    if (!region) return;
    region.textContent = message;
    region.className = `workspace-message${isError ? " error" : ""}`;
    region.hidden = false;
}

function pageHeading(eyebrow, title, description, action = "") {
    return `<div class="page-heading"><div><span class="eyebrow eyebrow-plain">${eyebrow}</span><h1>${title}</h1><p>${description}</p></div>${action}</div>`;
}

function selectedRole() {
    return signupForm.elements.role.value;
}

// FR-1.1: show only the current section for patient onboarding.
// The original request payload and dietitian registration flow are preserved.
const signupSteps = Array.from(signupForm.querySelectorAll("[data-signup-step]"));
const patientSignupProgress = document.querySelector("#patientSignupProgress");
const patientSignupActions = document.querySelector("#patientSignupActions");
const patientSignupBack = document.querySelector("#patientSignupBack");
const patientSignupNext = document.querySelector("#patientSignupNext");
const signupSubmit = document.querySelector("#signupSubmit");
let patientSignupStep = 1;
const signupStepNames = ["Your details", "Patient details", "Account security"];

function setPatientSignupStep(nextStep, { focus = false } = {}) {
    patientSignupStep = Math.max(1, Math.min(signupSteps.length, nextStep));
    const isClient = selectedRole() === "client";
    signupSteps.forEach((section, index) => {
        section.hidden = isClient && index + 1 !== patientSignupStep;
    });
    patientSignupProgress.hidden = !isClient;
    patientSignupActions.hidden = !isClient;
    patientSignupBack.hidden = !isClient || patientSignupStep === 1;
    patientSignupNext.hidden = !isClient || patientSignupStep === signupSteps.length;
    signupSubmit.hidden = isClient && patientSignupStep !== signupSteps.length;
    if (isClient) {
        document.querySelector("#patientSignupStepLabel").textContent =
            `Step ${patientSignupStep} of ${signupSteps.length} · ${signupStepNames[patientSignupStep - 1]}`;
        document.querySelector("#patientSignupProgressBar").style.width =
            `${(patientSignupStep / signupSteps.length) * 100}%`;
        patientSignupProgress
            .querySelector("[role=progressbar]")
            .setAttribute("aria-valuenow", String(patientSignupStep));
    }
    if (focus && isClient) {
        signupSteps[patientSignupStep - 1]
            .querySelector("h3, input, select")
            ?.focus({ preventScroll: true });
    }
}

// FR-1.2: Validate locally for immediate feedback; the API validates again.
const registrationFields = {
    email: document.querySelector("#signupEmail"),
    id: document.querySelector("#idNumber"),
    phone: document.querySelector("#signupPhone"),
    dob: document.querySelector("#dateOfBirth"),
};

function saIdHasValidChecksum(value) {
    let total = 0;
    [...value].reverse().forEach((character, index) => {
        let digit = Number(character);
        if (index % 2 === 1) {
            digit *= 2;
            digit = Math.floor(digit / 10) + (digit % 10);
        }
        total += digit;
    });
    return total % 10 === 0;
}

function registrationFieldError(field) {
    const { email, id, phone, dob } = registrationFields;
    const isClient = selectedRole() === "client";
    const value = field.value.trim();
    if (field === email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value) && value.length <= 150
            ? ""
            : "Enter a valid email address (for example, name@example.com).";
    }
    if (!isClient) return "";
    if (field === phone) {
        if (!/^\+?[0-9 ()-]+$/.test(value)) return "Enter a valid South African phone number.";
        const digits = value.replace(/[ ()-]/g, "");
        return /^(?:0[1-8][0-9]{8}|(?:\+27|27)[1-8][0-9]{8})$/.test(digits)
            ? ""
            : "Use a 10-digit South African number, for example 082 123 4567.";
    }
    if (field === id) {
        if (!/^[0-9]{13}$/.test(value)) return "South African ID must contain exactly 13 digits.";
        if (!saIdHasValidChecksum(value)) return "The ID number's check digit is incorrect.";
        if (dob.value && value.slice(0, 6) !== dob.value.slice(2).replaceAll("-", "")) {
            return "Your ID number and date of birth do not match.";
        }
        return "";
    }
    if (field === dob) {
        if (!value) return "Choose your date of birth.";
        const now = new Date();
        const localToday = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
        if (value > localToday) return "Date of birth cannot be in the future.";
        if (Number(value.slice(0, 4)) < 1900) return "Check your date of birth.";
        if (
            /^[0-9]{13}$/.test(id.value) &&
            id.value.slice(0, 6) !== value.slice(2).replaceAll("-", "")
        ) {
            return "Your date of birth must match your ID number.";
        }
        return "";
    }
    return "";
}

function updateRegistrationValidation(field) {
    const isClient = selectedRole() === "client";
    const applicable = field === registrationFields.email || isClient;
    const error = applicable ? registrationFieldError(field) : "";
    field.setCustomValidity(error);
    field.setAttribute("aria-invalid", error ? "true" : "false");
    const help = document.getElementById(`${field.id}Help`);
    if (help) {
        help.classList.toggle("is-invalid", Boolean(error));
        help.classList.toggle("is-valid", !error && Boolean(field.value.trim()) && applicable);
        if (error) help.textContent = error;
        else if (field === registrationFields.email)
            help.textContent = "Email address looks valid.";
        else if (field === registrationFields.phone) help.textContent = "Phone number looks valid.";
        else if (field === registrationFields.id) help.textContent = "ID number looks valid.";
        else help.textContent = "Date of birth looks valid.";
    }
    return !error;
}

Object.values(registrationFields).forEach((field) => {
    for (const eventName of ["input", "change", "blur"]) {
        field.addEventListener(eventName, () => {
            updateRegistrationValidation(field);
            if (field === registrationFields.dob)
                updateRegistrationValidation(registrationFields.id);
            if (field === registrationFields.id && registrationFields.dob.value) {
                updateRegistrationValidation(registrationFields.dob);
            }
        });
    }
});

function validateSignupStep(stepNumber) {
    const section = signupSteps[stepNumber - 1];
    const controls = Array.from(section.querySelectorAll("input, select"))
        // Ignore inactive role-specific fields, but validate earlier wizard steps
        // even while their step containers are temporarily hidden.
        .filter(
            (control) =>
                !control.disabled &&
                !control.closest("#clientFields[hidden], #dietitianFields[hidden]"),
        );
    // Refresh each field before native validation, including previously hidden steps.
    controls.forEach((control) => {
        if (Object.values(registrationFields).includes(control))
            updateRegistrationValidation(control);
    });
    const invalid = controls.find((control) => !control.checkValidity());
    if (invalid) {
        invalid.reportValidity();
        return false;
    }
    return true;
}

patientSignupNext.addEventListener("click", () => {
    if (validateSignupStep(patientSignupStep)) {
        setPatientSignupStep(patientSignupStep + 1, { focus: true });
    }
});
patientSignupBack.addEventListener("click", () => {
    setPatientSignupStep(patientSignupStep - 1, { focus: true });
});

function updateSignupRole() {
    const isClient = selectedRole() === "client";
    document.querySelector("#dietitianFields").hidden = isClient;
    document.querySelector("#clientFields").hidden = !isClient;
    signupForm.elements.license_number.required = !isClient;
    signupForm.elements.id_number.required = isClient;
    signupForm.elements.phone.required = isClient;
    Object.values(registrationFields).forEach((field) => {
        if (field !== registrationFields.email && !isClient) {
            field.setCustomValidity("");
            field.removeAttribute("aria-invalid");
        }
    });
    document.querySelector("#signupDraftActions").hidden = !isClient;
    const consentArea = document.querySelector("#clientPrivacyConsent");
    consentArea.hidden = !isClient;
    signupForm.elements.consent_to_care.required = isClient;
    signupForm.elements.consent_to_care.disabled = !isClient;
    signupForm.elements.privacy_notice_version.disabled = !isClient;
    signupForm.elements.gender.required = isClient;
    signupForm.elements.date_of_birth.required = isClient;
    signupForm.querySelectorAll(".role-option").forEach((option) => {
        option.classList.toggle("is-selected", option.querySelector("input").checked);
    });
    signupForm.querySelectorAll("[data-patient-signup-only]").forEach((element) => {
        element.hidden = !isClient;
    });
    // Hide the patient-only details entirely for dietitians, not merely their inputs.
    if (!isClient) signupSteps[1].hidden = true;
    setPatientSignupStep(1);
    if (!isClient) signupSteps[1].hidden = true;
}

function setAuthMode(mode) {
    const isSignup = mode === "signup";
    const isAdminSetup = mode === "admin-setup";
    loginForm.hidden = isSignup || isAdminSetup;
    signupForm.hidden = !isSignup;
    adminSetupForm.hidden = !isAdminSetup;
    document.querySelector("#loginTab").classList.toggle("is-active", mode === "login");
    document.querySelector("#signupTab").classList.toggle("is-active", isSignup);
    document.querySelector("#adminSetupTab").classList.toggle("is-active", isAdminSetup);
    document.querySelector("#loginTab").setAttribute("aria-selected", String(mode === "login"));
    document.querySelector("#signupTab").setAttribute("aria-selected", String(isSignup));
    document.querySelector("#adminSetupTab").setAttribute("aria-selected", String(isAdminSetup));
    document.querySelector("#authHeading").textContent = isAdminSetup
        ? "Set up your administrator."
        : isSignup
          ? "Create your account."
          : "Welcome back.";
    document.querySelector("#authSubheading").textContent = isAdminSetup
        ? "Create the first administrator for this installation."
        : isSignup
          ? "Join your nutrition practice workspace."
          : "Sign in to continue to your nutrition workspace.";
    authMessage.hidden = true;
    if (isSignup) updateSignupRole();
}

function passwordsMatch(passwordId, confirmationId) {
    const password = document.getElementById(passwordId);
    const confirmation = document.getElementById(confirmationId);
    const matches = password.value === confirmation.value;
    confirmation.setCustomValidity(matches ? "" : "Passwords do not match.");
    return matches;
}

function bindPasswordConfirmation(passwordId, confirmationId) {
    const password = document.getElementById(passwordId);
    const confirmation = document.getElementById(confirmationId);
    const validate = () => passwordsMatch(passwordId, confirmationId);
    password.addEventListener("input", validate);
    confirmation.addEventListener("input", validate);
}

async function fetchPatientContext(clientId) {
    const encodedId = encodeURIComponent(clientId);
    const [clients, profile] = await Promise.all([
        request(`/api/v1/clients?client_id=${encodedId}`),
        request(`/api/v1/clients/${encodedId}/profile`),
    ]);
    const lactation = await request(`/api/v1/clients/${encodedId}/lactation/overview`).catch(
        () => ({}),
    );
    const documents = await request(`/api/v1/clients/${encodedId}/medical-documents`).catch(
        () => [],
    );
    return {
        client: clients[0] || { id: clientId, name: clientId },
        profile,
        lactation,
        documents,
    };
}

function patientContextMarkup(client, profile, lactation = {}, documents = []) {
    const allergies = profile.allergies || [];
    const conditions = profile.conditions || [];
    const metrics = profile.metrics || [];
    const progress = profile.progress || [];
    const clientDetails = [
        ["Email", client.email],
        ["ID number", client.id_number],
        ["Date of birth", client.date_of_birth],
        ["Gender", client.gender],
        ["Height", client.height ? `${client.height} cm` : null],
        ["Activity level", client.activity_level],
        ["Dietary preferences", client.dietary_preferences],
    ].filter(([, value]) => value !== null && value !== undefined && value !== "");
    const progressRows = progress.map((entry) =>
        Object.entries(entry)
            .filter(([key, value]) => key !== "log_date" && value !== null && value !== undefined)
            .map(([key, value]) => `${escapeHtml(key.replaceAll("_", " "))}: ${escapeHtml(value)}`)
            .join(" · "),
    );
    const lactationGroups = [
        ["Status", lactation.status],
        ["Daily feeding", lactation["daily-feeding"]],
        ["Milk supply", lactation["milk-supply"]],
        ["Weaning", lactation.weaning],
        ["Maternal discomfort", lactation["maternal-discomfort"]],
        ["Infant sensitivities", lactation["infant-sensitivities"]],
    ].filter(([, entries]) => entries && entries.length);
    const lactationMarkup = lactationGroups.length
        ? lactationGroups
              .map(
                  ([label, entries]) =>
                      `<div class="form-field"><label>${escapeHtml(label)}</label><div class="text-input">${entries
                          .map((entry) =>
                              escapeHtml(
                                  Object.entries(entry)
                                      .filter(
                                          ([key, value]) =>
                                              !["log_id", "client_id", "logged_at"].includes(key) &&
                                              value !== null &&
                                              value !== "",
                                      )
                                      .map(
                                          ([key, value]) => `${key.replaceAll("_", " ")}: ${value}`,
                                      )
                                      .join(" · "),
                              ),
                          )
                          .join("<br>")}</div></div>`,
              )
              .join("")
        : '<p class="empty-state">No lactation records recorded.</p>';
    const documentsMarkup = documents.length
        ? documents
              .map(
                  (document) =>
                      `<li class="result-item"><a href="/api/v1/clients/${encodeURIComponent(client.id)}/medical-documents/${encodeURIComponent(document.document_id)}" data-private-medical-document="/api/v1/clients/${encodeURIComponent(client.id)}/medical-documents/${encodeURIComponent(document.document_id)}">${escapeHtml(document.file_name)}</a> · ${escapeHtml(document.condition_name || "Medical condition")} · Dr ${escapeHtml(document.doctor_name || "not provided")}<br>${escapeHtml(document.doctor_information || "")}</li>`,
              )
              .join("")
        : '<li class="result-item">No supporting medical documents uploaded.</li>';
    return `
    <section class="content-panel patient-context-preview">
      <h3>${escapeHtml(client.name)}</h3>
      <div class="form-field full-width"><label>Client details</label><div class="text-input">${clientDetails.length ? clientDetails.map(([label, value]) => `<strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}`).join(" · ") : "No demographic details recorded"}</div></div>
      <p class="stat-caption">${escapeHtml(client.id)} · ${escapeHtml(client.status || "Patient")}</p>
      <div class="form-grid">
        <div class="form-field"><label>Allergies</label><div class="text-input">${allergies.length ? allergies.map((item) => `${escapeHtml(item.allergen)} (${escapeHtml(item.severity)})`).join(", ") : "No allergy information recorded"}</div></div>
        <div class="form-field"><label>Medical conditions</label><div class="text-input">${conditions.length ? conditions.map((item) => escapeHtml(item.condition_name)).join(", ") : "No conditions recorded"}</div></div>
        <div class="form-field"><label>Recorded metrics</label><div class="text-input">${metrics.length ? metrics.map((item) => `${escapeHtml(item.metric_type)}: ${escapeHtml(item.value)}`).join(" · ") : "No metrics recorded"}</div></div>
        <div class="form-field"><label>Progress history</label><div class="text-input">${progress.length ? progressRows.join("<br>") : "No progress recorded"}</div></div>
        <div class="form-field full-width"><label>Lactation details</label><div class="form-grid">${lactationMarkup}</div></div>
        <div class="form-field full-width"><label>Medical documents and doctor information</label><ul class="result-list">${documentsMarkup}</ul></div>
      </div>
    </section>`;
}

function bindPatientContextButtons() {
    workspaceContent.querySelectorAll("[data-patient-context]").forEach((button) => {
        button.addEventListener("click", async () => {
            const preview = button
                .closest("[data-patient-card]")
                .querySelector("[data-patient-preview]");
            if (!preview.hidden) {
                preview.hidden = true;
                button.textContent = "View patient info";
                button.setAttribute("aria-expanded", "false");
                return;
            }
            preview.hidden = false;
            preview.innerHTML = '<p class="loading-copy">Loading patient information...</p>';
            button.disabled = true;
            try {
                const { client, profile, lactation, documents } = await fetchPatientContext(
                    button.dataset.patientContext,
                );
                preview.innerHTML = patientContextMarkup(client, profile, lactation, documents);
                button.textContent = "Hide patient info";
                button.setAttribute("aria-expanded", "true");
            } catch (error) {
                preview.innerHTML = `<p class="workspace-message error">${escapeHtml(error.message)}</p>`;
            } finally {
                button.disabled = false;
            }
        });
    });
}

async function renderDietitianDashboard() {
    const doctorName =
        currentUser && currentUser.full_name ? currentUser.full_name.split(" ")[0] : "John";
    const query = `?dietitian_id=${encodeURIComponent(currentUser.id)}`;
    const [clients, appointments, recommendations, plans, approval] = await Promise.all([
        request(`/api/v1/clients${query}`),
        request(`/api/v1/appointments${query}`),
        request("/api/v1/ai/recommendations/pending"),
        request(`/api/v1/meal-plans${query}`),
        request("/api/v1/dietitians/me/approval"),
    ]);
    workspaceContent.innerHTML = `
    <div class="page-heading">
      <div>
        <span class="eyebrow eyebrow-plain">DIETITIAN DASHBOARD</span>
        <h1>Good morning, Dr. ${escapeHtml(doctorName)}</h1>
        <p>Your overview and practice metrics at a glance.</p>
      </div>
      <button class="button button-primary" data-go="meal-plans" type="button">Draft meal plan <span aria-hidden="true">&#8594;</span></button>
    </div>
    ${dietitianApprovalMarkup(approval)}
    <section class="feature-panel dietitian-home-feature">
      <div class="feature-panel-copy">
        <span class="eyebrow">PERSON-CENTRED NUTRITION</span>
        <h2>Care that starts with the whole person.</h2>
        <p>Support everyday wellbeing, clinical nutrition needs, food preferences, and every stage of life with thoughtful, personalised care.</p>
        <button class="button button-lime" data-go="ai-workspace" type="button">Explore nutrition tools <span aria-hidden="true">&#8594;</span></button>
      </div>
    </section>
    <div data-message class="workspace-message" hidden></div>
    <div class="overview-grid">
      <section class="stat-panel">
        <div>
          <span class="stat-label">Patients</span>
          <strong class="stat-number">${clients.length}</strong>
        </div>
      </section>
      <section class="stat-panel">
        <div>
          <span class="stat-label">Appointments</span>
          <strong class="stat-number">${appointments.length}</strong>
        </div>
      </section>
      <section class="stat-panel">
        <div>
          <span class="stat-label">Pending Recommendations</span>
          <strong class="stat-number">${recommendations.length}</strong>
        </div>
      </section>
      <section class="stat-panel">
        <div>
          <span class="stat-label">Meal Plans</span>
          <strong class="stat-number">${plans.length}</strong>
        </div>
      </section>
    </div>
    <div class="section-heading"><h2>My Patients</h2><span>${clients.length} PATIENTS</span></div>
    <div class="dietitian-directory">
      ${
          clients.length
              ? clients
                    .map(
                        (client) => `
        <article class="dietitian-row">
          <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(
              client.name
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join(""),
          )}</div>
          <div class="dietitian-details"><h2>${escapeHtml(client.name)}</h2><p>${escapeHtml(client.id)} · ${escapeHtml(client.status)}</p></div>
          <div class="review-actions">
            <button class="button button-small button-approve" data-open-client="${escapeHtml(client.id)}" type="button">View</button>
          </div>
        </article>
      `,
                    )
                    .join("")
              : '<p class="empty-state">0 patients. Patients who join your practice will appear here.</p>'
      }
    </div>
    <div class="notice">Drafted meal plans are linked to the selected patient and appear in their meal plan view.</div>
  `;
    workspaceContent.querySelectorAll("[data-open-client]").forEach((button) => {
        button.addEventListener("click", () =>
            renderClientManagementProfile(button.dataset.openClient),
        );
    });
    bindApprovalResubmission();
    bindGoButtons();
}

function renderAIWorkspaceTabs(activePanel) {
    if (currentUser.type !== "dietitian") return "";
    return `
    <div class="ai-workspace-tabs" role="tablist" aria-label="Nutrition workspace">
      <button class="ai-workspace-tab${activePanel === "coach" ? " is-active" : ""}" role="tab" aria-selected="${activePanel === "coach"}" data-ai-panel="coach" type="button">Nutrition Coach</button>
      <button class="ai-workspace-tab${activePanel === "plan" ? " is-active" : ""}" role="tab" aria-selected="${activePanel === "plan"}" data-ai-panel="plan" type="button">Plan Studio</button>
    </div>`;
}

async function renderAIWorkspace(activePanel = "coach", clientId = "") {
    const panel = activePanel === "plan" && currentUser.type === "dietitian" ? "plan" : "coach";
    workspaceContent.innerHTML = `
    ${pageHeading("NUTRITION WORKSPACE", "Food, plans, and care guidance.", "Support a wide range of nutrition needs, from everyday wellbeing to clinical and life-stage care.")}
    <section class="nutrition-workspace-banner" aria-label="Personalised nutrition care">
      <div><span class="eyebrow">A MORE PERSONAL APPROACH</span><h2>Good nutrition is about more than a number.</h2><p>Build guidance around health, culture, preferences, access to food, and the person's own goals.</p></div>
    </section>
    ${renderAIWorkspaceTabs(panel)}
    <div data-message class="workspace-message" hidden></div>
    <div id="aiWorkspacePanel"></div>`;
    workspaceContent.querySelectorAll("[data-ai-panel]").forEach((button) => {
        button.addEventListener("click", () => renderAIWorkspace(button.dataset.aiPanel, clientId));
    });
    if (panel === "plan") {
        await renderAIStudio(clientId);
    } else {
        await renderAIChat();
    }
}

async function renderAIChat() {
    const userId = currentUser ? currentUser.id : "guest-user";
    const role = currentUser ? currentUser.type : "client";
    const panel = document.querySelector("#aiWorkspacePanel");
    panel.innerHTML = '<p class="loading-copy">Loading your conversation...</p>';
    const conversation = await request(
        `/api/v1/ai/chat?user_id=${encodeURIComponent(userId)}&role=${encodeURIComponent(role)}`,
    );
    const messages = conversation.messages || [];
    panel.innerHTML = `
    <section class="assistant-topics" aria-label="Nutrition assistant topics">
      <div class="assistant-topics-heading"><span class="eyebrow eyebrow-green">NUTRITION ASSISTANT</span><span>Choose a starting point or ask anything</span></div>
      <div class="assistant-topic-list">
        <button class="assistant-topic is-primary" data-topic="ask" type="button">Ask a question</button>
        <button class="assistant-topic" data-topic="recipe" type="button">Recipe Ideas</button>
        <button class="assistant-topic" data-topic="food" type="button">Food Questions</button>
        <button class="assistant-topic" data-topic="meal-plan" type="button">Meal Plan Help</button>
        <button class="assistant-topic" data-topic="hydration" type="button">Hydration</button>
        <button class="assistant-topic" data-topic="timing" type="button">Meal Timing</button>
        <button class="assistant-topic" data-topic="activity" type="button">Activity &amp; Workouts</button>
        <button class="assistant-topic" data-topic="habits" type="button">Healthy Habits</button>
        <button class="assistant-topic" data-topic="medical" type="button">Health Conditions</button>
        <button class="assistant-topic" data-topic="lifeStage" type="button">Life Stages</button>
        <button class="assistant-topic" data-topic="preferences" type="button">Food Preferences &amp; Budget</button>
        <button class="assistant-topic" data-ai-recommendations type="button">${role === "client" ? "My Recommendations" : "Review Recommendations"}</button>
      </div>
    </section>
    <section class="content-panel chat-panel">
      <div class="chat-thread">
        ${messages
            .map(
                (message) => `
          <div class="chat-bubble ${message.role === "assistant" ? "assistant" : "user"}">
            <strong>${message.role === "assistant" ? "Nutrition Coach" : "You"}</strong>
            <p>${escapeHtml(message.content)}</p>
          </div>
        `,
            )
            .join("")}
      </div>
      <form id="aiChatForm" class="chat-form">
        <textarea id="aiChatInput" name="message" placeholder="Ask about nutrition, health conditions, food access, life stages, preferences, or daily routines..." required></textarea>
        <div class="form-actions"><button class="button button-primary" type="submit">Send <span class="button-arrow" aria-hidden="true">&#8594;</span></button></div>
      </form>
    </section>
  `;
    const form = document.querySelector("#aiChatForm");
    const input = form.querySelector("#aiChatInput");
    const topicPrompts = {
        recipe: "Suggest a simple, balanced recipe using ingredients I have at home.",
        food: "I have a food and nutrition question: ",
        "meal-plan": "Help me adapt my meal plan to fit this situation: ",
        hydration: "Help me choose a realistic hydration goal for my day.",
        timing: "How can I time meals and snacks around my daily schedule?",
        activity: "What food, hydration, and recovery habits can support my activity?",
        habits: "Help me build one realistic healthy habit I can practice this week.",
        medical:
            "What nutrition considerations should I discuss with my dietitian for my health condition?",
        lifeStage: "What nutrition needs can change during my current life stage?",
        preferences:
            "Help me plan balanced meals that fit my cultural foods, budget, and dietary preferences.",
    };
    panel.querySelectorAll("[data-topic]").forEach((button) => {
        button.addEventListener("click", () => {
            input.focus();
            input.value = topicPrompts[button.dataset.topic] || "";
        });
    });
    panel.querySelector("[data-ai-recommendations]").addEventListener("click", () => {
        navTo(role === "client" ? "client-recommendations" : "reviews");
    });
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = input.value.trim();
        if (!message) return;
        const button = form.querySelector("button[type=submit]");
        button.disabled = true;
        try {
            await request("/api/v1/ai/chat", {
                method: "POST",
                body: JSON.stringify({ user_id: userId, role, message }),
            });
            input.value = "";
            await renderAIChat();
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
}

function renderWeightChart(history) {
    const minWeight = Math.floor(Math.min(...history.map((entry) => entry.value)) / 5) * 5;
    const maxWeight = Math.ceil(Math.max(...history.map((entry) => entry.value)) / 5) * 5;
    const range = maxWeight === minWeight ? 5 : maxWeight - minWeight;
    const plot = { left: 56, right: 626, top: 22, bottom: 166 };
    const ticks = [maxWeight, minWeight + range / 2, minWeight];
    const points = history.map((entry, index) => ({
        ...entry,
        x: plot.left + ((plot.right - plot.left) * index) / Math.max(history.length - 1, 1),
        y: plot.top + ((maxWeight - entry.value) / range) * (plot.bottom - plot.top),
    }));
    const pointList = points.map((point) => `${point.x},${point.y}`).join(" ");
    return `
    <svg class="weight-chart" viewBox="0 0 640 220" role="img" aria-label="Weight trend from ${escapeHtml(history[0].value)} kilograms to ${escapeHtml(history[history.length - 1].value)} kilograms">
      ${ticks
          .map((tick, index) => {
              const y = plot.top + ((plot.bottom - plot.top) * index) / (ticks.length - 1);
              return `<line class="weight-chart-grid" x1="${plot.left}" y1="${y}" x2="${plot.right}" y2="${y}"></line><text class="weight-chart-axis" x="2" y="${y + 4}">${tick}kg</text>`;
          })
          .join("")}
      <polyline class="weight-chart-line" points="${pointList}"></polyline>
      ${points.map((point) => `<circle class="weight-chart-point" cx="${point.x}" cy="${point.y}" r="4"><title>${escapeHtml(point.label)}: ${escapeHtml(point.value)} kg</title></circle><text class="weight-chart-label" x="${point.x}" y="198" text-anchor="middle">${escapeHtml(point.label)}</text>`).join("")}
    </svg>`;
}

async function renderClientManagementProfile(clientId) {
    const { client, profile, lactation, documents } = await fetchPatientContext(clientId);
    workspaceContent.innerHTML = `
    ${pageHeading("PATIENT PROFILE", client.name, "Current information recorded for this patient.")}
    ${patientContextMarkup(client, profile, lactation, documents)}
  `;
}

async function renderClientManagementList() {
    const clients = await request(
        `/api/v1/clients?dietitian_id=${encodeURIComponent(currentUser.id)}`,
    );
    workspaceContent.innerHTML = `
    ${pageHeading("MY PATIENTS", "Patient roster.", "Search and review patients in your care.")}
    <div class="section-heading"><h2>My Patients</h2><span>${clients.length} PATIENTS</span></div>
    <label class="field-label" for="clientSearch">Search patients</label>
    <input class="text-input" id="clientSearch" placeholder="Search by patient ID, condition, name, or status" type="search">
    <div class="dietitian-directory">
      ${
          clients.length
              ? clients
                    .map(
                        (client) => `
        <article class="dietitian-row" data-search="${escapeHtml([client.id, client.name, client.status].join(" "))}">
          <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(
              client.name
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join(""),
          )}</div>
          <div class="dietitian-details"><h2>${escapeHtml(client.name)}</h2><p>${escapeHtml(client.id)} · ${escapeHtml(client.status)}</p></div>
          <div class="review-actions">
            <button class="button button-small button-approve" data-open-client="${escapeHtml(client.id)}" type="button">View</button>
            <button class="button button-small" data-draft-plan="${escapeHtml(client.id)}" type="button">Draft plan</button>
          </div>
        </article>
      `,
                    )
                    .join("")
              : '<p class="empty-state">0 patients. Patients who join your practice will appear here.</p>'
      }
    </div>
  `;
    const searchInput = document.querySelector("#clientSearch");
    if (searchInput) {
        searchInput.addEventListener("input", (event) => {
            const query = event.target.value.trim().toLowerCase();
            workspaceContent.querySelectorAll(".dietitian-row").forEach((row) => {
                row.hidden = query && !row.dataset.search.toLowerCase().includes(query);
            });
        });
    }
    workspaceContent.querySelectorAll("[data-open-client]").forEach((button) => {
        button.addEventListener("click", () =>
            renderClientManagementProfile(button.dataset.openClient),
        );
    });
    workspaceContent.querySelectorAll("[data-draft-plan]").forEach((button) => {
        button.addEventListener("click", () => {
            sessionStorage.setItem("meal-plan-client", button.dataset.draftPlan);
            navTo("meal-plans");
        });
    });
}

function navTo(view, aiPanel = "coach") {
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.classList.toggle("is-current", item.dataset.view === view);
    });
    loadView(view, aiPanel);
}

function renderDietitianRows(dietitians) {
    if (dietitians.length === 0) {
        return '<p class="empty-state">No dietitians are listed yet.</p>';
    }
    return `<div class="dietitian-directory">${dietitians
        .map(
            (dietitian) => `
    <article class="dietitian-row">
      <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(
          dietitian.full_name
              .split(/\s+/)
              .slice(0, 2)
              .map((part) => part[0])
              .join("")
              .toUpperCase(),
      )}</div>
      <div class="dietitian-details"><h2>${escapeHtml(dietitian.full_name)}</h2><p>${escapeHtml(dietitian.specialisation || "Nutrition care")}${dietitian.practice_name ? ` · ${escapeHtml(dietitian.practice_name)}` : ""}${dietitian.branch_name ? ` · ${escapeHtml(dietitian.branch_name)}` : ""}</p>${dietitian.branch_address ? `<p class="document-hint">Location: ${escapeHtml(dietitian.branch_address)}</p>` : ""}</div>
      <span class="dietitian-status status-${escapeHtml(dietitian.status.toLowerCase())}">${escapeHtml(dietitian.status.replaceAll("_", " "))}</span>
    </article>`,
        )
        .join("")}</div>`;
}

async function renderClientDashboard(firstName) {
    const dietitians = await request("/api/v1/dietitians");
    workspaceContent.innerHTML = `
    ${pageHeading("PATIENT DASHBOARD", `Welcome, ${escapeHtml(firstName)}.`, "Nutrition support for your health, lifestyle, culture, preferences, and stage of life.")}
    <section class="feature-panel client-home-feature">
      <span class="eyebrow">YOUR CARE, AT A GLANCE</span>
      <h2>Your nutrition needs are personal.</h2>
      <p>Whether you want everyday nutrition guidance, support with a health condition, help through a life stage, sports-fuelling advice, or practical meal ideas, your care can be tailored to you.</p>
      <button class="button button-lime" data-go="client-progress" type="button">View my progress <span aria-hidden="true">&#8594;</span></button>
    </section>
    <div class="section-heading"><h2>My workspace</h2><span>QUICK ACCESS</span></div>
    <div class="quick-grid client-quick-grid">
      <button class="quick-link" data-go="my-profile" type="button"><strong>My Profile</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="health-conditions" type="button"><strong>Health Information</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="client-goals" type="button"><strong>My Goals</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="client-meal-plan" type="button"><strong>My Meal Plan</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="client-appointments" type="button"><strong>Appointments</strong><span aria-hidden="true">&#8599;</span></button>
        <button class="quick-link" data-go="ai-workspace" type="button"><strong>AI Coach</strong><span aria-hidden="true">&#8599;</span></button>
    </div>
    <div class="section-heading"><h2>Find a Dietitian</h2><span>${dietitians.length} AVAILABLE</span></div>
    ${
        dietitians.length
            ? `<div class="dietitian-directory patient-dietitian-directory">${dietitians
                  .map(
                      (dietitian) => `
      <article class="dietitian-row">
        <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(
            dietitian.full_name
                .split(/\s+/)
                .slice(0, 2)
                .map((part) => part[0])
                .join("")
                .toUpperCase(),
        )}</div>
        <div class="dietitian-details"><h2>${escapeHtml(dietitian.full_name)}</h2><p>${escapeHtml(dietitian.specialisation || "Nutrition care")}${dietitian.practice_name ? ` · ${escapeHtml(dietitian.practice_name)}` : ""}${dietitian.branch_name ? ` · ${escapeHtml(dietitian.branch_name)}` : ""}</p>${dietitian.branch_address ? `<p class="document-hint">Location: ${escapeHtml(dietitian.branch_address)}</p>` : ""}</div>
        <button class="button button-small button-approve" data-book-dietitian="${escapeHtml(dietitian.id)}" type="button">Book appointment</button>
      </article>`,
                  )
                  .join("")}</div>`
            : '<p class="empty-state">No approved Dietitians are listed right now.</p>'
    }`;
    bindGoButtons();
    workspaceContent.querySelectorAll("[data-book-dietitian]").forEach((button) => {
        button.addEventListener("click", () => {
            sessionStorage.setItem("patient-booking-dietitian", button.dataset.bookDietitian);
            navTo("client-appointments");
        });
    });
}

async function renderMyProfile() {
    const user = currentUser;
    const isClient = user.type === "client";
    let profileUser = user;
    if (isClient) {
        const clientRecord = (
            await request(`/api/v1/clients?client_id=${encodeURIComponent(user.id)}`).catch(
                () => [],
            )
        )[0];
        if (clientRecord) {
            profileUser = { ...user, ...clientRecord, id: user.id, full_name: user.full_name };
            currentUser = profileUser;
            sessionStorage.setItem(sessionKey, JSON.stringify(profileUser));
            const isMaleClient = String(profileUser.gender || "").toLowerCase() === "male";
            document.querySelectorAll("[data-maternal-only]").forEach((item) => {
                item.hidden = isMaleClient;
            });
        }
    }
    const approval =
        user.type === "dietitian" ? await request("/api/v1/dietitians/me/approval") : null;
    const fields = isClient
        ? [
              ["Patient ID", profileUser.id],
              ["Full name", profileUser.full_name],
              ["Email", profileUser.email],
              ["ID number", profileUser.id_number],
              ["Gender", profileUser.gender],
              ["Date of birth", profileUser.date_of_birth],
              ["Dietitian ID", profileUser.dietitian_id],
              ...(String(profileUser.gender || "").toLowerCase() === "male"
                  ? [["Testosterone", "Still under production"]]
                  : []),
          ]
        : [
              ["Dietitian ID", user.id],
              ["Full name", user.full_name],
              ["Email", user.email],
              ["License number", user.license_number],
              ["Account status", approval.status],
          ];
    workspaceContent.innerHTML = `
    ${pageHeading("MY PROFILE", isClient ? "My Profile." : "Dietitian Profile.", "Account information used to coordinate your nutrition care.")}
    ${approval ? `${dietitianApprovalMarkup(approval)}<div data-message class="workspace-message" hidden></div>` : ""}
    <section class="content-panel">
      <dl class="profile-details">${fields
          .map(
              ([label, value]) => `
        <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "Not provided")}</dd></div>
      `,
          )
          .join("")}</dl>
    </section>`;
    if (approval) bindApprovalResubmission();
}

function dietitianApprovalMarkup(approval) {
    if (approval.status === "APPROVED") return "";
    const statusText =
        approval.status === "REJECTED" ? "Registration rejected" : "Registration pending";
    const reason = approval.rejection_reason
        ? `<p><strong>Admin feedback:</strong> ${escapeHtml(approval.rejection_reason)}</p>`
        : "";
    const action =
        approval.status === "REJECTED"
            ? '<button class="button button-small button-primary" data-approval-resubmit type="button">Resubmit to admin</button>'
            : "";
    return `<section class="notice approval-feedback" aria-live="polite"><strong>${statusText}</strong>${reason}${approval.status === "PENDING" ? "<p>Your registration is awaiting admin review.</p>" : "<p>Address the feedback, upload any corrected verification documents, then resubmit for review.</p>"}${action}</section>`;
}

function bindApprovalResubmission() {
    workspaceContent
        .querySelector("[data-approval-resubmit]")
        ?.addEventListener("click", async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                await request("/api/v1/dietitians/me/approval/resubmit", { method: "POST" });
                if (workspaceContent.querySelector(".profile-details")) {
                    await renderMyProfile();
                } else {
                    await renderDietitianDashboard();
                }
            } catch (error) {
                button.disabled = false;
                showWorkspaceMessage(error.message, true);
            }
        });
}

async function renderClientHealth(clientId, section) {
    const profile = await request(`/api/v1/clients/${encodeURIComponent(clientId)}/profile`);
    const sectionTitles = {
        conditions: "Medical Conditions",
        allergies: "Allergies",
        pregnancy: "Pregnancy",
        lactation: "Lactation",
    };
    const title = sectionTitles[section] || "Health Information";
    let details = "";
    let form = "";
    if (section === "conditions") {
        details = renderTags(
            profile.conditions,
            "condition_name",
            "No medical conditions recorded.",
        );
        form = `<form id="clientHealthForm" class="form-grid"><div class="form-field"><label for="conditionName">Condition</label><input class="text-input" id="conditionName" name="condition_name" required></div><div class="form-field"><label for="conditionCode">ICD code (optional)</label><input class="text-input" id="conditionCode" name="icd_code"></div><div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add condition</button></div></form>`;
    } else if (section === "allergies") {
        details = renderTags(profile.allergies, "allergen", "No allergies recorded.");
        form = `<form id="clientHealthForm" class="form-grid"><div class="form-field"><label for="allergenName">Allergen</label><input class="text-input" id="allergenName" name="allergen" required></div><div class="form-field"><label for="allergySeverity">Severity</label><select id="allergySeverity" name="severity"><option value="mild">Mild</option><option value="moderate">Moderate</option><option value="severe">Severe</option><option value="anaphylactic">Anaphylactic</option></select></div><div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add allergy</button></div></form>`;
    } else if (section === "pregnancy") {
        const pregnancy = profile.pregnancy;
        details = pregnancy
            ? `<dl class="profile-details"><div><dt>Trimester</dt><dd>${escapeHtml(pregnancy.trimester || "Not provided")}</dd></div><div><dt>Due date</dt><dd>${escapeHtml(pregnancy.due_date || "Not provided")}</dd></div></dl>`
            : '<p class="empty-state">No pregnancy information recorded.</p>';
        form = `<form id="clientHealthForm" class="form-grid"><div class="form-field"><label for="trimester">Trimester</label><select id="trimester" name="trimester"><option value="1">First</option><option value="2">Second</option><option value="3">Third</option></select></div><div class="form-field"><label for="dueDate">Due date</label><input class="text-input" id="dueDate" name="due_date" type="date" required></div><div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save pregnancy details</button></div></form>`;
    } else {
        const lactation = profile.lactation;
        details = lactation
            ? `<dl class="profile-details"><div><dt>Status</dt><dd>${lactation.is_active ? "Active" : "Inactive"}</dd></div><div><dt>Notes</dt><dd>${escapeHtml(lactation.notes || "None")}</dd></div></dl>`
            : '<p class="empty-state">No lactation information recorded.</p>';
        form = `<form id="clientHealthForm" class="form-grid"><div class="form-field"><label for="lactationStatus">Status</label><select id="lactationStatus" name="is_active"><option value="true">Active</option><option value="false">Inactive</option></select></div><div class="form-field"><label for="lactationNotes">Notes</label><input class="text-input" id="lactationNotes" name="notes"></div><div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save lactation details</button></div></form>`;
    }
    workspaceContent.innerHTML = `
    ${pageHeading("HEALTH INFORMATION", title, "Keep your care team informed about current health details.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel"><p class="subsection-label">RECORDED DETAILS</p>${details}</section>
    <section class="content-panel health-edit-panel"><p class="subsection-label">UPDATE ${escapeHtml(title.toUpperCase())}</p>${form}</section>`;
    if (section === "conditions") {
        const documents = await request(
            `/api/v1/clients/${encodeURIComponent(clientId)}/medical-documents`,
        ).catch(() => []);
        workspaceContent.insertAdjacentHTML(
            "beforeend",
            `
      <section class="content-panel health-edit-panel">
        <p class="subsection-label">MEDICAL DOCUMENTS AND DOCTOR INFORMATION</p>
        <p class="progress-edit-copy">Upload lab results or another document supporting your medical condition. Your dietitian can review these records.</p>
        <form id="medicalDocumentForm" class="form-grid" enctype="multipart/form-data">
          <div class="form-field"><label for="medicalDocumentCondition">Condition supported</label><input class="text-input" id="medicalDocumentCondition" name="condition_name" required></div>
          <div class="form-field"><label for="medicalDocumentDoctor">Doctor name</label><input class="text-input" id="medicalDocumentDoctor" name="doctor_name" required></div>
          <div class="form-field full-width"><label for="medicalDocumentDoctorInfo">Doctor information</label><textarea class="text-input" id="medicalDocumentDoctorInfo" name="doctor_information" placeholder="Practice, phone number, email, or other relevant details" required></textarea></div>
          <div class="form-field full-width"><label for="medicalDocumentFile">Supporting document (PDF, JPEG, or PNG)</label><input class="text-input file-input" id="medicalDocumentFile" name="file" type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" required></div>
          <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Upload medical document</button></div>
        </form>
        <div class="section-heading"><h2>Previous documents</h2><span>${documents.length} SAVED</span></div>
        <div class="document-list">${documents.length ? documents.map((document) => `<article class="document-row"><div class="document-details"><h3><a href="/api/v1/clients/${encodeURIComponent(clientId)}/medical-documents/${encodeURIComponent(document.document_id)}" data-private-medical-document="/api/v1/clients/${encodeURIComponent(clientId)}/medical-documents/${encodeURIComponent(document.document_id)}">${escapeHtml(document.file_name)}</a></h3><p>${escapeHtml(document.condition_name || "Medical condition")} · ${escapeHtml(document.doctor_name || "Doctor not provided")}</p><p>${escapeHtml(document.doctor_information || "")}</p></div></article>`).join("") : '<p class="empty-state">No supporting medical documents uploaded yet.</p>'}</div>
      </section>`,
        );
        document.querySelector("#medicalDocumentForm").addEventListener("submit", async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = form.querySelector("button[type=submit]");
            button.disabled = true;
            try {
                await request(`/api/v1/clients/${encodeURIComponent(clientId)}/medical-documents`, {
                    method: "POST",
                    body: new FormData(form),
                });
                await renderClientHealth(clientId, section);
                showWorkspaceMessage("Medical document uploaded.");
            } catch (error) {
                showWorkspaceMessage(error.message, true);
                button.disabled = false;
            }
        });
    }
    document.querySelector("#clientHealthForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        let endpoint = section;
        if (section === "conditions") endpoint = "medical-conditions";
        if (section === "pregnancy") values.trimester = Number(values.trimester);
        if (section === "lactation") values.is_active = values.is_active === "true";
        try {
            await request(`/api/v1/clients/${encodeURIComponent(clientId)}/${endpoint}`, {
                method: "POST",
                body: JSON.stringify(values),
            });
            await renderClientHealth(clientId, section);
            showWorkspaceMessage(`${title} updated.`);
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        }
    });
}
// --- LACTATION TRACKING (extra sections shown on the Lactation page) ---

const lactationStatusLabels = {
    breastfeeding: "Breastfeeding",
    formula_feeding: "Not breastfeeding (formula feeding)",
    combo: "Combination feeding",
};
const lactationConcernLabels = {
    low_supply: "Low supply (increase milk)",
    over_supply: "Over-supply",
};
const lactationSymptomLabels = {
    mastitis: "Mastitis",
    clogged_duct: "Clogged duct",
    sore_nipples: "Sore nipples",
    cracked_nipples: "Cracked nipples",
    engorgement: "Engorgement",
    other: "Other",
};
const lactationInfantLabels = {
    food_reaction: "Food reaction",
    allergy: "Allergy",
    excessive_gas: "Excessive gas",
    reflux: "Reflux",
    colic: "Colic",
    other: "Other",
};

function lactationText(value, fallback = "Not provided") {
    return value === null || value === undefined || value === "" ? fallback : value;
}

function lactationOptions(labels) {
    return Object.entries(labels)
        .map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`)
        .join("");
}

function lactationList(title, items) {
    if (!items || !items.length) return "";
    return `<p class="subsection-label">${escapeHtml(title)}</p><ul class="result-list">${items.map((item) => `<li class="result-item"><span>${escapeHtml(item)}</span></li>`).join("")}</ul>`;
}

function lactationGuidanceMarkup(guidance, sections) {
    return sections.map(([key, label]) => lactationList(label, guidance[key])).join("");
}

function lactationHistory(entries, emptyText, describe) {
    if (!entries.length) return `<p class="empty-state">${escapeHtml(emptyText)}</p>`;
    return `<ul class="result-list">${entries
        .slice(0, 5)
        .map((entry) => `<li class="result-item"><span>${describe(entry)}</span></li>`)
        .join("")}</ul>`;
}

function lactationFormValues(form, numberFields = [], checkboxFields = []) {
    const values = {};
    for (const [key, raw] of new FormData(form)) {
        if (checkboxFields.includes(key) || raw === "") continue;
        values[key] = numberFields.includes(key) ? Number(raw) : raw;
    }
    checkboxFields.forEach((key) => {
        values[key] = form.elements[key].checked;
    });
    return values;
}

function bindLactationForm(
    formId,
    clientId,
    endpoint,
    numberFields,
    checkboxFields,
    successMessage,
) {
    const form = document.querySelector(`#${formId}`);
    if (!form) return;
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("button[type=submit]");
        button.disabled = true;
        try {
            const result = await request(
                `/api/v1/clients/${encodeURIComponent(clientId)}/lactation/${endpoint}`,
                {
                    method: "POST",
                    body: JSON.stringify(lactationFormValues(form, numberFields, checkboxFields)),
                },
            );
            // Keep the user on the full lactation tracker so the newly saved entry
            // is immediately reloaded from the API and remains visible.
            await renderLactationTracking(clientId);
            const flags = [...(result.red_flags || []), ...(result.observations || [])];
            if (result.seek_medical_care) {
                showWorkspaceMessage(
                    `${successMessage} Please contact a healthcare provider: ${flags.join(" ")}`,
                    true,
                );
            } else {
                showWorkspaceMessage(
                    flags.length ? `${successMessage} ${flags.join(" ")}` : successMessage,
                );
            }
        } catch (error) {
            button.disabled = false;
            showWorkspaceMessage(error.message, true);
        }
    });
}

async function renderLactationTracking(clientId) {
    const base = `/api/v1/clients/${encodeURIComponent(clientId)}/lactation`;
    let overview;
    try {
        overview = await request(`${base}/overview`);
    } catch (error) {
        showWorkspaceMessage(error.message, true);
        return;
    }
    workspaceContent.innerHTML = `
    ${pageHeading("HEALTH INFORMATION", "Lactation", "Track feeding, milk supply, weaning, maternal comfort, and infant sensitivities in one place.")}
    <div data-message class="workspace-message" hidden></div>`;
    const plan = overview.weaning[0];
    const weaningQuery = new URLSearchParams({
        current_sessions: plan ? plan.feeds_per_day_current : 6,
        target_sessions: plan ? plan.feeds_per_day_target : 0,
        approach: plan ? plan.approach : "gradual",
    });
    const [increaseGuide, oversupplyGuide, weaningGuide] = await Promise.all([
        request("/api/v1/lactation/guidance/increase-milk-production"),
        request("/api/v1/lactation/guidance/manage-oversupply"),
        request(`/api/v1/lactation/guidance/weaning-nutrition?${weaningQuery}`),
    ]);
    const status = overview.status[0];
    const guideSections = [
        ["principles", "WHAT TO DO"],
        ["nutrition", "NUTRITION"],
        ["seek_help_if", "SEEK HELP IF"],
    ];
    const weaningSections = [
        ["tips", "HOW TO WEAN"],
        ["nutrition", "NUTRITION"],
        ["avoid", "AVOID"],
        ["warning_signs", "WARNING SIGNS"],
    ];

    workspaceContent.insertAdjacentHTML(
        "beforeend",
        `
    <div class="section-heading"><h2>Feeding status and infant age</h2><span>CURRENT STATUS</span></div>
    <section class="content-panel">
      ${status ? `<dl class="profile-details"><div><dt>Current status</dt><dd>${escapeHtml(lactationStatusLabels[status.feeding_status] || status.feeding_status)}</dd></div><div><dt>Infant age</dt><dd>${status.infant_age_months != null ? `${escapeHtml(status.infant_age_months)} months` : status.infant_age_weeks != null ? `${escapeHtml(status.infant_age_weeks)} weeks` : "Not provided"}</dd></div><div><dt>Notes</dt><dd>${escapeHtml(lactationText(status.notes, "None"))}</dd></div></dl>` : '<p class="empty-state">No feeding status recorded yet.</p>'}
      <form id="lactationStatusForm" class="form-grid">
        <div class="form-field"><label for="lactFeedingStatus">Feeding status</label><select id="lactFeedingStatus" name="feeding_status">${lactationOptions(lactationStatusLabels)}</select></div>
        <div class="form-field"><label for="lactInfantMonths">Infant age (months)</label><input class="text-input" id="lactInfantMonths" name="infant_age_months" type="number" min="0" max="36"></div>
        <div class="form-field"><label for="lactInfantWeeks">Infant age (weeks, for newborns)</label><input class="text-input" id="lactInfantWeeks" name="infant_age_weeks" type="number" min="0" max="156"></div>
        <div class="form-field"><label for="lactBirthDate">Or infant birth date</label><input class="text-input" id="lactBirthDate" name="infant_birth_date" type="date"></div>
        <div class="form-field full-width"><label for="lactStatusNotes">Notes</label><input class="text-input" id="lactStatusNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save feeding status</button></div>
      </form>
    </section>

    <div class="section-heading"><h2>Daily feeding</h2><span>TODAY'S LOG</span></div>
    <section class="content-panel">
      <form id="lactationFeedingForm" class="form-grid">
        <div class="form-field"><label for="lactFeedDate">Date (blank = today)</label><input class="text-input" id="lactFeedDate" name="feed_date" type="date"></div>
        <div class="form-field"><label for="lactBreastSessions">Breastfeeding sessions</label><input class="text-input" id="lactBreastSessions" name="breastfeeding_sessions" type="number" min="0" max="30" value="0"></div>
        <div class="form-field"><label for="lactPumpSessions">Pumping sessions</label><input class="text-input" id="lactPumpSessions" name="pumping_sessions" type="number" min="0" max="20" value="0"></div>
        <div class="form-field"><label for="lactExpressedMl">Expressed milk (ml)</label><input class="text-input" id="lactExpressedMl" name="expressed_milk_ml" type="number" min="0" step="1" value="0"></div>
        <div class="form-field"><label for="lactFormulaFeeds">Formula feeds</label><input class="text-input" id="lactFormulaFeeds" name="formula_feeds" type="number" min="0" max="30" value="0"></div>
        <div class="form-field"><label for="lactFormulaMl">Formula (ml)</label><input class="text-input" id="lactFormulaMl" name="formula_ml" type="number" min="0" step="1" value="0"></div>
        <div class="form-field"><label for="lactWetDiapers">Wet diapers</label><input class="text-input" id="lactWetDiapers" name="wet_diapers" type="number" min="0" max="30"></div>
        <div class="form-field"><label for="lactDirtyDiapers">Dirty diapers</label><input class="text-input" id="lactDirtyDiapers" name="dirty_diapers" type="number" min="0" max="30"></div>
        <div class="form-field full-width"><label for="lactFeedNotes">Notes</label><input class="text-input" id="lactFeedNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save daily feeding</button></div>
      </form>
      <p class="subsection-label">RECENT DAYS</p>
      ${lactationHistory(overview["daily-feeding"], "No daily feeding logged yet.", (entry) => `${escapeHtml(String(entry.feed_date).slice(0, 10))}: ${escapeHtml(entry.breastfeeding_sessions)} breastfeeds, ${escapeHtml(entry.pumping_sessions)} pumps, ${escapeHtml(entry.expressed_milk_ml)} ml expressed, ${escapeHtml(entry.formula_ml)} ml formula, wet diapers ${escapeHtml(lactationText(entry.wet_diapers, "-"))}`)}
    </section>

    <div class="section-heading"><h2>Milk supply</h2><span>INCREASE OR MANAGE OVER-SUPPLY</span></div>
    <section class="content-panel">
      <form id="lactationSupplyForm" class="form-grid">
        <div class="form-field"><label for="lactConcern">Concern</label><select id="lactConcern" name="concern">${lactationOptions(lactationConcernLabels)}</select></div>
        <div class="form-field"><label for="lactSupplyDate">Date (blank = today)</label><input class="text-input" id="lactSupplyDate" name="log_date" type="date"></div>
        <div class="form-field"><label for="lactPumped24h">Total pumped in 24h (ml)</label><input class="text-input" id="lactPumped24h" name="pumped_ml_24h" type="number" min="0" step="1"></div>
        <div class="form-field"><label for="lactStrategies">Strategies tried</label><input class="text-input" id="lactStrategies" name="strategies_tried" placeholder="e.g. extra pumping, block feeding"></div>
        <div class="form-field full-width"><label for="lactSupplyNotes">Notes</label><input class="text-input" id="lactSupplyNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save supply entry</button></div>
      </form>
      ${lactationHistory(overview["milk-supply"], "No milk supply entries yet.", (entry) => `${escapeHtml(String(entry.log_date).slice(0, 10))}: ${escapeHtml(lactationConcernLabels[entry.concern] || entry.concern)}${entry.pumped_ml_24h != null ? ` - ${escapeHtml(entry.pumped_ml_24h)} ml/24h` : ""}`)}
      <details class="lactation-guide"><summary class="subsection-label">HOW TO INCREASE MILK PRODUCTION</summary>${lactationGuidanceMarkup(increaseGuide, guideSections)}</details>
      <details class="lactation-guide"><summary class="subsection-label">HOW TO MANAGE OVER-SUPPLY</summary>${lactationGuidanceMarkup(oversupplyGuide, guideSections)}</details>
    </section>

    <div class="section-heading"><h2>Weaning nutrition</h2><span>SAFELY LOWERING MILK PRODUCTION</span></div>
    <section class="content-panel">
      <form id="lactationWeaningForm" class="form-grid">
        <div class="form-field"><label for="lactWeanApproach">Approach</label><select id="lactWeanApproach" name="approach"><option value="gradual">Gradual</option><option value="partial">Partial</option><option value="abrupt_medical">Medically advised (faster)</option></select></div>
        <div class="form-field"><label for="lactWeanStart">Start date (blank = today)</label><input class="text-input" id="lactWeanStart" name="start_date" type="date"></div>
        <div class="form-field"><label for="lactWeanCurrent">Feeds/pumps per day now</label><input class="text-input" id="lactWeanCurrent" name="feeds_per_day_current" type="number" min="0" max="20" required></div>
        <div class="form-field"><label for="lactWeanTarget">Target feeds/pumps per day</label><input class="text-input" id="lactWeanTarget" name="feeds_per_day_target" type="number" min="0" max="20" value="0"></div>
        <div class="form-field full-width"><label for="lactWeanNotes">Notes</label><input class="text-input" id="lactWeanNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save weaning plan</button></div>
      </form>
      <p class="notice">Suggested pace: ${escapeHtml(weaningGuide.plan.suggested_pace)}. Dropping ${escapeHtml(weaningGuide.plan.sessions_to_drop)} session(s) takes about ${escapeHtml(weaningGuide.plan.estimated_weeks)} week(s).</p>
      ${lactationGuidanceMarkup(weaningGuide, weaningSections)}
    </section>

    <div class="section-heading"><h2>Maternal discomfort</h2><span>MASTITIS, CLOGGED DUCTS, NIPPLE PAIN</span></div>
    <section class="content-panel">
      <form id="lactationDiscomfortForm" class="form-grid">
        <div class="form-field"><label for="lactSymptom">Symptom</label><select id="lactSymptom" name="symptom_type">${lactationOptions(lactationSymptomLabels)}</select></div>
        <div class="form-field"><label for="lactDiscomfortSeverity">Severity (1-10)</label><input class="text-input" id="lactDiscomfortSeverity" name="severity" type="number" min="1" max="10" required></div>
        <div class="form-field"><label for="lactBreastSide">Breast</label><select id="lactBreastSide" name="breast_side"><option value="">Not specified</option><option value="left">Left</option><option value="right">Right</option><option value="both">Both</option></select></div>
        <div class="form-field"><label for="lactTemperature">Temperature (&deg;C, optional)</label><input class="text-input" id="lactTemperature" name="temperature_c" type="number" min="34" max="43" step="0.1"></div>
        <div class="form-field"><label><input type="checkbox" name="has_fever"> Fever</label></div>
        <div class="form-field"><label><input type="checkbox" name="flu_like_symptoms"> Flu-like symptoms</label></div>
        <div class="form-field"><label><input type="checkbox" name="redness_or_hard_lump"> Redness or hard lump</label></div>
        <div class="form-field"><label for="lactDiscomfortDate">Date (blank = today)</label><input class="text-input" id="lactDiscomfortDate" name="log_date" type="date"></div>
        <div class="form-field full-width"><label for="lactTreatment">Treatment tried</label><input class="text-input" id="lactTreatment" name="treatment_tried"></div>
        <div class="form-field full-width"><label for="lactDiscomfortNotes">Notes</label><input class="text-input" id="lactDiscomfortNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save symptom log</button></div>
      </form>
      ${lactationHistory(overview["maternal-discomfort"], "No maternal discomfort logged yet.", (entry) => `${escapeHtml(String(entry.log_date).slice(0, 10))}: ${escapeHtml(lactationSymptomLabels[entry.symptom_type] || entry.symptom_type)}, severity ${escapeHtml(entry.severity)}/10${entry.breast_side ? `, ${escapeHtml(entry.breast_side)}` : ""}${entry.has_fever ? ", fever" : ""}`)}
    </section>

    <div class="section-heading"><h2>Infant sensitivities</h2><span>FOOD REACTIONS, ALLERGIES, GAS, REFLUX, COLIC</span></div>
    <section class="content-panel">
      <form id="lactationInfantForm" class="form-grid">
        <div class="form-field"><label for="lactInfantCategory">Type</label><select id="lactInfantCategory" name="category">${lactationOptions(lactationInfantLabels)}</select></div>
        <div class="form-field"><label for="lactInfantSeverity">Severity (1-10)</label><input class="text-input" id="lactInfantSeverity" name="severity" type="number" min="1" max="10" required></div>
        <div class="form-field"><label for="lactTrigger">Suspected trigger food</label><input class="text-input" id="lactTrigger" name="suspected_trigger" placeholder="e.g. dairy, soy, eggs"></div>
        <div class="form-field"><label for="lactInfantDuration">Duration (minutes)</label><input class="text-input" id="lactInfantDuration" name="duration_minutes" type="number" min="0"></div>
        <div class="form-field"><label for="lactInfantDate">Date (blank = today)</label><input class="text-input" id="lactInfantDate" name="log_date" type="date"></div>
        <div class="form-field"><label><input type="checkbox" name="blood_in_stool"> Blood in stool</label></div>
        <div class="form-field"><label><input type="checkbox" name="breathing_difficulty_or_swelling"> Breathing difficulty or swelling</label></div>
        <div class="form-field full-width"><label for="lactInfantSymptoms">Symptoms</label><input class="text-input" id="lactInfantSymptoms" name="symptoms" placeholder="e.g. rash, gassy, spit-up, crying spells"></div>
        <div class="form-field full-width"><label for="lactInfantNotes">Notes</label><input class="text-input" id="lactInfantNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save infant log</button></div>
      </form>
      ${overview.recurring_triggers.length ? `<p class="notice">Foods suspected more than once: ${overview.recurring_triggers.map(escapeHtml).join(", ")}. Discuss these with your dietitian before changing your diet.</p>` : ""}
      ${lactationHistory(overview["infant-sensitivities"], "No infant sensitivities logged yet.", (entry) => `${escapeHtml(String(entry.log_date).slice(0, 10))}: ${escapeHtml(lactationInfantLabels[entry.category] || entry.category)}, severity ${escapeHtml(entry.severity)}/10${entry.suspected_trigger ? `, trigger: ${escapeHtml(entry.suspected_trigger)}` : ""}`)}
    </section>`,
    );

    bindLactationForm(
        "lactationStatusForm",
        clientId,
        "status",
        ["infant_age_months", "infant_age_weeks"],
        [],
        "Feeding status saved.",
    );
    bindLactationForm(
        "lactationFeedingForm",
        clientId,
        "daily-feeding",
        [
            "breastfeeding_sessions",
            "pumping_sessions",
            "expressed_milk_ml",
            "formula_feeds",
            "formula_ml",
            "wet_diapers",
            "dirty_diapers",
        ],
        [],
        "Daily feeding saved.",
    );
    bindLactationForm(
        "lactationSupplyForm",
        clientId,
        "milk-supply",
        ["pumped_ml_24h"],
        [],
        "Milk supply entry saved.",
    );
    bindLactationForm(
        "lactationWeaningForm",
        clientId,
        "weaning",
        ["feeds_per_day_current", "feeds_per_day_target"],
        [],
        "Weaning plan saved.",
    );
    bindLactationForm(
        "lactationDiscomfortForm",
        clientId,
        "maternal-discomfort",
        ["severity", "temperature_c"],
        ["has_fever", "flu_like_symptoms", "redness_or_hard_lump"],
        "Symptom log saved.",
    );
    bindLactationForm(
        "lactationInfantForm",
        clientId,
        "infant-sensitivities",
        ["severity", "duration_minutes"],
        ["blood_in_stool", "breathing_difficulty_or_swelling"],
        "Infant log saved.",
    );
}

function latestClientMetric(metrics, aliases, unit = "") {
    const names = aliases.map((name) => name.toLowerCase().replace(/[^a-z0-9]/g, ""));
    const metric = [...metrics].reverse().find((entry) =>
        names.includes(
            String(entry.metric_type)
                .toLowerCase()
                .replace(/[^a-z0-9]/g, ""),
        ),
    );
    return metric ? `${metric.value}${unit}` : "Not recorded";
}

function formatSleepHours(value) {
    const totalMinutes = Math.round(Number(value) * 60);
    return Number.isFinite(totalMinutes)
        ? `${Math.floor(totalMinutes / 60)}h ${totalMinutes % 60}m`
        : "Not recorded";
}

async function renderClientProgress(clientId) {
    const [progressResult, metricsResult] = await Promise.allSettled([
        request(`/api/v1/clients/${encodeURIComponent(clientId)}/progress`),
        request(`/api/v1/clients/${encodeURIComponent(clientId)}/metrics`),
    ]);
    const meals = await request(`/api/v1/clients/${encodeURIComponent(clientId)}/meals`).catch(
        () => [],
    );
    const progress = progressResult.status === "fulfilled" ? progressResult.value : [];
    const metrics = metricsResult.status === "fulfilled" ? metricsResult.value : [];
    const latest = progress.at(-1) || {};
    const weightHistory = progress
        .filter((entry) => Number(entry.weight_kg) > 0)
        .map((entry, index) => ({
            label: entry.log_date
                ? new Date(entry.log_date).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                  })
                : `Log ${index + 1}`,
            value: Number(entry.weight_kg),
        }));
    const metricCards = [
        [
            "Weight",
            latest.weight_kg
                ? `${latest.weight_kg} kg`
                : latestClientMetric(metrics, ["weight", "weight_kg"], " kg"),
        ],
        [
            "Body Fat",
            latest.body_fat_pct != null
                ? `${latest.body_fat_pct}%`
                : latestClientMetric(
                      metrics,
                      ["body fat", "body_fat", "body_fat_pct", "body fat %"],
                      "%",
                  ),
        ],
        [
            "Waist",
            latest.waist_cm != null
                ? `${latest.waist_cm} cm`
                : latestClientMetric(metrics, ["waist", "waist_cm", "waist circumference"], " cm"),
        ],
        [
            "Calories",
            latest.calories != null
                ? `${latest.calories.toLocaleString()} kcal`
                : latestClientMetric(metrics, ["calories", "calories consumed"], " kcal"),
        ],
        [
            "Water",
            latest.water_ml != null
                ? `${Number(latest.water_ml).toLocaleString()} ml`
                : latestClientMetric(metrics, ["water", "water intake", "water_ml"], " ml"),
        ],
        [
            "Steps",
            latest.steps != null
                ? Number(latest.steps).toLocaleString()
                : latestClientMetric(metrics, ["steps", "step count"]),
        ],
        [
            "Sleep",
            latest.sleep_hours != null
                ? formatSleepHours(latest.sleep_hours)
                : latestClientMetric(metrics, ["sleep", "sleep_hours", "sleep hours"], " h"),
        ],
    ];
    workspaceContent.innerHTML = `
    ${pageHeading("MY PROGRESS", "Progress metrics.", "Track the measurements and daily habits recorded for your care.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="client-progress-layout">
      <section class="content-panel weight-trend"><div class="progress-section-heading"><h2>Weight</h2><strong>${escapeHtml(metricCards[0][1])}</strong></div>
        ${weightHistory.length ? renderWeightChart(weightHistory) : '<p class="empty-state">No weight history has been recorded yet.</p>'}
      </section>
      <section class="content-panel"><h2 class="compact-heading">Health Metrics</h2><dl class="progress-metrics">${metricCards.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl></section>
    </div>`;
    workspaceContent.insertAdjacentHTML(
        "beforeend",
        `
    <section class="content-panel progress-edit-panel">
      <h2 class="compact-heading">Update My Progress</h2>
      <p class="progress-edit-copy">Enter any measurements you tracked today. Blank fields keep their previous values.</p>
      <form id="progressUpdateForm" class="form-grid">
        <div class="form-field"><label for="progressWeight">Weight (kg)</label><input class="text-input" id="progressWeight" name="weight_kg" type="number" min="0" step="0.1" value="${escapeHtml(latest.weight_kg ?? "")}"></div>
        <div class="form-field"><label for="progressBodyFat">Body Fat (%)</label><input class="text-input" id="progressBodyFat" name="body_fat_pct" type="number" min="0" max="100" step="0.1" value="${escapeHtml(latest.body_fat_pct ?? "")}"></div>
        <div class="form-field"><label for="progressWaist">Waist (cm)</label><input class="text-input" id="progressWaist" name="waist_cm" type="number" min="0" step="0.1" value="${escapeHtml(latest.waist_cm ?? "")}"></div>
        <div class="form-field"><label for="progressCalories">Calories (kcal)</label><input class="text-input" id="progressCalories" name="calories" type="number" min="0" step="1" value="${escapeHtml(latest.calories ?? "")}"></div>
        <div class="form-field"><label for="progressWater">Water (ml)</label><input class="text-input" id="progressWater" name="water_ml" type="number" min="0" step="1" value="${escapeHtml(latest.water_ml ?? "")}"></div>
        <div class="form-field"><label for="progressSteps">Steps</label><input class="text-input" id="progressSteps" name="steps" type="number" min="0" step="1" value="${escapeHtml(latest.steps ?? "")}"></div>
        <div class="form-field"><label for="progressSleep">Sleep (hours)</label><input class="text-input" id="progressSleep" name="sleep_hours" type="number" min="0" max="24" step="0.1" value="${escapeHtml(latest.sleep_hours ?? "")}"></div>
        <div class="form-field form-actions"><button class="button button-primary" type="submit">Save progress</button></div>
      </form>
    </section>`,
    );
    workspaceContent.insertAdjacentHTML(
        "beforeend",
        `
    <section class="content-panel progress-edit-panel">
      <h2 class="compact-heading">Meals eaten</h2>
      <p class="progress-edit-copy">Record every meal and snack. Previous entries remain available in your history.</p>
      <form id="mealLogForm" class="form-grid">
        <div class="form-field"><label for="mealLogDate">Date</label><input class="text-input" id="mealLogDate" name="log_date" type="date" required></div>
        <div class="form-field"><label for="mealLogTime">Time</label><input class="text-input" id="mealLogTime" name="meal_time" type="time"></div>
        <div class="form-field"><label for="mealLogType">Meal type</label><select class="text-input" id="mealLogType" name="meal_type"><option value="breakfast">Breakfast</option><option value="lunch">Lunch</option><option value="dinner">Dinner</option><option value="snack">Snack</option><option value="other">Other</option></select></div>
        <div class="form-field"><label for="mealLogCalories">Calories (optional)</label><input class="text-input" id="mealLogCalories" name="calories" type="number" min="0"></div>
        <div class="form-field full-width"><label for="mealLogDescription">What did you eat?</label><textarea class="text-input" id="mealLogDescription" name="description" required placeholder="e.g. Oats with banana and yoghurt"></textarea></div>
        <div class="form-field full-width"><label for="mealLogNotes">Notes (optional)</label><input class="text-input" id="mealLogNotes" name="notes"></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save meal</button></div>
      </form>
      <div class="section-heading"><h2>Meal history</h2><span>${meals.length} SAVED</span></div>
      <div class="result-list">${meals.length ? meals.map((meal) => `<article class="result-item"><span><strong>${escapeHtml(String(meal.log_date).slice(0, 10))}${meal.meal_time ? ` · ${escapeHtml(meal.meal_time)}` : ""} · ${escapeHtml(meal.meal_type)}</strong><br>${escapeHtml(meal.description)}${meal.calories != null ? ` · ${escapeHtml(meal.calories)} kcal` : ""}${meal.notes ? `<br>${escapeHtml(meal.notes)}` : ""}</span></article>`).join("") : '<p class="empty-state">No meals recorded yet.</p>'}</div>
    </section>`,
    );
    document.querySelector("#mealLogDate").value = new Date().toISOString().slice(0, 10);
    document.querySelector("#progressUpdateForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const values = {};
        for (const [key, rawValue] of new FormData(event.currentTarget)) {
            if (rawValue !== "") values[key] = Number(rawValue);
        }
        if (Object.keys(values).length === 0) {
            showWorkspaceMessage("Enter at least one progress metric before saving.", true);
            return;
        }
        try {
            await request(`/api/v1/clients/${encodeURIComponent(clientId)}/progress`, {
                method: "POST",
                body: JSON.stringify(values),
            });
            await renderClientProgress(clientId);
            showWorkspaceMessage("Progress updated.");
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        }
    });
    document.querySelector("#mealLogForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        if (values.calories === "") delete values.calories;
        else values.calories = Number(values.calories);
        try {
            await request(`/api/v1/clients/${encodeURIComponent(clientId)}/meals`, {
                method: "POST",
                body: JSON.stringify(values),
            });
            await renderClientProgress(clientId);
            showWorkspaceMessage("Meal saved to your history.");
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        }
    });
}

async function renderClientGoals(clientId) {
    const goals = await request(`/api/v1/goals?client_id=${encodeURIComponent(clientId)}`);
    workspaceContent.innerHTML = `
    ${pageHeading("MY GOALS", "Goals that move with you.", "Choose goals that reflect what matters to you, from daily habits and energy to hydration, digestion, health needs, or weight if relevant.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel"><form id="clientGoalForm" class="form-grid">
      <div class="form-field"><label for="goalMetric">Goal metric</label><select id="goalMetric" name="target_metric"><option>Balanced meals per day</option><option>Fruit and vegetable servings</option><option>Fiber servings</option><option>Water (ml)</option><option>Meals per day</option><option>Home-cooked meals per week</option><option>Protein servings</option><option>Sleep (hours)</option><option>Steps</option><option>Symptom-free days</option><option>Weight (optional)</option><option>Body fat (optional)</option><option>Waist (optional)</option><option>Calories (dietitian-guided)</option></select></div>
      <div class="form-field"><label for="goalTarget">Target value</label><input class="text-input" id="goalTarget" name="target_value" type="number" step="any" required></div>
      <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add goal</button></div>
    </form></section>
    <div class="section-heading"><h2>My goals</h2><span>${goals.length} SAVED</span></div>
    <div class="goal-list">${
        goals.length
            ? goals
                  .map(
                      (goal) => `
      <article class="goal-row"><div><span class="subsection-label">${escapeHtml(goal.target_metric)}</span><h3>Target ${escapeHtml(goal.target_value)}</h3></div><div class="goal-current"><span>Current</span><strong>${goal.current_value == null ? "Not recorded" : escapeHtml(goal.current_value)}</strong></div></article>`,
                  )
                  .join("")
            : '<p class="empty-state">No goals saved yet. Choose a goal that is meaningful to you. Goals can focus on habits, nourishment, hydration, symptoms, activity, or measurements when relevant.</p>'
    }</div>`;
    document.querySelector("#clientGoalForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        values.client_id = clientId;
        values.target_value = Number(values.target_value);
        try {
            await request("/api/v1/goals", { method: "POST", body: JSON.stringify(values) });
            await renderClientGoals(clientId);
            showWorkspaceMessage("Goal saved.");
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        }
    });
}

async function renderClientMealPlan(clientId, selectedTab = "today") {
    // The server identifies the client from their bearer session, never a query parameter.
    const plans = await request("/api/v1/meal-plans/approved");
    const tabs = ["today", "week", "details"];
    const renderSchedule = (plan, tab) => {
        const schedule = Array.isArray(plan.schedule) ? plan.schedule : [];
        const days = tab === "today" ? schedule.slice(0, 1) : schedule;
        if (!days.length) return '<p class="empty-state">No schedule has been shared.</p>';
        return days
            .map((day, index) => {
                const meals = Array.isArray(day.meals) ? day.meals : [];
                const entries = meals.map((meal) =>
                    typeof meal === "string"
                        ? meal
                        : [meal.name, meal.recipe_name, meal.meal_type].filter(Boolean).join(" — "),
                );
                return `<article class="meal-plan-row"><h3>Day ${escapeHtml(day.day || index + 1)}</h3><ul class="meal-summary">${entries.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article>`;
            })
            .join("");
    };
    const activeContent = plans.length
        ? plans
              .map((item) => {
                  const plan = item.plan || {};
                  return `<section class="content-panel"><h2>${escapeHtml(plan.diet_type || "Dietitian-approved meal plan")}</h2>
      <p class="appointment-note">Status: ${escapeHtml(item.status)} · ${escapeHtml(plan.days || "")} days</p>
      ${selectedTab === "details" ? `<p>Plan reviewed by your dietitian.</p>${renderSchedule(plan, "week")}` : renderSchedule(plan, selectedTab)}
    </section>`;
              })
              .join("")
        : '<section class="content-panel"><p class="empty-state">No approved meal plans have been shared by your dietitian yet.</p></section>';
    workspaceContent.innerHTML = `${pageHeading("MY MEAL PLAN", "A plan for everyday life.", "Only dietitian-approved plans appear here.")}
    <div class="meal-view-tabs" role="tablist" aria-label="Meal plan view">${tabs.map((tab) => `<button class="meal-view-tab${tab === selectedTab ? " is-active" : ""}" role="tab" aria-selected="${tab === selectedTab}" data-meal-tab="${tab}" type="button">${tab === "week" ? "This Week" : tab === "details" ? "Meal Details" : "Today"}</button>`).join("")}</div>
    ${activeContent}`;
    workspaceContent
        .querySelectorAll("[data-meal-tab]")
        .forEach((button) =>
            button.addEventListener("click", () =>
                renderClientMealPlan(clientId, button.dataset.mealTab),
            ),
        );
}

async function renderClientAppointments(
    clientId,
    selectedTab = "upcoming",
    selectedDietitianId = "",
) {
    const [appointments, dietitians] = await Promise.all([
        request(`/api/v1/appointments?client_id=${encodeURIComponent(clientId)}`),
        request("/api/v1/dietitians"),
    ]);
    const now = Date.now();
    const isUpcoming = (appointment) =>
        new Date(appointment.appointment_date).getTime() >= now &&
        ["PENDING", "CONFIRMED", "SCHEDULED"].includes(appointment.status || "SCHEDULED");
    const upcoming = appointments.filter(isUpcoming);
    const past = appointments.filter((appointment) => !isUpcoming(appointment));
    const activeTab = ["book", "upcoming", "past"].includes(selectedTab) ? selectedTab : "upcoming";
    const preferredDietitianId = selectedDietitianId || currentUser.dietitian_id || "";
    const rows = activeTab === "upcoming" ? upcoming : past;
    const appointmentRows = rows.length
        ? rows
              .map(
                  (appointment) => `
    <article class="appointment-row">
      <div><span class="appointment-status status-${escapeHtml((appointment.status || "scheduled").toLowerCase())}">${escapeHtml(appointment.status || "SCHEDULED")}</span><h3>${escapeHtml(new Date(appointment.appointment_date).toLocaleString())}</h3></div>
      <span>${escapeHtml(dietitians.find((dietitian) => dietitian.id === appointment.dietitian_id)?.full_name || `Dietitian ${appointment.dietitian_id}`)}</span>
      ${activeTab === "upcoming" ? `<button class="button button-small button-reject" data-cancel-appointment="${escapeHtml(appointment.appointment_id)}" type="button">Cancel appointment</button>` : ""}
    </article>`,
              )
              .join("")
        : `<p class="empty-state">${activeTab === "upcoming" ? "No upcoming appointments." : "No past appointments."}</p>`;
    const minDate = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16);
    workspaceContent.innerHTML = `
    ${pageHeading("MY APPOINTMENTS", "Time with your care team.", "Request a visit and track its status here.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="meal-view-tabs appointment-tabs" role="tablist" aria-label="Appointments">
      <button class="meal-view-tab${activeTab === "book" ? " is-active" : ""}" role="tab" aria-selected="${activeTab === "book"}" data-appointment-tab="book" type="button">Book Appointment</button>
      <button class="meal-view-tab${activeTab === "upcoming" ? " is-active" : ""}" role="tab" aria-selected="${activeTab === "upcoming"}" data-appointment-tab="upcoming" type="button">Upcoming</button>
      <button class="meal-view-tab${activeTab === "past" ? " is-active" : ""}" role="tab" aria-selected="${activeTab === "past"}" data-appointment-tab="past" type="button">Past</button>
    </div>
    ${
        activeTab === "book"
            ? `<section class="content-panel"><h2 class="compact-heading">Request an appointment</h2>${
                  dietitians.length
                      ? `
      <form id="appointmentForm" class="form-grid appointment-booking-form">
        <div class="form-field"><label for="appointmentDietitian">Dietitian</label><select class="text-input" id="appointmentDietitian" name="dietitian_id" required><option value="">Choose a Dietitian</option>${dietitians.map((dietitian) => `<option value="${escapeHtml(dietitian.id)}" ${dietitian.id === preferredDietitianId ? "selected" : ""}>${escapeHtml(dietitian.full_name)}${dietitian.practice_name ? ` · ${escapeHtml(dietitian.practice_name)}` : ""}${dietitian.branch_name ? ` · ${escapeHtml(dietitian.branch_name)}` : ""}${dietitian.branch_address ? ` · ${escapeHtml(dietitian.branch_address)}` : ""}</option>`).join("")}</select></div>
        <div class="form-field"><label for="appointmentDate">Preferred date and time</label><input class="text-input" id="appointmentDate" name="appointment_date" type="datetime-local" min="${minDate}" required></div>
        <div class="form-field form-actions"><button class="button button-primary" type="submit">Send request <span class="button-arrow" aria-hidden="true">&#8594;</span></button></div>
      </form>
      <p class="appointment-note">Your request stays pending until the selected Dietitian approves or rejects it.</p>`
                      : '<p class="empty-state">No approved Dietitians are available for booking right now.</p>'
              }</section>`
            : `
      <div class="section-heading"><h2>${activeTab === "upcoming" ? "Upcoming Appointments" : "Past Appointments"}</h2><span>${rows.length} APPOINTMENTS</span></div>
      <div class="appointment-list">${appointmentRows}</div>`
    }`;
    workspaceContent.querySelectorAll("[data-appointment-tab]").forEach((button) => {
        button.addEventListener("click", () =>
            renderClientAppointments(
                clientId,
                button.dataset.appointmentTab,
                document.querySelector("#appointmentDietitian")?.value || preferredDietitianId,
            ),
        );
    });
    const form = document.querySelector("#appointmentForm");
    if (form)
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const values = Object.fromEntries(new FormData(form));
            values.client_id = clientId;
            try {
                await request("/api/v1/appointments", {
                    method: "POST",
                    body: JSON.stringify(values),
                });
                await renderClientAppointments(clientId, "upcoming");
                showWorkspaceMessage("Appointment request sent. It is pending dietitian review.");
            } catch (error) {
                showWorkspaceMessage(error.message, true);
            }
        });
    workspaceContent.querySelectorAll("[data-cancel-appointment]").forEach((button) => {
        button.addEventListener("click", async () => {
            button.disabled = true;
            try {
                await request(
                    `/api/v1/appointments/${encodeURIComponent(button.dataset.cancelAppointment)}`,
                    {
                        method: "PATCH",
                        body: JSON.stringify({ action: "CANCELLED" }),
                    },
                );
                await renderClientAppointments(clientId, activeTab);
                showWorkspaceMessage("Appointment cancelled.");
            } catch (error) {
                button.disabled = false;
                showWorkspaceMessage(error.message, true);
            }
        });
    });
}

async function renderAppointmentRequests() {
    const appointments = await request(
        `/api/v1/appointments?dietitian_id=${encodeURIComponent(currentUser.id)}`,
    );
    const pending = appointments.filter((appointment) => appointment.status === "PENDING");
    workspaceContent.innerHTML = `
    ${pageHeading("APPOINTMENT REQUESTS", "Requests awaiting your review.", "Approve a request to confirm the appointment, or reject it.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="appointment-list">${
        pending.length
            ? pending
                  .map(
                      (appointment) => `
      <article class="appointment-request-row" data-appointment-id="${escapeHtml(appointment.appointment_id)}" data-patient-card>
        <div class="appointment-request-details"><span class="appointment-status status-pending">PENDING</span><h2>${escapeHtml(appointment.client_id)}</h2><p>${escapeHtml(new Date(appointment.appointment_date).toLocaleString())}</p></div>
        <div class="review-actions"><button class="button button-small" data-patient-context="${escapeHtml(appointment.client_id)}" aria-expanded="false" type="button">View patient info</button><button class="button button-small button-reject" data-appointment-decision="REJECTED" type="button">Reject</button><button class="button button-small button-approve" data-appointment-decision="APPROVED" type="button">Approve</button></div>
        <div data-patient-preview hidden></div>
      </article>`,
                  )
                  .join("")
            : '<p class="empty-state">No appointment requests need review.</p>'
    }</div>`;
    bindPatientContextButtons();
    workspaceContent.querySelectorAll("[data-appointment-decision]").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest("[data-appointment-id]");
            card.querySelectorAll("button").forEach((item) => {
                item.disabled = true;
            });
            const action = button.dataset.appointmentDecision;
            try {
                await request(
                    `/api/v1/appointments/${encodeURIComponent(card.dataset.appointmentId)}`,
                    {
                        method: "PATCH",
                        body: JSON.stringify({ action }),
                    },
                );
                await renderAppointmentRequests();
                showWorkspaceMessage(
                    action === "APPROVED"
                        ? "Appointment confirmed."
                        : "Appointment request rejected.",
                );
            } catch (error) {
                card.querySelectorAll("button").forEach((item) => {
                    item.disabled = false;
                });
                showWorkspaceMessage(error.message, true);
            }
        });
    });
}

async function renderClientRecommendations(clientId) {
    const recommendations = await request(
        `/api/v1/ai/recommendations?client_id=${encodeURIComponent(clientId)}`,
    );
    workspaceContent.innerHTML = `
    ${pageHeading("RECOMMENDATIONS", "Guidance reviewed for you.", "Recommendations appear here after your dietitian reviews them.")}
    <div class="recommendation-list">${
        recommendations.length
            ? recommendations
                  .map(
                      (item) => `
      <article class="review-card"><div class="review-meta"><span>${escapeHtml(item.status)}</span><span>${escapeHtml(item.recommendation_id)}</span></div><p class="stat-label">Goal: ${escapeHtml(item.dietary_goal || "Nutrition guidance")}</p><ul class="result-list">${(item.generated_plan || []).map((suggestion, index) => `<li class="result-item"><span class="result-index">0${index + 1}</span><span>${escapeHtml(suggestion)}</span></li>`).join("")}</ul>${item.review_notes ? `<p class="notice">Dietitian note: ${escapeHtml(item.review_notes)}</p>` : ""}</article>`,
                  )
                  .join("")
            : '<p class="empty-state">No recommendations have been shared yet. Your dietitian will review drafts before they appear here.</p>'
    }</div>`;
}

async function renderDietitians() {
    const dietitians = await request("/api/v1/dietitians");
    workspaceContent.innerHTML = `
    ${pageHeading("YOUR CARE TEAM", "Dietitians.", "Browse the dietitians listed in the practice directory.")}
    <div class="section-heading dietitian-section-heading"><h2>All dietitians</h2><span>${dietitians.length} LISTED</span></div>
    ${renderDietitianRows(dietitians)}`;
}

async function loadView(view, initialAIPanel = "coach") {
    workspaceContent.dataset.view = view;
    workspaceContent.classList.remove("view-enter");
    void workspaceContent.offsetWidth;
    workspaceContent.classList.add("view-enter");
    const firstName = currentUser.full_name.split(" ")[0];
    const clientId = currentUser.type === "client" ? currentUser.id : "";
    if (
        currentUser.type === "client" &&
        String(currentUser.gender || "").toLowerCase() === "male" &&
        ["health-pregnancy", "health-lactation"].includes(view)
    ) {
        await renderClientDashboard(firstName);
        return;
    }
    workspaceContent.innerHTML =
        '<div data-message class="workspace-message" hidden></div><p class="loading-copy">Loading your workspace...</p>';
    try {
        if (view === "overview") {
            if (currentUser.type === "admin") {
                await renderAdminDashboard();
                return;
            }
            if (currentUser.type === "client") {
                await renderClientDashboard(firstName);
                return;
            }
            if (currentUser.type === "dietitian") {
                await renderDietitianDashboard();
                return;
            }
            if (Object.hasOwn(staffRoleNames, currentUser.type)) {
                await renderStaffDashboard();
                return;
            }
            const pending = await request("/api/v1/ai/recommendations/pending");
            workspaceContent.innerHTML = `
        ${pageHeading("YOUR PRACTICE", `Good to see you, ${escapeHtml(firstName)}.`, "A clear view of the care happening today.")}
        ${currentUser.type === "dietitian" ? `<p class="account-id"><span>YOUR DIETITIAN ID</span><strong>${escapeHtml(currentUser.id)}</strong><span>Share this ID with patients when they create an account.</span></p>` : ""}
        <div class="overview-grid">
          <section class="feature-panel">
            <span class="eyebrow">PLAN STUDIO</span>
            <h2>Build a starting point for better habits.</h2>
            <p>Draft a nutrition plan around a patient’s goals and health context. Every draft stays with you for review.</p>
            <button class="button button-lime" data-go="ai-workspace" data-ai-panel="plan" type="button">Start a plan <span aria-hidden="true">&#8594;</span></button>
          </section>
          <section class="stat-panel">
            <div><span class="stat-label">Waiting for your review</span><strong class="stat-number">${pending.length}</strong><span class="stat-caption">Draft recommendations</span></div>
            <button class="stat-link" data-go="reviews" type="button">Open review queue <span aria-hidden="true">&#8594;</span></button>
          </section>
        </div>
        <div class="section-heading"><h2>Pick up where care happens</h2><span>YOUR WORKSPACE</span></div>
        <div class="quick-grid">
          <button class="quick-link" data-go="clients" type="button"><strong>Patient health record</strong><span aria-hidden="true">&#8599;</span></button>
          <button class="quick-link" data-go="foods" type="button"><strong>Browse food library</strong><span aria-hidden="true">&#8599;</span></button>
          <button class="quick-link" data-go="reviews" type="button"><strong>Review suggestions</strong><span aria-hidden="true">&#8599;</span></button>
        </div>
        <p class="notice">Suggestions are general starting points and require review by a licensed dietitian. They are not a substitute for clinical judgment.</p>`;
            bindGoButtons();
        } else if (view === "ai-workspace" || view === "ai" || view === "ai-chat") {
            const panel = view === "ai" ? "plan" : view === "ai-chat" ? "coach" : initialAIPanel;
            await renderAIWorkspace(panel, clientId);
        } else if (view === "client-checkin") {
            await renderClientCheckin(clientId);
        } else if (view === "reception-onboarding") {
            await renderReceptionOnboarding();
        } else if (view === "reception-checkin") {
            await renderReceptionCheckin();
        } else if (view === "my-profile") {
            await renderMyProfile();
        } else if (view === "health-lactation") {
            await renderLactationTracking(clientId);
        } else if (view.startsWith("health-")) {
            await renderClientHealth(clientId, view.slice("health-".length));
        } else if (view === "client-progress") {
            await renderClientProgress(clientId);
        } else if (view === "client-goals") {
            await renderClientGoals(clientId);
        } else if (view === "client-meal-plan") {
            await renderClientMealPlan(clientId);
        } else if (view === "client-appointments") {
            const selectedDietitianId =
                sessionStorage.getItem("patient-booking-dietitian") ||
                currentUser.dietitian_id ||
                "";
            sessionStorage.removeItem("patient-booking-dietitian");
            await renderClientAppointments(
                clientId,
                selectedDietitianId ? "book" : "upcoming",
                selectedDietitianId,
            );
        } else if (view === "appointment-requests") {
            await renderAppointmentRequests();
        } else if (view === "support") {
            await window.mountSupport(workspaceContent, {
                request,
                isAdmin: currentUser.type === "admin",
                escapeHtml,
            });
        } else if (view === "admin-staff") {
            await renderAdminStaff();
        } else if (view === "admin-access-events" || view === "staff-access-events") {
            await renderAccessEvents();
        } else if (view === "staff-profile") {
            await renderStaffProfile();
        } else if (view === "admin-dietitians") {
            await renderAdminDietitians();
        } else if (view === "admin-businesses") {
            await renderAdminBusinesses();
        } else if (view === "admin-branches") {
            await renderAdminBranches();
        } else if (view === "admin-clients") {
            await renderAdminClients();
        } else if (view === "admin-reports") {
            await renderAdminReports();
        } else if (view === "admin-audit-logs") {
            await renderAdminAuditLogs();
        } else if (view === "admin-settings") {
            await renderAdminSettings();
        } else if (view === "client-recommendations") {
            await renderClientRecommendations(clientId);
        } else if (view === "verification-documents") {
            await renderDietitianDocuments();
        } else if (view === "dietitian-branches") {
            await renderDietitianBranches();
        } else if (view === "reviews") {
            await renderReviews();
        } else if (view === "clients") {
            if (currentUser.type === "dietitian") {
                await renderClientManagementList();
            } else {
                renderClientRecord(clientId);
                if (clientId) await loadClientProfile(clientId);
            }
        } else if (view === "dietitians") {
            await renderDietitians();
        } else if (view === "foods") {
            await renderFoods();
        } else if (view === "recipes") {
            await renderRecipes();
        } else if (view === "meal-plans") {
            await renderMealPlans();
        } else if (view === "admin-approvals") {
            await renderAdminApprovals();
        }
    } catch (error) {
        workspaceContent.innerHTML = `${pageHeading("WORKSPACE", "Could not load this view.", "Check that the API is running, then try again.")}<div class="workspace-message error">${escapeHtml(error.message)}</div>`;
    }
}

async function renderAIStudio(clientId = "") {
    let clients = [];
    try {
        clients = await request(
            `/api/v1/clients?dietitian_id=${encodeURIComponent(currentUser.id)}`,
        );
    } catch {
        clients = [];
    }
    const goalSuggestions = [
        "Build balanced, satisfying meals",
        "Improve everyday nutrition and wellbeing",
        "Support diabetes care with dietitian guidance",
        "Support heart health and lower sodium intake",
        "Manage nutrition alongside kidney disease with clinical guidance",
        "Support digestive comfort and regularity",
        "Plan meals around food allergies or intolerances",
        "Support pregnancy nutrition",
        "Support postpartum and breastfeeding nutrition",
        "Support infant or child growth and feeding",
        "Meet nutrition needs as an older adult",
        "Fuel sport, exercise, and recovery",
        "Improve energy and meal regularity",
        "Improve hydration",
        "Plan affordable meals using familiar cultural foods",
        "Plan vegetarian or vegan meals with balanced nutrition",
        "Navigate texture-modified or swallowing-related food needs with clinical guidance",
        "Support recovery from illness or surgery with the care team",
        "Build a more peaceful, flexible relationship with food",
        "Weight management, if appropriate for the patient",
    ];
    document.querySelector("#aiWorkspacePanel").innerHTML = `
    <section class="content-panel">
      <form id="aiForm" class="form-grid">
        <div class="form-field"><label for="aiClientId">Search patient ID or name</label><input class="text-input" id="aiClientId" name="client_id" list="aiClientOptions" placeholder="Start typing a patient ID" value="${escapeHtml(clientId)}" required><datalist id="aiClientOptions">${clients.map((client) => `<option value="${escapeHtml(client.id)}" label="${escapeHtml(client.name)}"></option>`).join("")}</datalist></div>
        <div class="form-field"><label for="dietaryGoal">Patient priority / nutrition need</label><input class="text-input" id="dietaryGoal" name="dietary_goal" list="aiGoalOptions" placeholder="Choose or describe the patient’s nutrition needs" required><datalist id="aiGoalOptions">${goalSuggestions.map((goal) => `<option value="${escapeHtml(goal)}"></option>`).join("")}</datalist></div>
        <div class="form-field full-width"><span class="notice">Consider the patient’s stated priority, life stage, cultural foods, preferences, access and budget, allergies, and recorded medical conditions. Drafts are suggestions only and must be clinically reviewed before sharing.</span></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Generate draft <span aria-hidden="true">&#8594;</span></button></div>
      </form>
      <div id="planResult" aria-live="polite"></div>
    </section>`;
    document.querySelector("#aiForm").addEventListener("submit", generatePlan);
}

async function renderDietitianDocuments() {
    const [documents, assignment] = await Promise.all([
        request("/api/v1/dietitians/me/documents"),
        request("/api/v1/dietitians/me/branches"),
    ]);
    const currentBranch = assignment.branches.find(
        (branch) => branch.branch_id === assignment.current_branch_id,
    );
    const branchReady = Boolean(currentBranch?.name?.trim() && currentBranch?.address?.trim());
    workspaceContent.innerHTML = `
    ${pageHeading("REGISTRATION", "Verification documents.", "Submit license and identity documents for admin review.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel">
      <div class="section-heading form-section-heading"><h2>Practice branch and location</h2><span>REQUIRED</span></div>
      ${
          currentBranch && branchReady
              ? `<p><strong>${escapeHtml(currentBranch.name)}</strong><br>${escapeHtml(currentBranch.address)}</p><p class="document-hint">This location will be visible to clients after your registration is approved. Add another branch below to update your base location.</p>`
              : '<p class="document-hint">Add your branch name and full location before submitting verification documents. Clients will see it after an administrator approves your registration.</p>'
      }
      <form id="registrationBranchForm" class="form-grid">
        <div class="form-field"><label for="registrationBranchName">Branch name</label><input class="text-input" id="registrationBranchName" name="name" maxlength="150" required></div>
        <div class="form-field full-width"><label for="registrationBranchAddress">Branch location / address</label><input class="text-input" id="registrationBranchAddress" name="address" maxlength="255" autocomplete="street-address" required></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">${branchReady ? "Add and set as current base" : "Save branch and location"}</button></div>
      </form>
    </section>
    <section class="content-panel document-upload-panel">
      <form id="verificationUploadForm" class="form-grid">
        <div class="form-field full-width"><label for="verificationFile">Choose a PDF, JPEG, or PNG document</label><input class="text-input file-input" id="verificationFile" name="file" type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" ${branchReady ? "required" : "disabled required"}></div>
        <div class="form-field full-width"><p class="document-hint">Maximum file size: 10 MB. Documents are stored securely and visible only to you and administrators reviewing your registration.</p></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit" ${branchReady ? "" : "disabled"}>Submit for review <span aria-hidden="true">&#8594;</span></button></div>
      </form>
    </section>
    <div class="section-heading"><h2>Submitted documents</h2><span>${documents.length} FILES</span></div>
    <div class="document-list">${
        documents.length
            ? documents
                  .map(
                      (document) => `
      <article class="document-row"><span class="document-icon" aria-hidden="true">&#9636;</span><div class="document-details"><h3>${escapeHtml(document.file_name)}</h3><p>${escapeHtml(document.content_type)} · ${new Date(document.uploaded_at).toLocaleDateString()}</p><p>${escapeHtml(document.branch_name)} · ${escapeHtml(document.branch_address)}</p></div><span class="plan-status">SUBMITTED</span></article>`,
                  )
                  .join("")
            : '<p class="empty-state">No documents submitted. Add a license or identity document to continue approval.</p>'
    }</div>`;
    document
        .querySelector("#registrationBranchForm")
        .addEventListener("submit", saveRegistrationBranch);
    document
        .querySelector("#verificationUploadForm")
        .addEventListener("submit", submitVerificationDocument);
}

async function saveRegistrationBranch(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const values = Object.fromEntries(new FormData(form));
    try {
        await request("/api/v1/dietitians/me/branches", {
            method: "POST",
            body: JSON.stringify(values),
        });
        await renderDietitianDocuments();
        showWorkspaceMessage("Branch and location saved.");
    } catch (error) {
        button.disabled = false;
        showWorkspaceMessage(error.message, true);
    }
}

async function submitVerificationDocument(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const file = form.elements.file.files[0];
    if (!file) return;
    button.disabled = true;
    try {
        const body = new FormData();
        body.append("file", file);
        await request("/api/v1/dietitians/me/documents", { method: "POST", body });
        await renderDietitianDocuments();
        showWorkspaceMessage("Document submitted for review.");
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    } finally {
        button.disabled = false;
    }
}

async function renderDietitianBranches() {
    const assignment = await request("/api/v1/dietitians/me/branches");
    workspaceContent.innerHTML = `
    ${pageHeading("PRACTICE LOCATIONS", "My branches.", "Add practice locations. Each new branch becomes your current base and is visible to administrators and clients after approval.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel">
      <div class="section-heading form-section-heading"><h2>Add a branch</h2><span>NEW LOCATION</span></div>
      <form id="dietitianBranchForm" class="form-grid">
        <div class="form-field"><label for="dietitianBranchName">Branch name</label><input class="text-input" id="dietitianBranchName" name="name" maxlength="150" required></div>
        <div class="form-field full-width"><label for="dietitianBranchAddress">Location / address</label><input class="text-input" id="dietitianBranchAddress" name="address" maxlength="255" autocomplete="street-address" required></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add and set as my base</button></div>
      </form>
    </section>
    <div class="section-heading"><h2>Practice locations</h2><span>${assignment.branches.length} BRANCHES</span></div>
    ${renderAdminTable(
        ["Branch", "Address", "Base"],
        assignment.branches.map((branch) => [
            branch.name,
            branch.address,
            branch.branch_id === assignment.current_branch_id ? "Current base" : "",
        ]),
        "No branches are registered for this practice.",
    )}`;
    document.querySelector("#dietitianBranchForm").addEventListener("submit", savePracticeBranch);
}

async function savePracticeBranch(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const values = Object.fromEntries(new FormData(form));
    try {
        await request("/api/v1/dietitians/me/branches", {
            method: "POST",
            body: JSON.stringify(values),
        });
        await renderDietitianBranches();
        showWorkspaceMessage("Branch added and set as your current base.");
    } catch (error) {
        button.disabled = false;
        showWorkspaceMessage(error.message, true);
    }
}

async function generatePlan(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const values = Object.fromEntries(new FormData(form));
    button.disabled = true;
    button.firstChild.textContent = "Generating... ";
    try {
        const result = await request("/api/v1/ai/generate-plan", {
            method: "POST",
            body: JSON.stringify(values),
        });
        const recommendation = result.recommendation;
        document.querySelector("#planResult").innerHTML = `
      <p class="subsection-label">DRAFT FOR REVIEW</p>
      <ul class="result-list">${recommendation.generated_plan.map((item, index) => `<li class="result-item"><span class="result-index">0${index + 1}</span><span>${escapeHtml(item)}</span></li>`).join("")}</ul>
      ${retrievedSourcesMarkup(recommendation.retrieved_references)}
      <p class="notice">Saved as pending review. This suggestion has not been approved for a client.</p>`;
        refreshReviewCount();
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    } finally {
        button.disabled = false;
        button.firstChild.textContent = "Generate draft ";
    }
}

// Show the evidence used for a draft. Excerpts are untrusted and must be checked by a dietitian.
function retrievedSourcesMarkup(references) {
    const sources = Array.isArray(references) ? references : [];
    if (!sources.length)
        return `<p class="notice">No local nutrition references were retrieved for this draft. Verify the guidance independently before approving.</p>`;
    return `<details class="review-sources"><summary>Review retrieved references (${sources.length})</summary>
    <p class="stat-caption">These excerpts are supporting context, not verified clinical conclusions. Check the original documents.</p>
    <ol>${sources.map((ref) => `<li><strong>${escapeHtml(ref.source || "Unknown source")}</strong>${ref.paragraph != null ? ` · Paragraph ${escapeHtml(ref.paragraph)}` : ""}<blockquote>${escapeHtml(ref.excerpt || "")}</blockquote></li>`).join("")}</ol>
  </details>`;
}

async function renderReviews() {
    const recommendations = await request("/api/v1/ai/recommendations/pending");
    workspaceContent.innerHTML = `
    ${pageHeading("HUMAN REVIEW", "Review queue.", "Every AI suggestion waits here until a dietitian decides what happens next.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="review-list">${
        recommendations.length
            ? recommendations
                  .map(
                      (item) => `
      <article class="review-card" data-recommendation="${escapeHtml(item.recommendation_id)}" data-patient-card>
        <div class="review-meta"><span class="review-client">Patient ${escapeHtml(item.client_id)}</span><span>${escapeHtml(item.recommendation_id)} &middot; PENDING REVIEW</span></div>
        <p class="stat-label">Goal: ${escapeHtml(item.dietary_goal)}</p>
        <ul class="result-list">${item.generated_plan.map((plan, index) => `<li class="result-item"><span class="result-index">0${index + 1}</span><span>${escapeHtml(plan)}</span></li>`).join("")}</ul>
        ${retrievedSourcesMarkup(item.retrieved_references)}
        <label class="form-field review-notes"><span class="field-label">Review note <span class="stat-caption">(optional)</span></span><input class="text-input" name="notes" placeholder="Add context for this decision"></label>
        <div class="review-actions"><button class="button button-small" data-patient-context="${escapeHtml(item.client_id)}" aria-expanded="false" type="button">View patient info</button><button class="button button-small button-reject" data-review="REJECTED" type="button">Reject</button><button class="button button-small button-approve" data-review="APPROVED" type="button">Approve</button></div>
        <div data-patient-preview hidden></div>
      </article>`,
                  )
                  .join("")
            : '<div class="empty-state">Nothing waiting for review. New drafts will appear here.</div>'
    }</div>`;
    bindPatientContextButtons();
    workspaceContent.querySelectorAll("[data-review]").forEach((button) => {
        button.addEventListener("click", reviewRecommendation);
    });
    document.querySelector("#reviewCount").textContent = String(recommendations.length);
}

async function reviewRecommendation(event) {
    const button = event.currentTarget;
    const card = button.closest("[data-recommendation]");
    const recommendationId = card.dataset.recommendation;
    const notes = card.querySelector("[name=notes]").value.trim();
    button.disabled = true;
    try {
        await request(`/api/v1/ai/recommendations/${encodeURIComponent(recommendationId)}`, {
            method: "PATCH",
            body: JSON.stringify({ action: button.dataset.review, notes }),
        });
        await renderReviews();
        refreshReviewCount();
    } catch (error) {
        button.disabled = false;
        showWorkspaceMessage(error.message, true);
    }
}

function renderClientRecord(clientId = "") {
    workspaceContent.innerHTML = `
    ${pageHeading("PATIENT HEALTH", "Patient record.", "Review context that helps keep recommendations personal.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel">
      <form id="clientLookup" class="form-grid">
        <div class="form-field"><label for="recordClientId">Patient ID</label><input class="text-input" id="recordClientId" value="${escapeHtml(clientId)}" placeholder="Enter a patient ID" required></div>
        <div class="form-field form-actions"><button class="button button-primary" type="submit">Load record</button></div>
      </form>
      <div id="clientProfile"></div>
    </section>`;
    document.querySelector("#clientLookup").addEventListener("submit", async (event) => {
        event.preventDefault();
        await loadClientProfile(document.querySelector("#recordClientId").value.trim());
    });
}

async function loadClientProfile(clientId) {
    const target = document.querySelector("#clientProfile");
    target.innerHTML = '<p class="loading-copy">Loading patient context...</p>';
    try {
        const profile = await request(`/api/v1/clients/${encodeURIComponent(clientId)}/profile`);
        target.innerHTML = `
      <p class="subsection-label">HEALTH CONTEXT</p>
      <div class="form-grid">
        <form class="form-field" id="allergyForm"><label for="allergen">Add allergy</label><input class="text-input" id="allergen" name="allergen" placeholder="Allergen" required><select name="severity" aria-label="Severity"><option value="mild">Mild</option><option value="moderate">Moderate</option><option value="severe">Severe</option></select><button class="button quiet-button" type="submit">Save allergy</button></form>
        <form class="form-field" id="conditionForm"><label for="condition">Add medical condition</label><input class="text-input" id="condition" name="condition_name" placeholder="Condition name" required><input class="text-input" name="icd_code" placeholder="ICD code (optional)"><button class="button quiet-button" type="submit">Save condition</button></form>
      </div>
      <p class="subsection-label">RECORDED DETAILS</p>
      <div class="form-grid"><div><strong class="stat-label">Allergies</strong>${renderTags(profile.allergies, "allergen", "No allergies recorded")}</div><div><strong class="stat-label">Medical conditions</strong>${renderTags(profile.conditions, "condition_name", "No conditions recorded")}</div></div>`;
        document
            .querySelector("#allergyForm")
            .addEventListener("submit", (event) => submitClientEntry(event, clientId, "allergies"));
        document
            .querySelector("#conditionForm")
            .addEventListener("submit", (event) =>
                submitClientEntry(event, clientId, "medical-conditions"),
            );
    } catch (error) {
        target.innerHTML = `<p class="workspace-message error">${escapeHtml(error.message)}</p>`;
    }
}

function renderTags(items = [], key, emptyText) {
    if (!items.length) return `<p class="empty-state">${emptyText}</p>`;
    return `<ul class="result-list">${items.map((item) => `<li class="result-item"><span>${escapeHtml(item[key])}${item.severity ? ` &middot; ${escapeHtml(item.severity)}` : ""}</span></li>`).join("")}</ul>`;
}

async function submitClientEntry(event, clientId, kind) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (!values.icd_code) delete values.icd_code;
    try {
        await request(`/api/v1/clients/${encodeURIComponent(clientId)}/${kind}`, {
            method: "POST",
            body: JSON.stringify(values),
        });
        await loadClientProfile(clientId);
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    }
}

async function renderFoods() {
    const foods = await request("/api/v1/foods");
    workspaceContent.innerHTML = `
    ${pageHeading("REFERENCE", "Food library.", "A quick reference for ingredients in the practice catalog.")}
    ${
        currentUser.type === "admin"
            ? `
      <div data-message class="workspace-message" hidden></div>
      <section class="content-panel">
        <div class="section-heading form-section-heading"><h2>Add a food</h2><span>NEW FOOD</span></div>
        <form id="foodForm" class="form-grid">
          <div class="form-field"><label for="foodName">Food name</label><input class="text-input" id="foodName" name="name" maxlength="150" required></div>
          <div class="form-field"><label for="foodCalories">Calories (kcal)</label><input class="text-input" id="foodCalories" name="calories" type="number" min="0" step="1" required></div>
          <div class="form-field"><label for="foodProtein">Protein (g)</label><input class="text-input" id="foodProtein" name="protein_g" type="number" min="0" step="0.1" value="0" required></div>
          <div class="form-field"><label for="foodCarbs">Carbohydrates (g)</label><input class="text-input" id="foodCarbs" name="carbs_g" type="number" min="0" step="0.1" value="0" required></div>
          <div class="form-field"><label for="foodFat">Fat (g)</label><input class="text-input" id="foodFat" name="fat_g" type="number" min="0" step="0.1" value="0" required></div>
          <div class="form-field"><label for="foodGlycemicIndex">Glycemic index (optional)</label><input class="text-input" id="foodGlycemicIndex" name="glycemic_index" type="number" min="0" max="100" step="1"></div>
          <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add to library</button></div>
        </form>
      </section>`
            : ""
    }
    <div class="food-list">
      <div class="food-row food-header"><span>FOOD</span><span>CALORIES</span><span>PROTEIN</span><span>CARBS</span><span>FAT</span></div>
      ${foods.map((food) => `<div class="food-row"><span class="food-name">${escapeHtml(food.name)}</span><span>${food.calories} kcal</span><span>${food.protein_g} g</span><span>${food.carbs_g} g</span><span>${food.fat_g} g</span></div>`).join("")}
    </div>`;
    const form = document.querySelector("#foodForm");
    if (form) form.addEventListener("submit", createFood);
}

async function createFood(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const values = Object.fromEntries(new FormData(form));
    values.calories = Number(values.calories);
    values.protein_g = Number(values.protein_g);
    values.carbs_g = Number(values.carbs_g);
    values.fat_g = Number(values.fat_g);
    values.glycemic_index = values.glycemic_index === "" ? null : Number(values.glycemic_index);
    button.disabled = true;
    try {
        await request("/api/v1/foods", { method: "POST", body: JSON.stringify(values) });
        await renderFoods();
        showWorkspaceMessage("Food added to the library.");
    } catch (error) {
        button.disabled = false;
        showWorkspaceMessage(error.message, true);
    }
}

async function renderRecipes() {
    const recipes = await request("/api/v1/recipes");
    workspaceContent.innerHTML = `
    ${pageHeading("RECIPE BOOK", "Recipes.", "Keep practical, repeatable recipes close at hand.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel recipe-form-panel">
      <div class="section-heading form-section-heading"><h2>Add a recipe</h2><span>NEW RECIPE</span></div>
      <form id="recipeForm" class="form-grid">
        <div class="form-field full-width"><label for="recipeTitle">Recipe name</label><input class="text-input" id="recipeTitle" name="title" placeholder="e.g. Berry overnight oats" required></div>
        <div class="form-field"><label for="recipeIngredients">Ingredients</label><textarea id="recipeIngredients" name="ingredients" placeholder="One ingredient per line" required></textarea></div>
        <div class="form-field"><label for="recipeInstructions">Instructions</label><textarea id="recipeInstructions" name="instructions" placeholder="How to prepare the recipe" required></textarea></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Save recipe <span aria-hidden="true">&#8594;</span></button></div>
      </form>
    </section>
    <div class="section-heading"><h2>Saved recipes</h2><span>${recipes.length} RECIPES</span></div>
    <div class="recipe-list">${
        recipes.length
            ? recipes
                  .map(
                      (recipe) => `
      <article class="recipe-row">
        <div class="recipe-row-top"><h3>${escapeHtml(recipe.title)}</h3><span>${escapeHtml(recipe.recipe_id)}</span></div>
        <p class="recipe-ingredients">${recipe.ingredients.map(escapeHtml).join(" · ") || "No ingredients recorded"}</p>
        <p class="recipe-instructions">${escapeHtml(recipe.instructions)}</p>
      </article>`,
                  )
                  .join("")
            : '<p class="empty-state">No recipes saved yet. Add the first one above.</p>'
    }</div>`;
    document.querySelector("#recipeForm").addEventListener("submit", createRecipe);
}

async function createRecipe(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const values = Object.fromEntries(new FormData(form));
    values.ingredients = values.ingredients
        .split(/\r?\n/)
        .map((ingredient) => ingredient.trim())
        .filter(Boolean);
    button.disabled = true;
    try {
        await request("/api/v1/recipes", { method: "POST", body: JSON.stringify(values) });
        await renderRecipes();
        showWorkspaceMessage("Recipe saved.");
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    } finally {
        button.disabled = false;
    }
}

async function renderMealPlans() {
    const query = new URLSearchParams({ dietitian_id: currentUser.id });
    // Keep usable sections visible when one endpoint (especially the optional
    // legacy-plan endpoint) fails. Do not silently treat authorization errors
    // as an empty result; show the affected service and its actual error.
    const sources = [
        ["Patients", `/api/v1/clients?${query}`],
        ["Recipes", "/api/v1/recipes"],
        ["Review queue", "/api/v1/meal-plans/review-queue"],
        ["Legacy plans", `/api/v1/meal-plans?${query}`],
    ];
    const responses = await Promise.allSettled(sources.map(([, url]) => request(url)));
    const problems = responses.flatMap((result, index) =>
        result.status === "rejected"
            ? [`${sources[index][0]}: ${result.reason?.message || "Unable to load"}`]
            : [],
    );
    const [clients, recipes, drafts, legacyPlans] = responses.map((result) =>
        result.status === "fulfilled" && Array.isArray(result.value) ? result.value : [],
    );
    const problemsHtml = problems.length
        ? `<div class="workspace-message error" role="alert">Some meal-planning information could not be loaded: <ul>${problems.map((message) => `<li>${escapeHtml(message)}</li>`).join("")}</ul>Check your local API and database connection before saving or approving plans.</div>`
        : "";
    const clientOptions = clients
        .map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`)
        .join("");
    const recipeOptions = recipes
        .filter((r) => Array.isArray(r.ingredients) && r.ingredients.length)
        .map(
            (r) =>
                `<label class="meal-review-option"><input type="checkbox" name="recipe_id" value="${escapeHtml(r.recipe_id)}"> ${escapeHtml(r.title)}</label>`,
        )
        .join("");
    workspaceContent.innerHTML = `
    ${pageHeading("MEAL PLANNING", "Review meal plans.", "Prepare screened drafts and approve them before client delivery.")}
    ${problemsHtml}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel"><div class="section-heading"><h2>New draft</h2><span>DIETITIAN ONLY</span></div>
      <p class="notice">Enter clinically reviewed context. The system cannot certify nutritional adequacy or allergy safety.</p>
      ${
          clients.length && recipeOptions
              ? `<form id="mealDraftForm" class="form-grid">
        <div class="form-field"><label>Patient</label><select name="client_id" required>${clientOptions}</select></div>
        <div class="form-field"><label>Plan focus</label><input class="text-input" name="diet_type" required maxlength="50" placeholder="Balanced"></div>
        <div class="form-field"><label>Days</label><input class="text-input" name="days" type="number" min="1" max="30" value="7" required></div>
        <div class="form-field"><label>Life stage (required for screening)</label><input class="text-input" name="life_stage" required placeholder="adult"></div>
        <div class="form-field"><label>Allergies (comma separated; enter none if reviewed)</label><input class="text-input" name="allergies" required placeholder="none"></div>
        <div class="form-field"><label>Conditions (comma separated; enter none if reviewed)</label><input class="text-input" name="conditions" required placeholder="none"></div>
        <div class="form-field"><label>Candidate recipes</label><div class="meal-review-options">${recipeOptions}</div></div>
        <div class="form-field form-actions"><button class="button button-primary" type="submit">Save draft for review</button></div>
      </form>`
              : '<p class="empty-state">Add an assigned patient and recipes with ingredient lists to create drafts.</p>'
      }
    </section>
    <section class="content-panel"><div class="section-heading"><h2>Dietitian review queue</h2><span>${drafts.length} PLANS</span></div>
      ${
          drafts.length
              ? drafts
                    .map((d) => {
                        const draft = d.draft_json || {};
                        const schedule = (draft.schedule || [])
                            .map(
                                (day) =>
                                    `<li>Day ${escapeHtml(day.day)}: ${escapeHtml(day.candidate_recipe?.title || "Unspecified")}</li>`,
                            )
                            .join("");
                        return `<article class="meal-plan-row"><div class="meal-plan-heading"><h3>${escapeHtml(draft.diet_type || "Meal plan")}</h3><span class="plan-status">${escapeHtml(d.status)}</span></div>
          <p>Patient: ${escapeHtml(d.client_id)} · ${escapeHtml(draft.days || "")} days</p>
          <ul class="meal-summary">${schedule}</ul>
          <p><strong>Screening cautions:</strong> ${escapeHtml((draft.cautions || []).join("; ") || "None recorded; independent clinical review still required.")}</p>
          ${
              d.status === "PENDING_REVIEW"
                  ? `<form class="mealReviewForm" data-plan-id="${escapeHtml(d.plan_id)}">
            <div class="form-field"><label>Decision</label><select name="decision"><option value="APPROVED">Approve</option><option value="MODIFIED">Modify</option><option value="REJECTED">Reject</option></select></div>
            <div class="form-field"><label>Review note (required)</label><textarea class="text-input" name="review_note" required maxlength="2000"></textarea></div>
            <div class="form-field"><label>Revised schedule JSON (only when modifying; include each day)</label><textarea class="text-input" name="revised_schedule" placeholder='[{"day":1,"candidate_recipe":{"title":"..."}}]'></textarea></div>
            <button class="button button-primary" type="submit">Submit review</button></form>`
                  : `<p>Review note: ${escapeHtml(d.review_note || "—")}</p>`
          }
        </article>`;
                    })
                    .join("")
              : '<p class="empty-state">No saved drafts available. If the review queue failed to load, see the warning above.</p>'
      }
    </section>
    <section class="content-panel"><h2>Existing legacy plans</h2><p>${legacyPlans.length} plans from the previous meal-planning system. These are separate from the new approval queue.</p></section>`;
    const form = document.querySelector("#mealDraftForm");
    if (form) {
        const selectedClient = sessionStorage.getItem("meal-plan-client");
        if (selectedClient && clients.some((c) => String(c.id) === String(selectedClient)))
            form.elements.client_id.value = selectedClient;
        sessionStorage.removeItem("meal-plan-client");
        form.addEventListener("submit", createMealPlan);
    }
    document
        .querySelectorAll(".mealReviewForm")
        .forEach((form) => form.addEventListener("submit", submitMealReview));
}

async function createMealPlan(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const values = Object.fromEntries(new FormData(form));
    const recipe_ids = [...form.querySelectorAll("input[name=recipe_id]:checked")].map(
        (el) => el.value,
    );
    if (!recipe_ids.length) return showWorkspaceMessage("Select at least one recipe.", true);
    const split = (str) =>
        str.trim().toLowerCase() === "none"
            ? []
            : str
                  .split(",")
                  .map((x) => x.trim())
                  .filter(Boolean);
    const payload = {
        client_id: values.client_id,
        diet_type: values.diet_type,
        days: Number(values.days),
        life_stage: values.life_stage,
        allergies: split(values.allergies),
        conditions: split(values.conditions),
        recipe_ids,
    };
    button.disabled = true;
    try {
        await request("/api/v1/meal-plans/drafts", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        await renderMealPlans();
        showWorkspaceMessage("Draft saved. It is not visible to the client until approved.");
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    } finally {
        button.disabled = false;
    }
}

async function submitMealReview(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const decision = form.elements.decision.value;
    const review_note = form.elements.review_note.value.trim();
    let revised_schedule = null;
    if (decision === "MODIFIED") {
        try {
            revised_schedule = JSON.parse(form.elements.revised_schedule.value);
        } catch {
            return showWorkspaceMessage("Enter valid JSON for the revised schedule.", true);
        }
        if (!Array.isArray(revised_schedule))
            return showWorkspaceMessage("Revised schedule must be a JSON array.", true);
    }
    if (!review_note) return showWorkspaceMessage("A review note is required.", true);
    button.disabled = true;
    try {
        const payload = { decision, review_note };
        if (decision === "MODIFIED") payload.revised_schedule = revised_schedule;
        await request(
            `/api/v1/meal-plans/drafts/${encodeURIComponent(form.dataset.planId)}/decision`,
            { method: "POST", body: JSON.stringify(payload) },
        );
        await renderMealPlans();
        showWorkspaceMessage("Review decision saved.");
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    } finally {
        button.disabled = false;
    }
}

async function refreshReviewCount() {
    try {
        const pending = await request("/api/v1/ai/recommendations/pending");
        document.querySelector("#reviewCount").textContent = String(pending.length);
    } catch {
        document.querySelector("#reviewCount").textContent = "!";
    }
}

async function refreshAdminApprovalCount() {
    try {
        const pending = await request("/api/v1/admin/approvals/pending");
        document.querySelector("#adminApprovalCount").textContent = String(pending.length);
    } catch {
        document.querySelector("#adminApprovalCount").textContent = "!";
    }
}

function renderAdminTable(headers, rows, emptyMessage) {
    if (!rows.length) return `<p class="empty-state">${emptyMessage}</p>`;
    return `<div class="admin-table-wrap"><table class="admin-data-table"><thead><tr>${headers.map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((value) => `<td>${escapeHtml(value ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function renderAdminDashboard() {
    const summary = await request("/api/v1/admin/dashboard");
    const cards = [
        ["Dietitians", summary.dietitians],
        ["Patients", summary.clients],
        ["Branches", summary.branches],
        ["Businesses", summary.businesses],
        ["Pending approvals", summary.pending_approvals],
        ["Appointments", summary.appointments],
        ["Meal plans", summary.meal_plans],
        ["Approval actions", summary.audit_events],
    ];
    workspaceContent.innerHTML = `
    ${pageHeading("ADMIN DASHBOARD", "Practice overview.", "Monitor registrations, care activity, and organization records.")}
    <div class="admin-stat-grid">${cards.map(([label, value]) => `<section class="admin-stat"><span>${escapeHtml(label)}</span><strong>${Number(value).toLocaleString()}</strong></section>`).join("")}</div>
    <div class="section-heading"><h2>Administration</h2><span>QUICK ACCESS</span></div>
    <div class="quick-grid admin-quick-grid">
      <button class="quick-link" data-go="admin-approvals" type="button"><strong>Review dietitian approvals</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="admin-dietitians" type="button"><strong>Manage dietitians</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="admin-clients" type="button"><strong>Browse patients</strong><span aria-hidden="true">&#8599;</span></button>
      <button class="quick-link" data-go="admin-reports" type="button"><strong>View reports</strong><span aria-hidden="true">&#8599;</span></button>
    </div>`;
    bindGoButtons();
}

async function renderStaffDashboard() {
    const profile = await request("/api/v1/staff/me");
    const role = staffRoleNames[profile.role] || profile.role;
    if (profile.role === "branch_manager") {
        const overview = await request("/api/v1/branch-manager/overview");
        workspaceContent.innerHTML = `
        ${pageHeading("BRANCH MANAGEMENT", `Welcome, ${escapeHtml(profile.full_name)}.`, `Managing ${escapeHtml(overview.branch_name)}.`)}
        <div class="admin-stat-grid">
          <section class="admin-stat"><span>Assigned branch</span><strong class="staff-role-card">${escapeHtml(overview.branch_name)}</strong></section>
          <section class="admin-stat"><span>Active branch staff</span><strong>${Number(overview.active_staff)}</strong></section>
          <section class="admin-stat"><span>Reception staff</span><strong>${Number(overview.reception_staff)}</strong></section>
          <section class="admin-stat"><span>Branch managers</span><strong>${Number(overview.branch_managers)}</strong></section>
        </div>
        <section class="content-panel"><h2 class="compact-heading">Branch operations</h2>
          <p>Manage patient onboarding and check-in at your assigned branch. Staff statistics only cover this branch; confidential clinical records and system administration remain restricted.</p>
          <div class="quick-grid">
            <button class="quick-link" data-go="reception-onboarding" type="button"><strong>Register patient</strong><span aria-hidden="true">&#8599;</span></button>
            <button class="quick-link" data-go="reception-checkin" type="button"><strong>Patient check-in</strong><span aria-hidden="true">&#8599;</span></button>
            <button class="quick-link" data-go="staff-profile" type="button"><strong>My profile</strong><span aria-hidden="true">&#8599;</span></button>
          </div>
        </section>`;
        bindGoButtons();
        return;
    }
    workspaceContent.innerHTML = `
    ${pageHeading("TEAM WORKSPACE", `Welcome, ${escapeHtml(profile.full_name)}.`, "Your access is controlled by your assigned practice role.")}
    <div class="admin-stat-grid"><section class="admin-stat"><span>Assigned role</span><strong class="staff-role-card">${escapeHtml(role)}</strong></section>
    <section class="admin-stat"><span>Account</span><strong class="staff-role-card">${profile.is_active ? "Active" : "Inactive"}</strong></section></div>
    <section class="content-panel"><h2 class="compact-heading">Secure staff access</h2>
    <p>Your practice role controls available tasks. Clinical records and administrative settings remain restricted.</p>
    <div class="quick-grid"><button class="quick-link" type="button" data-go="staff-profile"><strong>View my staff profile</strong><span aria-hidden="true">&#8599;</span></button>
    ${profile.role === "reception" ? '<button class="quick-link" data-go="reception-onboarding" type="button"><strong>Register patient</strong></button><button class="quick-link" data-go="reception-checkin" type="button"><strong>Check in a patient</strong></button>' : ""}
    ${profile.role === "compliance_officer" ? '<button class="quick-link" type="button" data-go="staff-access-events"><strong>View access audit</strong><span aria-hidden="true">&#8599;</span></button>' : ""}</div></section>`;
    bindGoButtons();
}

async function renderStaffProfile() {
    const profile = await request("/api/v1/staff/me");
    workspaceContent.innerHTML = `
    ${pageHeading("STAFF PROFILE", "My staff profile.", "Review your assigned role and branch.")}
    <section class="content-panel"><dl class="profile-details">
      <div><dt>Name</dt><dd>${escapeHtml(profile.full_name)}</dd></div>
      <div><dt>Email</dt><dd>${escapeHtml(profile.email)}</dd></div>
      <div><dt>Role</dt><dd>${escapeHtml(staffRoleNames[profile.role] || profile.role)}</dd></div>
      <div><dt>Branch ID</dt><dd>${escapeHtml(profile.branch_id || "Organization-wide")}</dd></div>
      <div><dt>Status</dt><dd>${profile.is_active ? "Active" : "Inactive"}</dd></div>
    </dl></section>`;
}

async function renderAccessEvents() {
    const events = await request("/api/v1/admin/access-events?limit=100");
    workspaceContent.innerHTML = `
    ${pageHeading("SECURITY", "Access events.", "Recent protected-API requests, including denied access attempts. Patient information and credentials are not displayed.")}
    <p class="notice">Shows recent access events, not the complete POPIA compliance audit. Logs may be incomplete until database migration and production-grade audit controls are implemented.</p>
    ${renderAdminTable(
        ["Timestamp", "Actor role", "Account ID", "Action", "Resource", "HTTP status"],
        events.map((event) => [
            event.occurred_at ? new Date(event.occurred_at).toLocaleString() : "—",
            event.actor_role,
            event.actor_id || "Anonymous",
            event.http_method,
            event.resource_path,
            event.status_code,
        ]),
        "No access events recorded yet.",
    )}`;
}

async function renderAdminStaff() {
    const [staff, branches] = await Promise.all([
        request("/api/v1/admin/staff"),
        request("/api/v1/admin/branches"),
    ]);
    const staffRoles = Object.entries(staffRoleNames);
    const roleChoices = (selected) =>
        staffRoles
            .map(
                ([value, label]) =>
                    `<option value="${escapeHtml(value)}" ${selected === value ? "selected" : ""}>${escapeHtml(label)}</option>`,
            )
            .join("");
    const branchChoices = (selected) =>
        `<option value="">Organization-wide / not assigned</option>` +
        branches
            .map(
                (branch) =>
                    `<option value="${escapeHtml(branch.branch_id)}" ${selected === branch.branch_id ? "selected" : ""}>${escapeHtml(branch.name)} (${escapeHtml(branch.business_name || "Practice")})</option>`,
            )
            .join("");
    workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Staff & roles.", "Provision reception, branch management, compliance, executive, and content accounts.")}
    <div data-message class="workspace-message" role="status" aria-live="polite" hidden></div>
    <section class="content-panel"><h2 class="compact-heading">Add a staff account</h2>
      <p class="notice">The account password must be shared securely. New roles do not automatically have access to medical records or administrator settings.</p>
      <form id="staffCreateForm" class="form-grid">
        <div class="form-field"><label for="staffFullName">Full name</label><input class="text-input" id="staffFullName" name="full_name" maxlength="200" required></div>
        <div class="form-field"><label for="staffEmail">Email</label><input class="text-input" id="staffEmail" name="email" type="email" maxlength="150" required></div>
        <div class="form-field"><label for="staffRole">Role</label><select class="text-input" id="staffRole" name="role" required>${roleChoices("reception")}</select></div>
        <div class="form-field"><label for="staffBranch">Assigned branch</label><select class="text-input" id="staffBranch" name="branch_id">${branchChoices(null)}</select></div>
        <div class="form-field full-width"><label for="staffPassword">Initial password (at least 12 characters)</label><input class="text-input" id="staffPassword" name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Create staff account</button></div>
      </form>
    </section>
    <div class="section-heading"><h2>Staff directory</h2><span>${staff.length} ACCOUNTS</span></div>
    ${
        staff.length
            ? `<div class="admin-table-wrap"><table class="admin-data-table"><thead><tr>
      <th scope="col">Name</th><th scope="col">Email</th><th scope="col">Role</th><th scope="col">Branch</th><th scope="col">Status</th><th scope="col">Actions</th>
    </tr></thead><tbody>${staff
        .map(
            (user) => `<tr data-staff-row="${escapeHtml(user.staff_id)}">
      <td>${escapeHtml(user.full_name)}</td><td>${escapeHtml(user.email)}</td>
      <td><select class="text-input" data-staff-role aria-label="Role for ${escapeHtml(user.full_name)}">${roleChoices(user.role)}</select></td>
      <td><select class="text-input" data-staff-branch aria-label="Branch for ${escapeHtml(user.full_name)}">${branchChoices(user.branch_id)}</select></td>
      <td>${user.is_active ? "Active" : "Inactive"}</td>
      <td><button class="button" type="button" data-staff-save>Save</button>
      <button class="button" type="button" data-staff-toggle="${user.is_active ? "off" : "on"}">${user.is_active ? "Disable" : "Enable"}</button></td>
    </tr>`,
        )
        .join("")}</tbody></table></div>`
            : '<p class="empty-state">No staff accounts added yet.</p>'
    }`;
    workspaceContent.querySelector("#staffCreateForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const payload = Object.fromEntries(new FormData(form));
        if (!payload.branch_id) payload.branch_id = null;
        try {
            await request("/api/v1/admin/staff", { method: "POST", body: JSON.stringify(payload) });
            await renderAdminStaff();
            showWorkspaceMessage("Staff account created. Share its initial password securely.");
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        }
    });
    workspaceContent
        .querySelectorAll("[data-staff-save], [data-staff-toggle]")
        .forEach((button) => {
            button.addEventListener("click", async () => {
                const row = button.closest("[data-staff-row]");
                const turningOff = button.dataset.staffToggle === "off";
                if (
                    turningOff &&
                    !window.confirm("Disable this staff account and revoke its current session?")
                )
                    return;
                const payload = {
                    role: row.querySelector("[data-staff-role]").value,
                    branch_id: row.querySelector("[data-staff-branch]").value || null,
                    is_active: button.hasAttribute("data-staff-toggle")
                        ? !turningOff
                        : !row.querySelector('[data-staff-toggle="on"]'),
                };
                button.disabled = true;
                try {
                    await request(
                        `/api/v1/admin/staff/${encodeURIComponent(row.dataset.staffRow)}`,
                        {
                            method: "PUT",
                            body: JSON.stringify(payload),
                        },
                    );
                    await renderAdminStaff();
                    showWorkspaceMessage(
                        "Staff permissions updated. Existing sessions were revoked.",
                    );
                } catch (error) {
                    button.disabled = false;
                    showWorkspaceMessage(error.message, true);
                }
            });
        });
}

async function renderAdminDietitians() {
    const dietitians = await request("/api/v1/admin/dietitians");
    workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Dietitians.", "Review registered practitioners and their organization assignments.")}
    ${renderAdminTable(
        ["Name", "Email", "License", "Business", "Branch", "Location", "Status"],
        dietitians.map((item) => [
            item.full_name,
            item.email,
            item.license_number,
            item.business_name,
            item.branch_name,
            item.branch_address,
            item.status,
        ]),
        "No dietitians are registered yet.",
    )}`;
}

async function renderAdminBusinesses() {
    const businesses = await request("/api/v1/admin/businesses");
    workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Businesses.", "View registered practices and their branch and practitioner counts.")}
    ${renderAdminTable(
        ["Business", "Registration", "Contact", "Branches", "Dietitians"],
        businesses.map((item) => [
            item.name,
            item.registration_number,
            item.contact_email,
            item.branch_count,
            item.dietitian_count,
        ]),
        "No businesses are registered yet.",
    )}`;
}

async function renderAdminBranches() {
    const [branches, businesses] = await Promise.all([
        request("/api/v1/admin/branches"),
        request("/api/v1/admin/businesses"),
    ]);
    workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Branches.", "Review practice locations or add a branch to a registered business.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel admin-branch-form-panel"><form id="adminBranchForm" class="form-grid">
      <div class="form-field"><label for="branchName">Branch name</label><input class="text-input" id="branchName" name="name" required></div>
      <div class="form-field"><label for="branchBusiness">Business</label><select id="branchBusiness" name="business_id"><option value="">General Practice / first business</option>${businesses.map((business) => `<option value="${escapeHtml(business.business_id)}">${escapeHtml(business.name)}</option>`).join("")}</select></div>
      <div class="form-field full-width"><label for="branchAddress">Address</label><input class="text-input" id="branchAddress" name="address"></div>
      <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add branch</button></div>
    </form></section>
    <div class="section-heading"><h2>Registered branches</h2><span>${branches.length} BRANCHES</span></div>
    ${renderAdminTable(
        ["Branch", "Address", "Business", "Dietitians"],
        branches.map((item) => [item.name, item.address, item.business_name, item.dietitian_count]),
        "No branches are registered yet.",
    )}`;
    document.querySelector("#adminBranchForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        if (!values.business_id) delete values.business_id;
        try {
            await request("/api/v1/branches", { method: "POST", body: JSON.stringify(values) });
            await renderAdminBranches();
            showWorkspaceMessage("Branch added.");
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        }
    });
}

async function renderAdminClients() {
    const clients = await request("/api/v1/admin/clients");
    workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Patients.", "Review patient account records and care-team assignments.")}
    ${renderAdminTable(
        ["Name", "Patient ID", "Email", "Dietitian", "Status"],
        clients.map((item) => [
            item.name,
            item.client_id,
            item.email,
            item.dietitian_name,
            item.status,
        ]),
        "No patient accounts are registered yet.",
    )}`;
}

async function renderAdminReports() {
    const summary = await request("/api/v1/admin/dashboard");
    workspaceContent.innerHTML = `
    ${pageHeading("REPORTS", "System reports.", "Current organization and care activity totals.")}
    ${renderAdminTable(
        ["Measure", "Total"],
        [
            ["Businesses", summary.businesses],
            ["Branches", summary.branches],
            ["Dietitians", summary.dietitians],
            ["Patients", summary.clients],
            ["Pending approvals", summary.pending_approvals],
            ["Appointments", summary.appointments],
            ["Meal plans", summary.meal_plans],
            ["Approval actions", summary.audit_events],
        ],
        "No report data is available yet.",
    )}`;
}

async function renderAdminAuditLogs() {
    const logs = await request("/api/v1/admin/audit-logs");
    workspaceContent.innerHTML = `
    ${pageHeading("AUDIT LOGS", "Administrative activity.", "Review approval decisions and their recorded notes.")}
    ${renderAdminTable(
        ["Date", "Administrator", "Entity", "Entity ID", "Action", "Notes"],
        logs.map((item) => [
            item.action_date ? new Date(item.action_date).toLocaleString() : "",
            item.admin_name || item.admin_id,
            item.entity_type,
            item.entity_id,
            item.action,
            item.comments,
        ]),
        "No audit events have been recorded yet.",
    )}`;
}

async function renderAdminSettings() {
    const [health, setup] = await Promise.all([
        request("/health"),
        request("/api/v1/admin/setup-status"),
    ]);
    workspaceContent.innerHTML = `
    ${pageHeading("SETTINGS", "System settings.", "Review installation status and the active administrator account.")}
    <section class="content-panel"><dl class="profile-details">
      <div><dt>API status</dt><dd>${escapeHtml(health.status)}</dd></div>
      <div><dt>Database</dt><dd>${escapeHtml(health.database)}</dd></div>
      <div><dt>Recommendation model</dt><dd>${escapeHtml("Configured on server")}</dd></div>
      <div><dt>Administrator</dt><dd>${escapeHtml(currentUser.full_name)} · ${escapeHtml(currentUser.email)}</dd></div>
      <div><dt>Initial setup</dt><dd>${setup.available ? "Available" : "Complete"}</dd></div>
    </dl></section>`;
}

async function renderAdminApprovals() {
    const pending = await request("/api/v1/admin/approvals/pending");
    workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Dietitian approvals.", "Review license registrations before adding dietitians to the directory.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="admin-approval-list">${
        pending.length
            ? pending
                  .map(
                      (dietitian) => `
      <article class="admin-approval-row" data-dietitian-id="${escapeHtml(dietitian.dietitian_id)}">
        <div class="admin-approval-main">
          <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(
              dietitian.full_name
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join("")
                  .toUpperCase(),
          )}</div>
          <div class="dietitian-details"><h2>${escapeHtml(dietitian.full_name)}</h2><p>${escapeHtml(dietitian.email)} · License ${escapeHtml(dietitian.license_number)}</p><p>${escapeHtml(dietitian.practice_name || "Nutrition practice")} · ${escapeHtml(dietitian.branch_name || "Branch not provided")} · ${escapeHtml(dietitian.branch_address || "Address not provided")}</p><p class="document-hint">Branch ID: ${escapeHtml(dietitian.branch_id || "—")} · Business ID: ${escapeHtml(dietitian.business_id || "—")}</p></div>
          <span class="dietitian-status status-pending">PENDING</span>
        </div>
        <div class="admin-document-list">${
            dietitian.documents.length
                ? dietitian.documents
                      .map(
                          (document) => `
          <div class="admin-document-row"><div><span>${escapeHtml(document.file_name)} · ${escapeHtml(document.content_type)}</span><p class="document-hint">${escapeHtml(document.practice_name || "Practice")} · ${escapeHtml(document.branch_name || "Branch")} · ${escapeHtml(document.branch_address || "Address not provided")}</p><p class="document-hint">Branch ID: ${escapeHtml(document.branch_id || "—")} · Business ID: ${escapeHtml(document.business_id || "—")}</p></div><button class="button quiet-button button-small" data-document-id="${escapeHtml(document.document_id)}" data-file-name="${escapeHtml(document.file_name)}" type="button">View document</button></div>`,
                      )
                      .join("")
                : '<p class="document-hint">No verification documents submitted yet.</p>'
        }</div>
        <label class="form-field admin-approval-notes"><span class="field-label">Decision note <span class="stat-caption">(required for rejection; optional for approval)</span></span><input class="text-input" name="notes" placeholder="Explain the reason for rejection or approval"></label>
        <div class="review-actions"><button class="button button-small button-reject" data-admin-decision="REJECTED" type="button">Reject</button><button class="button button-small button-approve" data-admin-decision="APPROVED" type="button" ${dietitian.documents.length ? "" : "disabled"}>Approve</button></div>
      </article>`,
                  )
                  .join("")
            : '<p class="empty-state">No dietitian registrations are waiting for review.</p>'
    }</div>`;
    workspaceContent.querySelectorAll("[data-admin-decision]").forEach((button) => {
        button.addEventListener("click", reviewDietitianRegistration);
    });
    workspaceContent.querySelectorAll("[data-document-id]").forEach((button) => {
        button.addEventListener("click", viewDietitianDocument);
    });
    document.querySelector("#adminApprovalCount").textContent = String(pending.length);
}

async function viewDietitianDocument(event) {
    const button = event.currentTarget;
    const token = sessionStorage.getItem(adminTokenKey);
    button.disabled = true;
    try {
        const response = await fetch(
            `/api/v1/admin/dietitian-documents/${encodeURIComponent(button.dataset.documentId)}`,
            {
                headers: { Authorization: `Bearer ${token}` },
            },
        );
        if (!response.ok) throw new Error("Could not open this document.");
        const documentUrl = URL.createObjectURL(await response.blob());
        const fileName = button.dataset.fileName;
        workspaceContent.insertAdjacentHTML(
            "beforeend",
            `
      <dialog class="document-preview" aria-label="Verification document preview">
        <header class="document-preview-header"><strong>${escapeHtml(fileName)}</strong><button class="button quiet-button button-small" type="button">Close</button></header>
        <iframe src="${documentUrl}" title="${escapeHtml(fileName)}"></iframe>
      </dialog>`,
        );
        const dialog = workspaceContent.querySelector(".document-preview");
        dialog.querySelector("button").addEventListener("click", () => dialog.close());
        dialog.addEventListener(
            "close",
            () => {
                URL.revokeObjectURL(documentUrl);
                dialog.remove();
            },
            { once: true },
        );
        dialog.showModal();
    } catch (error) {
        showWorkspaceMessage(error.message, true);
    } finally {
        button.disabled = false;
    }
}

async function reviewDietitianRegistration(event) {
    const button = event.currentTarget;
    const card = button.closest("[data-dietitian-id]");
    const notes = card.querySelector("[name=notes]").value.trim();
    if (button.dataset.adminDecision === "REJECTED" && !notes) {
        showWorkspaceMessage("Enter a reason before rejecting this registration.", true);
        card.querySelector("[name=notes]").focus();
        return;
    }
    button.disabled = true;
    try {
        await request("/api/v1/admin/approvals", {
            method: "POST",
            body: JSON.stringify({
                dietitian_id: card.dataset.dietitianId,
                status: button.dataset.adminDecision,
                notes,
            }),
        });
        await renderAdminApprovals();
        showWorkspaceMessage("Decision recorded in the audit log.");
    } catch (error) {
        button.disabled = false;
        showWorkspaceMessage(error.message, true);
    }
}

async function updateAdminSetupTab() {
    const tab = document.querySelector("#adminSetupTab");
    try {
        const setup = await request("/api/v1/admin/setup-status");
        tab.hidden = !setup.available;
        tab.closest(".auth-tabs").classList.toggle("has-admin-setup", setup.available);
    } catch {
        tab.hidden = true;
        tab.closest(".auth-tabs").classList.remove("has-admin-setup");
    }
}

function bindGoButtons() {
    workspaceContent.querySelectorAll("[data-go]").forEach((button) => {
        button.addEventListener("click", () =>
            navTo(button.dataset.go, button.dataset.aiPanel || "coach"),
        );
    });
}

function escapeHtml(value) {
    return String(value).replace(
        /[&<>"']/g,
        (character) =>
            ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            })[character],
    );
}

document.querySelector("#loginTab").addEventListener("click", () => setAuthMode("login"));
document.querySelector("#signupTab").addEventListener("click", () => setAuthMode("signup"));
document
    .querySelector("#adminSetupTab")
    .addEventListener("click", () => setAuthMode("admin-setup"));
signupForm.elements.role.forEach((input) => input.addEventListener("change", updateSignupRole));
document.querySelectorAll("#signOutButton, #mobileSignOutButton").forEach((button) => {
    button.addEventListener("click", signOut);
});
document
    .querySelectorAll(".nav-item")
    .forEach((item) => item.addEventListener("click", () => navTo(item.dataset.view)));

loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = loginForm.querySelector("button[type=submit]");
    button.disabled = true;
    try {
        const result = await request("/api/v1/auth/login", {
            method: "POST",
            body: JSON.stringify(Object.fromEntries(new FormData(loginForm))),
        });
        if (result.user.type === "admin") {
            sessionStorage.removeItem(staffTokenKey);
            sessionStorage.setItem(adminTokenKey, result.access_token);
            sessionStorage.removeItem(dietitianTokenKey);
            showWorkspace(result.user, "overview");
        } else if (result.user.type === "dietitian") {
            sessionStorage.setItem(dietitianTokenKey, result.access_token);
            sessionStorage.removeItem(adminTokenKey);
            sessionStorage.removeItem(staffTokenKey);
            showWorkspace(result.user);
        } else if (Object.hasOwn(staffRoleNames, result.user.type)) {
            sessionStorage.removeItem(adminTokenKey);
            sessionStorage.removeItem(dietitianTokenKey);
            sessionStorage.removeItem(clientTokenKey);
            sessionStorage.setItem(staffTokenKey, result.access_token);
            showWorkspace(result.user);
        } else {
            sessionStorage.removeItem(staffTokenKey);
            sessionStorage.removeItem(adminTokenKey);
            sessionStorage.removeItem(dietitianTokenKey);
            sessionStorage.setItem(clientTokenKey, result.access_token);
            showWorkspace(result.user);
        }
    } catch (error) {
        showAuthMessage(error.message);
    } finally {
        button.disabled = false;
    }
});

// FR-1.6: JSON-encode optional attachments in bounded base64 without uploading
// anything to an external service. The API checks signatures and limits again.
async function registrationFileAttachment(input, maxBytes, allowedTypes) {
    const file = input.files?.[0];
    if (!file) return null;
    if (file.size > maxBytes || file.size === 0 || !allowedTypes.includes(file.type)) {
        throw new Error(`Check ${input.id}: please select an accepted file within its size limit.`);
    }
    const buffer = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < buffer.length; i += 8192) {
        binary += String.fromCharCode(...buffer.subarray(i, i + 8192));
    }
    return { filename: file.name, content_type: file.type, data_base64: btoa(binary) };
}

// FR-1.10: explicit, short-lived device-only draft. Sensitive fields are NEVER
// stored. Registration works normally if storage is disabled.
const registrationDraftKey = "nutricare-patient-onboarding-draft-v1";
const registrationDraftTTL = 24 * 60 * 60 * 1000;
const registrationDraftFields = ["first_name", "last_name", "email", "phone", "gender"];
function clearRegistrationDraft() {
    try {
        localStorage.removeItem(registrationDraftKey);
    } catch {
        /* storage may be blocked */
    }
}
function registrationDraftMessage(message) {
    document.querySelector("#signupDraftMessage").textContent = message;
}
document.querySelector("#signupSaveDraft").addEventListener("click", () => {
    if (selectedRole() !== "client") return;
    try {
        const data = Object.fromEntries(
            registrationDraftFields.map((name) => [name, signupForm.elements[name].value]),
        );
        localStorage.setItem(registrationDraftKey, JSON.stringify({ saved_at: Date.now(), data }));
        registrationDraftMessage(
            "Draft saved here for up to 24 hours. Sensitive fields were not saved.",
        );
    } catch {
        registrationDraftMessage("Your browser does not allow saving a draft on this device.");
    }
});
document.querySelector("#signupRestoreDraft").addEventListener("click", () => {
    try {
        const saved = JSON.parse(localStorage.getItem(registrationDraftKey) || "null");
        if (
            !saved ||
            !saved.saved_at ||
            Date.now() - saved.saved_at > registrationDraftTTL ||
            Date.now() < saved.saved_at
        ) {
            clearRegistrationDraft();
            registrationDraftMessage("No valid draft found. Drafts expire after 24 hours.");
            return;
        }
        registrationDraftFields.forEach((name) => {
            signupForm.elements[name].value = saved.data?.[name] || "";
        });
        for (const field of Object.values(registrationFields)) {
            if (field.value) updateRegistrationValidation(field);
        }
        setPatientSignupStep(1);
        registrationDraftMessage(
            "Draft restored. Re-enter your identity number, birth date, password and consent.",
        );
    } catch {
        registrationDraftMessage("Could not restore a draft on this device.");
    }
});
document.querySelector("#signupClearDraft").addEventListener("click", () => {
    clearRegistrationDraft();
    registrationDraftMessage("Saved draft discarded.");
});

signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = signupForm.querySelector("button[type=submit]");
    const role = selectedRole();
    if (role === "client") {
        // Recheck previous steps before sending anything to the API.
        for (const step of [1, 2]) {
            if (!validateSignupStep(step)) {
                setPatientSignupStep(step);
                validateSignupStep(step);
                return;
            }
        }
    }
    if (role === "client" && !signupForm.elements.consent_to_care.checked) {
        setPatientSignupStep(3);
        showAuthMessage(
            "Please review the privacy notice and confirm your consent before creating an account.",
        );
        signupForm.elements.consent_to_care.reportValidity();
        return;
    }
    if (!passwordsMatch("signupPassword", "signupConfirmPassword")) {
        showAuthMessage("Passwords do not match.");
        signupForm.elements.confirm_password.reportValidity();
        return;
    }
    const values = Object.fromEntries(new FormData(signupForm));
    values.email = values.email.trim().toLowerCase();
    if (role === "client") {
        values.phone = values.phone.trim();
        // Never infer consent: send an explicit boolean only when checked.
        values.consent_to_care = signupForm.elements.consent_to_care.checked;
    } else {
        delete values.consent_to_care;
        delete values.privacy_notice_version;
    }
    delete values.role;
    delete values.confirm_password;
    delete values.profile_photo_file;
    delete values.initial_document_file;
    if (role === "client") {
        try {
            values.profile_photo = await registrationFileAttachment(
                signupForm.elements.profile_photo_file,
                1024 * 1024,
                ["image/jpeg", "image/png"],
            );
            values.initial_document = await registrationFileAttachment(
                signupForm.elements.initial_document_file,
                3 * 1024 * 1024,
                ["application/pdf", "image/jpeg", "image/png"],
            );
        } catch (error) {
            showAuthMessage(error.message);
            return;
        }
    }
    button.disabled = true;
    try {
        const path = role === "dietitian" ? "dietitian" : "client";
        await request(`/api/v1/auth/register/${path}`, {
            method: "POST",
            body: JSON.stringify(values),
        });
        const result = await request("/api/v1/auth/login", {
            method: "POST",
            body: JSON.stringify({ email: values.email, password: values.password }),
        });
        if (result.user.type === "dietitian") {
            sessionStorage.setItem(dietitianTokenKey, result.access_token);
            sessionStorage.removeItem(adminTokenKey);
        } else {
            sessionStorage.removeItem(adminTokenKey);
            sessionStorage.removeItem(dietitianTokenKey);
            sessionStorage.setItem(clientTokenKey, result.access_token);
        }
        if (role === "client") clearRegistrationDraft();
        showWorkspace(result.user, "overview");
    } catch (error) {
        showAuthMessage(error.message);
    } finally {
        button.disabled = false;
    }
});

adminSetupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = adminSetupForm.querySelector("button[type=submit]");
    if (!passwordsMatch("adminSetupPassword", "adminSetupConfirmPassword")) {
        showAuthMessage("Passwords do not match.");
        return;
    }
    const values = Object.fromEntries(new FormData(adminSetupForm));
    delete values.confirm_password;
    button.disabled = true;
    try {
        await request("/api/v1/admin/setup", { method: "POST", body: JSON.stringify(values) });
        const result = await request("/api/v1/auth/login", {
            method: "POST",
            body: JSON.stringify({ email: values.email, password: values.password }),
        });
        sessionStorage.setItem(adminTokenKey, result.access_token);
        showWorkspace(result.user, "overview");
    } catch (error) {
        showAuthMessage(error.message);
    } finally {
        button.disabled = false;
    }
});

// FR-1.7: authenticated patient QR view; the code is never the patient's ID.
async function renderClientCheckin(clientId) {
    workspaceContent.innerHTML = `${pageHeading("CHECK-IN", "Your QR check-in.", "Show your private code to reception when you arrive.")}
    <section class="content-panel" aria-label="Check-in QR"><p>Generate a fresh QR code for your visit. The previous code will stop working.</p>
    <button class="button button-primary" id="generateCheckinQR" type="button">Generate my check-in QR</button>
    <div id="clientQRDisplay" class="qr-display" role="status"></div></section>`;
    document.querySelector("#generateCheckinQR").addEventListener("click", async (event) => {
        event.currentTarget.disabled = true;
        try {
            const result = await request(
                `/api/v1/clients/${encodeURIComponent(clientId)}/checkin-code`,
                { method: "POST" },
            );
            const svgBlob = new Blob([result.qr_svg], { type: "image/svg+xml" });
            const url = URL.createObjectURL(svgBlob);
            const target = document.querySelector("#clientQRDisplay");
            target.innerHTML = `<img alt="Your private check-in QR code" src="${url}" width="260" height="260"><p>Show this QR to authorized reception staff.</p>`;
            target
                .querySelector("img")
                .addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
        } catch (error) {
            document.querySelector("#clientQRDisplay").textContent = error.message;
        } finally {
            event.currentTarget.disabled = false;
        }
    });
}

// FR-1.8: patient personally enters their own private password and checks
// the consent box. Reception never sees that password in a dashboard.
async function renderReceptionOnboarding() {
    workspaceContent.innerHTML = `${pageHeading("RECEPTION", "Assisted patient registration.", "Let the patient enter their password and review consent themselves.")}
  <div data-message class="workspace-message" hidden></div>
  <section class="content-panel"><form id="assistedRegistration" class="form-grid">
  <div class="form-field"><label for="assistedFirst">First name</label><input id="assistedFirst" class="text-input" name="first_name" required></div>
  <div class="form-field"><label for="assistedLast">Last name</label><input id="assistedLast" class="text-input" name="last_name" required></div>
  <div class="form-field"><label for="assistedEmail">Email</label><input id="assistedEmail" class="text-input" name="email" type="email" required></div>
  <div class="form-field"><label for="assistedID">South African ID number</label><input id="assistedID" class="text-input" name="id_number" inputmode="numeric" minlength="13" maxlength="13" required></div>
  <div class="form-field"><label for="assistedPhone">Phone</label><input id="assistedPhone" class="text-input" name="phone" type="tel" required></div>
  <div class="form-field"><label for="assistedDOB">Date of birth</label><input id="assistedDOB" class="text-input" name="date_of_birth" type="date" required></div>
  <div class="form-field"><label for="assistedGender">Gender</label><select id="assistedGender" class="text-input" name="gender" required><option value="">Choose</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></div>
  <div class="form-field"><label for="assistedPassword">Patient creates a private password</label><input id="assistedPassword" class="text-input" name="password" type="password" autocomplete="new-password" minlength="8" required></div>
  <div class="form-field full-width"><details aria-label="Patient privacy notice">${document.querySelector("#registrationPrivacyNotice").innerHTML}</details>
  <label><input name="consent_to_care" type="checkbox" required> The patient has read the notice and personally agrees to this registration and care processing.</label>
  <p class="notice">The recorded IP belongs to this reception terminal. Do not press Register until the patient confirms consent.</p></div>
  <div class="form-field full-width"><button class="button button-primary" type="submit">Register patient</button></div>
  </form></section>`;
    const form = document.querySelector("#assistedRegistration");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        button.disabled = true;
        const data = Object.fromEntries(new FormData(form));
        data.consent_to_care = form.elements.consent_to_care.checked;
        data.privacy_notice_version = "2026-10-28-v1";
        try {
            const result = await request("/api/v1/auth/register/client/assisted", {
                method: "POST",
                body: JSON.stringify(data),
            });
            form.reset();
            showWorkspaceMessage(
                `Registration created: ${result.user.id}. Welcome email queued.`,
                false,
            );
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
}

async function renderReceptionCheckin() {
    workspaceContent.innerHTML = `${pageHeading("RECEPTION", "Patient check-in.", "Scan the patient's QR with a keyboard-type scanner or paste the code.")}
  <div data-message class="workspace-message" hidden></div>
  <section class="content-panel"><form id="receptionCheckinForm" class="form-grid">
  <div class="form-field full-width"><label for="receptionQRValue">Check-in code</label><input id="receptionQRValue" class="text-input" name="checkin_code" autocomplete="off" required placeholder="Scan the QR code"></div>
  <div class="form-field full-width"><button class="button button-primary" type="submit">Check in patient</button></div>
  </form></section>`;
    const form = document.querySelector("#receptionCheckinForm");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("button");
        button.disabled = true;
        try {
            const result = await request("/api/v1/reception/check-in", {
                method: "POST",
                body: JSON.stringify({ checkin_code: form.elements.checkin_code.value }),
            });
            form.reset();
            showWorkspaceMessage(`Check-in recorded for patient ${result.client_id}.`, false);
        } catch (error) {
            showWorkspaceMessage(error.message, true);
        } finally {
            button.disabled = false;
        }
    });
}

bindPasswordConfirmation("signupPassword", "signupConfirmPassword");
bindPasswordConfirmation("adminSetupPassword", "adminSetupConfirmPassword");
document.querySelector("#signupPassword").addEventListener("input", (event) => {
    event.currentTarget.setCustomValidity(
        event.currentTarget.validity.tooShort ? "Use at least 8 characters." : "",
    );
});

updateSignupRole();
updateAdminSetupTab();
try {
    const savedUser = JSON.parse(sessionStorage.getItem(sessionKey) || "null");
    const hasAdminToken = Boolean(sessionStorage.getItem(adminTokenKey));
    if (savedUser && savedUser.id && savedUser.full_name) {
        if (savedUser.type === "admin" && hasAdminToken) {
            showWorkspace(savedUser, "overview");
        } else if (Object.hasOwn(staffRoleNames, savedUser.type)) {
            if (sessionStorage.getItem(staffTokenKey)) showWorkspace(savedUser);
        } else if (savedUser.type !== "admin") {
            showWorkspace(savedUser);
        }
    }
} catch {
    sessionStorage.removeItem(sessionKey);
    sessionStorage.removeItem(adminTokenKey);
}
