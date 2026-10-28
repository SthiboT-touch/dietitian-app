ALTER TABLE admin ADD COLUMN IF NOT EXISTS role VARCHAR(30) NOT NULL DEFAULT 'admin';

ALTER TABLE admin DROP CONSTRAINT IF EXISTS admin_role_check;

ALTER TABLE admin ADD CONSTRAINT admin_role_check
CHECK (role IN ('admin','reception_staff','branch_manager','compliance','executive','content_manager'));
