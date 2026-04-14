#!/usr/bin/env python3
"""
Star-Office-UI Telegram Bot
Подключает Telegram к пиксельному офису — управление состоянием,
мониторинг агентов, чтение дневника.

Требования: pip install python-telegram-bot requests
Запуск: python3 telegram_bot.py
"""

import os
import sys
import logging
import json
from datetime import datetime

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─── Конфигурация ────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "8693039013:AAEU6oRcR8S_LZ2DILeyw9C18pw1EfxdAGU",
)
OFFICE_API_URL = os.environ.get("OFFICE_API_URL", "http://127.0.0.1:19000")

# Ограничение доступа (пустой список = доступ для всех)
# Заполни свой Telegram user ID для безопасности
ALLOWED_USER_IDS: list[int] = json.loads(os.environ.get("ALLOWED_USER_IDS", "[]"))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("star-office-bot")

# ─── Маппинг состояний ───────────────────────────────────────────────────────

STATE_EMOJI = {
    "idle": "😴",
    "writing": "✍️",
    "researching": "🔍",
    "executing": "⚙️",
    "syncing": "🔄",
    "error": "❌",
}

STATE_LABELS_RU = {
    "idle": "Отдыхает",
    "writing": "Пишет",
    "researching": "Исследует",
    "executing": "Выполняет",
    "syncing": "Синхронизация",
    "error": "Ошибка",
}

# ─── Утилиты API ─────────────────────────────────────────────────────────────


def api_get(path: str) -> dict | None:
    """GET-запрос к Star-Office-UI API."""
    try:
        r = requests.get(f"{OFFICE_API_URL}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("API GET %s failed: %s", path, e)
        return None


def api_post(path: str, data: dict) -> dict | None:
    """POST-запрос к Star-Office-UI API."""
    try:
        r = requests.post(f"{OFFICE_API_URL}{path}", json=data, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("API POST %s failed: %s", path, e)
        return None


def check_access(update: Update) -> bool:
    """Проверка доступа по Telegram user ID."""
    if not ALLOWED_USER_IDS:
        return True
    return update.effective_user.id in ALLOWED_USER_IDS


# ─── Команды бота ────────────────────────────────────────────────────────────


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Приветствие и список команд."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    user = update.effective_user
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🏢 Я — бот пиксельного офиса Star-Office-UI.\n\n"
        "📋 Команды:\n"
        "/status — текущее состояние офиса\n"
        "/agents — список агентов\n"
        "/set — сменить состояние\n"
        "/memo — дневник за вчера\n"
        "/health — проверка здоровья сервера\n"
        "/help — эта справка"
    )
    await update.message.reply_text(text)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    if not check_access(update):
        return
    await cmd_start(update, ctx)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Текущее состояние офиса."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    data = api_get("/status")
    if data is None:
        await update.message.reply_text("🔌 Не удалось подключиться к офису. Сервер запущен?")
        return

    state = data.get("state", "idle")
    detail = data.get("detail", "")
    office_name = data.get("officeName", "Star Office")
    updated = data.get("updated_at", "—")

    emoji = STATE_EMOJI.get(state, "❓")
    label = STATE_LABELS_RU.get(state, state)

    text = (
        f"🏢 {office_name}\n\n"
        f"{emoji} Состояние: {label}\n"
    )
    if detail:
        text += f"📝 Детали: {detail}\n"
    text += f"🕐 Обновлено: {updated}"

    await update.message.reply_text(text)


async def cmd_agents(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Список агентов в офисе."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    data = api_get("/agents")
    if data is None:
        await update.message.reply_text("🔌 Не удалось подключиться к офису.")
        return

    agents = data.get("agents", [])
    if not agents:
        await update.message.reply_text("🏢 В офисе пока нет агентов.")
        return

    lines = ["🤖 Агенты в офисе:\n"]
    for a in agents:
        name = a.get("name", a.get("agentId", "???"))
        state = a.get("state", "idle")
        detail = a.get("detail", "")
        emoji = STATE_EMOJI.get(state, "❓")
        label = STATE_LABELS_RU.get(state, state)
        line = f"  {emoji} {name} — {label}"
        if detail:
            line += f" ({detail})"
        lines.append(line)

    await update.message.reply_text("\n".join(lines))


async def cmd_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать кнопки выбора состояния."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    buttons = []
    for state_key in ["idle", "writing", "researching", "executing", "syncing", "error"]:
        emoji = STATE_EMOJI[state_key]
        label = STATE_LABELS_RU[state_key]
        buttons.append(
            InlineKeyboardButton(f"{emoji} {label}", callback_data=f"set_state:{state_key}")
        )

    # 2 кнопки в ряд
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("🎛 Выбери состояние офиса:", reply_markup=markup)


async def callback_set_state(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопки состояния."""
    query = update.callback_query
    await query.answer()

    if not check_access(update):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return

    _, state_key = query.data.split(":", 1)
    result = api_post("/set_state", {"state": state_key})

    if result and result.get("status") == "ok":
        emoji = STATE_EMOJI.get(state_key, "❓")
        label = STATE_LABELS_RU.get(state_key, state_key)
        await query.edit_message_text(f"✅ Состояние изменено: {emoji} {label}")
    else:
        await query.edit_message_text("❌ Ошибка при смене состояния.")


async def cmd_memo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Дневник за вчера."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    data = api_get("/yesterday-memo")
    if data is None:
        await update.message.reply_text("🔌 Не удалось подключиться к офису.")
        return

    if data.get("success"):
        date = data.get("date", "?")
        memo = data.get("memo", "(пусто)")
        # Telegram лимит 4096 символов
        text = f"📓 Дневник за {date}:\n\n{memo}"
        if len(text) > 4000:
            text = text[:4000] + "\n\n… (обрезано)"
        await update.message.reply_text(text)
    else:
        msg = data.get("msg", "Дневник не найден")
        await update.message.reply_text(f"📓 {msg}")


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Проверка здоровья сервера."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    data = api_get("/health")
    if data is None:
        await update.message.reply_text("🔴 Сервер не отвечает!")
        return

    status = data.get("status", "unknown")
    ts = data.get("timestamp", "—")

    if status == "ok":
        await update.message.reply_text(f"🟢 Сервер работает\n🕐 {ts}")
    else:
        await update.message.reply_text(f"🟡 Статус: {status}\n🕐 {ts}")


# ─── Регистрация команд в меню Telegram ──────────────────────────────────────


async def post_init(app):
    """Устанавливаем подсказки команд в Telegram."""
    commands = [
        BotCommand("start", "Приветствие"),
        BotCommand("status", "Состояние офиса"),
        BotCommand("agents", "Список агентов"),
        BotCommand("set", "Сменить состояние"),
        BotCommand("memo", "Дневник за вчера"),
        BotCommand("health", "Проверка сервера"),
        BotCommand("help", "Справка"),
    ]
    await app.bot.set_my_commands(commands)
    me = await app.bot.get_me()
    log.info("Бот запущен: @%s (%s)", me.username, me.id)


# ─── Точка входа ─────────────────────────────────────────────────────────────


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не задан!")
        sys.exit(1)

    log.info("Star-Office Telegram Bot запускается…")
    log.info("API: %s", OFFICE_API_URL)

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("agents", cmd_agents))
    app.add_handler(CommandHandler("set", cmd_set))
    app.add_handler(CommandHandler("memo", cmd_memo))
    app.add_handler(CommandHandler("health", cmd_health))

    # Callback для inline-кнопок
    app.add_handler(CallbackQueryHandler(callback_set_state, pattern=r"^set_state:"))

    log.info("Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
