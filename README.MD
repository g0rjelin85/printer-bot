# Printer Bot

Telegram-бот для домашнего сервера с автообновлением из GitHub по последнему тегу.

## Возможности
- `/start` — приветствие + текущая версия
- `/version` — показать текущую версию (git tag)
- `/update` — обновить до последнего тега и перезапустить

## Установка
```bash
git clone https://github.com/yourname/printer-bot.git
cd printer-bot
pip install -r requirements.txt
```

🚀 Команды
Команда	Описание
/version	Показать текущую версию (тег)
/tags	Получить список тегов из GitHub
/update	Обновить бот до последнего тега
/update <tag>	Обновить до указанного тега
/restart	Перезапустить бот вручную
🧩 Обновление вручную

Если бот не отвечает:

cd ~/printer-bot
bash update_bot.sh

📜 Логи

Лог работы: printer-bot/bot.log

Лог обновлений: printer-bot/logs/update.log

🛠️ Примечания

Работает под user-level systemd:

systemctl --user status printerbot.service


Перезапуск после обновления выполняется безопасно через nohup.

Обновление происходит только по тегам (git fetch --tags + git checkout tags/<tag>).
