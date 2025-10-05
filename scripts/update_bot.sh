#!/bin/bash
set -euo pipefail

export PATH="/usr/bin:/usr/local/bin"
export HOME="/home/$(whoami)"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

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
GIT="/usr/bin/git"
SYSTEMCTL="/usr/bin/systemctl"
PYTHON_PATH="/usr/bin/python3"
LOG_FILE="$PROJECT_DIR/logs/update.log"

mkdir -p "$(dirname "$LOG_FILE")"
echo ">>> $(date) Начинаем обновление" >> "$LOG_FILE"

cd "$PROJECT_DIR"
log "git remote -v"
$GIT remote -v >> "$LOG_FILE" 2>&1 || true
log "git status (до fetch)"
$GIT status >> "$LOG_FILE" 2>&1 || true

log "Обновляем удалённые ссылки и теги (timeout 120s)"
timeout 120 $GIT fetch --all --prune >> "$LOG_FILE" 2>&1
timeout 120 $GIT fetch --tags --force >> "$LOG_FILE" 2>&1
log "fetch завершён"

if [ -n "$1" ] && [ "$1" != "restart" ]; then
  TAG="$1"
else
  TAG=$($GIT describe --tags $($GIT rev-list --tags --max-count=1))
fi

log "Проверяем существование тега: $TAG"
if ! $GIT rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  log "Ошибка: тег $TAG не найден в репозитории"
  exit 1
fi

log "Сбрасываем локальные изменения (reset --hard)"
$GIT reset --hard >> "$LOG_FILE" 2>&1 || true
log "Удаляем неотслеживаемые файлы (clean -fd)"
$GIT clean -fd >> "$LOG_FILE" 2>&1 || true

log "Обновляем ветку deploy на тег $TAG"
$GIT checkout -B deploy "tags/$TAG" >> "$LOG_FILE" 2>&1
log "Текущая ветка: $($GIT branch --show-current)"

log "Устанавливаем зависимости..."
$PYTHON_PATH -m pip install --user -r requirements.txt >> "$LOG_FILE" 2>&1

log "daemon-reload и рестарт сервиса"
$SYSTEMCTL --user daemon-reload >> "$LOG_FILE" 2>&1 || true
$SYSTEMCTL --user restart "$SERVICE_NAME" >> "$LOG_FILE" 2>&1

log "Обновление завершено успешно"