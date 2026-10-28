const TRAD_SESSION = "nutrition-traditional-session";
const TRAD_ADMIN_TOKEN = "nutrition-practice-admin-token";
const TRAD_CLIENT_TOKEN = "nutrition-practice-client-token";
const TRAD_STAFF_TOKEN = "nutrition-practice-staff-token";
const TRAD_DIETITIAN_TOKEN = "nutrition-practice-dietitian-token";
function tradUser() {
    try {
        return JSON.parse(sessionStorage.getItem(TRAD_SESSION) || "null");
    } catch (e) {
        return null;
    }
}
function tradClientId() {
    const user = tradUser();
    return (
        new URLSearchParams(window.combinedPageQuery || location.search).get("client_id") ||
        (user && user.type === "client" ? user.id : "")
    );
}
async function tradRequest(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData) && !headers.has("Content-Type"))
        headers.set("Content-Type", "application/json");
    const token =
        sessionStorage.getItem(TRAD_ADMIN_TOKEN) ||
        sessionStorage.getItem(TRAD_DIETITIAN_TOKEN) ||
        sessionStorage.getItem(TRAD_CLIENT_TOKEN) ||
        sessionStorage.getItem(TRAD_STAFF_TOKEN);
    if (token) headers.set("Authorization", "Bearer " + token);
    const response = await fetch(url, { ...options, headers });
    const body = await response.json().catch(() => null);
    if (!response.ok)
        throw new Error(
            body && body.detail ? body.detail : "Request failed (" + response.status + ")",
        );
    return body;
}
function tradMessage(text, error = false) {
    const box = document.querySelector("[data-message]");
    if (box) {
        box.textContent = text;
        box.classList.toggle("traditional-error", error);
        box.classList.remove("hidden");
    }
}
function tradEscape(value) {
    return String(value ?? "").replace(
        /[&<>'"]/g,
        (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c],
    );
}
function tradRows(rows) {
    return rows
        .map(
            (row) =>
                "<tr>" +
                row.map((value) => "<td>" + tradEscape(value) + "</td>").join("") +
                "</tr>",
        )
        .join("");
}
function tradFillUser() {
    const user = tradUser();
    document
        .querySelectorAll("[data-user-name]")
        .forEach((el) => (el.textContent = user ? user.full_name : "Guest"));
    document
        .querySelectorAll("[data-client-id]")
        .forEach((el) => (el.textContent = tradClientId() || "Not signed in"));
}
function tradSignOut() {
    sessionStorage.removeItem(TRAD_SESSION);
    sessionStorage.removeItem(TRAD_ADMIN_TOKEN);
    sessionStorage.removeItem(TRAD_DIETITIAN_TOKEN);
    sessionStorage.removeItem(TRAD_CLIENT_TOKEN);
    sessionStorage.removeItem(TRAD_STAFF_TOKEN);
    window.navigateCombinedPage("index.html");
}
async function tradLogin(form) {
    const values = Object.fromEntries(new FormData(form));
    try {
        const result = await tradRequest("/api/v1/auth/login", {
            method: "POST",
            body: JSON.stringify(values),
        });
        sessionStorage.setItem(TRAD_SESSION, JSON.stringify(result.user));
        sessionStorage.removeItem(TRAD_ADMIN_TOKEN);
        sessionStorage.removeItem(TRAD_DIETITIAN_TOKEN);
        sessionStorage.removeItem(TRAD_CLIENT_TOKEN);
        sessionStorage.removeItem(TRAD_STAFF_TOKEN);
        if (result.user.type === "admin")
            sessionStorage.setItem(TRAD_ADMIN_TOKEN, result.access_token);
        if (result.user.type === "dietitian")
            sessionStorage.setItem(TRAD_DIETITIAN_TOKEN, result.access_token);
        if (result.user.type === "client")
            sessionStorage.setItem(TRAD_CLIENT_TOKEN, result.access_token);
        if (
            [
                "reception",
                "branch_manager",
                "compliance_officer",
                "executive",
                "content_manager",
            ].includes(result.user.type)
        )
            sessionStorage.setItem(TRAD_STAFF_TOKEN, result.access_token);
        window.navigateCombinedPage("menu.html");
    } catch (e) {
        tradMessage(e.message, true);
    }
}
async function tradRegister(form) {
    const values = Object.fromEntries(new FormData(form));
    const role = values.role;
    delete values.role;
    delete values.confirm_password;
    try {
        await tradRequest("/api/v1/auth/register/" + role, {
            method: "POST",
            body: JSON.stringify(values),
        });
        tradMessage("Account created. You can now sign in.");
        form.reset();
    } catch (e) {
        tradMessage(e.message, true);
    }
}
function tradBindForms() {
    document.querySelectorAll("[data-logout]").forEach((b) =>
        b.addEventListener("click", (event) => {
            event.preventDefault();
            tradSignOut();
        }),
    );
    const login = document.querySelector("#traditionalLoginForm");
    if (login)
        login.addEventListener("submit", (e) => {
            e.preventDefault();
            tradLogin(login);
        });
    const register = document.querySelector("#traditionalRegisterForm");
    if (register) {
        const role = register.elements.role;
        const updateRole = () => {
            const client = register.elements.role.value === "client";
            document.querySelector("#traditionalClientFields").classList.toggle("hidden", !client);
            document
                .querySelector("#traditionalDietitianFields")
                .classList.toggle("hidden", client);
            ["id_number", "phone_number", "gender", "date_of_birth"].forEach((name) => {
                if (register.elements[name]) register.elements[name].required = client;
            });
            register.elements.license_number.required = !client;
        };
        role.forEach((r) => r.addEventListener("change", updateRole));
        updateRole();
        register.addEventListener("submit", (e) => {
            e.preventDefault();
            if (register.elements.password.value !== register.elements.confirm_password.value) {
                tradMessage("Passwords do not match.", true);
                return;
            }
            tradRegister(register);
        });
    }
    document.querySelectorAll("[data-json-form]").forEach((form) =>
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const values = Object.fromEntries(new FormData(form));
                const result = await tradRequest(form.dataset.endpoint, {
                    method: "POST",
                    body: JSON.stringify(values),
                });
                tradMessage(result.message || "Information saved.");
                form.reset();
                if (form.dataset.reload) location.reload();
            } catch (error) {
                tradMessage(error.message, true);
            }
        }),
    );
}
async function tradLoadProfile() {
    const id = tradClientId();
    if (!id) return;
    try {
        const clients = await tradRequest("/api/v1/clients?client_id=" + encodeURIComponent(id));
        const profile = await tradRequest("/api/v1/clients/" + encodeURIComponent(id) + "/profile");
        const c = clients[0] || {};
        const values = {
            Name: c.name,
            Email: c.email,
            "Client ID": c.id || id,
            "ID number": c.id_number,
            Gender: c.gender,
            "Date of birth": c.date_of_birth,
        };
        const target = document.querySelector("[data-profile-table]");
        if (target) target.innerHTML = tradRows(Object.entries(values));
        const details = document.querySelector("[data-profile-details]");
        if (details) details.textContent = JSON.stringify(profile, null, 2);
    } catch (e) {
        tradMessage(e.message, true);
    }
}
async function tradLoadProgress() {
    const id = tradClientId();
    if (!id) return;
    try {
        const rows = await tradRequest("/api/v1/clients/" + encodeURIComponent(id) + "/progress");
        const target = document.querySelector("[data-progress-table]");
        if (target)
            target.innerHTML = rows.length
                ? tradRows(
                      rows.map((x) => [
                          x.log_date,
                          x.weight_kg,
                          x.calories,
                          x.water_ml,
                          x.steps,
                          x.sleep_hours,
                      ]),
                  )
                : "<tr><td colspan='6'>No progress records yet.</td></tr>";
    } catch (e) {
        tradMessage(e.message, true);
    }
}
async function tradLoadMeals() {
    const id = tradClientId();
    if (!id) return;
    try {
        const rows = await tradRequest("/api/v1/clients/" + encodeURIComponent(id) + "/meals");
        const target = document.querySelector("[data-meals-table]");
        if (target)
            target.innerHTML = rows.length
                ? tradRows(
                      rows.map((x) => [
                          x.log_date,
                          x.meal_time,
                          x.meal_type,
                          x.description,
                          x.calories,
                      ]),
                  )
                : "<tr><td colspan='5'>No meals recorded yet.</td></tr>";
    } catch (e) {
        tradMessage(e.message, true);
    }
}
async function tradLoadLactation() {
    const id = tradClientId();
    if (!id) return;
    try {
        const data = await tradRequest(
            "/api/v1/clients/" + encodeURIComponent(id) + "/lactation/overview",
        );
        const target = document.querySelector("[data-lactation-table]");
        if (target) {
            const rows = [];
            Object.entries(data).forEach(([kind, items]) => {
                if (Array.isArray(items))
                    items.forEach((item) => rows.push([kind, JSON.stringify(item)]));
            });
            target.innerHTML = rows.length
                ? tradRows(rows)
                : "<tr><td colspan='2'>No lactation records yet.</td></tr>";
        }
    } catch (e) {
        tradMessage(e.message, true);
    }
}
async function tradLoadAdmin() {
    try {
        const [admins, branches, clients] = await Promise.all([
            tradRequest("/api/v1/admin/administrators"),
            tradRequest("/api/v1/admin/branches"),
            tradRequest("/api/v1/admin/clients"),
        ]);
        const fill = (selector, rows, empty) => {
            const el = document.querySelector(selector);
            if (el)
                el.innerHTML = rows.length
                    ? tradRows(rows)
                    : "<tr><td colspan='5'>" + empty + "</td></tr>";
        };
        fill(
            "[data-admin-table]",
            admins.map((x) => [x.admin_id, x.full_name, x.email]),
            "No administrators.",
        );
        fill(
            "[data-branch-table]",
            branches.map((x) => [x.name, x.address, x.business_name, x.dietitian_count]),
            "No branches.",
        );
        fill(
            "[data-client-table]",
            clients.map((x) => [x.client_id, x.name, x.email, x.dietitian_name, x.status]),
            "No clients.",
        );
    } catch (e) {
        tradMessage(e.message, true);
    }
}
document.addEventListener("DOMContentLoaded", () => {
    tradFillUser();
    tradBindForms();
    if (document.querySelector("[data-profile-table]")) tradLoadProfile();
    if (document.querySelector("[data-progress-table]")) tradLoadProgress();
    if (document.querySelector("[data-meals-table]")) tradLoadMeals();
    if (document.querySelector("[data-lactation-table]")) tradLoadLactation();
    if (document.querySelector("[data-admin-table]")) tradLoadAdmin();
});

document.addEventListener("DOMContentLoaded", async () => {
    const root = document.querySelector("[data-support-root]");
    if (!root) return;
    if (!tradUser()) {
        tradMessage("Please sign in to use support.", true);
        return;
    }
    try {
        await window.mountSupport(root, {
            request: tradRequest,
            isAdmin: tradUser().type === "admin",
            escapeHtml: tradEscape,
        });
    } catch (error) {
        tradMessage(error.message, true);
    }
});
