"""Enable branch-manager attribution on existing approval logs."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: F401,E402
import database  # noqa: E402

if __name__ == "__main__":
    with database.cursor() as cursor:
        cursor.execute(Path(__file__).with_name("024_branch_manager_approvals.sql").read_text())
    print("Branch manager approvals migration applied.")
