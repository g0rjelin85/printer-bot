import json
import subprocess
import os
import sys
import re
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === Настройка логирования ===
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "printerbot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version = get_current_version()
    await update.message.reply_text(
        f"👋 Привет! Я *Printer Bot*.\n📦 Текущая версия: *{version}*",
        parse_mode="Markdown"
    )
    logger.info(f"/start вызван пользователем {update.effective_user.id}")


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


async def update_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 У вас нет прав для выполнения этой команды.")
        logger.warning(f"/update попытка от неавторизованного пользователя {user_id}")
        return

    tag = context.args[0] if context.args else None
    logger.info(f"/update вызван пользователем {user_id}, запрошен тег: {tag}")

    try:
        fetch_tags()

        # Определяем тег
        if not tag:
            rev_list = subprocess.run(
                ["git", "rev-list", "--tags", "--max-count=1"],
                cwd=PROJECT_PATH,
                capture_output=True,
                text=True,
                check=True
            )
            commit_hash = rev_list.stdout.strip()
            latest_tag = subprocess.run(
                ["git", "describe", "--tags", commit_hash],
                cwd=PROJECT_PATH,
                capture_output=True,
                text=True,
                check=True
            )
            tag = latest_tag.stdout.strip()

        if not tag:
            await update.message.reply_text("❌ Не удалось определить тег для обновления.")
            logger.error("Не удалось определить тег для обновления")
            return

        # Checkout
        logger.info(f"Переключаемся на тег {tag}")
        checkout = subprocess.run(
            ["git", "checkout", f"tags/{tag}", "-f"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True
        )
        logger.info(f"git checkout завершен:\n{checkout.stdout}\n{checkout.stderr}")

        # Перезапуск сервиса
        logger.info(f"Перезапуск systemd сервиса {SERVICE_NAME}")
        restart = subprocess.run(
            ["systemctl", "--user", "restart", SERVICE_NAME],
            capture_output=True,
            text=True
        )

        if restart.returncode == 0:
            await update.message.reply_text(f"✅ Обновлено до версии *{tag}*")
            logger.info(f"Сервис успешно перезапущен, версия {tag}")
        else:
            err_output = restart.stderr
            await update.message.reply_text(f"⚠️ Обновлено до версии *{tag}*, но ошибка при перезапуске")
            logger.error(f"Ошибка при перезапуске сервиса:\n{err_output}")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обновлении: {str(e)}")
        logger.exception(f"Ошибка при выполнении /update: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("tags", tags))
    app.add_handler(CommandHandler("update", update_repo))

    logger.info("Запуск Printer Bot...")
    app.run_polling()


if __name__ == "__main__":
    main()

