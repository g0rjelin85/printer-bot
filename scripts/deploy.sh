#!/bin/bash
set -e

# === Настройки ===
PROJECT_PATH="$HOME/printer-bot"       # автоматически текущий пользователь
SERVICE_NAME="printerbot.service"       # имя user-level systemd сервиса
TARGET="${1:-latest}"                   # цель обновления: latest или тег

echo "🔄 Переходим в папку проекта: $PROJECT_PATH"
cd "$PROJECT_PATH"

if [ "$TARGET" = "latest" ]; then
    echo "📦 Подтягиваем все теги из GitHub..."
    git fetch --tags
    
    echo "🏷 Определяем последний тег..."
    LATEST_TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
    echo "Последний тег: $LATEST_TAG"
    
    echo "🔄 Создаём/обновляем ветку deploy на тег $LATEST_TAG..."
    git checkout -B deploy "$LATEST_TAG"
    
    VERSION_INFO="$LATEST_TAG"
    
else
    echo "📦 Подтягиваем все теги из GitHub..."
    git fetch --tags
    
    echo "🔄 Создаём/обновляем ветку deploy на тег $TARGET..."
    git checkout -B deploy "$TARGET"
    
    VERSION_INFO="$TARGET"
fi

echo "📦 Устанавливаем зависимости..."
pip install --user -r requirements.txt

echo "🔄 Перезапускаем сервис $SERVICE_NAME..."
systemctl --user restart "$SERVICE_NAME"

echo "✅ Обновление до версии $VERSION_INFO выполнено успешно!"