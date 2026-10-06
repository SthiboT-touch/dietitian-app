from pathlib import Path
import secrets
import sys
import uuid


BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import app
import database


DEFAULT_ADMIN_EMAILS = [
    ("admin1@nutritionpractice.local", "Admin", "One"),
    ("admin2@nutritionpractice.local", "Admin", "Two"),
    ("admin3@nutritionpractice.local", "Admin", "Three"),
]


def main():
    if not app.DATABASE_ENABLED:
        raise SystemExit("Configure DATABASE_URL before creating persistent administrator accounts.")

    created = []
    with database.cursor() as cursor:
        cursor.execute("SELECT email FROM admin")
        existing_emails = {row["email"].casefold() for row in cursor.fetchall()}
        for email, first_name, last_name in DEFAULT_ADMIN_EMAILS:
            if email.casefold() in existing_emails:
                continue
            password = secrets.token_urlsafe(18)
            cursor.execute(
                "INSERT INTO admin (admin_id, first_name, last_name, email, password) "
                "VALUES (%s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), first_name, last_name, email, app.hash_password(password)),
            )
            created.append((email, password))
            existing_emails.add(email.casefold())

    if created:
        print("Save these temporary administrator credentials now; passwords are shown only once:")
        for email, password in created:
            print(f"{email}\t{password}")
    else:
        print("All three seeded administrator accounts already exist; no accounts were changed.")


if __name__ == "__main__":
    main()
