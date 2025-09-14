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
    sys.exit("❌ Не найден config/config.json. Скопируйте config/config.json.example в config/config.json и настройте его.")

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


def fetch_tags():
    """Подтягивает все теги с GitHub."""
    subprocess.run(["git", "fetch", "--tags"], cwd=PROJECT_PATH)


def get_current_version() -> str:
    """Возвращает текущий git-тег (версию)."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=PROJECT_PATH,
        capture_output=True,
        text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "неизвестно"


def get_all_tags() -> list:
    """Возвращает список всех тегов, отсортированных по времени создания."""
    fetch_tags()  # подтягиваем новые теги перед выводом
    result = subprocess.run(
        ["git", "tag", "--sort=creatordate"],
        cwd=PROJECT_PATH,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        tags = result.stdout.strip().split("\n")
        return [t for t in tags if t]
    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version = get_current_version()
    await update.message.reply_text(
        f"👋 Привет! Я *Printer Bot*.\n"
        f"📦 Текущая версия: *{version}*\n\n"
        f"Доступные команды:\n"
        f"/update [tag] — обновить и перезапустить (по тегу или последнему)\n"
        f"/version — показать текущую версию\n"
        f"/tags — показать доступные версии",
        parse_mode="Markdown"
    )


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = get_current_version()
    await update.message.reply_text(f"📦 Текущая версия: *{v}*", parse_mode="Markdown")


async def tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_tags = get_all_tags()
    if all_tags:
        await update.message.reply_text("📄 Доступные теги:\n" + "\n".join(all_tags))
    else:
        await update.message.reply_text("❌ Не удалось получить список тегов.")


async def update_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 У вас нет прав для выполнения этой команды.")
        return

    tag = context.args[0] if context.args else None  # тег из команды, если указан

    try:
        fetch_tags()  # подтягиваем все новые теги перед обновлением

        # Если тег не указан — используем последний
        if not tag:
            rev_list = subprocess.run(
                ["git", "rev-list", "--tags", "--max-count=1"],
                cwd=PROJECT_PATH,
                capture_output=True,
                text=True
            )
            commit_hash = rev_list.stdout.strip()
            latest_tag = subprocess.run(
                ["git", "describe", "--tags", commit_hash],
                cwd=PROJECT_PATH,
                capture_output=True,
                text=True
            )
            tag = latest_tag.stdout.strip()

        if not tag:
            await update.message.reply_text("❌ Не удалось определить тег для обновления.")
            return

        # Переключение на выбранный тег
        checkout = subprocess.run(
            ["git", "checkout", f"tags/{tag}", "-f"],
            cwd=PROJECT_PATH,
            capture_output=True,
            text=True
        )
        output = escape_markdown(checkout.stdout + checkout.stderr)

        # Перезапуск сервиса
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
                f"⚠️ Обновлено до версии *{tag}*, но при перезапуске ошибка:\n```\n{err_output}\n```",
                parse_mode="Markdown"
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обновлении: {escape_markdown(str(e))}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("tags", tags))
    app.add_handler(CommandHandler("update", update_repo))

    app.run_polling()


if __name__ == "__main__":
    main()

