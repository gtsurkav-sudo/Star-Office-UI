#!/usr/bin/env zsh
set -o pipefail

BOT_DIR="/Users/jojidigital/projects/Star-Office-UI"
BOT_SCRIPT="$BOT_DIR/backend/telegram_bot.py"
BOT_LOG="/tmp/star-office-bot.log"
CF_LOG="/tmp/cloudflared.log"
PID_FILE="$BOT_DIR/backend/.telegram_bot.pid"

BOT_TOKEN="8693039013:AAEU6oRcR8S_LZ2DILeyw9C18pw1EfxdAGU"
TELEGRAM_API="https://api.telegram.org/bot${BOT_TOKEN}"

# Убить старые процессы
pkill -f cloudflared 2>/dev/null
ps aux | grep "telegram_bot.py" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
sleep 2
rm -f "$PID_FILE"

# 1. Запуск cloudflared
echo "=== Запуск cloudflared ==="
nohup cloudflared tunnel --no-autoupdate --url http://localhost:25700 > "$CF_LOG" 2>&1 &
CF_PID=$!

# 2. Ждём URL от cloudflared
echo "Ждём URL от cloudflared..."
CF_URL=""
for i in $(seq 1 30); do
    CF_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG" 2>/dev/null | head -1)
    if [ -n "$CF_URL" ]; then
        echo "URL получен: $CF_URL (попытка $i)"
        break
    fi
    sleep 1
done

if [ -z "$CF_URL" ]; then
    echo "ОШИБКА: cloudflared не дал URL"
    cat "$CF_LOG"
    exit 1
fi

# 3. Ждём DNS propagation
echo "Ожидание DNS propagation..."
for i in $(seq 1 20); do
    IP=$(dig "${CF_URL#https://}" @8.8.8.8 +short 2>/dev/null | head -1)
    if [ -n "$IP" ]; then
        echo "DNS OK: ${CF_URL#https://} → $IP (попытка $i)"
        break
    fi
    echo "DNS ещё не готов... (попытка $i/20)"
    sleep 3
done

if [ -z "$IP" ]; then
    echo "WARN: DNS всё ещё не готов, пробуем запустить"
fi

# 4. Запуск бота с webhook URL
echo ""
echo "=== Запуск бота с WEBHOOK_URL=$CF_URL ==="
cd "$BOT_DIR"
source .env
export WEBHOOK_URL="$CF_URL"
export WEBHOOK_PORT=25700
nohup .venv/bin/python "$BOT_SCRIPT" >> "$BOT_LOG" 2>&1 &
BOT_PID=$!

echo "Ожидание старта бота (8 секунд)..."
sleep 8

# 5. Проверка webhook
echo ""
echo "=== Webhook info ==="
curl -s "${TELEGRAM_API}/getWebhookInfo" | python3 -c "
import sys,json
d=json.load(sys.stdin).get('result',{})
print(f\"URL: {d.get('url','EMPTY')}\")
print(f\"Pending: {d.get('pending_update_count')}\")
print(f\"Err: {d.get('last_error_message','none')}\")
"

echo ""
echo "=== Ready! ==="
echo "Cloudflared PID: $CF_PID"
echo "Bot PID: $BOT_PID"
echo "Webhook URL: ${CF_URL}/${BOT_TOKEN}"
