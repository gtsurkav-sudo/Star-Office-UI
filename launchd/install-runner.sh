#!/bin/bash
# ============================================
# Установка GitHub Actions Self-Hosted Runner
# для Star-Office-UI на Mac
#
# Запуск:
#   bash ~/projects/Star-Office-UI/launchd/install-runner.sh
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

RUNNER_DIR="$HOME/actions-runner"
REPO="gtsurkav-sudo/Star-Office-UI"

echo ""
echo "========================================"
echo "  GitHub Actions Self-Hosted Runner"
echo "========================================"
echo ""

# ─── Шаг 1: Получить токен ───────────────────────────────────────────────

echo "Для установки нужен одноразовый токен из GitHub."
echo ""
info "Открой в браузере:"
echo "  https://github.com/$REPO/settings/actions/runners/new"
echo ""
info "Или выполни (если есть gh CLI):"
echo "  gh api -X POST repos/$REPO/actions/runners/registration-token --jq .token"
echo ""
read -p "Вставь токен: " RUNNER_TOKEN

if [ -z "$RUNNER_TOKEN" ]; then
    fail "Токен не указан"
fi

# ─── Шаг 2: Скачать runner ───────────────────────────────────────────────

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [ ! -f "./config.sh" ]; then
    info "Определяю архитектуру..."
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        RUNNER_ARCH="osx-arm64"
    else
        RUNNER_ARCH="osx-x64"
    fi

    RUNNER_VERSION="2.322.0"
    RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"

    info "Скачиваю runner ($RUNNER_ARCH)..."
    curl -o actions-runner.tar.gz -L "$RUNNER_URL"

    info "Распаковываю..."
    tar xzf actions-runner.tar.gz
    rm -f actions-runner.tar.gz

    ok "Runner скачан"
else
    ok "Runner уже скачан"
fi

# ─── Шаг 3: Настроить ────────────────────────────────────────────────────

if [ ! -f ".runner" ]; then
    info "Настраиваю runner..."
    ./config.sh \
        --url "https://github.com/$REPO" \
        --token "$RUNNER_TOKEN" \
        --name "joji-mac" \
        --labels "self-hosted,macOS,ARM64,star-office" \
        --work "_work" \
        --replace \
        --unattended

    ok "Runner настроен"
else
    ok "Runner уже настроен"
fi

# ─── Шаг 4: Установить как launchd-сервис ────────────────────────────────

info "Устанавливаю как сервис..."
cd "$RUNNER_DIR"

# Создаём plist для runner
PLIST_NAME="com.staroffice.github-runner"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

cat > "$PLIST_PATH" << PEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${RUNNER_DIR}/run.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${RUNNER_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/github-runner.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/github-runner.err</string>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
PEOF

# Загрузить
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

ok "Runner установлен как launchd-сервис"

echo ""
echo "========================================"
echo "  Готово! Runner запущен."
echo "========================================"
echo ""
info "Проверь статус:"
echo "  launchctl list | grep github-runner"
echo "  tail -f /tmp/github-runner.log"
echo ""
info "Runner появится на:"
echo "  https://github.com/$REPO/settings/actions/runners"
echo ""
info "Теперь при каждом push в master workflow"
echo "  проверит статус всех Star-Office сервисов."
echo ""
