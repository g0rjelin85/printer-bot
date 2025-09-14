import json
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import os
import sys
import re

# === Загрузка конфигурации ===
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
if not os.path.exists(CONFIG_PATH):
    sys.exit("❌ Не найден config/config.json. "
             "Скопируйте config/config.json.example в config/config.json и настройте его.")

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

BOT_TOKEN = CONFIG["BOT_TOKEN"]
PROJECT_PATH = CONFIG["PROJECT_PATH"]
ALLOWED_USERS = CONFIG["ALLOWED_USERS"]
SERVICE_NAME = CONFIG["SERVICE_NAME"]


def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{"".join(re.escape(c) for c in escape_chars)}])', r'\\\1', text)


def get_current_version() -> str:
    """Возвращает текущий git-тег (версию)."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=PROJECT_PATH,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return "неизвестно"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version = get_current_version()
    await update.message.reply_text(
        f"👋 Привет! Я *Printer Bot*.\n"
        f"📦 Текущая версия: *{version}*\n\n"
        f"Доступные команды:\n"
        f"/update — обновить и перезапустить\n"
        f"/version — показать текущую версию",
        parse_mode="Markdown"
    )


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = get_current_version()
    await update.message.reply_text(f"📦 Текущая версия: *{v}*", parse_mode="Markdown")


async def update_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 У вас нет прав для выполнения этой команды.")
        return

    try:
        # Подтягиваем теги
        subprocess.run(["git", "fetch", "--tags"], cwd=PROJECT_PATH)

        # Определяем последний тег
        rev_list = subprocess.run(
            ["git", "rev-list", "--tags", "--max-count=1"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True
        )
        commit_hash = rev_list.stdout.strip()
        if not commit_hash:
            await update.message.reply_text("❌ Не удалось определить последний тег.")
            return

        latest_tag = subprocess.run(
            ["git", "describe", "--tags", commit_hash],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True
        )
        tag = latest_tag.stdout.strip()
        if not tag:
            await update.message.reply_text("❌ Не удалось определить последний тег.")
            return

        # Переключаемся на последний тег
        checkout = subprocess.run(
            ["git", "checkout", f"tags/{tag}", "-f"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True
        )
        output = escape_markdown(checkout.stdout + checkout.stderr)

        # Рестарт сервиса
        restart = subprocess.run(
            ["systemctl", "--user", "restart", SERVICE_NAME],
            capture_output=True,
            text=True
        )

        if restart.returncode == 0:
            await update.message.reply_text(
                f"✅ Обновлено до версии *{tag}*.\n```\n{output}\n```",
                parse_mode="Markdown"
            )
        else:
            err_output = escape_markdown(restart.stderr)
            await update.message.reply_text(
                f"⚠️ Обновлено до версии *{tag}*, "
                f"но при перезапуске ошибка:\n```\n{err_output}\n```",
                parse_mode="Markdown"
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обновлении: {escape_markdown(str(e))}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("update", update_repo))

    app.run_polling()


if __name__ == "__main__":
    main()

