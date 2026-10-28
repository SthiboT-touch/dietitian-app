/* Support tickets and account recovery for the main app. */
window.mountSupport = async function (root, { request, isAdmin, escapeHtml }) {
    const esc = escapeHtml;
    root.innerHTML = `<section class="content-panel">
    <h2>${isAdmin ? "User support tickets" : "Support & tickets"}</h2>
    <p>Get help with your account or the app. Do not include passwords or medical information in a ticket.</p>
    <p data-support-message role="status" aria-live="polite"></p>
    ${
        !isAdmin
            ? `<form data-new-ticket class="form-grid">
      <label class="form-field">Subject<input class="text-input" name="subject" maxlength="160" required></label>
      <label class="form-field full-width">How can we help?<textarea class="text-input" name="body" maxlength="5000" required></textarea></label>
      <button class="button button-primary" type="submit">Submit ticket</button>
    </form>`
            : ""
    }
    <button class="button quiet-button" type="button" data-refresh-tickets>Refresh tickets</button>
    <label>Filter by status <select data-ticket-filter><option value="">All tickets</option><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option></select></label>
    <div data-ticket-list></div><div data-ticket-detail></div>
  </section>
  ${
      isAdmin
          ? `<section class="content-panel">
    <h2>Change a user's password</h2>
    <form data-account-search class="form-grid">
      <label class="form-field">Find an account by name or email<input class="text-input" name="q" minlength="2" maxlength="150" required></label>
      <button class="button" type="submit">Search accounts</button>
    </form>
    <form data-password-change class="form-grid" hidden>
      <label class="form-field full-width">Account<select class="text-input" name="account" required></select></label>
      <label class="form-field">New password<input class="text-input" name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label>
      <label class="form-field">Confirm new password<input class="text-input" name="confirmation" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label>
      <p>Changing the password signs this user out. Share the new password with them securely.</p>
      <button class="button button-primary" type="submit">Change password</button>
    </form>
    <p data-account-message role="status" aria-live="polite"></p>
  </section>`
          : ""
  }`;
    const message = (text, account = false) => {
        root.querySelector(
            account ? "[data-account-message]" : "[data-support-message]",
        ).textContent = text;
    };
    const bindForm = (form, action, account = false) => {
        if (!form) return;
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            button.disabled = true;
            message("", account);
            try {
                await action(form);
            } catch (error) {
                message(error.message, account);
            } finally {
                button.disabled = false;
            }
        });
    };
    let tickets = [];
    function showList() {
        const status = root.querySelector("[data-ticket-filter]").value;
        const rows = tickets.filter((ticket) => !status || ticket.status === status);
        root.querySelector("[data-ticket-list]").innerHTML = rows.length
            ? `<ul class="result-list">${rows.map((ticket) => `<li class="result-item"><button class="button quiet-button" data-ticket-id="${esc(ticket.ticket_id)}" type="button">${esc(ticket.subject)}</button> <strong>${esc(ticket.status.replaceAll("_", " "))}</strong> <small>${esc(new Date(ticket.updated_at).toLocaleString())}${isAdmin ? ` · ${esc(ticket.owner_role)} ${esc(ticket.owner_id)}` : ""}</small></li>`).join("")}</ul>`
            : '<p class="empty-state">No tickets found.</p>';
    }
    async function refresh() {
        tickets = await request("/api/v1/support/tickets");
        showList();
    }
    async function openTicket(id) {
        const ticket = await request(`/api/v1/support/tickets/${encodeURIComponent(id)}`);
        const detail = root.querySelector("[data-ticket-detail]");
        detail.innerHTML = `<h3>${esc(ticket.subject)}</h3>
      <p>${ticket.contact_email ? `Contact email: ${esc(ticket.contact_email)} ? ` : ""}Ticket ${esc(ticket.ticket_id)} · ${esc(ticket.status.replaceAll("_", " "))}</p>
      ${ticket.messages.map((item) => `<article class="result-item"><strong>${esc(item.author_role === "admin" ? "Administrator" : "User")}</strong> <small>${esc(new Date(item.created_at).toLocaleString())}</small><p style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(item.body)}</p></article>`).join("")}
      <form data-ticket-reply class="form-grid"><label class="form-field full-width">Reply<textarea class="text-input" name="body" maxlength="5000" required></textarea></label><button class="button button-primary" type="submit">Send reply</button></form>
      ${isAdmin ? `<form data-ticket-status class="form-grid"><label class="form-field">Ticket status<select class="text-input" name="status">${["OPEN", "IN_PROGRESS", "RESOLVED"].map((status) => `<option value="${status}" ${ticket.status === status ? "selected" : ""}>${status.replaceAll("_", " ")}</option>`).join("")}</select></label><button class="button" type="submit">Update status</button></form>` : ""}`;
        bindForm(detail.querySelector("[data-ticket-reply]"), async (form) => {
            await request(`/api/v1/support/tickets/${encodeURIComponent(id)}/messages`, {
                method: "POST",
                body: JSON.stringify({ body: form.elements.body.value }),
            });
            await refresh();
            await openTicket(id);
            message("Reply sent.");
        });
        bindForm(detail.querySelector("[data-ticket-status]"), async (form) => {
            await request(`/api/v1/admin/support/tickets/${encodeURIComponent(id)}`, {
                method: "PATCH",
                body: JSON.stringify({ status: form.elements.status.value }),
            });
            await refresh();
            await openTicket(id);
            message("Ticket status updated.");
        });
    }
    root.querySelector("[data-ticket-list]").addEventListener("click", async (event) => {
        const button = event.target.closest("[data-ticket-id]");
        if (button) {
            try {
                await openTicket(button.dataset.ticketId);
            } catch (error) {
                message(error.message);
            }
        }
    });
    root.querySelector("[data-ticket-filter]").addEventListener("change", showList);
    root.querySelector("[data-refresh-tickets]").addEventListener("click", async () => {
        try {
            await refresh();
        } catch (error) {
            message(error.message);
        }
    });
    bindForm(root.querySelector("[data-new-ticket]"), async (form) => {
        const ticket = await request("/api/v1/support/tickets", {
            method: "POST",
            body: JSON.stringify({
                subject: form.elements.subject.value,
                body: form.elements.body.value,
            }),
        });
        form.reset();
        await refresh();
        await openTicket(ticket.ticket_id);
        message("Your support ticket has been submitted.");
    });
    let accounts = [];
    const passwordForm = root.querySelector("[data-password-change]");
    bindForm(
        root.querySelector("[data-account-search]"),
        async (form) => {
            passwordForm.hidden = true;
            passwordForm.reset();
            accounts = [];
            accounts = await request(
                `/api/v1/admin/accounts?q=${encodeURIComponent(form.elements.q.value.trim())}`,
            );
            passwordForm.elements.account.innerHTML =
                '<option value="">Select an account</option>' +
                accounts
                    .map(
                        (account, index) =>
                            `<option value="${index}">${esc(account.full_name)} · ${esc(account.email)} (${esc(account.account_type)})</option>`,
                    )
                    .join("");
            passwordForm.hidden = accounts.length === 0;
            message(
                accounts.length
                    ? "Select the user whose password you want to change."
                    : "No accounts found.",
                true,
            );
        },
        true,
    );
    bindForm(
        passwordForm,
        async (form) => {
            if (form.elements.password.value !== form.elements.confirmation.value)
                throw new Error("Passwords do not match.");
            const account = accounts[Number(form.elements.account.value)];
            if (!account || form.elements.account.value === "")
                throw new Error("Select an account.");
            const result = await request(
                `/api/v1/admin/accounts/${encodeURIComponent(account.account_type)}/${encodeURIComponent(account.id)}/password`,
                {
                    method: "POST",
                    body: JSON.stringify({ password: form.elements.password.value }),
                },
            );
            form.elements.password.value = "";
            form.elements.confirmation.value = "";
            message(result.message, true);
        },
        true,
    );
    await refresh();
};

// Public login-page support deliberately sends no session token.
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-guest-support]").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            const message = form.querySelector("[data-guest-support-message]");
            button.disabled = true;
            message.textContent = "Submitting your request?";
            try {
                const response = await fetch("/api/v1/support/guest-tickets", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(Object.fromEntries(new FormData(form))),
                });
                const result = await response.json();
                if (!response.ok)
                    throw new Error(
                        typeof result.detail === "string"
                            ? result.detail
                            : "Check your email address and complete all fields.",
                    );
                form.reset();
                message.textContent = `${result.message} Reference: ${result.ticket_id}`;
            } catch (error) {
                message.textContent = error.message;
            } finally {
                button.disabled = false;
            }
        });
    });
});
