# config.py
import os

# === Обязательные переменные ===

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("Переменная BOT_TOKEN не установлена")

if not BASE_URL:
    raise RuntimeError("Переменная BASE_URL (RENDER_EXTERNAL_URL) не установлена")

# === Администратор ===

ADMIN_ID = os.getenv("ADMIN_ID")
if ADMIN_ID:
    ADMIN_ID = ADMIN_ID.strip()

# === Web-сервер / Webhook ===

PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# === Игровые константы ===

K_FACTOR = 30
MATCH_COOLDOWN_MINUTES = 30
CHALLENGE_RANGE = 10

# === Сообщество ===
# Публичная группа для поиска соперников и общения.
# Если пусто — строка про группу не показывается в боте.
COMMUNITY_CHAT_URL = "https://t.me/+CjLSnnUt4y5mZDEy"
