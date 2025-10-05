#!/bin/bash
set -euo pipefail

# Локальная функция логирования с отметкой времени
log() { echo ">>> $(date '+%F %T %Z') $*" >> "$LOG_FILE"; }

# Ловим любые ошибки и логируем место падения
on_error() {
  local exit_code=$?
  log "ОШИБКА (exit=$exit_code) на линии $BASH_LINENO: последняя команда: '$BASH_COMMAND'"
  exit $exit_code
}
trap on_error ERR

PROJECT_DIR="$HOME/printer-bot"
SERVICE_NAME="printerbot.service"
PYTHON_PATH="/usr/bin/python3"
LOG_FILE="$PROJECT_DIR/logs/update.log"

mkdir -p "$(dirname "$LOG_FILE")"
echo ">>> $(date) Начинаем обновление" >> "$LOG_FILE"

cd "$PROJECT_DIR"
log "git remote -v"
git remote -v >> "$LOG_FILE" 2>&1 || true
log "git status (до fetch)"
git status >> "$LOG_FILE" 2>&1 || true

log "Обновляем удалённые ссылки и теги (timeout 120s)"
timeout 120 git fetch --all --prune >> "$LOG_FILE" 2>&1
timeout 120 git fetch --tags --force >> "$LOG_FILE" 2>&1
log "fetch завершён"

if [ -n "$1" ] && [ "$1" != "restart" ]; then
  TAG="$1"
else
  TAG=$(git describe --tags $(git rev-list --tags --max-count=1))
fi

log "Проверяем существование тега: $TAG"
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  log "Ошибка: тег $TAG не найден в репозитории"
  exit 1
fi

log "Сбрасываем локальные изменения (reset --hard)"
git reset --hard >> "$LOG_FILE" 2>&1 || true
log "Удаляем неотслеживаемые файлы (clean -fd)"
git clean -fd >> "$LOG_FILE" 2>&1 || true

log "Обновляем ветку deploy на тег $TAG"
git checkout -B deploy "tags/$TAG" >> "$LOG_FILE" 2>&1
log "Текущая ветка: $(git branch --show-current)"

log "Устанавливаем зависимости..."
$PYTHON_PATH -m pip install --user -r requirements.txt >> "$LOG_FILE" 2>&1

log "daemon-reload и рестарт сервиса"
systemctl --user daemon-reload >> "$LOG_FILE" 2>&1 || true
systemctl --user restart "$SERVICE_NAME" >> "$LOG_FILE" 2>&1

log "Обновление завершено успешно"