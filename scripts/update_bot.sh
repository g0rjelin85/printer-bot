#!/bin/bash
set -euo pipefail

PROJECT_DIR="$HOME/printer-bot"
SERVICE_NAME="printerbot.service"
PYTHON_PATH="/usr/bin/python3"
LOG_FILE="$PROJECT_DIR/logs/update.log"

mkdir -p "$(dirname "$LOG_FILE")"
echo ">>> $(date) Начинаем обновление" >> "$LOG_FILE"

cd "$PROJECT_DIR"
echo ">>> git remote -v" >> "$LOG_FILE"
git remote -v >> "$LOG_FILE" 2>&1 || true
echo ">>> git status" >> "$LOG_FILE"
git status >> "$LOG_FILE" 2>&1 || true

echo ">>> Обновляем удалённые ссылки и теги" >> "$LOG_FILE"
git fetch --all --prune >> "$LOG_FILE" 2>&1
git fetch --tags --force >> "$LOG_FILE" 2>&1

if [ -n "$1" ] && [ "$1" != "restart" ]; then
  TAG="$1"
else
  TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
fi

# Проверяем, что тег существует
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo ">>> Ошибка: тег $TAG не найден в репозитории." >> "$LOG_FILE"
  exit 1
fi

echo ">>> Сбрасываем локальные изменения (reset --hard)" >> "$LOG_FILE"
git reset --hard >> "$LOG_FILE" 2>&1 || true
echo ">>> Удаляем неотслеживаемые файлы (clean -fd)" >> "$LOG_FILE"
git clean -fd >> "$LOG_FILE" 2>&1 || true

echo ">>> Обновляем ветку deploy на тег $TAG" >> "$LOG_FILE"
git checkout -B deploy "tags/$TAG" >> "$LOG_FILE" 2>&1
echo ">>> Текущая ветка: $(git branch --show-current)" >> "$LOG_FILE"

echo ">>> Устанавливаем зависимости..." >> "$LOG_FILE"
$PYTHON_PATH -m pip install --user -r requirements.txt >> "$LOG_FILE" 2>&1

echo ">>> daemon-reload и рестарт сервиса" >> "$LOG_FILE"
systemctl --user daemon-reload >> "$LOG_FILE" 2>&1 || true
systemctl --user restart "$SERVICE_NAME" >> "$LOG_FILE" 2>&1

echo ">>> Обновление завершено успешно." >> "$LOG_FILE"