# utils.py
from config import ADMIN_ID


def display_name(row) -> str:
    return row['full_name'] or row['username'] or "Аноним"


def is_admin(user_id: int) -> bool:
    if not ADMIN_ID:
        return False
    return str(user_id) == str(ADMIN_ID)
