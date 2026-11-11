-- Preserve check-in history while allowing administrator and dietitian actors.
ALTER TABLE client_checkin_event ALTER COLUMN staff_id DROP NOT NULL;
ALTER TABLE client_checkin_event ADD COLUMN IF NOT EXISTS actor_id VARCHAR(36);
ALTER TABLE client_checkin_event ADD COLUMN IF NOT EXISTS actor_role VARCHAR(32);

UPDATE client_checkin_event e
SET actor_id = e.staff_id,
    actor_role = COALESCE(s.role, 'reception')
FROM staff_account s
WHERE e.staff_id = s.staff_id
  AND (e.actor_id IS NULL OR e.actor_role IS NULL);

UPDATE client_checkin_event
SET actor_id = staff_id,
    actor_role = 'reception'
WHERE actor_id IS NULL OR actor_role IS NULL;

ALTER TABLE client_checkin_event
    ALTER COLUMN actor_role SET DEFAULT 'reception',
    ALTER COLUMN actor_role SET NOT NULL;
