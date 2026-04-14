# OpenClaw Claw — Изолированный контур

Автономный AI-контур на базе [OpenClaw](https://github.com/openclaw/openclaw), работающий независимо от других агентских систем.

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                   Telegram Bot                       │
│               @Joji_OKLAW_bot                        │
│         /chat  /claw_status  текст→агент             │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │    Star-Office-UI         │
         │    Flask :19000           │
         │    Пиксельный офис        │
         │    /status /set /agents   │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   OpenClaw Gateway        │
         │   WebSocket + HTTP        │
         │   127.0.0.1:18790         │
         └──┬───────────────────┬────┘
            │                   │
   ┌────────▼────────┐ ┌───────▼─────────┐
   │   claw-main     │ │ claw-researcher │
   │   DeepSeek V3.2 │ │ DeepSeek R1     │
   │   ⭐ default     │ │ reasoning=true  │
   └────────┬────────┘ └───────┬─────────┘
            │                   │
   ┌────────▼───────────────────▼────────┐
   │         ~/.openclaw-claw/           │
   │  workspace-main/  workspace-researcher/ │
   │  memory/  skills/  agents/          │
   │  openclaw.json                      │
   └─────────────────────────────────────┘
```

## Ключевые параметры

| Параметр | Значение |
|----------|----------|
| Gateway порт | `18790` |
| Хост | `127.0.0.1` (только локально) |
| Конфиг | `~/.openclaw-claw/openclaw.json` |
| Память | QMD hybrid search (BM25 + vector, 70/30) |
| Сессия | 720 минут |

## Модели

| Агент | Модель | Назначение |
|-------|--------|-----------|
| `claw-main` | `deepseek/deepseek-chat` (DeepSeek V3.2) | Основной — файлы, код, команды, деплой |
| `claw-researcher` | `deepseek/deepseek-reasoner` (DeepSeek R1) | Глубокий анализ и исследования |

Оба агента: контекст 164K токенов, cost $0.28/M input, $0.42/M output.

## Файлы контура

| Файл | Описание |
|------|----------|
| [SOUL.md](SOUL.md) | Идентичность агента Claw — роль, возможности, ограничения, стиль общения, интеграция со Star Office |
| [USER.md](USER.md) | Профиль оператора JOJI — стек, предпочтения, рабочий стиль |
| [AGENTS.md](AGENTS.md) | Операционные инструкции — память, команды, управление агентами, файлы, веб |
| [MEMORY.md](MEMORY.md) | Долгосрочная память — решения, проекты, состояние системы |

## Запуск

```bash
# Gateway
OPENCLAW_HOME=~/.openclaw-claw openclaw gateway

# Или через launchd (автозапуск при входе)
bash ~/projects/Star-Office-UI/launchd/install-launchd.sh
```

## Взаимодействие

```bash
# CLI
OPENCLAW_HOME=~/.openclaw-claw openclaw agent --agent claw-main --message "Привет"

# Telegram
/chat Привет, что ты умеешь?

# Любое сообщение боту (без команды) → claw-main
```

## Изоляция

Контур `openclaw-claw` полностью изолирован:
- Отдельная директория `~/.openclaw-claw/` (не `~/.openclaw/`)
- Отдельный порт `18790` (не стандартный `18789`)
- Собственные workspace, memory, skills
- Не взаимодействует с другими агентскими системами
