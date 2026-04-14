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
import subprocess
import asyncio
import shutil
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
OPENCLAW_GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18790")
OPENCLAW_HOME = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw-claw"))

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
        "/chat <текст> — написать агенту Claw\n"
        "/claw_status — статус OpenClaw Gateway\n"
        "/memo — дневник за вчера\n"
        "/health — проверка здоровья сервера\n"
        "/help — эта справка\n\n"
        "💬 Или просто напиши сообщение — оно уйдёт в claw-main."
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


# ─── OpenClaw команды ────────────────────────────────────────────────────────


def openclaw_cli_available() -> bool:
    """Проверяет наличие openclaw CLI."""
    return shutil.which("openclaw") is not None


async def run_openclaw_agent(message: str, agent: str = "claw-main", timeout: int = 120) -> str:
    """Отправить сообщение агенту через openclaw CLI."""
    env = os.environ.copy()
    env["OPENCLAW_HOME"] = OPENCLAW_HOME

    cmd = [
        "openclaw", "agent",
        "--agent", agent,
        "--message", message,
        "--json",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            log.error("openclaw agent error: %s", err)
            return f"❌ Ошибка OpenClaw: {err[:500]}"

        raw = stdout.decode("utf-8", errors="replace").strip()

        # Парсим JSON-ответ
        try:
            data = json.loads(raw)
            # openclaw agent --json возвращает поле result или output
            reply = (
                data.get("result")
                or data.get("output")
                or data.get("text")
                or data.get("content")
                or raw
            )
            if isinstance(reply, list):
                reply = "\n".join(str(item) for item in reply)
            return str(reply).strip() or "(пустой ответ)"
        except json.JSONDecodeError:
            # Не JSON — возвращаем как текст
            return raw[:4000] if raw else "(пустой ответ)"

    except asyncio.TimeoutError:
        return "⏳ Агент не ответил за 2 минуты. Попробуй позже."
    except FileNotFoundError:
        return "❌ openclaw CLI не найден. Установи: npm install -g openclaw@latest"
    except Exception as e:
        log.error("openclaw agent exception: %s", e)
        return f"❌ Ошибка: {e}"


async def cmd_claw_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Статус OpenClaw Gateway."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    lines = ["🔧 OpenClaw Gateway\n"]

    # 1. Проверяем HTTP health
    gw_health = None
    try:
        r = requests.get(f"{OPENCLAW_GATEWAY_URL}/health", timeout=3)
        gw_health = r.json() if r.status_code == 200 else None
    except Exception:
        pass

    if gw_health:
        lines.append(f"🟢 Gateway: работает")
        lines.append(f"🌐 {OPENCLAW_GATEWAY_URL}")
        if "version" in gw_health:
            lines.append(f"📦 Версия: {gw_health['version']}")
    else:
        # Проверяем через /status
        gw_status = None
        try:
            r = requests.get(f"{OPENCLAW_GATEWAY_URL}/status", timeout=3)
            gw_status = r.json() if r.status_code == 200 else None
        except Exception:
            pass

        if gw_status:
            lines.append("🟢 Gateway: работает")
            lines.append(f"🌐 {OPENCLAW_GATEWAY_URL}")
        else:
            lines.append("🔴 Gateway: не отвечает")
            lines.append(f"🌐 {OPENCLAW_GATEWAY_URL}")

    # 2. CLI
    if openclaw_cli_available():
        lines.append("✅ CLI: openclaw найден")
    else:
        lines.append("⚠️ CLI: openclaw не в PATH")

    # 3. Конфиг
    config_path = os.path.join(OPENCLAW_HOME, "openclaw.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
            port = cfg.get("gateway", {}).get("port", "?")
            agents = cfg.get("agents", {}).get("list", [])
            lines.append(f"📁 Конфиг: {config_path}")
            lines.append(f"🚪 Порт: {port}")
            lines.append(f"\n🤖 Агенты OpenClaw:")
            for a in agents:
                aid = a.get("id", "?")
                name = a.get("name", aid)
                model = a.get("model", {}).get("primary", "?")
                default = " ⭐" if a.get("default") else ""
                lines.append(f"  • {name} ({aid}) — {model}{default}")
        except Exception as e:
            lines.append(f"⚠️ Ошибка чтения конфига: {e}")
    else:
        lines.append(f"⚠️ Конфиг не найден: {config_path}")

    await update.message.reply_text("\n".join(lines))


async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отправить сообщение агенту claw-main через OpenClaw."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    # Текст после /chat
    user_msg = update.message.text
    if user_msg:
        # Убираем /chat и /chat@botname
        parts = user_msg.split(None, 1)
        user_msg = parts[1] if len(parts) > 1 else ""
    else:
        user_msg = ""

    if not user_msg.strip():
        await update.message.reply_text(
            "💬 Использование: /chat <сообщение>\n\n"
            "Пример: /chat Привет, что ты умеешь?"
        )
        return

    # Индикатор «печатает»
    await update.message.chat.send_action("typing")

    reply = await run_openclaw_agent(user_msg, agent="claw-main")

    # Telegram лимит 4096 символов
    if len(reply) > 4000:
        # Отправляем частями
        for i in range(0, len(reply), 4000):
            chunk = reply[i:i + 4000]
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(f"🤖 Claw Main:\n\n{reply}")


async def handle_text_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Любое текстовое сообщение (без команды) отправляется в claw-main."""
    if not check_access(update):
        return

    user_msg = update.message.text
    if not user_msg or not user_msg.strip():
        return

    await update.message.chat.send_action("typing")
    reply = await run_openclaw_agent(user_msg, agent="claw-main")

    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i + 4000])
    else:
        await update.message.reply_text(f"🤖 Claw Main:\n\n{reply}")


# ─── Регистрация команд в меню Telegram ──────────────────────────────────────


async def post_init(app):
    """Устанавливаем подсказки команд в Telegram."""
    commands = [
        BotCommand("start", "Приветствие"),
        BotCommand("status", "Состояние офиса"),
        BotCommand("agents", "Список агентов"),
        BotCommand("set", "Сменить состояние"),
        BotCommand("chat", "Написать агенту Claw"),
        BotCommand("claw_status", "Статус OpenClaw Gateway"),
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
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("claw_status", cmd_claw_status))

    # Callback для inline-кнопок
    app.add_handler(CallbackQueryHandler(callback_set_state, pattern=r"^set_state:"))

    # Любой текст без команды → claw-main
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    log.info("Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
