import json
import subprocess
import os
import sys
import re
import logging
import time
import glob
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === Настройка логирования ===
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "printerbot.log")


def setup_logging():
    """Настраивает логирование с ротацией файлов."""
    # Создаем логгер
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Формат логов
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    
    # Обработчик для файла с ротацией (max 10 файлов по 1 МБ)
    file_handler = RotatingFileHandler(
        LOG_FILE, 
        maxBytes=1024*1024,  # 1 МБ
        backupCount=10,      # максимум 10 файлов
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Добавляем обработчики
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def cleanup_old_logs():
    """Удаляет старые лог-файлы, оставляя только последние 10."""
    try:
        log_pattern = os.path.join(LOG_DIR, "printerbot.log.*")
        log_files = glob.glob(log_pattern)
        
        if len(log_files) > 10:
            # Сортируем по времени модификации (старые первыми)
            log_files.sort(key=os.path.getmtime)
            
            # Удаляем самые старые файлы
            files_to_remove = log_files[:-10]
            for file_path in files_to_remove:
                try:
                    os.remove(file_path)
                    logger.info(f"Удален старый лог-файл: {file_path}")
                except OSError as e:
                    logger.warning(f"Не удалось удалить {file_path}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при очистке старых логов: {e}")


# Инициализируем логирование
logger = setup_logging()
cleanup_old_logs()

# === Загрузка конфигурации ===
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
if not os.path.exists(CONFIG_PATH):
    logger.critical("Не найден config/config.json. Завершаем работу.")
    sys.exit("❌ Не найден config/config.json.")

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

BOT_TOKEN = CONFIG["BOT_TOKEN"]
PROJECT_PATH = CONFIG["PROJECT_PATH"]
ALLOWED_USERS = CONFIG["ALLOWED_USERS"]
SERVICE_NAME = CONFIG["SERVICE_NAME"]


def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{"".join(re.escape(c) for c in escape_chars)}])', r'\\\1', text)


def fetch_tags():
    """Подтягивает все теги с GitHub."""
    try:
        logger.info("Подтягиваем теги с GitHub...")
        subprocess.run(["git", "fetch", "--tags"], cwd=PROJECT_PATH, check=True)
        logger.info("Теги успешно подтянуты.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при git fetch --tags: {e}")


def get_current_version() -> str:
    """Получает текущую версию (тег)."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "неизвестно"


def get_all_tags() -> list:
    fetch_tags()
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=creatordate"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True,
            check=True
        )
        tags = result.stdout.strip().split("\n")
        return [t for t in tags if t]
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при получении тегов: {e}")
        return []


def get_systemd_status() -> dict:
    """Получает статус systemd сервиса."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            check=True
        )
        is_active = result.stdout.strip() == "active"
        
        # Получаем подробную информацию о сервисе
        status_result = subprocess.run(
            ["systemctl", "--user", "show", SERVICE_NAME, "--property=ActiveState,SubState,LoadState"],
            capture_output=True,
            text=True,
            check=True
        )
        
        status_info = {}
        for line in status_result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                status_info[key] = value
        
        return {
            "is_active": is_active,
            "active_state": status_info.get("ActiveState", "unknown"),
            "sub_state": status_info.get("SubState", "unknown"),
            "load_state": status_info.get("LoadState", "unknown")
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при проверке статуса systemd: {e}")
        return {
            "is_active": False,
            "active_state": "error",
            "sub_state": "error", 
            "load_state": "error"
        }


def get_service_uptime() -> str:
    """Получает uptime сервиса."""
    try:
        # Получаем время запуска сервиса
        result = subprocess.run(
            ["systemctl", "--user", "show", SERVICE_NAME, "--property=ActiveEnterTimestamp"],
            capture_output=True,
            text=True,
            check=True
        )
        
        timestamp_line = result.stdout.strip()
        if "ActiveEnterTimestamp=" in timestamp_line:
            timestamp_str = timestamp_line.split("=", 1)[1]
            if timestamp_str and timestamp_str != "n/a":
                try:
                    # Парсим timestamp в формате systemd
                    start_time = datetime.fromisoformat(timestamp_str.replace(" ", "T"))
                    uptime = datetime.now() - start_time
                    
                    days = uptime.days
                    hours, remainder = divmod(uptime.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    if days > 0:
                        return f"{days}д {hours}ч {minutes}м"
                    elif hours > 0:
                        return f"{hours}ч {minutes}м"
                    else:
                        return f"{minutes}м {seconds}с"
                except ValueError:
                    return "неизвестно"
        
        return "неизвестно"
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при получении uptime: {e}")
        return "ошибка"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version = get_current_version()
    await update.message.reply_text(
        f"👋 Привет! Я *Printer Bot*.\n📦 Текущая версия: *{version}*\n\nИспользуйте /help для просмотра всех команд.",
        parse_mode="Markdown"
    )
    logger.info(f"/start вызван пользователем {update.effective_user.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех доступных команд."""
    user_id = update.effective_user.id
    logger.info(f"/help вызван пользователем {user_id}")
    
    help_text = """🤖 *Printer Bot - Справка по командам*

📋 *Основные команды:*
/start - Запуск бота и приветствие
/help - Показать эту справку
/version - Показать текущую версию
/status - Статус systemd сервиса и uptime

🏷️ *Управление версиями:*
/tags - Показать все доступные теги
/update - Обновить до последнего тега
/update <tag> - Обновить до указанного тега

🔧 *Управление сервисом:*
/restart - Перезапустить systemd сервис

⚠️ *Важно:*
• Команды /update и /restart перезапускают бота
• После выполнения этих команд бот завершится и перезапустится автоматически
• Используйте /status для проверки состояния после перезапуска

🔧 *Техническая информация:*
• Бот работает как systemd сервис
• Автоматическое обновление из GitHub по тегам
• Логирование с ротацией файлов
• Безопасные обновления через update_bot.sh

📝 *Права доступа:*
Команды /update и /restart доступны только авторизованным пользователям."""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = get_current_version()
    await update.message.reply_text(f"📦 Текущая версия: *{v}*", parse_mode="Markdown")
    logger.info(f"/version вызван пользователем {update.effective_user.id}, версия {v}")


async def tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_tags = get_all_tags()
    if all_tags:
        await update.message.reply_text("📄 Доступные теги:\n" + "\n".join(all_tags))
        logger.info(f"/tags вызван пользователем {update.effective_user.id}")
    else:
        await update.message.reply_text("❌ Не удалось получить список тегов.")
        logger.warning(f"/tags не удалось получить теги для пользователя {update.effective_user.id}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус systemd сервиса, текущий тег и uptime."""
    user_id = update.effective_user.id
    logger.info(f"/status вызван пользователем {user_id}")
    
    try:
        # Получаем статус systemd
        systemd_status = get_systemd_status()
        current_version = get_current_version()
        uptime = get_service_uptime()
        
        # Формируем сообщение
        status_emoji = "🟢" if systemd_status["is_active"] else "🔴"
        status_text = "активен" if systemd_status["is_active"] else "неактивен"
        
        message = f"""📊 *Статус Printer Bot*

{status_emoji} **Systemd сервис:** {status_text}
📦 **Текущая версия:** `{current_version}`
⏱️ **Uptime:** {uptime}

🔧 **Детали:**
• Состояние: `{systemd_status["active_state"]}`
• Подсостояние: `{systemd_status["sub_state"]}`
• Загружен: `{systemd_status["load_state"]}`"""
        
        await update.message.reply_text(message, parse_mode="Markdown")
        logger.info(f"Статус отправлен пользователю {user_id}: активен={systemd_status['is_active']}, версия={current_version}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при получении статуса: {str(e)}")
        logger.exception(f"Ошибка при выполнении /status: {e}")


async def restart_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапускает systemd сервис через update_bot.sh."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 У вас нет прав для выполнения этой команды.")
        logger.warning(f"/restart попытка от неавторизованного пользователя {user_id}")
        return
    
    logger.info(f"/restart вызван пользователем {user_id}")
    
    try:
        await update.message.reply_text("🔄 Перезапуск сервиса Printer Bot...")
        
        # Используем update_bot.sh для безопасного перезапуска
        update_script = os.path.join(PROJECT_PATH, "scripts", "update_bot.sh")
        subprocess.Popen(
            ["bash", update_script, "restart"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        logger.info(f"Команда перезапуска отправлена через update_bot.sh, завершаем процесс")
        sys.exit(0)
        
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /restart: {e}")
        await update.message.reply_text(f"❌ Ошибка при перезапуске: {str(e)}")
        # Даже при ошибке пытаемся завершиться для перезапуска
        sys.exit(1)


async def update_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 У вас нет прав для выполнения этой команды.")
        logger.warning(f"/update попытка от неавторизованного пользователя {user_id}")
        return

    target = context.args[0] if context.args else None
    logger.info(f"/update вызван пользователем {user_id}, запрошен тег: {target}")

    try:
        # Определяем цель обновления
        if target and target != "latest":
            # Обновление по конкретному тегу
            logger.info(f"Обновление по тегу {target}")
            
            # Проверяем, существует ли тег
            fetch_tags()  # подтягиваем новые теги
            tag_check = subprocess.run(
                ["git", "tag", "-l", target],
                cwd=PROJECT_PATH,
                capture_output=True,
                text=True,
                check=True
            )
            if not tag_check.stdout.strip():
                await update.message.reply_text(f"❌ Тег *{target}* не найден.", parse_mode="Markdown")
                return
            
            version_info = target
        else:
            # Обновление до последнего тега (по умолчанию)
            logger.info("Обновление до последнего тега")
            version_info = "последний тег"

        # Отправляем сообщение о перезапуске
        await update.message.reply_text(f"🔄 Обновление до версии *{version_info}*...")
        
        # Используем update_bot.sh для безопасного обновления
        update_script = os.path.join(PROJECT_PATH, "scripts", "update_bot.sh")
        cmd = ["bash", update_script]
        if target and target != "latest":
            cmd.append(target)
        
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        logger.info(f"Команда обновления отправлена через update_bot.sh, завершаем процесс для версии {version_info}")
        sys.exit(0)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обновлении: {str(e)}")
        logger.exception(f"Ошибка при выполнении /update: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("tags", tags))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("restart", restart_service))
    app.add_handler(CommandHandler("update", update_repo))

    logger.info("Запуск Printer Bot...")
    app.run_polling()


if __name__ == "__main__":
    main()