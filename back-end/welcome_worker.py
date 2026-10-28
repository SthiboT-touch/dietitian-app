"""Optional durable FR-1.5 SMTP worker, started with Docker Compose profile notifications.

Do not enable for real recipients until the welcome copy and SMTP details are approved.
Database row is claimed with SKIP LOCKED; retries happen at 30/60/120 seconds.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
import database
from onboarding_services import smtp_is_configured, send_welcome_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_once():
    if not smtp_is_configured():
        return False
    with database.cursor() as cursor:
        cursor.execute(
            "SELECT message_id, recipient_email, recipient_name, attempts "
            "FROM registration_welcome_outbox "
            "WHERE state IN ('PENDING', 'RETRY') AND next_attempt_at <= NOW() "
            "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        row = cursor.fetchone()
        if not row:
            return False
        cursor.execute("UPDATE registration_welcome_outbox SET state='SENDING' WHERE message_id=%s", (row['message_id'],))
        # The same transaction holds the row lock while SMTP responds.
        try:
            send_welcome_email(row['recipient_email'], row['recipient_name'])
        except Exception:
            attempt = row['attempts'] + 1
            delay = min(300, 30 * (2 ** min(attempt, 3)))
            cursor.execute(
                "UPDATE registration_welcome_outbox SET state='RETRY', attempts=%s, "
                "next_attempt_at=NOW()+(%s * INTERVAL '1 second') WHERE message_id=%s",
                (attempt, delay, row['message_id']),
            )
            logger.warning("Welcome email delivery failed; retry scheduled")
        else:
            cursor.execute(
                "UPDATE registration_welcome_outbox SET state='SENT', sent_at=NOW(), attempts=attempts+1 "
                "WHERE message_id=%s", (row['message_id'],)
            )
            logger.info("Welcome email delivered")
    return True


if __name__ == '__main__':
    logger.info('Welcome mail worker started')
    while True:
        try:
            if not run_once():
                time.sleep(30)
        except Exception as error:
            # Avoid logging SMTP credentials, recipient information or message data.
            logger.error('Welcome email queue temporarily unavailable (error_type=%s)', type(error).__name__)
            time.sleep(30)
