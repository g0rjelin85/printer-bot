#!/bin/bash
set -e

PROJECT_DIR="$HOME/printer-bot"
SERVICE_NAME="printerbot.service"
PYTHON_PATH="/usr/bin/python3"
LOG_FILE="$PROJECT_DIR/logs/update.log"

mkdir -p "$(dirname "$LOG_FILE")"
echo ">>> $(date) Начало обновления" >> "$LOG_FILE"

cd "$PROJECT_DIR"
git fetch --tags >> "$LOG_FILE" 2>&1

if [ -n "$1" ] && [ "$1" != "restart" ]; then
  TAG="$1"
else
  TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
fi

echo ">>> Переключаемся на тег $TAG" >> "$LOG_FILE"
git checkout "tags/$TAG" >> "$LOG_FILE" 2>&1

echo ">>> Обновляем зависимости..." >> "$LOG_FILE"
$PYTHON_PATH -m pip install --user -r requirements.txt >> "$LOG_FILE" 2>&1

echo ">>> Перезапуск systemd..." >> "$LOG_FILE"
systemctl --user restart "$SERVICE_NAME" >> "$LOG_FILE" 2>&1

echo ">>> Обновление завершено успешно." >> "$LOG_FILE"
