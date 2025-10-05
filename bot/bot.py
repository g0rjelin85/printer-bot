import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import socket
import pathlib
from datetime import datetime
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, F, Router, types
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

PRINTER_NAME = CONFIG["printer_name"]          # например "Brother_HL2132R"
TEMP_DIR = CONFIG["temp_dir"]
PRINTER_IP = CONFIG.get("printer_ip", "")
PRINTER_PORT = int(CONFIG.get("printer_port", 9100))

SUPPORTED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
SUPPORTED_PDF_EXT   = {".pdf"}
SUPPORTED_WORD_EXT  = {".doc", ".docx", ".rtf", ".odt"}
SUPPORTED_XL_EXT    = {".xls", ".xlsx", ".csv"}

# === Router ===
router = Router()

def ensure_dirs():
    os.makedirs(TEMP_DIR, exist_ok=True)


def run(cmd, **kwargs):
    """Вспомогательная функция для subprocess с логом ошибок."""
    print(">>>", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def convert_to_pdf(input_path: str) -> str:
    """Преобразует DOC/DOCX/XLS/XLSX/RTF/ODT/CSV → PDF через LibreOffice headless."""
    pdf_path = os.path.splitext(input_path)[0] + ".pdf"
    try:
        run(["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", TEMP_DIR, input_path])
        return pdf_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ошибка конвертации LibreOffice: {e}")


def send_to_printer(path: str):
    """Отправка файла на печать через CUPS (`lp`) или напрямую по IP (RAW-9100)."""
    if PRINTER_IP:
        print(f"Отправка напрямую на {PRINTER_IP}:{PRINTER_PORT}")
        with open(path, "rb") as f:
            data = f.read()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect((PRINTER_IP, PRINTER_PORT))
            s.sendall(data)
    else:
        run(["lp", "-d", PRINTER_NAME, path])


def process_file(input_path: str):
    """Определяет тип и печатает документ."""
    ext = pathlib.Path(input_path).suffix.lower()

    if ext in SUPPORTED_PDF_EXT:
        send_to_printer(input_path)
    elif ext in SUPPORTED_IMAGE_EXT:
        # просто печатаем, CUPS умеет изображения
        send_to_printer(input_path)
    elif ext in SUPPORTED_WORD_EXT | SUPPORTED_XL_EXT:
        pdf_path = convert_to_pdf(input_path)
        send_to_printer(pdf_path)
    else:
        raise RuntimeError(f"Формат '{ext}' не поддерживается.")


@router.message(F.content_type == ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    ensure_dirs()
    doc = message.document  # это aiogram.types.Document
    ext = pathlib.Path(doc.file_name).suffix
    input_path = os.path.join(TEMP_DIR, f"input{ext}")

    try:
        await doc.download(destination=input_path)
        process_file(input_path)
        await message.reply("Документ отправлен на печать ✅")
    except Exception as e:
        msg = f"❌ Не удалось напечатать документ.\nОшибка: {e}"
        await message.reply(msg)
        logger.exception(msg)


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


@router.message(Command(commands=["start"]))
async def cmd_start(message: Message) -> None:
    version = get_current_version()
    await message.answer(
        f"Привет! Я Printer Bot.\nТекущая версия: {version}\n\nИспользуй /help для списка команд."
    )
    logger.info(f"/start вызван пользователем {message.from_user.id}")


@router.message(Command(commands=["help"]))
async def cmd_help(message: Message) -> None:
    help_text = (
        "/start — приветствие\n"
        "/help — список команд\n"
        "/version — текущая версия (git tag)\n"
        "/status — состояние сервиса\n"
        "/tags — все теги\n"
        "/update — показать 5 последних тегов\n"
        "/update <tag> — обновить до указанного тега\n"
        "/restart — перезапустить бота\n"
    )
    await message.answer(help_text)


@router.message(Command(commands=["version"]))
async def cmd_version(message: Message) -> None:
    v = get_current_version()
    await message.answer(f"Текущая версия: {v}")


@router.message(Command(commands=["tags"]))
async def cmd_tags(message: Message) -> None:
    tags = get_latest_tags(limit=100)  # полный список может быть большим; ограничим разумно
    if tags:
        await message.answer("Доступные теги:\n" + "\n".join(tags))
    else:
        await message.answer("Не удалось получить список тегов.")


@router.message(Command(commands=["status"]))
async def cmd_status(message: Message) -> None:
    status = get_systemd_status()
    version = get_current_version()
    status_text = "активен" if status["is_active"] else "неактивен"
    reply = (
        "Статус Printer Bot\n"
        f"Systemd сервис: {status_text}\n"
        f"Текущая версия: {version}\n"
        f"Состояние: {status['active_state']} / {status['sub_state']}\n"
        f"Загружен: {status['load_state']}"
    )
    await message.answer(reply)


def _ensure_allowed(user_id: int) -> bool:
    # Разрешаем, если пользователь в списке ALLOWED_USERS или равен BOT_ADMIN_ID (если задан)
    if BOT_ADMIN_ID is not None and str(user_id) == str(BOT_ADMIN_ID):
        return True
    return user_id in ALLOWED_USERS


@router.message(Command(commands=["restart"]))
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


@router.message(Command(commands=["update"]))
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
                "Последние доступные теги:\n\n" + formatted + "\n\n" +
                "Укажите тег командой: /update <tag>",
            )
            return

        # Проверяем, что тег существует (повышенное логирование)
        fetch_tags()
        logger.info(f"Проверяем наличие тега: {tag}; PROJECT_PATH={PROJECT_PATH}")
        check = subprocess.run(
            ["git", "tag", "-l", tag],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True,
        )
        logger.info(f"git tag -l {tag} -> rc={check.returncode}, out='{check.stdout.strip()}', err='{check.stderr.strip() if check.stderr else ''}'")
        if check.returncode != 0 or not check.stdout.strip():
            await message.answer(f"Тег {tag} не найден.")
            return

        await message.answer(f"Обновление до версии {tag}...")
        update_script = os.path.join(PROJECT_PATH, "scripts", "update_bot.sh")
        log_file = os.path.join(PROJECT_PATH, "logs", "update.log")
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(f"\n>>> {datetime.now().isoformat()} Запуск обновления из бота: tag={tag}, user={message.from_user.id}\n")
                lf.write(f"PROJECT_PATH={PROJECT_PATH}\nSCRIPT={update_script}\n")
        except Exception as le:
            logger.warning(f"Не удалось записать пролог в update.log: {le}")

        cmd = ["nohup", "bash", update_script, tag]
        logger.info(f"Запуск скрипта обновления: cmd={cmd}, cwd={PROJECT_PATH}")
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"update_bot.sh запущен, pid={proc.pid}")
        #logger.info(f"Команда обновления до {tag} отправлена, завершаем процесс")
        #os._exit(0)
    except Exception as e:
        logger.exception(f"Ошибка при выполнении /update: {e}")
        await message.answer(f"❌ Ошибка при обновлении: {e}")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Запуск Printer Bot (aiogram 3)...")
    # Регистрируем команды бота для меню клиента
    try:
        from aiogram.types import BotCommand
        await bot.set_my_commands([
            BotCommand(command="start", description="Приветствие"),
            BotCommand(command="help", description="Список команд"),
            BotCommand(command="version", description="Текущая версия"),
            BotCommand(command="status", description="Статус сервиса"),
            BotCommand(command="tags", description="Все теги"),
            BotCommand(command="update", description="Показать 5 последних тегов"),
            BotCommand(command="restart", description="Перезапуск бота"),
        ])
    except Exception as e:
        logger.warning(f"Не удалось установить команды бота: {e}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())