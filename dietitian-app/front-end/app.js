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

let currentUser = null;

async function request(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = sessionStorage.getItem(adminTokenKey) || sessionStorage.getItem(dietitianTokenKey);
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(url, { ...options, headers });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && (payload.detail || payload.message);
    throw new Error(typeof detail === "string" ? detail : `Request failed with status ${response.status}`);
  }
  return payload;
}

function showAuthMessage(message, kind = "error") {
  authMessage.textContent = message;
  authMessage.className = kind === "success" ? "form-message success" : "form-message";
  authMessage.hidden = false;
}

function showWorkspace(user, initialView = "overview") {
  currentUser = user;
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
    weekday: "long", month: "long", day: "numeric",
  }).format(new Date());
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-current", item.dataset.view === initialView);
  });
  const isClient = user.type === "client";
  const isAdmin = user.type === "admin";
  const isDietitian = user.type === "dietitian";
  document.querySelectorAll("[data-standard-only]").forEach((item) => { item.hidden = isAdmin; });
  document.querySelectorAll("[data-client-only]").forEach((item) => { item.hidden = !isClient; });
  document.querySelectorAll("[data-dietitian-only]").forEach((item) => { item.hidden = !isDietitian; });
  document.querySelectorAll("[data-admin-only]").forEach((item) => { item.hidden = !isAdmin; });
  document.querySelector('[data-view="overview"]').innerHTML = '<span class="nav-glyph">&#9633;</span>Dashboard';
  document.querySelector('[data-view="clients"]').innerHTML = '<span class="nav-glyph">&#9787;</span>My Patients';
  document.querySelector("#signOutButton").lastChild.textContent = isAdmin ? "Logout" : "Sign out";
  document.querySelector("#mobileSignOutButton").textContent = isAdmin ? "Logout" : "Sign out";
  loadView(initialView);
  if (isAdmin) {
    document.querySelector("#reviewCount").textContent = "0";
    refreshAdminApprovalCount();
  } else if (isClient) {
    document.querySelector("#reviewCount").textContent = "0";
  } else {
    refreshReviewCount();
  }
}

function signOut() {
  sessionStorage.removeItem(sessionKey);
  sessionStorage.removeItem(adminTokenKey);
  sessionStorage.removeItem(dietitianTokenKey);
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

function updateSignupRole() {
  const isClient = selectedRole() === "client";
  document.querySelector("#dietitianFields").hidden = isClient;
  document.querySelector("#clientFields").hidden = !isClient;
  signupForm.elements.license_number.required = !isClient;
  signupForm.elements.date_of_birth.required = isClient;
  signupForm.querySelectorAll(".role-option").forEach((option) => {
    option.classList.toggle("is-selected", option.querySelector("input").checked);
  });
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
  document.querySelector("#authHeading").textContent = isAdminSetup ? "Set up your administrator." : isSignup ? "Create your account." : "Welcome back.";
  document.querySelector("#authSubheading").textContent = isAdminSetup
    ? "Create the first administrator for this installation."
    : isSignup ? "Join your nutrition practice workspace." : "Sign in to continue to your nutrition workspace.";
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
  return { client: clients[0] || { id: clientId, name: clientId }, profile };
}

function patientContextMarkup(client, profile) {
  const allergies = profile.allergies || [];
  const conditions = profile.conditions || [];
  const metrics = profile.metrics || [];
  const latestProgress = (profile.progress || []).at(-1);
  const progressItems = latestProgress
    ? Object.entries(latestProgress).filter(([key, value]) => key !== "log_date" && value !== null && value !== undefined)
    : [];
  return `
    <section class="content-panel patient-context-preview">
      <h3>${escapeHtml(client.name)}</h3>
      <p class="stat-caption">${escapeHtml(client.id)} · ${escapeHtml(client.status || "Patient")}</p>
      <div class="form-grid">
        <div class="form-field"><label>Allergies</label><div class="text-input">${allergies.length ? allergies.map((item) => `${escapeHtml(item.allergen)} (${escapeHtml(item.severity)})`).join(", ") : "No allergy information recorded"}</div></div>
        <div class="form-field"><label>Medical conditions</label><div class="text-input">${conditions.length ? conditions.map((item) => escapeHtml(item.condition_name)).join(", ") : "No conditions recorded"}</div></div>
        <div class="form-field"><label>Recorded metrics</label><div class="text-input">${metrics.length ? metrics.map((item) => `${escapeHtml(item.metric_type)}: ${escapeHtml(item.value)}`).join(" · ") : "No metrics recorded"}</div></div>
        <div class="form-field"><label>Latest progress</label><div class="text-input">${progressItems.length ? progressItems.map(([key, value]) => `${escapeHtml(key.replaceAll("_", " "))}: ${escapeHtml(value)}`).join(" · ") : "No progress recorded"}</div></div>
      </div>
    </section>`;
}

function bindPatientContextButtons() {
  workspaceContent.querySelectorAll("[data-patient-context]").forEach((button) => {
    button.addEventListener("click", async () => {
      const preview = button.closest("[data-patient-card]").querySelector("[data-patient-preview]");
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
        const { client, profile } = await fetchPatientContext(button.dataset.patientContext);
        preview.innerHTML = patientContextMarkup(client, profile);
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
  const doctorName = currentUser && currentUser.full_name ? currentUser.full_name.split(" ")[0] : "John";
  const query = `?dietitian_id=${encodeURIComponent(currentUser.id)}`;
  const [clients, appointments, recommendations, plans] = await Promise.all([
    request(`/api/v1/clients${query}`),
    request(`/api/v1/appointments${query}`),
    request("/api/v1/ai/recommendations/pending"),
    request(`/api/v1/meal-plans${query}`),
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
          <span class="stat-label">Pending AI Reviews</span>
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
      ${clients.length ? clients.map((client) => `
        <article class="dietitian-row">
          <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(client.name.split(/\s+/).slice(0,2).map((part) => part[0]).join(""))}</div>
          <div class="dietitian-details"><h2>${escapeHtml(client.name)}</h2><p>${escapeHtml(client.id)} · ${escapeHtml(client.status)}</p></div>
          <div class="review-actions">
            <button class="button button-small button-approve" data-open-client="${escapeHtml(client.id)}" type="button">View</button>
          </div>
        </article>
      `).join("") : '<p class="empty-state">0 patients. Patients who join your practice will appear here.</p>'}
    </div>
    <div class="notice">Drafted meal plans are linked to the selected patient and appear in their meal plan view.</div>
  `;
  workspaceContent.querySelectorAll("[data-open-client]").forEach((button) => {
    button.addEventListener("click", () => renderClientManagementProfile(button.dataset.openClient));
  });
  bindGoButtons();
}

function renderAIWorkspaceTabs(activePanel) {
  if (currentUser.type !== "dietitian") return "";
  return `
    <div class="ai-workspace-tabs" role="tablist" aria-label="AI workspace">
      <button class="ai-workspace-tab${activePanel === "coach" ? " is-active" : ""}" role="tab" aria-selected="${activePanel === "coach"}" data-ai-panel="coach" type="button">AI Coach</button>
      <button class="ai-workspace-tab${activePanel === "plan" ? " is-active" : ""}" role="tab" aria-selected="${activePanel === "plan"}" data-ai-panel="plan" type="button">Plan Studio</button>
    </div>`;
}

async function renderAIWorkspace(activePanel = "coach", clientId = "") {
  const panel = activePanel === "plan" && currentUser.type === "dietitian" ? "plan" : "coach";
  workspaceContent.innerHTML = `
    ${pageHeading("AI WORKSPACE", "Food, plans, and care guidance.", "Chat about everyday nutrition or draft a plan for dietitian review.")}
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
  const conversation = await request(`/api/v1/ai/chat?user_id=${encodeURIComponent(userId)}&role=${encodeURIComponent(role)}`);
  const messages = conversation.messages || [];
  panel.innerHTML = `
    <section class="assistant-topics" aria-label="AI nutrition assistant topics">
      <div class="assistant-topics-heading"><span class="eyebrow eyebrow-green">AI NUTRITION ASSISTANT</span><span>Choose a starting point or ask anything</span></div>
      <div class="assistant-topic-list">
        <button class="assistant-topic is-primary" data-topic="ask" type="button">Ask AI</button>
        <button class="assistant-topic" data-topic="recipe" type="button">Recipe Ideas</button>
        <button class="assistant-topic" data-topic="food" type="button">Food Questions</button>
        <button class="assistant-topic" data-topic="meal-plan" type="button">Meal Plan Help</button>
        <button class="assistant-topic" data-topic="hydration" type="button">Hydration</button>
        <button class="assistant-topic" data-topic="timing" type="button">Meal Timing</button>
        <button class="assistant-topic" data-topic="activity" type="button">Activity &amp; Workouts</button>
        <button class="assistant-topic" data-topic="habits" type="button">Healthy Habits</button>
        <button class="assistant-topic" data-ai-recommendations type="button">${role === "client" ? "My AI Recommendations" : "Review Recommendations"}</button>
      </div>
    </section>
    <section class="content-panel chat-panel">
      <div class="chat-thread">
        ${messages.map((message) => `
          <div class="chat-bubble ${message.role === "assistant" ? "assistant" : "user"}">
            <strong>${message.role === "assistant" ? "AI Coach" : "You"}</strong>
            <p>${escapeHtml(message.content)}</p>
          </div>
        `).join("")}
      </div>
      <form id="aiChatForm" class="chat-form">
        <textarea id="aiChatInput" name="message" placeholder="Ask about food, workouts, hydration, or healthy routines..." required></textarea>
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
    x: plot.left + (plot.right - plot.left) * index / Math.max(history.length - 1, 1),
    y: plot.top + (maxWeight - entry.value) / range * (plot.bottom - plot.top),
  }));
  const pointList = points.map((point) => `${point.x},${point.y}`).join(" ");
  return `
    <svg class="weight-chart" viewBox="0 0 640 220" role="img" aria-label="Weight trend from ${escapeHtml(history[0].value)} kilograms to ${escapeHtml(history[history.length - 1].value)} kilograms">
      ${ticks.map((tick, index) => {
        const y = plot.top + (plot.bottom - plot.top) * index / (ticks.length - 1);
        return `<line class="weight-chart-grid" x1="${plot.left}" y1="${y}" x2="${plot.right}" y2="${y}"></line><text class="weight-chart-axis" x="2" y="${y + 4}">${tick}kg</text>`;
      }).join("")}
      <polyline class="weight-chart-line" points="${pointList}"></polyline>
      ${points.map((point) => `<circle class="weight-chart-point" cx="${point.x}" cy="${point.y}" r="4"><title>${escapeHtml(point.label)}: ${escapeHtml(point.value)} kg</title></circle><text class="weight-chart-label" x="${point.x}" y="198" text-anchor="middle">${escapeHtml(point.label)}</text>`).join("")}
    </svg>`;
}

async function renderClientManagementProfile(clientId) {
  const { client, profile } = await fetchPatientContext(clientId);
  workspaceContent.innerHTML = `
    ${pageHeading("PATIENT PROFILE", client.name, "Current information recorded for this patient.")}
    ${patientContextMarkup(client, profile)}
  `;
}

async function renderClientManagementList() {
  const clients = await request(`/api/v1/clients?dietitian_id=${encodeURIComponent(currentUser.id)}`);
  workspaceContent.innerHTML = `
    ${pageHeading("MY PATIENTS", "Patient roster.", "Search and review patients in your care.")}
    <div class="section-heading"><h2>My Patients</h2><span>${clients.length} PATIENTS</span></div>
    <label class="field-label" for="clientSearch">Search patients</label>
    <input class="text-input" id="clientSearch" placeholder="Search by patient ID, condition, name, or status" type="search">
    <div class="dietitian-directory">
      ${clients.length ? clients.map((client) => `
        <article class="dietitian-row" data-search="${escapeHtml([client.id, client.name, client.status].join(" "))}">
          <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(client.name.split(/\s+/).slice(0,2).map((part) => part[0]).join(""))}</div>
          <div class="dietitian-details"><h2>${escapeHtml(client.name)}</h2><p>${escapeHtml(client.id)} · ${escapeHtml(client.status)}</p></div>
          <div class="review-actions">
            <button class="button button-small button-approve" data-open-client="${escapeHtml(client.id)}" type="button">View</button>
            <button class="button button-small" data-draft-plan="${escapeHtml(client.id)}" type="button">Draft plan</button>
          </div>
        </article>
      `).join("") : '<p class="empty-state">0 patients. Patients who join your practice will appear here.</p>'}
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
    button.addEventListener("click", () => renderClientManagementProfile(button.dataset.openClient));
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
  return `<div class="dietitian-directory">${dietitians.map((dietitian) => `
    <article class="dietitian-row">
      <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(dietitian.full_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase())}</div>
      <div class="dietitian-details"><h2>${escapeHtml(dietitian.full_name)}</h2><p>${escapeHtml(dietitian.specialisation || "Nutrition care")}${dietitian.practice_name ? ` · ${escapeHtml(dietitian.practice_name)}` : ""}${dietitian.branch_name ? ` · ${escapeHtml(dietitian.branch_name)}` : ""}</p></div>
      <span class="dietitian-status status-${escapeHtml(dietitian.status.toLowerCase())}">${escapeHtml(dietitian.status.replaceAll("_", " "))}</span>
    </article>`).join("")}</div>`;
}

async function renderClientDashboard(firstName) {
  const dietitians = await request("/api/v1/dietitians");
  workspaceContent.innerHTML = `
    ${pageHeading("PATIENT DASHBOARD", `Welcome, ${escapeHtml(firstName)}.`, "Your health information, progress, and care plan in one place.")}
    <section class="feature-panel client-home-feature">
      <span class="eyebrow">YOUR CARE, AT A GLANCE</span>
      <h2>Small steps make meaningful progress.</h2>
      <p>Check your latest progress, review your meal plan, or ask the AI Coach a nutrition question.</p>
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
    ${dietitians.length ? `<div class="dietitian-directory patient-dietitian-directory">${dietitians.map((dietitian) => `
      <article class="dietitian-row">
        <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(dietitian.full_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase())}</div>
        <div class="dietitian-details"><h2>${escapeHtml(dietitian.full_name)}</h2><p>${escapeHtml(dietitian.specialisation || "Nutrition care")}${dietitian.practice_name ? ` · ${escapeHtml(dietitian.practice_name)}` : ""}${dietitian.branch_name ? ` · ${escapeHtml(dietitian.branch_name)}` : ""}</p></div>
        <button class="button button-small button-approve" data-book-dietitian="${escapeHtml(dietitian.id)}" type="button">Book appointment</button>
      </article>`).join("")}</div>` : '<p class="empty-state">No approved Dietitians are listed right now.</p>'}`;
  bindGoButtons();
  workspaceContent.querySelectorAll("[data-book-dietitian]").forEach((button) => {
    button.addEventListener("click", () => {
      sessionStorage.setItem("patient-booking-dietitian", button.dataset.bookDietitian);
      navTo("client-appointments");
    });
  });
}

function renderMyProfile() {
  const user = currentUser;
  const isClient = user.type === "client";
  const fields = isClient
    ? [
      ["Patient ID", user.id], ["Full name", user.full_name], ["Email", user.email],
      ["Date of birth", user.date_of_birth], ["Dietitian ID", user.dietitian_id],
    ]
    : [
      ["Dietitian ID", user.id], ["Full name", user.full_name], ["Email", user.email],
      ["License number", user.license_number], ["Account status", user.status],
    ];
  workspaceContent.innerHTML = `
    ${pageHeading("MY PROFILE", isClient ? "My Profile." : "Dietitian Profile.", "Account information used to coordinate your nutrition care.")}
    <section class="content-panel">
      <dl class="profile-details">${fields.map(([label, value]) => `
        <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "Not provided")}</dd></div>
      `).join("")}</dl>
    </section>`;
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
    details = renderTags(profile.conditions, "condition_name", "No medical conditions recorded.");
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

function latestClientMetric(metrics, aliases, unit = "") {
  const names = aliases.map((name) => name.toLowerCase().replace(/[^a-z0-9]/g, ""));
  const metric = [...metrics].reverse().find((entry) =>
    names.includes(String(entry.metric_type).toLowerCase().replace(/[^a-z0-9]/g, ""))
  );
  return metric ? `${metric.value}${unit}` : "Not recorded";
}

function formatSleepHours(value) {
  const totalMinutes = Math.round(Number(value) * 60);
  return Number.isFinite(totalMinutes) ? `${Math.floor(totalMinutes / 60)}h ${totalMinutes % 60}m` : "Not recorded";
}

async function renderClientProgress(clientId) {
  const [progressResult, metricsResult] = await Promise.allSettled([
    request(`/api/v1/clients/${encodeURIComponent(clientId)}/progress`),
    request(`/api/v1/clients/${encodeURIComponent(clientId)}/metrics`),
  ]);
  const progress = progressResult.status === "fulfilled" ? progressResult.value : [];
  const metrics = metricsResult.status === "fulfilled" ? metricsResult.value : [];
  const latest = progress.at(-1) || {};
  const weightHistory = progress
    .filter((entry) => Number(entry.weight_kg) > 0)
    .map((entry, index) => ({
      label: entry.log_date ? new Date(entry.log_date).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : `Log ${index + 1}`,
      value: Number(entry.weight_kg),
    }));
  const metricCards = [
    ["Weight", latest.weight_kg ? `${latest.weight_kg} kg` : latestClientMetric(metrics, ["weight", "weight_kg"], " kg")],
    ["Body Fat", latest.body_fat_pct != null ? `${latest.body_fat_pct}%` : latestClientMetric(metrics, ["body fat", "body_fat", "body_fat_pct", "body fat %"], "%")],
    ["Waist", latest.waist_cm != null ? `${latest.waist_cm} cm` : latestClientMetric(metrics, ["waist", "waist_cm", "waist circumference"], " cm")],
    ["Calories", latest.calories != null ? `${latest.calories.toLocaleString()} kcal` : latestClientMetric(metrics, ["calories", "calories consumed"], " kcal")],
    ["Water", latest.water_ml != null ? `${Number(latest.water_ml).toLocaleString()} ml` : latestClientMetric(metrics, ["water", "water intake", "water_ml"], " ml")],
    ["Steps", latest.steps != null ? Number(latest.steps).toLocaleString() : latestClientMetric(metrics, ["steps", "step count"])],
    ["Sleep", latest.sleep_hours != null ? formatSleepHours(latest.sleep_hours) : latestClientMetric(metrics, ["sleep", "sleep_hours", "sleep hours"], " h")],
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
  workspaceContent.insertAdjacentHTML("beforeend", `
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
    </section>`);
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
}

async function renderClientGoals(clientId) {
  const goals = await request(`/api/v1/goals?client_id=${encodeURIComponent(clientId)}`);
  workspaceContent.innerHTML = `
    ${pageHeading("MY GOALS", "Goals that move with you.", "Set a measurable target with your care team.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel"><form id="clientGoalForm" class="form-grid">
      <div class="form-field"><label for="goalMetric">Goal metric</label><select id="goalMetric" name="target_metric"><option>Weight</option><option>Body Fat</option><option>Waist</option><option>Calories</option><option>Water</option><option>Steps</option><option>Sleep</option></select></div>
      <div class="form-field"><label for="goalTarget">Target value</label><input class="text-input" id="goalTarget" name="target_value" type="number" step="any" required></div>
      <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Add goal</button></div>
    </form></section>
    <div class="section-heading"><h2>My goals</h2><span>${goals.length} SAVED</span></div>
    <div class="goal-list">${goals.length ? goals.map((goal) => `
      <article class="goal-row"><div><span class="subsection-label">${escapeHtml(goal.target_metric)}</span><h3>Target ${escapeHtml(goal.target_value)}</h3></div><div class="goal-current"><span>Current</span><strong>${goal.current_value == null ? "Not recorded" : escapeHtml(goal.current_value)}</strong></div></article>`).join("") : '<p class="empty-state">No goals saved yet. Add a target to start tracking it with your care team.</p>'}</div>`;
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
  const plans = await request(`/api/v1/meal-plans?client_id=${encodeURIComponent(clientId)}`);
  const meals = plans[0]?.meals || [];
  const tabs = ["today", "week", "details"];
  const activeContent = selectedTab === "today"
    ? (meals.length ? `<h2 class="compact-heading">Today's meals</h2><ul class="meal-summary">${meals.map((meal) => `<li>${escapeHtml(meal)}</li>`).join("")}</ul>` : '<p class="empty-state">No meal plan is available yet.</p>')
    : selectedTab === "week"
      ? (plans.length ? `<div class="meal-plan-list">${plans.map((plan) => `<article class="meal-plan-row"><div class="meal-plan-heading"><h3>${escapeHtml(plan.diet_type)} plan</h3><span>${plan.days} days</span></div><ul class="meal-summary">${plan.meals.map((meal) => `<li>${escapeHtml(meal)}</li>`).join("")}</ul></article>`).join("")}</div>` : '<p class="empty-state">No weekly plan is available yet.</p>')
      : (meals.length ? `<dl class="meal-details-list">${meals.map((meal, index) => `<div><dt>Meal ${index + 1}</dt><dd>${escapeHtml(meal)}</dd></div>`).join("")}</dl>` : '<p class="empty-state">Meal details will appear here when your dietitian shares a plan.</p>');
  workspaceContent.innerHTML = `
    ${pageHeading("MY MEAL PLAN", "A plan for everyday life.", "Review the meal guidance shared by your dietitian.")}
    <div class="meal-view-tabs" role="tablist" aria-label="Meal plan view">${tabs.map((tab) => `<button class="meal-view-tab${tab === selectedTab ? " is-active" : ""}" role="tab" aria-selected="${tab === selectedTab}" data-meal-tab="${tab}" type="button">${tab === "week" ? "This Week" : tab === "details" ? "Meal Details" : "Today"}</button>`).join("")}</div>
    <section class="content-panel">${activeContent}</section>`;
  workspaceContent.querySelectorAll("[data-meal-tab]").forEach((button) => {
    button.addEventListener("click", () => renderClientMealPlan(clientId, button.dataset.mealTab));
  });
}

async function renderClientAppointments(clientId, selectedTab = "upcoming", selectedDietitianId = "") {
  const [appointments, dietitians] = await Promise.all([
    request(`/api/v1/appointments?client_id=${encodeURIComponent(clientId)}`),
    request("/api/v1/dietitians"),
  ]);
  const now = Date.now();
  const isUpcoming = (appointment) => new Date(appointment.appointment_date).getTime() >= now
    && ["PENDING", "CONFIRMED", "SCHEDULED"].includes(appointment.status || "SCHEDULED");
  const upcoming = appointments.filter(isUpcoming);
  const past = appointments.filter((appointment) => !isUpcoming(appointment));
  const activeTab = ["book", "upcoming", "past"].includes(selectedTab) ? selectedTab : "upcoming";
  const preferredDietitianId = selectedDietitianId || currentUser.dietitian_id || "";
  const rows = activeTab === "upcoming" ? upcoming : past;
  const appointmentRows = rows.length ? rows.map((appointment) => `
    <article class="appointment-row">
      <div><span class="appointment-status status-${escapeHtml((appointment.status || "scheduled").toLowerCase())}">${escapeHtml(appointment.status || "SCHEDULED")}</span><h3>${escapeHtml(new Date(appointment.appointment_date).toLocaleString())}</h3></div>
      <span>${escapeHtml(dietitians.find((dietitian) => dietitian.id === appointment.dietitian_id)?.full_name || `Dietitian ${appointment.dietitian_id}`)}</span>
      ${activeTab === "upcoming" ? `<button class="button button-small button-reject" data-cancel-appointment="${escapeHtml(appointment.appointment_id)}" type="button">Cancel appointment</button>` : ""}
    </article>`).join("") : `<p class="empty-state">${activeTab === "upcoming" ? "No upcoming appointments." : "No past appointments."}</p>`;
  const minDate = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  workspaceContent.innerHTML = `
    ${pageHeading("MY APPOINTMENTS", "Time with your care team.", "Request a visit and track its status here.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="meal-view-tabs appointment-tabs" role="tablist" aria-label="Appointments">
      <button class="meal-view-tab${activeTab === "book" ? " is-active" : ""}" role="tab" aria-selected="${activeTab === "book"}" data-appointment-tab="book" type="button">Book Appointment</button>
      <button class="meal-view-tab${activeTab === "upcoming" ? " is-active" : ""}" role="tab" aria-selected="${activeTab === "upcoming"}" data-appointment-tab="upcoming" type="button">Upcoming</button>
      <button class="meal-view-tab${activeTab === "past" ? " is-active" : ""}" role="tab" aria-selected="${activeTab === "past"}" data-appointment-tab="past" type="button">Past</button>
    </div>
    ${activeTab === "book" ? `<section class="content-panel"><h2 class="compact-heading">Request an appointment</h2>${dietitians.length ? `
      <form id="appointmentForm" class="form-grid appointment-booking-form">
        <div class="form-field"><label for="appointmentDietitian">Dietitian</label><select class="text-input" id="appointmentDietitian" name="dietitian_id" required><option value="">Choose a Dietitian</option>${dietitians.map((dietitian) => `<option value="${escapeHtml(dietitian.id)}" ${dietitian.id === preferredDietitianId ? "selected" : ""}>${escapeHtml(dietitian.full_name)}${dietitian.practice_name ? ` · ${escapeHtml(dietitian.practice_name)}` : ""}</option>`).join("")}</select></div>
        <div class="form-field"><label for="appointmentDate">Preferred date and time</label><input class="text-input" id="appointmentDate" name="appointment_date" type="datetime-local" min="${minDate}" required></div>
        <div class="form-field form-actions"><button class="button button-primary" type="submit">Send request <span class="button-arrow" aria-hidden="true">&#8594;</span></button></div>
      </form>
      <p class="appointment-note">Your request stays pending until the selected Dietitian approves or rejects it.</p>` : '<p class="empty-state">No approved Dietitians are available for booking right now.</p>'}</section>` : `
      <div class="section-heading"><h2>${activeTab === "upcoming" ? "Upcoming Appointments" : "Past Appointments"}</h2><span>${rows.length} APPOINTMENTS</span></div>
      <div class="appointment-list">${appointmentRows}</div>`}`;
  workspaceContent.querySelectorAll("[data-appointment-tab]").forEach((button) => {
    button.addEventListener("click", () => renderClientAppointments(
      clientId,
      button.dataset.appointmentTab,
      document.querySelector("#appointmentDietitian")?.value || preferredDietitianId,
    ));
  });
  const form = document.querySelector("#appointmentForm");
  if (form) form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    values.client_id = clientId;
    try {
      await request("/api/v1/appointments", { method: "POST", body: JSON.stringify(values) });
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
        await request(`/api/v1/appointments/${encodeURIComponent(button.dataset.cancelAppointment)}`, {
          method: "PATCH",
          body: JSON.stringify({ action: "CANCELLED" }),
        });
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
  const appointments = await request(`/api/v1/appointments?dietitian_id=${encodeURIComponent(currentUser.id)}`);
  const pending = appointments.filter((appointment) => appointment.status === "PENDING");
  workspaceContent.innerHTML = `
    ${pageHeading("APPOINTMENT REQUESTS", "Requests awaiting your review.", "Approve a request to confirm the appointment, or reject it.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="appointment-list">${pending.length ? pending.map((appointment) => `
      <article class="appointment-request-row" data-appointment-id="${escapeHtml(appointment.appointment_id)}" data-patient-card>
        <div class="appointment-request-details"><span class="appointment-status status-pending">PENDING</span><h2>${escapeHtml(appointment.client_id)}</h2><p>${escapeHtml(new Date(appointment.appointment_date).toLocaleString())}</p></div>
        <div class="review-actions"><button class="button button-small" data-patient-context="${escapeHtml(appointment.client_id)}" aria-expanded="false" type="button">View patient info</button><button class="button button-small button-reject" data-appointment-decision="REJECTED" type="button">Reject</button><button class="button button-small button-approve" data-appointment-decision="APPROVED" type="button">Approve</button></div>
        <div data-patient-preview hidden></div>
      </article>`).join("") : '<p class="empty-state">No appointment requests need review.</p>'}</div>`;
  bindPatientContextButtons();
  workspaceContent.querySelectorAll("[data-appointment-decision]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-appointment-id]");
      card.querySelectorAll("button").forEach((item) => { item.disabled = true; });
      const action = button.dataset.appointmentDecision;
      try {
        await request(`/api/v1/appointments/${encodeURIComponent(card.dataset.appointmentId)}`, {
          method: "PATCH",
          body: JSON.stringify({ action }),
        });
        await renderAppointmentRequests();
        showWorkspaceMessage(action === "APPROVED" ? "Appointment confirmed." : "Appointment request rejected.");
      } catch (error) {
        card.querySelectorAll("button").forEach((item) => { item.disabled = false; });
        showWorkspaceMessage(error.message, true);
      }
    });
  });
}

async function renderClientRecommendations(clientId) {
  const recommendations = await request(`/api/v1/ai/recommendations?client_id=${encodeURIComponent(clientId)}`);
  workspaceContent.innerHTML = `
    ${pageHeading("AI RECOMMENDATIONS", "Guidance reviewed for you.", "Recommendations appear here after your dietitian reviews them.")}
    <div class="recommendation-list">${recommendations.length ? recommendations.map((item) => `
      <article class="review-card"><div class="review-meta"><span>${escapeHtml(item.status)}</span><span>${escapeHtml(item.recommendation_id)}</span></div><p class="stat-label">Goal: ${escapeHtml(item.dietary_goal || "Nutrition guidance")}</p><ul class="result-list">${(item.generated_plan || []).map((suggestion, index) => `<li class="result-item"><span class="result-index">0${index + 1}</span><span>${escapeHtml(suggestion)}</span></li>`).join("")}</ul>${item.review_notes ? `<p class="notice">Dietitian note: ${escapeHtml(item.review_notes)}</p>` : ""}</article>`).join("") : '<p class="empty-state">No recommendations have been shared yet. Your dietitian will review AI drafts before they appear here.</p>'}</div>`;
}

async function renderDietitians() {
  const dietitians = await request("/api/v1/dietitians");
  workspaceContent.innerHTML = `
    ${pageHeading("YOUR CARE TEAM", "Dietitians.", "Browse the dietitians listed in the practice directory.")}
    <div class="section-heading dietitian-section-heading"><h2>All dietitians</h2><span>${dietitians.length} LISTED</span></div>
    ${renderDietitianRows(dietitians)}`;
}

async function loadView(view, initialAIPanel = "coach") {
  const firstName = currentUser.full_name.split(" ")[0];
  const clientId = currentUser.type === "client" ? currentUser.id : "";
  workspaceContent.innerHTML = '<div data-message class="workspace-message" hidden></div><p class="loading-copy">Loading your workspace...</p>';
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
      const pending = await request("/api/v1/ai/recommendations/pending");
      workspaceContent.innerHTML = `
        ${pageHeading("YOUR PRACTICE", `Good to see you, ${escapeHtml(firstName)}.`, "A clear view of the care happening today.")}
        ${currentUser.type === "dietitian" ? `<p class="account-id"><span>YOUR DIETITIAN ID</span><strong>${escapeHtml(currentUser.id)}</strong><span>Share this ID with patients when they create an account.</span></p>` : ""}
        <div class="overview-grid">
          <section class="feature-panel">
            <span class="eyebrow">AI PLAN STUDIO</span>
            <h2>Build a starting point for better habits.</h2>
            <p>Draft a nutrition plan around a patient’s goals and health context. Every draft stays with you for review.</p>
            <button class="button button-lime" data-go="ai-workspace" data-ai-panel="plan" type="button">Start a plan <span aria-hidden="true">&#8594;</span></button>
          </section>
          <section class="stat-panel">
            <div><span class="stat-label">Waiting for your review</span><strong class="stat-number">${pending.length}</strong><span class="stat-caption">AI-generated drafts</span></div>
            <button class="stat-link" data-go="reviews" type="button">Open review queue <span aria-hidden="true">&#8594;</span></button>
          </section>
        </div>
        <div class="section-heading"><h2>Pick up where care happens</h2><span>YOUR WORKSPACE</span></div>
        <div class="quick-grid">
          <button class="quick-link" data-go="clients" type="button"><strong>Patient health record</strong><span aria-hidden="true">&#8599;</span></button>
          <button class="quick-link" data-go="foods" type="button"><strong>Browse food library</strong><span aria-hidden="true">&#8599;</span></button>
          <button class="quick-link" data-go="reviews" type="button"><strong>Review AI suggestions</strong><span aria-hidden="true">&#8599;</span></button>
        </div>
        <p class="notice">AI suggestions are general starting points and require review by a licensed dietitian. They are not a substitute for clinical judgment.</p>`;
      bindGoButtons();
    } else if (view === "ai-workspace" || view === "ai" || view === "ai-chat") {
      const panel = view === "ai" ? "plan" : view === "ai-chat" ? "coach" : initialAIPanel;
      await renderAIWorkspace(panel, clientId);
    } else if (view === "my-profile") {
      renderMyProfile();
    } else if (view.startsWith("health-")) {
      await renderClientHealth(clientId, view.slice("health-".length));
    } else if (view === "client-progress") {
      await renderClientProgress(clientId);
    } else if (view === "client-goals") {
      await renderClientGoals(clientId);
    } else if (view === "client-meal-plan") {
      await renderClientMealPlan(clientId);
    } else if (view === "client-appointments") {
      const selectedDietitianId = sessionStorage.getItem("patient-booking-dietitian") || currentUser.dietitian_id || "";
      sessionStorage.removeItem("patient-booking-dietitian");
      await renderClientAppointments(clientId, selectedDietitianId ? "book" : "upcoming", selectedDietitianId);
    } else if (view === "appointment-requests") {
      await renderAppointmentRequests();
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
    clients = await request(`/api/v1/clients?dietitian_id=${encodeURIComponent(currentUser.id)}`);
  } catch {
    clients = [];
  }
  const goalSuggestions = [
    "More balanced meals",
    "Increase fiber",
    "Support workout recovery",
    "Improve hydration",
    "Lower sodium",
    "Improve meal consistency",
  ];
  document.querySelector("#aiWorkspacePanel").innerHTML = `
    <section class="content-panel">
      <form id="aiForm" class="form-grid">
        <div class="form-field"><label for="aiClientId">Search patient ID or name</label><input class="text-input" id="aiClientId" name="client_id" list="aiClientOptions" placeholder="Start typing a patient ID" value="${escapeHtml(clientId)}" required><datalist id="aiClientOptions">${clients.map((client) => `<option value="${escapeHtml(client.id)}" label="${escapeHtml(client.name)}"></option>`).join("")}</datalist></div>
        <div class="form-field"><label for="dietaryGoal">Primary goal</label><input class="text-input" id="dietaryGoal" name="dietary_goal" list="aiGoalOptions" placeholder="Search or enter a primary goal" required><datalist id="aiGoalOptions">${goalSuggestions.map((goal) => `<option value="${escapeHtml(goal)}"></option>`).join("")}</datalist></div>
        <div class="form-field full-width"><span class="notice">Recorded allergies and medical conditions for this patient are sent to the model as context. Review the generated suggestions before sharing.</span></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Generate draft <span aria-hidden="true">&#8594;</span></button></div>
      </form>
      <div id="planResult" aria-live="polite"></div>
    </section>`;
  document.querySelector("#aiForm").addEventListener("submit", generatePlan);
}

async function renderDietitianDocuments() {
  const documents = await request("/api/v1/dietitians/me/documents");
  workspaceContent.innerHTML = `
    ${pageHeading("REGISTRATION", "Verification documents.", "Submit license and identity documents for admin review.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel document-upload-panel">
      <form id="verificationUploadForm" class="form-grid">
        <div class="form-field full-width"><label for="verificationFile">Choose a PDF, JPEG, or PNG document</label><input class="text-input file-input" id="verificationFile" name="file" type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" required></div>
        <div class="form-field full-width"><p class="document-hint">Maximum file size: 10 MB. Documents are stored securely and visible only to you and administrators reviewing your registration.</p></div>
        <div class="form-field full-width form-actions"><button class="button button-primary" type="submit">Submit for review <span aria-hidden="true">&#8594;</span></button></div>
      </form>
    </section>
    <div class="section-heading"><h2>Submitted documents</h2><span>${documents.length} FILES</span></div>
    <div class="document-list">${documents.length ? documents.map((document) => `
      <article class="document-row"><span class="document-icon" aria-hidden="true">&#9636;</span><div class="document-details"><h3>${escapeHtml(document.file_name)}</h3><p>${escapeHtml(document.content_type)} · ${new Date(document.uploaded_at).toLocaleDateString()}</p></div><span class="plan-status">SUBMITTED</span></article>`).join("") : '<p class="empty-state">No documents submitted. Add a license or identity document to continue approval.</p>'}</div>`;
  document.querySelector("#verificationUploadForm").addEventListener("submit", submitVerificationDocument);
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

async function generatePlan(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const values = Object.fromEntries(new FormData(form));
  button.disabled = true;
  button.firstChild.textContent = "Generating... ";
  try {
    const result = await request("/api/v1/ai/generate-plan", { method: "POST", body: JSON.stringify(values) });
    const recommendation = result.recommendation;
    document.querySelector("#planResult").innerHTML = `
      <p class="subsection-label">DRAFT FOR REVIEW</p>
      <ul class="result-list">${recommendation.generated_plan.map((item, index) => `<li class="result-item"><span class="result-index">0${index + 1}</span><span>${escapeHtml(item)}</span></li>`).join("")}</ul>
      <p class="notice">Saved as pending review. This suggestion has not been approved for a client.</p>`;
    refreshReviewCount();
  } catch (error) {
    showWorkspaceMessage(error.message, true);
  } finally {
    button.disabled = false;
    button.firstChild.textContent = "Generate draft ";
  }
}

async function renderReviews() {
  const recommendations = await request("/api/v1/ai/recommendations/pending");
  workspaceContent.innerHTML = `
    ${pageHeading("HUMAN REVIEW", "Review queue.", "Every AI suggestion waits here until a dietitian decides what happens next.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="review-list">${recommendations.length ? recommendations.map((item) => `
      <article class="review-card" data-recommendation="${escapeHtml(item.recommendation_id)}" data-patient-card>
        <div class="review-meta"><span class="review-client">Patient ${escapeHtml(item.client_id)}</span><span>${escapeHtml(item.recommendation_id)} &middot; PENDING REVIEW</span></div>
        <p class="stat-label">Goal: ${escapeHtml(item.dietary_goal)}</p>
        <ul class="result-list">${item.generated_plan.map((plan, index) => `<li class="result-item"><span class="result-index">0${index + 1}</span><span>${escapeHtml(plan)}</span></li>`).join("")}</ul>
        <label class="form-field review-notes"><span class="field-label">Review note <span class="stat-caption">(optional)</span></span><input class="text-input" name="notes" placeholder="Add context for this decision"></label>
        <div class="review-actions"><button class="button button-small" data-patient-context="${escapeHtml(item.client_id)}" aria-expanded="false" type="button">View patient info</button><button class="button button-small button-reject" data-review="REJECTED" type="button">Reject</button><button class="button button-small button-approve" data-review="APPROVED" type="button">Approve</button></div>
        <div data-patient-preview hidden></div>
      </article>`).join("") : '<div class="empty-state">Nothing waiting for review. New AI drafts will appear here.</div>'}</div>`;
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
    document.querySelector("#allergyForm").addEventListener("submit", (event) => submitClientEntry(event, clientId, "allergies"));
    document.querySelector("#conditionForm").addEventListener("submit", (event) => submitClientEntry(event, clientId, "medical-conditions"));
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
    await request(`/api/v1/clients/${encodeURIComponent(clientId)}/${kind}`, { method: "POST", body: JSON.stringify(values) });
    await loadClientProfile(clientId);
  } catch (error) {
    showWorkspaceMessage(error.message, true);
  }
}

async function renderFoods() {
  const foods = await request("/api/v1/foods");
  workspaceContent.innerHTML = `
    ${pageHeading("REFERENCE", "Food library.", "A quick reference for ingredients in the practice catalog.")}
    <div class="food-list">
      <div class="food-row food-header"><span>FOOD</span><span>CALORIES</span><span>PROTEIN</span><span>CARBS</span><span>FAT</span></div>
      ${foods.map((food) => `<div class="food-row"><span class="food-name">${escapeHtml(food.name)}</span><span>${food.calories} kcal</span><span>${food.protein_g} g</span><span>${food.carbs_g} g</span><span>${food.fat_g} g</span></div>`).join("")}
    </div>`;
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
    <div class="recipe-list">${recipes.length ? recipes.map((recipe) => `
      <article class="recipe-row">
        <div class="recipe-row-top"><h3>${escapeHtml(recipe.title)}</h3><span>${escapeHtml(recipe.recipe_id)}</span></div>
        <p class="recipe-ingredients">${recipe.ingredients.map(escapeHtml).join(" · ") || "No ingredients recorded"}</p>
        <p class="recipe-instructions">${escapeHtml(recipe.instructions)}</p>
      </article>`).join("") : '<p class="empty-state">No recipes saved yet. Add the first one above.</p>'}</div>`;
  document.querySelector("#recipeForm").addEventListener("submit", createRecipe);
}

async function createRecipe(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const values = Object.fromEntries(new FormData(form));
  values.ingredients = values.ingredients.split(/\r?\n/).map((ingredient) => ingredient.trim()).filter(Boolean);
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
  const query = currentUser.type === "client"
    ? new URLSearchParams({ client_id: currentUser.id })
    : new URLSearchParams({ dietitian_id: currentUser.id });
  const [clients, plans] = await Promise.all([
    request(`/api/v1/clients?${query}`),
    request(`/api/v1/meal-plans?${query}`),
  ]);
  const clientOptions = clients.map((client) =>
    `<option value="${escapeHtml(client.id)}">${escapeHtml(client.name)}</option>`
  ).join("");
  workspaceContent.innerHTML = `
    ${pageHeading("MEAL PLANNING", "Meal plans.", "Create a practical plan and keep it linked to a patient record.")}
    <div data-message class="workspace-message" hidden></div>
    <section class="content-panel">
      <div class="section-heading form-section-heading"><h2>Create a plan</h2><span>NEW PLAN</span></div>
      ${clients.length ? `
        <form id="mealPlanForm" class="form-grid">
          <div class="form-field"><label for="planClient">Patient</label><select id="planClient" name="client_id" required>${clientOptions}</select></div>
          <div class="form-field"><label for="planDietType">Plan focus</label><input class="text-input" id="planDietType" name="diet_type" placeholder="Balanced, vegetarian, low sodium..." maxlength="50" required></div>
          <div class="form-field"><label for="planDays">Duration</label><input class="text-input" id="planDays" name="days" type="number" min="1" max="30" value="7" required></div>
          <div class="form-field form-actions"><button class="button button-primary" type="submit">Create meal plan <span aria-hidden="true">&#8594;</span></button></div>
        </form>` : '<p class="empty-state">No linked patient records are available for meal planning.</p>'}
    </section>
    <div class="section-heading"><h2>Saved plans</h2><span>${plans.length} PLANS</span></div>
    <div class="meal-plan-list">${plans.length ? plans.map((plan) => `
      <article class="meal-plan-row">
        <div class="meal-plan-heading"><div><span class="subsection-label">${escapeHtml(plan.diet_type)}</span><h3>${plan.days}-day plan</h3></div><span class="plan-status">${escapeHtml(plan.status)}</span></div>
        <p class="meal-plan-client">Patient ${escapeHtml(plan.client_id)}</p>
        <ul class="meal-summary">${plan.meals.map((meal) => `<li>${escapeHtml(meal)}</li>`).join("")}</ul>
      </article>`).join("") : '<p class="empty-state">No meal plans yet. Create the first one above.</p>'}</div>`;
  const form = document.querySelector("#mealPlanForm");
  if (form) {
    const selectedClient = sessionStorage.getItem("meal-plan-client");
    if (selectedClient && clients.some((client) => client.id === selectedClient)) {
      form.elements.client_id.value = selectedClient;
    }
    sessionStorage.removeItem("meal-plan-client");
    form.addEventListener("submit", createMealPlan);
  }
}

async function createMealPlan(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const values = Object.fromEntries(new FormData(form));
  values.days = Number(values.days);
  button.disabled = true;
  try {
    await request("/api/v1/meal-plans", { method: "POST", body: JSON.stringify(values) });
    await renderMealPlans();
    showWorkspaceMessage("Meal plan saved.");
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
    ["Dietitians", summary.dietitians], ["Patients", summary.clients],
    ["Branches", summary.branches], ["Businesses", summary.businesses],
    ["Pending approvals", summary.pending_approvals], ["Appointments", summary.appointments],
    ["Meal plans", summary.meal_plans], ["Audit events", summary.audit_events],
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

async function renderAdminDietitians() {
  const dietitians = await request("/api/v1/admin/dietitians");
  workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Dietitians.", "Review registered practitioners and their organization assignments.")}
    ${renderAdminTable(["Name", "Email", "License", "Business", "Branch", "Status"], dietitians.map((item) => [item.full_name, item.email, item.license_number, item.business_name, item.branch_name, item.status]), "No dietitians are registered yet.")}`;
}

async function renderAdminBusinesses() {
  const businesses = await request("/api/v1/admin/businesses");
  workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Businesses.", "View registered practices and their branch and practitioner counts.")}
    ${renderAdminTable(["Business", "Registration", "Contact", "Branches", "Dietitians"], businesses.map((item) => [item.name, item.registration_number, item.contact_email, item.branch_count, item.dietitian_count]), "No businesses are registered yet.")}`;
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
    ${renderAdminTable(["Branch", "Address", "Business", "Dietitians"], branches.map((item) => [item.name, item.address, item.business_name, item.dietitian_count]), "No branches are registered yet.")}`;
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
    ${renderAdminTable(["Name", "Patient ID", "Email", "Dietitian", "Status"], clients.map((item) => [item.name, item.client_id, item.email, item.dietitian_name, item.status]), "No patient accounts are registered yet.")}`;
}

async function renderAdminReports() {
  const summary = await request("/api/v1/admin/dashboard");
  workspaceContent.innerHTML = `
    ${pageHeading("REPORTS", "System reports.", "Current organization and care activity totals.")}
    ${renderAdminTable(["Measure", "Total"], [
      ["Businesses", summary.businesses], ["Branches", summary.branches],
      ["Dietitians", summary.dietitians], ["Patients", summary.clients],
      ["Pending approvals", summary.pending_approvals], ["Appointments", summary.appointments],
      ["Meal plans", summary.meal_plans], ["Audit events", summary.audit_events],
    ], "No report data is available yet.")}`;
}

async function renderAdminAuditLogs() {
  const logs = await request("/api/v1/admin/audit-logs");
  workspaceContent.innerHTML = `
    ${pageHeading("AUDIT LOGS", "Administrative activity.", "Review approval decisions and their recorded notes.")}
    ${renderAdminTable(["Date", "Administrator", "Entity", "Entity ID", "Action", "Notes"], logs.map((item) => [item.action_date ? new Date(item.action_date).toLocaleString() : "", item.admin_name || item.admin_id, item.entity_type, item.entity_id, item.action, item.comments]), "No audit events have been recorded yet.")}`;
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
      <div><dt>AI model</dt><dd>${escapeHtml("Configured on server")}</dd></div>
      <div><dt>Administrator</dt><dd>${escapeHtml(currentUser.full_name)} · ${escapeHtml(currentUser.email)}</dd></div>
      <div><dt>Initial setup</dt><dd>${setup.available ? "Available" : "Complete"}</dd></div>
    </dl></section>`;
}

async function renderAdminApprovals() {
  const pending = await request("/api/v1/admin/approvals/pending");
  workspaceContent.innerHTML = `
    ${pageHeading("ADMINISTRATION", "Dietitian approvals.", "Review license registrations before adding dietitians to the directory.")}
    <div data-message class="workspace-message" hidden></div>
    <div class="admin-approval-list">${pending.length ? pending.map((dietitian) => `
      <article class="admin-approval-row" data-dietitian-id="${escapeHtml(dietitian.dietitian_id)}">
        <div class="admin-approval-main">
          <div class="dietitian-avatar" aria-hidden="true">${escapeHtml(dietitian.full_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase())}</div>
          <div class="dietitian-details"><h2>${escapeHtml(dietitian.full_name)}</h2><p>${escapeHtml(dietitian.email)} · License ${escapeHtml(dietitian.license_number)}</p><p>${escapeHtml(dietitian.practice_name || "Nutrition practice")}${dietitian.branch_name ? ` · ${escapeHtml(dietitian.branch_name)}` : ""}</p></div>
          <span class="dietitian-status status-pending">PENDING</span>
        </div>
        <div class="admin-document-list">${dietitian.documents.length ? dietitian.documents.map((document) => `
          <div class="admin-document-row"><span>${escapeHtml(document.file_name)} · ${escapeHtml(document.content_type)}</span><button class="button quiet-button button-small" data-document-id="${escapeHtml(document.document_id)}" data-file-name="${escapeHtml(document.file_name)}" type="button">View document</button></div>`).join("") : '<p class="document-hint">No verification documents submitted yet.</p>'}</div>
        <label class="form-field admin-approval-notes"><span class="field-label">Decision note <span class="stat-caption">(optional)</span></span><input class="text-input" name="notes" placeholder="Record verification details"></label>
        <div class="review-actions"><button class="button button-small button-reject" data-admin-decision="REJECTED" type="button">Reject</button><button class="button button-small button-approve" data-admin-decision="APPROVED" type="button" ${dietitian.documents.length ? "" : "disabled"}>Approve</button></div>
      </article>`).join("") : '<p class="empty-state">No dietitian registrations are waiting for review.</p>'}</div>`;
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
    const response = await fetch(`/api/v1/admin/dietitian-documents/${encodeURIComponent(button.dataset.documentId)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Could not open this document.");
    const documentUrl = URL.createObjectURL(await response.blob());
    const fileName = button.dataset.fileName;
    workspaceContent.insertAdjacentHTML("beforeend", `
      <dialog class="document-preview" aria-label="Verification document preview">
        <header class="document-preview-header"><strong>${escapeHtml(fileName)}</strong><button class="button quiet-button button-small" type="button">Close</button></header>
        <iframe src="${documentUrl}" title="${escapeHtml(fileName)}"></iframe>
      </dialog>`);
    const dialog = workspaceContent.querySelector(".document-preview");
    dialog.querySelector("button").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      URL.revokeObjectURL(documentUrl);
      dialog.remove();
    }, { once: true });
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
  button.disabled = true;
  try {
    await request("/api/v1/admin/approvals", {
      method: "POST",
      body: JSON.stringify({
        dietitian_id: card.dataset.dietitianId,
        status: button.dataset.adminDecision,
        notes: card.querySelector("[name=notes]").value.trim(),
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
    button.addEventListener("click", () => navTo(button.dataset.go, button.dataset.aiPanel || "coach"));
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

document.querySelector("#loginTab").addEventListener("click", () => setAuthMode("login"));
document.querySelector("#signupTab").addEventListener("click", () => setAuthMode("signup"));
document.querySelector("#adminSetupTab").addEventListener("click", () => setAuthMode("admin-setup"));
signupForm.elements.role.forEach((input) => input.addEventListener("change", updateSignupRole));
document.querySelectorAll("#signOutButton, #mobileSignOutButton").forEach((button) => {
  button.addEventListener("click", signOut);
});
document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => navTo(item.dataset.view)));

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
      sessionStorage.setItem(adminTokenKey, result.access_token);
      sessionStorage.removeItem(dietitianTokenKey);
      showWorkspace(result.user, "overview");
    } else if (result.user.type === "dietitian") {
      sessionStorage.setItem(dietitianTokenKey, result.access_token);
      sessionStorage.removeItem(adminTokenKey);
      showWorkspace(result.user);
    } else {
      sessionStorage.removeItem(adminTokenKey);
      sessionStorage.removeItem(dietitianTokenKey);
      showWorkspace(result.user);
    }
  } catch (error) {
    showAuthMessage(error.message);
  } finally {
    button.disabled = false;
  }
});

signupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = signupForm.querySelector("button[type=submit]");
  const role = selectedRole();
  if (!passwordsMatch("signupPassword", "signupConfirmPassword")) {
    showAuthMessage("Passwords do not match.");
    return;
  }
  const values = Object.fromEntries(new FormData(signupForm));
  delete values.role;
  delete values.confirm_password;
  button.disabled = true;
  try {
    const path = role === "dietitian" ? "dietitian" : "client";
    const registration = await request(`/api/v1/auth/register/${path}`, {
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
    }
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

bindPasswordConfirmation("signupPassword", "signupConfirmPassword");
bindPasswordConfirmation("adminSetupPassword", "adminSetupConfirmPassword");
document.querySelector("#signupPassword").addEventListener("input", (event) => {
  event.currentTarget.setCustomValidity(event.currentTarget.validity.tooShort ? "Use at least 8 characters." : "");
});

updateSignupRole();
updateAdminSetupTab();
try {
  const savedUser = JSON.parse(sessionStorage.getItem(sessionKey) || "null");
  const hasAdminToken = Boolean(sessionStorage.getItem(adminTokenKey));
  if (savedUser && savedUser.id && savedUser.full_name) {
    if (savedUser.type === "admin" && hasAdminToken) {
      showWorkspace(savedUser, "overview");
    } else if (savedUser.type !== "admin") {
      showWorkspace(savedUser);
    }
  }
} catch {
  sessionStorage.removeItem(sessionKey);
  sessionStorage.removeItem(adminTokenKey);
}