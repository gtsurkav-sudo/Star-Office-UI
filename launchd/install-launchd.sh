#!/bin/bash
# ============================================
# Star-Office-UI — Установка автозапуска через launchd
# Регистрирует 3 сервиса:
#   1. OpenClaw Gateway (порт 18790)
#   2. Star-Office-UI Backend (порт 19000)
#   3. Telegram-бот
#
# Запуск:
#   bash ~/projects/Star-Office-UI/launchd/install-launchd.sh
# ============================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
info() { echo -e "${CYAN}ℹ️  $1${NC}"; }

echo ""
echo "========================================"
echo "  Star-Office — Автозапуск через launchd"
echo "========================================"
echo ""

# ─── Определяем пути ──────────────────────────────────────────────────────

HOME_DIR="$HOME"
PROJECT_DIR="$HOME/projects/Star-Office-UI"
LAUNCHD_SRC="$PROJECT_DIR/launchd"
LAUNCHD_DST="$HOME/Library/LaunchAgents"
OPENCLAW_HOME="$HOME/.openclaw-claw"

# Проверки
[ -d "$PROJECT_DIR" ]    || fail "Не найден $PROJECT_DIR"
[ -d "$LAUNCHD_SRC" ]    || fail "Не найден $LAUNCHD_SRC"
[ -f "$PROJECT_DIR/.venv/bin/python3" ] || fail "Не найден .venv — запусти: cd $PROJECT_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt"

mkdir -p "$LAUNCHD_DST"

# Находим openclaw
OPENCLAW_BIN=""
if command -v openclaw &>/dev/null; then
    OPENCLAW_BIN="$(which openclaw)"
elif [ -f "$HOME/.nvm/versions/node/$(node --version 2>/dev/null)/bin/openclaw" ]; then
    OPENCLAW_BIN="$HOME/.nvm/versions/node/$(node --version)/bin/openclaw"
elif [ -f "/usr/local/bin/openclaw" ]; then
    OPENCLAW_BIN="/usr/local/bin/openclaw"
fi

# Находим node bin dir (для nvm)
NODE_BIN_DIR=""
if command -v node &>/dev/null; then
    NODE_BIN_DIR="$(dirname "$(which node)")"
else
    NODE_BIN_DIR="/usr/local/bin"
fi

# ─── Функция: установить plist ────────────────────────────────────────────

install_plist() {
    local SRC_NAME="$1"
    local LABEL="$2"
    local SKIP_IF_MISSING="$3"  # "openclaw" — пропускать если нет openclaw

    local SRC="$LAUNCHD_SRC/$SRC_NAME"
    local DST="$LAUNCHD_DST/$SRC_NAME"

    if [ ! -f "$SRC" ]; then
        warn "Шаблон не найден: $SRC — пропускаю"
        return
    fi

    if [ "$SKIP_IF_MISSING" = "openclaw" ] && [ -z "$OPENCLAW_BIN" ]; then
        warn "OpenClaw не найден в PATH — пропускаю $LABEL"
        warn "Установи: npm install -g openclaw@latest"
        return
    fi

    # Остановить старый, если есть
    if launchctl list "$LABEL" &>/dev/null; then
        info "Останавливаю старый $LABEL…"
        launchctl unload "$DST" 2>/dev/null || true
    fi

    # Копируем и подставляем пути
    cp "$SRC" "$DST"
    sed -i '' "s|__HOME__|$HOME_DIR|g" "$DST"

    if [ -n "$OPENCLAW_BIN" ]; then
        sed -i '' "s|__OPENCLAW_BIN__|$OPENCLAW_BIN|g" "$DST"
    fi
    sed -i '' "s|__NODE_BIN_DIR__|$NODE_BIN_DIR|g" "$DST"

    # Загружаем
    launchctl load "$DST"
    ok "$LABEL → загружен"
}

# ─── Установка ────────────────────────────────────────────────────────────

echo "--- 1/3: OpenClaw Gateway (порт 18790) ---"
install_plist "com.staroffice.gateway.plist" "com.staroffice.gateway" "openclaw"
echo ""

echo "--- 2/3: Star-Office-UI Backend (порт 19000) ---"
# Убедимся что run.sh исполняемый
chmod +x "$PROJECT_DIR/backend/run.sh"
install_plist "com.staroffice.backend.plist" "com.staroffice.backend" ""
echo ""

echo "--- 3/3: Telegram-бот ---"
install_plist "com.staroffice.telegram.plist" "com.staroffice.telegram" ""
echo ""

# ─── Проверка ─────────────────────────────────────────────────────────────

echo "--- Проверка ---"
sleep 3

check_service() {
    local LABEL="$1"
    local PORT="$2"
    local NAME="$3"

    if [ -n "$PORT" ]; then
        if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q "200"; then
            ok "$NAME работает на порту $PORT"
        else
            warn "$NAME — порт $PORT пока не отвечает (подожди 5-10 сек)"
        fi
    fi

    if launchctl list "$LABEL" &>/dev/null; then
        ok "$LABEL зарегистрирован в launchd"
    else
        warn "$LABEL не найден в launchd"
    fi
}

check_service "com.staroffice.gateway" "18790" "OpenClaw Gateway"
check_service "com.staroffice.backend" "19000" "Star-Office Backend"
# Telegram бот не слушает порт, проверяем только launchd
if launchctl list "com.staroffice.telegram" &>/dev/null; then
    ok "Telegram-бот зарегистрирован в launchd"
else
    warn "Telegram-бот не найден в launchd"
fi

echo ""
echo "========================================"
echo "  Готово! Сервисы стартуют при входе."
echo "========================================"
echo ""
info "Логи:"
echo "  tail -f /tmp/openclaw-gateway.log"
echo "  tail -f /tmp/staroffice-backend.log"
echo "  tail -f /tmp/staroffice-telegram.log"
echo ""
info "Управление:"
echo "  launchctl stop  com.staroffice.gateway"
echo "  launchctl start com.staroffice.gateway"
echo "  launchctl stop  com.staroffice.backend"
echo "  launchctl start com.staroffice.backend"
echo "  launchctl stop  com.staroffice.telegram"
echo "  launchctl start com.staroffice.telegram"
echo ""
info "Удалить автозапуск:"
echo "  bash $LAUNCHD_SRC/uninstall-launchd.sh"
echo ""
