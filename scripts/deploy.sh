#!/bin/bash
set -e

PROJECT_PATH="/home/username/printer-bot"
SERVICE_NAME="printerbot.service"

echo "📥 Обновляем репозиторий..."
cd "$PROJECT_PATH"
git fetch --tags
LATEST_TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
git checkout "tags/$LATEST_TAG" -f

echo "🔄 Перезапускаем сервис..."
systemctl --user daemon-reload
systemctl --user restart "$SERVICE_NAME"

echo "✅ Printer Bot обновлён до версии $LATEST_TAG и перезапущен!"

