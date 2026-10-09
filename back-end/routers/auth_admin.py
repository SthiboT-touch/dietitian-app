"""1. Authentication, administration and practice setup."""
import secrets
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Request as FastAPIRequest, status, UploadFile
from fastapi.responses import Response
from datetime import date
import database
import config
from state import users_db, admins_db, businesses_db, branches_db, admin_sessions_db, dietitian_sessions_db, dietitian_documents_db, approval_log_db, appointments_db, meal_plans_db
from schemas import DietitianRegister, ClientRegister, LoginRequest, AdminSetup, AdminApproval, BranchCreate
from security import hash_password, verify_password, public_user, request_is_loopback, require_admin, require_dietitian
from helpers import email_is_registered, build_full_name


router = APIRouter()


# --- 1. AUTHENTICATION, ADMINISTRATION & PRACTICE SETUP ---



@router.post("/api/v1/auth/register/dietitian", tags=["1. Auth & Admin"])
def register_dietitian(data: DietitianRegister):
    if email_is_registered(data.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user_id = f"diet_{uuid.uuid4().hex[:8]}"
    full_name = build_full_name(data.first_name, data.last_name)
    registration = {**data.model_dump(exclude={"password"}), "full_name": full_name}
    if config.DATABASE_ENABLED:
        password_hash = hash_password(data.password)
        business_id = str(uuid.uuid4())
        branch_id = str(uuid.uuid4())
        with database.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dietitian WHERE registration_number = %s", (data.license_number,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="This license number is already registered")
            cursor.execute(
                "INSERT INTO business (business_id, name, registration_number, contact_email) "
                "VALUES (%s, %s, %s, %s)",
                (business_id, f"{full_name} Practice", f"PRACTICE-{business_id}", data.email),
            )
            cursor.execute(
                "INSERT INTO branch (branch_id, business_id, name, address) VALUES (%s, %s, %s, %s)",
                (branch_id, business_id, "Main Practice", None),
            )
            cursor.execute(
                "INSERT INTO dietitian "
                "(dietitian_id, branch_id, first_name, last_name, email, password, registration_number) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, branch_id, data.first_name.strip(), data.last_name.strip(), data.email, password_hash, data.license_number),
            )
        user = {
            "id": user_id,
            "type": "dietitian",
            "status": "PENDING",
            **registration,
            "password_hash": password_hash,
        }
        return {"message": "Dietitian registered successfully", "user": public_user(user)}
    business_id = f"business_{uuid.uuid4().hex[:8]}"
    branch_id = f"branch_{uuid.uuid4().hex[:8]}"
    businesses_db[business_id] = {
        "business_id": business_id,
        "name": f"{full_name} Practice",
        "registration_number": f"PRACTICE-{business_id}",
        "contact_email": data.email,
        "branch_count": 1,
        "dietitian_count": 1,
    }
    branches_db[branch_id] = {
        "branch_id": branch_id,
        "business_id": business_id,
        "business_name": f"{full_name} Practice",
        "name": "Main Practice",
        "address": "",
        "dietitian_count": 1,
    }
    user = {
        "id": user_id,
        "type": "dietitian",
        "status": "PENDING",
        "business_id": business_id,
        "branch_id": branch_id,
        **registration,
        "password_hash": hash_password(data.password),
    }
    users_db[user_id] = user
    return {"message": "Dietitian registered successfully", "user": public_user(user)}

@router.post("/api/v1/auth/register/client", tags=["1. Auth & Admin"])
def register_client(data: ClientRegister):
    if email_is_registered(data.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    full_name = build_full_name(data.first_name, data.last_name)
    registration = {**data.model_dump(exclude={"password"}), "full_name": full_name}
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if data.dietitian_id:
                cursor.execute("SELECT 1 FROM dietitian WHERE dietitian_id = %s", (data.dietitian_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Dietitian not found")
            user_id = f"cli_{uuid.uuid4().hex[:8]}"
            cursor.execute(
                "INSERT INTO client (client_id, dietitian_id, name, email, password, date_of_birth) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, data.dietitian_id, full_name, data.email, hash_password(data.password), data.date_of_birth),
            )
        user = {"id": user_id, "type": "client", **registration}
        return {"message": "Patient registered successfully", "user": user}
    dietitian = users_db.get(data.dietitian_id) if data.dietitian_id else None
    if data.dietitian_id and (not dietitian or dietitian.get("type") != "dietitian"):
        raise HTTPException(status_code=404, detail="Dietitian not found")
    user_id = f"cli_{uuid.uuid4().hex[:8]}"
    user = {
        "id": user_id,
        "type": "client",
        **registration,
        "password_hash": hash_password(data.password),
    }
    users_db[user_id] = user
    return {"message": "Patient registered successfully", "user": public_user(user)}


def admin_setup_available() -> bool:
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM admin)")
            return not cursor.fetchone()["exists"]
    return not admins_db


@router.get("/api/v1/admin/setup-status", tags=["1. Auth & Admin"])
def get_admin_setup_status(request: FastAPIRequest):
    return {"available": request_is_loopback(request) and admin_setup_available()}


@router.post("/api/v1/admin/setup", status_code=status.HTTP_201_CREATED, tags=["1. Auth & Admin"])
def setup_first_admin(data: AdminSetup, request: FastAPIRequest):
    if not request_is_loopback(request):
        raise HTTPException(status_code=403, detail="Admin setup is available only from this computer")
    admin_id = str(uuid.uuid4())
    full_name = build_full_name(data.first_name, data.last_name)
    password_hash = hash_password(data.password)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (731904281,))
            cursor.execute("SELECT EXISTS (SELECT 1 FROM admin)")
            if cursor.fetchone()["exists"]:
                raise HTTPException(status_code=409, detail="Admin setup has already been completed")
            cursor.execute(
                "INSERT INTO admin (admin_id, first_name, last_name, email, password) "
                "VALUES (%s, %s, %s, %s, %s)",
                (admin_id, data.first_name.strip(), data.last_name.strip(), data.email, password_hash),
            )
    else:
        if admins_db:
            raise HTTPException(status_code=409, detail="Admin setup has already been completed")
        admins_db[admin_id] = {
            "id": admin_id,
            "type": "admin",
            "full_name": full_name,
            "email": data.email,
            "password_hash": password_hash,
        }
    return {
        "message": "Administrator account created",
        "user": {"id": admin_id, "type": "admin", "full_name": full_name, "email": data.email},
    }

@router.post("/api/v1/auth/login", tags=["1. Auth & Admin"])
def login(data: LoginRequest):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT dietitian_id AS id, 'dietitian' AS type, "
                "TRIM(first_name || ' ' || last_name) AS full_name, email, "
                "registration_number AS license_number, status, password AS password_hash "
                "FROM dietitian WHERE LOWER(email) = LOWER(%s)",
                (data.email,),
            )
            user = cursor.fetchone()
            if not user:
                cursor.execute(
                    "SELECT client_id AS id, 'client' AS type, name AS full_name, email, "
                    "dietitian_id, date_of_birth, password AS password_hash "
                    "FROM client WHERE LOWER(email) = LOWER(%s)",
                    (data.email,),
                )
                user = cursor.fetchone()
            if not user:
                cursor.execute(
                    "SELECT admin_id AS id, 'admin' AS type, "
                    "TRIM(first_name || ' ' || last_name) AS full_name, email, password AS password_hash "
                    "FROM admin WHERE LOWER(email) = LOWER(%s)",
                    (data.email,),
                )
                user = cursor.fetchone()
    else:
        user = next((user for user in users_db.values() if user["email"].casefold() == data.email.casefold()), None)
        if not user:
            user = next((user for user in admins_db.values() if user["email"].casefold() == data.email.casefold()), None)
    if not user or not verify_password(data.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access_token = f"mock_jwt_token_{uuid.uuid4().hex[:12]}"
    if user["type"] == "admin":
        access_token = secrets.token_urlsafe(32)
        admin_sessions_db[access_token] = user["id"]
    elif user["type"] == "dietitian":
        access_token = secrets.token_urlsafe(32)
        dietitian_sessions_db[access_token] = user["id"]
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": public_user(user),
    }


@router.get("/api/v1/dietitians", tags=["1. Auth & Admin"])
def get_dietitians():
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT d.dietitian_id AS id, TRIM(d.first_name || ' ' || d.last_name) AS full_name, "
                "d.registration_number AS license_number, d.specialisation, d.status, "
                "b.name AS branch_name, bus.name AS practice_name "
                "FROM dietitian d JOIN branch b ON b.branch_id = d.branch_id "
                "JOIN business bus ON bus.business_id = b.business_id "
                "WHERE d.status = 'APPROVED' "
                "ORDER BY LOWER(d.last_name), LOWER(d.first_name)"
            )
            return [dict(row) for row in cursor.fetchall()]
    dietitians = [
        {
            "id": user["id"],
            "full_name": user["full_name"],
            "license_number": user["license_number"],
            "specialisation": user.get("specialisation"),
            "status": user.get("status", "APPROVED"),
            "branch_name": None,
            "practice_name": None,
        }
        for user in users_db.values()
        if user.get("type") == "dietitian" and user.get("status") == "APPROVED"
    ]
    return sorted(dietitians, key=lambda user: user["full_name"].casefold())


@router.get("/api/v1/dietitians/me/approval", tags=["1. Auth & Admin"])
def get_my_dietitian_approval(dietitian_id: str = Depends(require_dietitian)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT d.status, ("
                "SELECT al.comments FROM approval_log al "
                "WHERE al.entity_type = 'DIETITIAN' AND al.entity_id = d.dietitian_id "
                "AND al.action = 'REJECTED' ORDER BY al.action_date DESC LIMIT 1"
                ") AS rejection_reason FROM dietitian d WHERE d.dietitian_id = %s",
                (dietitian_id,),
            )
            approval = cursor.fetchone()
        if not approval:
            raise HTTPException(status_code=404, detail="Dietitian not found")
        return dict(approval)

    user = users_db.get(dietitian_id)
    if not user or user.get("type") != "dietitian":
        raise HTTPException(status_code=404, detail="Dietitian not found")
    latest_rejection = next(
        (
            entry for entry in reversed(approval_log_db)
            if entry.get("entity_type") == "DIETITIAN"
            and entry.get("entity_id") == dietitian_id
            and entry.get("action") == "REJECTED"
        ),
        None,
    )
    return {
        "status": user.get("status", "PENDING"),
        "rejection_reason": latest_rejection.get("comments") if latest_rejection else None,
    }


@router.post("/api/v1/dietitians/me/approval/resubmit", tags=["1. Auth & Admin"])
def resubmit_dietitian_approval(dietitian_id: str = Depends(require_dietitian)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "UPDATE dietitian SET status = 'PENDING' "
                "WHERE dietitian_id = %s AND status = 'REJECTED' "
                "RETURNING dietitian_id",
                (dietitian_id,),
            )
            if cursor.fetchone():
                return {"message": "Registration resubmitted for admin review", "status": "PENDING"}
            cursor.execute("SELECT status FROM dietitian WHERE dietitian_id = %s", (dietitian_id,))
            dietitian = cursor.fetchone()
            if not dietitian:
                raise HTTPException(status_code=404, detail="Dietitian not found")
            raise HTTPException(status_code=409, detail="Only rejected registrations can be resubmitted")

    user = users_db.get(dietitian_id)
    if not user or user.get("type") != "dietitian":
        raise HTTPException(status_code=404, detail="Dietitian not found")
    if user.get("status") != "REJECTED":
        raise HTTPException(status_code=409, detail="Only rejected registrations can be resubmitted")
    user["status"] = "PENDING"
    return {"message": "Registration resubmitted for admin review", "status": "PENDING"}


@router.get("/api/v1/dietitians/me/documents", tags=["1. Auth & Admin"])
def list_my_dietitian_documents(dietitian_id: str = Depends(require_dietitian)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT document_id, file_name, content_type, uploaded_at FROM dietitian_document "
                "WHERE dietitian_id = %s ORDER BY uploaded_at DESC",
                (dietitian_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
    return sorted(
        [
            {key: value for key, value in document.items() if key != "file_data"}
            for document in dietitian_documents_db.values()
            if document["dietitian_id"] == dietitian_id
        ],
        key=lambda document: document["uploaded_at"],
        reverse=True,
    )


@router.post("/api/v1/dietitians/me/documents", status_code=status.HTTP_201_CREATED, tags=["1. Auth & Admin"])
async def submit_dietitian_document(
    file: UploadFile = File(...),
    dietitian_id: str = Depends(require_dietitian),
):
    file_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not file_name or len(file_name) > 255:
        raise HTTPException(status_code=400, detail="Choose a file with a valid name")
    contents = await file.read(config.MAX_DIETITIAN_DOCUMENT_BYTES + 1)
    if len(contents) > config.MAX_DIETITIAN_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Documents must be 10 MB or smaller")
    if contents.startswith(b"%PDF-"):
        content_type = "application/pdf"
    elif contents.startswith(b"\xff\xd8\xff"):
        content_type = "image/jpeg"
    elif contents.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type = "image/png"
    else:
        raise HTTPException(status_code=415, detail="Upload a valid PDF, JPEG, or PNG document")

    document_id = str(uuid.uuid4())
    uploaded_at = None
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dietitian_document (document_id, dietitian_id, file_name, content_type, file_data) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING uploaded_at",
                (document_id, dietitian_id, file_name, content_type, contents),
            )
            uploaded_at = cursor.fetchone()["uploaded_at"]
    else:
        uploaded_at = date.today().isoformat()
        dietitian_documents_db[document_id] = {
            "document_id": document_id,
            "dietitian_id": dietitian_id,
            "file_name": file_name,
            "content_type": content_type,
            "file_data": contents,
            "uploaded_at": uploaded_at,
        }
    return {
        "document_id": document_id,
        "file_name": file_name,
        "content_type": content_type,
        "uploaded_at": uploaded_at,
    }


@router.get("/api/v1/admin/dietitian-documents/{document_id}", tags=["1. Auth & Admin"])
def download_dietitian_document(document_id: str, admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT content_type, file_data FROM dietitian_document WHERE document_id = %s",
                (document_id,),
            )
            document = cursor.fetchone()
    else:
        document = dietitian_documents_db.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=bytes(document["file_data"]),
        media_type=document["content_type"],
        headers={"Content-Disposition": "inline; filename=verification-document"},
    )


@router.get("/api/v1/admin/approvals/pending", tags=["1. Auth & Admin"])
def get_pending_dietitian_approvals(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT d.dietitian_id AS dietitian_id, d.first_name, d.last_name, d.email, "
                "d.registration_number AS license_number, d.status, b.name AS branch_name, "
                "bus.name AS practice_name FROM dietitian d "
                "JOIN branch b ON b.branch_id = d.branch_id "
                "JOIN business bus ON bus.business_id = b.business_id "
                "WHERE d.status = 'PENDING' ORDER BY LOWER(d.last_name), LOWER(d.first_name)"
            )
            dietitians = cursor.fetchall()
            pending = []
            for row in dietitians:
                cursor.execute(
                    "SELECT document_id, file_name, content_type, uploaded_at FROM dietitian_document "
                    "WHERE dietitian_id = %s ORDER BY uploaded_at DESC",
                    (row["dietitian_id"],),
                )
                pending.append({
                    **dict(row),
                    "full_name": f"{row['first_name']} {row['last_name']}".strip(),
                    "documents": [dict(document) for document in cursor.fetchall()],
                })
            return pending
    return [
        {
            "dietitian_id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "license_number": user["license_number"],
            "status": user["status"],
            "documents": [
                {key: value for key, value in document.items() if key != "file_data"}
                for document in dietitian_documents_db.values()
                if document["dietitian_id"] == user["id"]
            ],
        }
        for user in users_db.values()
        if user.get("type") == "dietitian" and user.get("status") == "PENDING"
    ]


@router.post("/api/v1/admin/approvals", tags=["1. Auth & Admin"])
def review_dietitian(data: AdminApproval, admin_id: str = Depends(require_admin)):
    notes = data.notes.strip() if data.notes else ""
    if data.status == "REJECTED" and not notes:
        raise HTTPException(status_code=422, detail="A reason is required when rejecting a dietitian")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if data.status == "APPROVED":
                cursor.execute(
                    "SELECT COUNT(*) AS document_count FROM dietitian_document WHERE dietitian_id = %s",
                    (data.dietitian_id,),
                )
                if cursor.fetchone()["document_count"] == 0:
                    raise HTTPException(status_code=409, detail="A verification document is required before approval")
            cursor.execute(
                "UPDATE dietitian SET status = %s WHERE dietitian_id = %s RETURNING dietitian_id",
                (data.status, data.dietitian_id),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Dietitian not found")
            cursor.execute(
                "INSERT INTO approval_log (admin_id, entity_type, entity_id, action, comments) "
                "VALUES (%s, 'DIETITIAN', %s, %s, %s)",
                (admin_id, data.dietitian_id, data.status, notes or None),
            )
        return {"message": f"Dietitian status updated to {data.status}"}
    if data.dietitian_id not in users_db:
        raise HTTPException(status_code=404, detail="Dietitian not found")
    if data.status == "APPROVED" and not any(
        document["dietitian_id"] == data.dietitian_id for document in dietitian_documents_db.values()
    ):
        raise HTTPException(status_code=409, detail="A verification document is required before approval")
    users_db[data.dietitian_id]["status"] = data.status
    approval_log_db.append({
        "admin_id": admin_id,
        "entity_type": "DIETITIAN",
        "entity_id": data.dietitian_id,
        "action": data.status,
        "comments": notes or None,
    })
    return {"message": f"Dietitian status updated to {data.status}"}

@router.post("/api/v1/branches", tags=["1. Auth & Admin"])
def create_branch(data: BranchCreate, admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        branch_id = str(uuid.uuid4())
        with database.cursor() as cursor:
            business_id = data.business_id
            if business_id:
                cursor.execute("SELECT business_id FROM business WHERE business_id = %s", (business_id,))
            else:
                cursor.execute("SELECT business_id FROM business ORDER BY name LIMIT 1")
            business = cursor.fetchone()
            if not business:
                if data.business_id:
                    raise HTTPException(status_code=404, detail="Business not found")
                business_id = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO business (business_id, name, registration_number) VALUES (%s, %s, %s)",
                    (business_id, "General Practice", f"PRACTICE-{business_id}"),
                )
            else:
                business_id = business["business_id"]
            cursor.execute(
                "INSERT INTO branch (branch_id, business_id, name, address) VALUES (%s, %s, %s, %s)",
                (branch_id, business_id, data.name, data.address),
            )
        return {
            "message": "Branch created successfully",
            "branch": {"branch_id": branch_id, "business_id": business_id, "name": data.name, "address": data.address},
        }
    business_id = data.business_id
    if business_id and business_id not in businesses_db:
        raise HTTPException(status_code=404, detail="Business not found")
    if not business_id:
        business_id = next(iter(businesses_db), None)
    if not business_id:
        business_id = f"business_{uuid.uuid4().hex[:8]}"
        businesses_db[business_id] = {
            "business_id": business_id,
            "name": "General Practice",
            "registration_number": f"PRACTICE-{business_id}",
            "contact_email": None,
            "branch_count": 0,
            "dietitian_count": 0,
        }
    business = businesses_db[business_id]
    branch_id = f"branch_{uuid.uuid4().hex[:8]}"
    branch = {
        "branch_id": branch_id,
        "business_id": business_id,
        "business_name": business["name"],
        "name": data.name,
        "address": data.address,
        "dietitian_count": 0,
    }
    branches_db[branch_id] = branch
    business["branch_count"] += 1
    return {"message": "Branch created successfully", "branch": branch}


@router.get("/api/v1/admin/dashboard", tags=["1. Auth & Admin"])
def get_admin_dashboard(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        counts = {}
        with database.cursor() as cursor:
            for label, table in [
                ("businesses", "business"),
                ("branches", "branch"),
                ("dietitians", "dietitian"),
                ("clients", "client"),
                ("appointments", "appointment"),
                ("meal_plans", "meal_plan"),
            ]:
                cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
                counts[label] = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) AS total FROM dietitian WHERE status = 'PENDING'")
            counts["pending_approvals"] = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) AS total FROM approval_log")
            counts["audit_events"] = cursor.fetchone()["total"]
        return counts
    dietitians = [user for user in users_db.values() if user.get("type") == "dietitian"]
    return {
        "businesses": len(businesses_db),
        "branches": len(branches_db),
        "dietitians": len(dietitians),
        "clients": sum(user.get("type") == "client" for user in users_db.values()),
        "appointments": len(appointments_db),
        "meal_plans": len(meal_plans_db),
        "pending_approvals": sum(user.get("type") == "dietitian" and user.get("status") == "PENDING" for user in users_db.values()),
        "audit_events": len(approval_log_db),
    }


@router.get("/api/v1/admin/dietitians", tags=["1. Auth & Admin"])
def list_admin_dietitians(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT d.dietitian_id, TRIM(d.first_name || ' ' || d.last_name) AS full_name, "
                "d.email, d.registration_number AS license_number, d.status, b.name AS branch_name, "
                "bus.name AS business_name FROM dietitian d "
                "JOIN branch b ON b.branch_id = d.branch_id "
                "JOIN business bus ON bus.business_id = b.business_id "
                "ORDER BY LOWER(d.last_name), LOWER(d.first_name)"
            )
            return [dict(row) for row in cursor.fetchall()]
    rows = []
    for user in users_db.values():
        if user.get("type") != "dietitian":
            continue
        branch = branches_db.get(user.get("branch_id"), {})
        rows.append({
            "dietitian_id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "license_number": user.get("license_number", ""),
            "status": user.get("status", "PENDING"),
            "branch_name": branch.get("name", "Main Practice"),
            "business_name": branch.get("business_name", f"{user['full_name']} Practice"),
        })
    return sorted(rows, key=lambda item: item["full_name"].casefold())


@router.get("/api/v1/admin/businesses", tags=["1. Auth & Admin"])
def list_admin_businesses(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT b.business_id, b.name, b.registration_number, b.contact_email, "
                "COUNT(DISTINCT br.branch_id) AS branch_count, COUNT(DISTINCT d.dietitian_id) AS dietitian_count "
                "FROM business b LEFT JOIN branch br ON br.business_id = b.business_id "
                "LEFT JOIN dietitian d ON d.branch_id = br.branch_id "
                "GROUP BY b.business_id ORDER BY LOWER(b.name)"
            )
            return [dict(row) for row in cursor.fetchall()]
    return sorted(businesses_db.values(), key=lambda item: item["name"].casefold())


@router.get("/api/v1/admin/branches", tags=["1. Auth & Admin"])
def list_admin_branches(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT br.branch_id, br.name, br.address, b.business_id, b.name AS business_name, "
                "COUNT(d.dietitian_id) AS dietitian_count FROM branch br "
                "JOIN business b ON b.business_id = br.business_id "
                "LEFT JOIN dietitian d ON d.branch_id = br.branch_id "
                "GROUP BY br.branch_id, b.business_id ORDER BY LOWER(b.name), LOWER(br.name)"
            )
            return [dict(row) for row in cursor.fetchall()]
    return sorted(branches_db.values(), key=lambda item: (item["business_name"].casefold(), item["name"].casefold()))


@router.get("/api/v1/admin/clients", tags=["1. Auth & Admin"])
def list_admin_clients(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT c.client_id, c.name, c.email, c.status, c.date_of_birth, "
                "TRIM(d.first_name || ' ' || d.last_name) AS dietitian_name "
                "FROM client c LEFT JOIN dietitian d ON d.dietitian_id = c.dietitian_id "
                "ORDER BY LOWER(c.name)"
            )
            return [
                {**dict(row), "date_of_birth": row["date_of_birth"].isoformat() if row["date_of_birth"] else None}
                for row in cursor.fetchall()
            ]
    return [
        {
            "client_id": user["id"],
            "name": user["full_name"],
            "email": user["email"],
            "status": "ACTIVE",
            "date_of_birth": user.get("date_of_birth").isoformat() if user.get("date_of_birth") else None,
            "dietitian_name": users_db.get(user.get("dietitian_id"), {}).get("full_name"),
        }
        for user in sorted(users_db.values(), key=lambda item: item.get("full_name", "").casefold())
        if user.get("type") == "client"
    ]


@router.get("/api/v1/admin/audit-logs", tags=["1. Auth & Admin"])
def list_admin_audit_logs(admin_id: str = Depends(require_admin)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT al.approval_log_id AS log_id, al.admin_id, "
                "TRIM(a.first_name || ' ' || a.last_name) AS admin_name, al.entity_type, "
                "al.entity_id, al.action, al.comments, al.action_date "
                "FROM approval_log al JOIN admin a ON a.admin_id = al.admin_id "
                "ORDER BY al.action_date DESC LIMIT 500"
            )
            return [
                {**dict(row), "action_date": row["action_date"].isoformat()}
                for row in cursor.fetchall()
            ]
    return [
        {"log_id": f"audit-{index + 1}", **entry, "action_date": entry.get("action_date", "")}
        for index, entry in enumerate(reversed(approval_log_db))
    ]
