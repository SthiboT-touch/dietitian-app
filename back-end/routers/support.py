"""Authenticated support conversations and administrator account recovery."""

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

import config
import database
import state
from security import current_identity, hash_password
from registration_validation import validate_email

router = APIRouter(tags=["Support & Account Recovery"])


def identity(authorization: Optional[str] = Header(default=None)):
    role, account_id = current_identity(authorization)
    # Legacy organization accounts also use the admin session store. Resolve
    # their actual role before granting support administration privileges.
    if role == "admin":
        if config.DATABASE_ENABLED:
            with database.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(role, 'admin') AS role FROM admin WHERE admin_id = %s",
                    (account_id,),
                )
                account = cursor.fetchone()
        else:
            account = state.admins_db.get(account_id)
        if not account:
            raise HTTPException(401, "Sign-in required")
        role = account.get("role") or account.get("type") or "admin"
    return role, account_id


def administrator(actor=Depends(identity)):
    if actor[0] != "admin":
        raise HTTPException(403, "Administrator access required")
    return actor


class Message(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Message is required")
        return value.strip()


class TicketCreate(Message):
    subject: str = Field(min_length=1, max_length=160)

    @field_validator("subject")
    @classmethod
    def subject_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Subject is required")
        return value.strip()


class TicketStatus(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]


class GuestTicket(TicketCreate):
    contact_email: str = Field(min_length=3, max_length=150)

    @field_validator("contact_email")
    @classmethod
    def email_format(cls, value):
        return validate_email(value)


class PasswordChange(BaseModel):
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def password_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Password cannot contain only spaces")
        return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ticket(ticket_id, actor, cursor=None):
    if cursor:
        cursor.execute("SELECT * FROM support_ticket WHERE ticket_id = %s FOR UPDATE", (ticket_id,))
        row = cursor.fetchone()
    else:
        row = state.support_tickets_db.get(ticket_id)
    if not row or (actor[0] != "admin" and (row["owner_role"], row["owner_id"]) != actor):
        raise HTTPException(404, "Ticket not found")
    return dict(row)


@router.get("/api/v1/support/tickets")
def list_tickets(actor=Depends(identity)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if actor[0] == "admin":
                cursor.execute("SELECT * FROM support_ticket ORDER BY updated_at DESC LIMIT 200")
            else:
                cursor.execute(
                    "SELECT * FROM support_ticket WHERE owner_role = %s AND owner_id = %s ORDER BY updated_at DESC LIMIT 200",
                    actor,
                )
            return [dict(row) for row in cursor.fetchall()]
    return sorted(
        (
            dict(t)
            for t in state.support_tickets_db.values()
            if actor[0] == "admin" or (t["owner_role"], t["owner_id"]) == actor
        ),
        key=lambda t: t["updated_at"],
        reverse=True,
    )[:200]


@router.post("/api/v1/support/tickets", status_code=201)
def create_ticket(data: TicketCreate, actor=Depends(identity)):
    ticket = dict(
        ticket_id=str(uuid4()),
        owner_role=actor[0],
        owner_id=actor[1],
        subject=data.subject,
        status="OPEN",
        created_at=_now(),
        updated_at=_now(),
    )
    message = dict(
        message_id=str(uuid4()),
        ticket_id=ticket["ticket_id"],
        author_role=actor[0],
        author_id=actor[1],
        body=data.body,
        created_at=ticket["created_at"],
    )
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO support_ticket (ticket_id, owner_role, owner_id, subject, status, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                tuple(ticket.values()),
            )
            _insert_message(cursor, message)
    else:
        state.support_tickets_db[ticket["ticket_id"]] = ticket
        state.support_messages_db[message["message_id"]] = message
    return ticket


def _insert_message(cursor, message):
    cursor.execute(
        "INSERT INTO support_message (message_id, ticket_id, author_role, author_id, body, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        tuple(message.values()),
    )


@router.post("/api/v1/support/guest-tickets", status_code=201)
def guest_ticket(data: GuestTicket):
    # Guest requests never attach to an account based on an unverified email.
    ticket = dict(
        ticket_id=str(uuid4()),
        owner_role="guest",
        owner_id=str(uuid4()),
        subject=data.subject,
        status="OPEN",
        created_at=_now(),
        updated_at=_now(),
        contact_email=data.contact_email,
    )
    message = dict(
        message_id=str(uuid4()),
        ticket_id=ticket["ticket_id"],
        author_role="guest",
        author_id=ticket["owner_id"],
        body=data.body,
        created_at=ticket["created_at"],
    )
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            # Serialize limits for the same contact address across API workers.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (data.contact_email,))
            rate_limit_window = (
                "datetime(created_at) > datetime('now', '-1 hour')"
                if database.is_sqlite()
                else "created_at > NOW() - INTERVAL '1 hour'"
            )
            cursor.execute(
                "SELECT COUNT(*) AS total FROM support_ticket "
                f"WHERE contact_email = %s AND {rate_limit_window}",
                (data.contact_email,),
            )
            if cursor.fetchone()["total"] >= 5:
                raise HTTPException(429, "Too many requests. Please try again in an hour.")
            cursor.execute(
                "INSERT INTO support_ticket (ticket_id, owner_role, owner_id, subject, status, created_at, updated_at, contact_email) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(ticket.values()),
            )
            _insert_message(cursor, message)
    else:
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        recent = sum(
            1
            for t in state.support_tickets_db.values()
            if t.get("contact_email") == data.contact_email
            and datetime.fromisoformat(t["created_at"]).timestamp() > cutoff
        )
        if recent >= 5:
            raise HTTPException(429, "Too many requests. Please try again in an hour.")
        state.support_tickets_db[ticket["ticket_id"]] = ticket
        state.support_messages_db[message["message_id"]] = message
    return {
        "ticket_id": ticket["ticket_id"],
        "message": "Your support request has been submitted. Keep your ticket reference.",
    }


@router.get("/api/v1/support/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, actor=Depends(identity)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            ticket = _ticket(ticket_id, actor, cursor)
            cursor.execute(
                "SELECT * FROM support_message WHERE ticket_id = %s ORDER BY created_at, message_id",
                (ticket_id,),
            )
            messages = [dict(row) for row in cursor.fetchall()]
    else:
        ticket = _ticket(ticket_id, actor)
        messages = sorted(
            (dict(m) for m in state.support_messages_db.values() if m["ticket_id"] == ticket_id),
            key=lambda m: m["created_at"],
        )
    return {**ticket, "messages": messages}


@router.post("/api/v1/support/tickets/{ticket_id}/messages", status_code=201)
def reply(ticket_id: str, data: Message, actor=Depends(identity)):
    message = dict(
        message_id=str(uuid4()),
        ticket_id=ticket_id,
        author_role=actor[0],
        author_id=actor[1],
        body=data.body,
        created_at=_now(),
    )
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            _ticket(ticket_id, actor, cursor)
            _insert_message(cursor, message)
            cursor.execute(
                "UPDATE support_ticket SET updated_at = %s, status = CASE WHEN status = 'RESOLVED' THEN 'OPEN' ELSE status END WHERE ticket_id = %s",
                (message["created_at"], ticket_id),
            )
    else:
        _ticket(ticket_id, actor)
        state.support_messages_db[message["message_id"]] = message
        ticket = state.support_tickets_db[ticket_id]
        ticket["updated_at"] = message["created_at"]
        if ticket["status"] == "RESOLVED":
            ticket["status"] = "OPEN"
    return message


@router.patch("/api/v1/admin/support/tickets/{ticket_id}")
def update_status(ticket_id: str, data: TicketStatus, actor=Depends(administrator)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            _ticket(ticket_id, actor, cursor)
            cursor.execute(
                "UPDATE support_ticket SET status = %s, updated_at = %s WHERE ticket_id = %s",
                (data.status, _now(), ticket_id),
            )
    else:
        _ticket(ticket_id, actor)
        state.support_tickets_db[ticket_id].update(status=data.status, updated_at=_now())
    return {"message": "Ticket status updated", "status": data.status}


# Table and column names are fixed here, never interpolated from user input.
ACCOUNT_TABLES = {
    "client": ("client", "client_id", "password", "name"),
    "dietitian": ("dietitian", "dietitian_id", "password", "TRIM(first_name || ' ' || last_name)"),
    "admin": ("admin", "admin_id", "password", "TRIM(first_name || ' ' || last_name)"),
    "staff": ("staff_account", "staff_id", "password_hash", "full_name"),
}


def _accounts():
    for kind, store in (
        ("client", state.users_db),
        ("dietitian", state.users_db),
        ("admin", state.admins_db),
        ("staff", state.staff_accounts_db),
    ):
        for account_id, account in store.items():
            if kind in {"client", "dietitian"} and account.get("type") != kind:
                continue
            yield kind, account_id, account


@router.get("/api/v1/admin/accounts")
def find_accounts(q: str = Query(min_length=2, max_length=150), actor=Depends(administrator)):
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(422, "Enter at least two characters")
    if config.DATABASE_ENABLED:
        result = []
        with database.cursor() as cursor:
            for kind, (table, key, _, name) in ACCOUNT_TABLES.items():
                if kind == "staff":
                    if not database.table_exists(cursor, "staff_account"):
                        continue
                cursor.execute(
                    f"SELECT {key} AS id, {name} AS full_name, email FROM {table} "
                    f"WHERE INSTR(LOWER(email), LOWER(%s)) > 0 "
                    f"OR INSTR(LOWER({name}), LOWER(%s)) > 0 ORDER BY email LIMIT 50",
                    (q.strip(), q.strip()),
                )
                result.extend({**dict(row), "account_type": kind} for row in cursor.fetchall())
        return result
    query = q.strip().casefold()
    return [
        {
            "id": key,
            "account_type": kind,
            "full_name": a.get("full_name", a.get("name", "")),
            "email": a.get("email", ""),
        }
        for kind, key, a in _accounts()
        if query in a.get("email", "").casefold()
        or query in a.get("full_name", a.get("name", "")).casefold()
    ][:200]


@router.post("/api/v1/admin/accounts/{account_type}/{account_id}/password")
def change_password(
    account_type: Literal["client", "dietitian", "admin", "staff"],
    account_id: str,
    data: PasswordChange,
    actor=Depends(administrator),
):
    password_hash = hash_password(data.password)
    if config.DATABASE_ENABLED:
        table, key, column, _ = ACCOUNT_TABLES[account_type]
        with database.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {column} = %s WHERE {key} = %s RETURNING {key}",
                (password_hash, account_id),
            )
            if not cursor.fetchone():
                raise HTTPException(404, "Account not found")
    else:
        account = next(
            (a for kind, key, a in _accounts() if kind == account_type and key == account_id), None
        )
        if account is None:
            raise HTTPException(404, "Account not found")
        account["password_hash"] = password_hash
    sessions = {
        "client": state.client_sessions_db,
        "dietitian": state.dietitian_sessions_db,
        "admin": state.admin_sessions_db,
        "staff": state.staff_sessions_db,
    }[account_type]
    for token, owner in list(sessions.items()):
        if owner == account_id:
            sessions.pop(token, None)
    return {"message": "Password changed. Existing sessions have been signed out."}
