#!/bin/bash
set -e

# === Настройки ===
PROJECT_PATH="$HOME/printer-bot"       # автоматически текущий пользователь
SERVICE_NAME="printerbot.service"       # имя user-level systemd сервиса

echo "🔄 Переходим в папку проекта: $PROJECT_PATH"
cd "$PROJECT_PATH"

echo "📦 Подтягиваем все теги из GitHub..."
git fetch --tags

echo "🏷 Определяем последний тег..."
LATEST_TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
echo "Последний тег: $LATEST_TAG"

echo "🔄 Переключаемся на тег $LATEST_TAG..."
git checkout "tags/$LATEST_TAG" -f

echo "🔄 Перезапускаем сервис $SERVICE_NAME..."
systemctl --user restart "$SERVICE_NAME"

echo "✅ Обновление до версии $LATEST_TAG выполнено успешно!"

