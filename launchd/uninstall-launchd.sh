#!/bin/bash
# Удаление автозапуска Star-Office из launchd

set -e

GREEN='\033[0;32m'
NC='\033[0m'
ok() { echo -e "${GREEN}✅ $1${NC}"; }

LAUNCHD_DIR="$HOME/Library/LaunchAgents"

for LABEL in com.staroffice.gateway com.staroffice.backend com.staroffice.telegram; do
    PLIST="$LAUNCHD_DIR/$LABEL.plist"
    if [ -f "$PLIST" ]; then
        launchctl unload "$PLIST" 2>/dev/null || true
        rm -f "$PLIST"
        ok "$LABEL — удалён"
    else
        echo "⏭  $LABEL — не установлен"
    fi
done

echo ""
echo "Автозапуск удалён. Сервисы остановлены."
