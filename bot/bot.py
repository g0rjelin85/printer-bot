import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message

# === Логирование (ротация файлов) ===
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "printerbot.log")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers.clear()
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=10, encoding="utf-8")
_file_handler.setFormatter(_formatter)
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_formatter)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)

# === Конфигурация ===
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
if not os.path.exists(CONFIG_PATH):
    logger.critical("Не найден config/config.json. Завершаем работу.")
    sys.exit("❌ Не найден config/config.json.")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BOT_TOKEN = CONFIG["BOT_TOKEN"]
PROJECT_PATH = CONFIG["PROJECT_PATH"]
ALLOWED_USERS = CONFIG["ALLOWED_USERS"]
SERVICE_NAME = CONFIG["SERVICE_NAME"]
BOT_ADMIN_ID = CONFIG.get("BOT_ADMIN_ID")  # необязательно; при наличии также дает право

# === Router ===
router = Router()


def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{"".join(re.escape(c) for c in escape_chars)}])', r'\\\1', text)


def fetch_tags() -> None:
    try:
        logger.info("Подтягиваем теги с GitHub...")
        subprocess.run(["git", "fetch", "--tags"], cwd=PROJECT_PATH, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при git fetch --tags: {e}")


def get_latest_tags(limit: int = 5) -> list:
    fetch_tags()
    try:
        # Получаем все теги отсортированные по дате создания
        result = subprocess.run(
            ["git", "tag", "--sort=-creatordate"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True,
            check=True,
        )
        tags = [t for t in result.stdout.strip().split("\n") if t]
        return tags[:limit]
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при получении тегов: {e}")
        return []


def get_current_version() -> str:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "неизвестно"


def get_systemd_status() -> dict:
    try:
        active_res = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            check=True,
        )
        is_active = active_res.stdout.strip() == "active"
        show_res = subprocess.run(
            ["systemctl", "--user", "show", SERVICE_NAME, "--property=ActiveState,SubState,LoadState"],
            capture_output=True,
            text=True,
            check=True,
        )
        status_info = {}
        for line in show_res.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                status_info[k] = v
        return {
            "is_active": is_active,
            "active_state": status_info.get("ActiveState", "unknown"),
            "sub_state": status_info.get("SubState", "unknown"),
            "load_state": status_info.get("LoadState", "unknown"),
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при проверке статуса systemd: {e}")
        return {"is_active": False, "active_state": "error", "sub_state": "error", "load_state": "error"}


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    version = get_current_version()
    await message.answer(
        f"👋 Привет! Я *Printer Bot*.\n📦 Текущая версия: *{escape_markdown(version)}*\n\nИспользуйте /help для просмотра всех команд.",
        parse_mode="Markdown",
    )
    logger.info(f"/start вызван пользователем {message.from_user.id}")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    help_text = (
        "🤖 *Printer Bot - Справка по командам*\n\n"
        "📋 *Основные команды:*\n"
        "/start - Запуск бота и приветствие\n"
        "/help - Показать эту справку\n"
        "/version - Показать текущую версию\n"
        "/status - Статус systemd сервиса и uptime\n\n"
        "🏷️ *Управление версиями:*\n"
        "/tags - Показать все доступные теги\n"
        "/update - Показать 5 последних тегов для обновления\n"
        "/update <tag> - Обновить до указанного тега\n\n"
        "🔧 *Управление сервисом:*\n"
        "/restart - Перезапустить systemd сервис\n\n"
        "⚠️ *Важно:*\n"
        "• Команды /update и /restart перезапускают бота\n"
        "• После выполнения этих команд бот завершится и перезапустится автоматически\n"
        "• Используйте /status для проверки состояния после перезапуска\n\n"
        "🔧 *Техническая информация:*\n"
        "• Обновление выполняется по тегам через scripts/update_bot.sh\n"
    )
    await message.answer(help_text, parse_mode="Markdown")


@router.message(Command("version"))
async def cmd_version(message: Message) -> None:
    v = get_current_version()
    await message.answer(f"📦 Текущая версия: *{escape_markdown(v)}*", parse_mode="Markdown")


@router.message(Command("tags"))
async def cmd_tags(message: Message) -> None:
    tags = get_latest_tags(limit=100)  # полный список может быть большим; ограничим разумно
    if tags:
        await message.answer("📄 Доступные теги:\n" + "\n".join(tags))
    else:
        await message.answer("❌ Не удалось получить список тегов.")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    status = get_systemd_status()
    version = get_current_version()
    status_emoji = "🟢" if status["is_active"] else "🔴"
    status_text = "активен" if status["is_active"] else "неактивен"
    reply = (
        "📊 *Статус Printer Bot*\n\n"
        f"{status_emoji} **Systemd сервис:** {status_text}\n"
        f"📦 **Текущая версия:** `{escape_markdown(version)}`\n"
        f"🔧 Состояние: `{status['active_state']}` / `{status['sub_state']}`\n"
        f"Загружен: `{status['load_state']}`"
    )
    await message.answer(reply, parse_mode="Markdown")


def _ensure_allowed(user_id: int) -> bool:
    # Разрешаем, если пользователь в списке ALLOWED_USERS или равен BOT_ADMIN_ID (если задан)
    if BOT_ADMIN_ID is not None and str(user_id) == str(BOT_ADMIN_ID):
        return True
    return user_id in ALLOWED_USERS


@router.message(Command("restart"))
async def cmd_restart(message: Message) -> None:
    if not _ensure_allowed(message.from_user.id):
        await message.answer("🚫 У вас нет прав для выполнения этой команды.")
        return
    try:
        await message.answer("🔄 Перезапуск сервиса Printer Bot...")
        update_script = os.path.join(PROJECT_PATH, "scripts", "update_bot.sh")
        subprocess.Popen(
            ["nohup", "bash", update_script, "restart"],
            cwd=PROJECT_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Команда перезапуска отправлена через update_bot.sh, завершаем процесс")
        os._exit(0)
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /restart: {e}")
        await message.answer(f"❌ Ошибка при перезапуске: {e}")
        sys.exit(1)


@router.message(Command("update"))
async def cmd_update(message: Message) -> None:
    if not _ensure_allowed(message.from_user.id):
        await message.answer("🚫 У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split(maxsplit=1)
    tag = args[1].strip() if len(args) > 1 else None

    try:
        if not tag or tag.lower() == "latest":
            last_tags = get_latest_tags(limit=5)
            if not last_tags:
                await message.answer("❌ Не удалось определить доступные теги для обновления.")
                return
            formatted = "\n".join(f"- {t}" for t in last_tags)
            await message.answer(
                "🏷️ Последние доступные теги:\n\n" + formatted + "\n\n" +
                "Укажите тег командой: `/update <tag>`",
                parse_mode="Markdown",
            )
            return

        # Проверяем, что тег существует
        fetch_tags()
        check = subprocess.run(
            ["git", "tag", "-l", tag],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True,
            check=True,
        )
        if not check.stdout.strip():
            await message.answer(f"❌ Тег *{escape_markdown(tag)}* не найден.", parse_mode="Markdown")
            return

        await message.answer(f"🔄 Обновление до версии *{escape_markdown(tag)}*...", parse_mode="Markdown")
        update_script = os.path.join(PROJECT_PATH, "scripts", "update_bot.sh")
        subprocess.Popen(
            ["nohup", "bash", update_script, tag],
            cwd=PROJECT_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"Команда обновления до {tag} отправлена через update_bot.sh, завершаем процесс")
        os._exit(0)
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /update: {e}")
        await message.answer(f"❌ Ошибка при обновлении: {e}")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Запуск Printer Bot (aiogram 3)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())