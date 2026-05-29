#!/usr/bin/env python3
"""
Star-Office-UI Telegram Bot
Подключает Telegram к пиксельному офису — управление состоянием,
мониторинг агентов, чтение дневника.

Требования: pip install python-telegram-bot requests websockets
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
import signal
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
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

OPENCLAW_GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18790")
OPENCLAW_HOME = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw-claw"))
OFFICE_JOIN_KEY = os.environ.get("OFFICE_JOIN_KEY", "claw-main-2026")
OFFICE_AGENT_NAME = os.environ.get("OFFICE_AGENT_NAME", "Claw Main")
_office_agent_id: str | None = None
_STAR_OFFICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PID файл для предотвращения дублирования
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".telegram_bot.pid")

# Ограничение доступа (пустой список = доступ для всех)
# Заполни свой Telegram user ID для безопасности
ALLOWED_USER_IDS: list[int] = json.loads(os.environ.get("ALLOWED_USER_IDS", "[]"))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("star-office-bot")


def enforce_single_instance() -> None:
    """Проверяет PID-файл и убивает старый процесс, если он есть."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            # Проверяем, жив ли процесс
            try:
                os.kill(old_pid, 0)  # сигнал 0 = проверка существования
                log.warning("Найден старый процесс PID %d, убиваю...", old_pid)
                os.kill(old_pid, signal.SIGTERM)
                import time
                time.sleep(2)
                # Если не умер — SIGKILL
                try:
                    os.kill(old_pid, 0)
                    os.kill(old_pid, signal.SIGKILL)
                    time.sleep(1)
                except OSError:
                    pass
            except OSError:
                pass  # старый процесс уже мёртв
        except (ValueError, OSError):
            pass

    # Пишем свой PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    log.info("PID %d записан в %s", os.getpid(), PID_FILE)


def close_old_telegram_session() -> None:
    """Принудительно закрывает все старые GetUpdates сессии через Telegram API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/close"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            result = resp.json()
            log.info("Telegram /close: %s", result.get("description", result.get("ok", "ok")))
        else:
            log.warning("Telegram /close: HTTP %s", resp.status_code)
    except Exception as e:
        log.warning("Telegram /close failed: %s", e)

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


async def office_join() -> None:
    """Зарегистрировать Claw в пиксельном офисе."""
    global _office_agent_id
    try:
        resp = await asyncio.to_thread(
            api_post,
            "/join-agent",
            {
                "name": OFFICE_AGENT_NAME,
                "state": "idle",
                "detail": "Подключён к Пиксельному офису",
                "joinKey": OFFICE_JOIN_KEY,
            },
        )
        if resp and resp.get("ok"):
            _office_agent_id = resp.get("agentId")
            log.info("Office join success: %s", _office_agent_id)
        else:
            log.warning("Office join failed: %s", resp)
    except Exception as e:
        log.warning("Office join exception (некритично): %s", e)


async def office_push(state: str, detail: str = "") -> None:
    """Обновить статус Claw в пиксельном офисе."""
    if not _office_agent_id:
        log.warning("Office push skipped: no agentId")
        return
    try:
        resp = await asyncio.to_thread(
            api_post,
            "/agent-push",
            {
                "agentId": _office_agent_id,
                "joinKey": OFFICE_JOIN_KEY,
                "state": state,
                "detail": detail,
            },
        )
        if resp and resp.get("ok"):
            log.info("Office push ok: %s (%s)", state, detail)
        else:
            log.warning("Office push failed: %s", resp)
    except Exception as e:
        log.error("Office push exception: %s", e)


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
    """Отправить сообщение агенту через DeepSeek API напрямую."""
    log.info("DeepSeek API: запрос для %s: %s", agent, message[:100])

    if not DEEPSEEK_API_KEY:
        return (
            f"🤖 {agent} (автономный режим):\n\n"
            f"📩 Получено: «{message}»\n\n"
            f"⚠️ DeepSeek API ключ не настроен. Добавьте DEEPSEEK_API_KEY в .env"
        )

    # Системный промпт от Claw Main
    system_prompt = (
        "Ты — Claw Main, главный AI-ассистент и front-controller JOJI. "
        "Отвечай на русском языке. Будь техничным, точным и лаконичным. "
        "JOJI — Senior AI Systems Architect и DevOps инженер из Тбилиси. "
        "\n"
        "Твоя архитектура — изолированный OpenClaw контур с тобой во главе. "
        "У тебя есть команда специализированных сабагентов, которым ты делегируешь задачи:\n"
        "- claw-coder — код, скрипты, GitHub, CI/CD, ревью\n"
        "- claw-researcher — глубокое исследование, фактчекинг, анализ\n"
        "- claw-scraper — веб-скрапинг, парсинг, сбор данных\n"
        "- claw-builder — сайты, UI, фронтенд, деплой\n"
        "- claw-automator — cron, автоматизация, мониторинг\n"
        "- claw-docs — документация, отчёты, README\n"
        "- claw-orchestrator — сложное мульти-агентное планирование\n"
        "Ты сам решаешь: отвечать напрямую или делегировать сабагенту. "
        "При перечислении агентов перечисли именно этот список.\n"
        "\n"
        "Твой Telegram-бот имеет полный доступ к интернету через Python requests. "
        "Если нужна информация из сети — используй web_search (поиск в интернете) "
        "или web_fetch (загрузка страницы). Не говори, что ты без интернета — "
        "у тебя есть полный доступ к сети через DeepSeek API."
    )

    try:
        url = f"{DEEPSEEK_API_URL}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            "temperature": 0.5,
            "max_tokens": 2000,
        }

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: requests.post(url, headers=headers, json=payload, timeout=timeout),
        )

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                log.info("DeepSeek API: ответ %d токенов", len(content))
                return content
            return "⚠️ Пустой ответ от DeepSeek"
        else:
            log.error("DeepSeek API error %s: %s", resp.status_code, resp.text[:300])
            return (
                f"🤖 {agent} (автономный режим):\n\n"
                f"📩 Получено: «{message}»\n\n"
                f"⚠️ Ошибка DeepSeek API ({resp.status_code})"
            )

    except requests.exceptions.Timeout:
        return f"⚠️ DeepSeek API не ответил за {timeout} секунд"
    except Exception as e:
        log.error("run_openclaw_agent error: %s", e)
        return (
            f"🤖 {agent} (автономный режим):\n\n"
            f"📩 Получено: «{message}»\n\n"
            f"⚠️ Ошибка: {e}"
        )


async def set_star_office_state(state: str, detail: str = "") -> None:
    """Обновить глобальный статус пиксельного офиса (двигает Star)."""
    script = os.path.join(_STAR_OFFICE_DIR, "set_state.py")
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", script, state, detail,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
    except Exception as e:
        log.warning("set_star_office_state failed: %s", e)


async def run_openclaw_agent_with_status(message: str, agent: str = "claw-main", timeout: int = 120) -> str:
    """Запустить агента с обновлением статуса в пиксельном офисе."""
    loop = asyncio.get_event_loop()
    start = loop.time()
    await asyncio.gather(
        office_push("executing", "Выполняю запрос через DeepSeek API…"),
        set_star_office_state("executing", "Обрабатываю запрос…"),
    )
    try:
        reply = await run_openclaw_agent(message, agent=agent, timeout=timeout)
    finally:
        elapsed = loop.time() - start
        if elapsed < 3.0:
            await asyncio.sleep(3.0 - elapsed)
        await asyncio.gather(
            office_push("idle", "Ожидаю команд в изолированном контуре"),
            set_star_office_state("idle", "Готов к работе"),
        )
    return reply


async def cmd_test_office(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Тест: проверить, что статус пушится в офис."""
    if not check_access(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await office_push("executing", "Тестовая работа в офисе")
    await update.message.reply_text("✅ Пушнул executing — смотри в офис!")
    await asyncio.sleep(5)
    await office_push("idle", "Тест завершён")
    await update.message.reply_text("✅ Пушнул idle обратно")


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

    reply = await run_openclaw_agent_with_status(user_msg, agent="claw-main")

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
    reply = await run_openclaw_agent_with_status(user_msg, agent="claw-main")

    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i + 4000])
    else:
        await update.message.reply_text(f"🤖 Claw Main:\n\n{reply}")


# ─── Регистрация команд в меню Telegram ──────────────────────────────────────


async def office_heartbeat() -> None:
    """Фоновый heartbeat: держать Claw в офисе активным."""
    while True:
        await asyncio.sleep(60)
        await office_push("idle", "Ожидаю команд в изолированном контуре")


async def post_init(app):
    """Устанавливаем подсказки команд в Telegram."""
    asyncio.create_task(office_heartbeat())
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
    await office_join()
    me = await app.bot.get_me()
    log.info("Бот запущен: @%s (%s)", me.username, me.id)


# ─── Точка входа ─────────────────────────────────────────────────────────────


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не задан!")
        sys.exit(1)

    # Принудительно убиваем старый процесс и закрываем сессии Telegram
    enforce_single_instance()
    close_old_telegram_session()

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
    app.add_handler(CommandHandler("testoffice", cmd_test_office))
    app.add_handler(CommandHandler("claw_status", cmd_claw_status))

    # Callback для inline-кнопок
    app.add_handler(CallbackQueryHandler(callback_set_state, pattern=r"^set_state:"))

    # Любой текст без команды → claw-main
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    log.info("Webhook mode — no polling")

    # Определяем порт: из окружения или 25700
    WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "25700"))
    WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "127.0.0.1")
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

    if WEBHOOK_URL:
        log.info("Webhook mode — удаление webhook + long polling")
        
        # Удаляем webhook, чтобы не было конфликтов с cloudflared
        import httpx
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True},
                timeout=10,
            )
            log.info("deleteWebhook: %s", r.json())
        except Exception as e:
            log.warning("deleteWebhook failed: %s", e)
        
        # Оставляем cloudflared для возможности прямого тестирования через HTTP
        # а бот работает через long polling
        log.info("Старт long polling (timeout=50, interval=0.5)")
        app.run_polling(
            drop_pending_updates=False,
            poll_interval=0.5,
            timeout=50,
        )
    else:
        log.warning("WEBHOOK_URL не задан — fallback на polling")
        app.run_polling(
            drop_pending_updates=True,
            poll_interval=0.5,
            timeout=50,
        )


def cleanup():
    """Удалить PID-файл при выходе."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        log.info("PID-файл %s удалён", PID_FILE)


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
