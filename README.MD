# Printer Bot

Telegram-бот для управления принтером с автообновлением из GitHub.

## Возможности

- **Управление версиями**: Обновление по тегам
- **Мониторинг**: Проверка статуса systemd сервиса и uptime
- **Безопасные обновления**: Без detached HEAD, с автоматическим перезапуском
- **Логирование**: Ротация логов (max 10 файлов по 1 МБ)

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Запуск бота и приветствие |
| `/help` | Показать справку по командам |
| `/version` | Показать текущую версию |
| `/status` | Статус systemd сервиса и uptime |
| `/tags` | Показать все доступные теги |
| `/update` | Обновить до последнего тега |
| `/update <tag>` | Обновить до указанного тега |
| `/restart` | Перезапустить systemd сервис |

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/g0rjelin85/printer-bot.git
cd printer-bot
```

### 2. Настройка конфигурации

```bash
cp config/config.json.example config/config.json
# Отредактируйте config/config.json с вашими данными
```

### 3. Установка зависимостей

```bash
pip install --user -r requirements.txt
```

### 4. Настройка systemd сервиса

```bash
# Скопируйте файл сервиса
cp printerbot.service ~/.config/systemd/user/

# Активируйте сервис
systemctl --user daemon-reload
systemctl --user enable --now printerbot.service
```

## Конфигурация

Файл `config/config.json`:

```json
{
  "BOT_TOKEN": "YOUR_BOT_TOKEN",
  "PROJECT_PATH": "/home/username/printer-bot",
  "ALLOWED_USERS": [123456789],
  "SERVICE_NAME": "printerbot.service",
  "BOT_ADMIN_ID": 123456789
}
```

### Параметры

- `BOT_TOKEN` - Токен Telegram бота от @BotFather
- `PROJECT_PATH` - Путь к проекту на сервере
- `ALLOWED_USERS` - Массив ID пользователей с правами на обновление
- `SERVICE_NAME` - Имя systemd сервиса

## Обновление

### Автоматическое обновление через бота

```bash
/update          # До последнего тега
/update v1.2.3   # До конкретного тега
```

## Release workflow

Рекомендуемый процесс разработки и релизов:

1) Разработка в ветке `develop`
   - Создавайте фичи через PR в `develop`.

2) Подготовка релиза
   - Создайте PR из `develop` в `master`.
   - После ревью смержите в `master`.

3) Создание версии (тега)
   - Текущая версия: `v0.0.6`.
   - Примеры команд:
     ```bash
     git checkout master
     git pull
     git tag -a v0.0.7 -m "Release v0.0.7"
     git push origin v0.0.7
     ```

4) Обновление бота на сервере
   - Через бота: `/update` или `/update v0.0.7`
   - Или вручную: `bash scripts/deploy.sh v0.0.7`

### Ручное обновление

```bash
cd ~/printer-bot
bash scripts/deploy.sh          # До последнего тега
bash scripts/deploy.sh v1.2.3   # До конкретного тега
```

## Мониторинг

### Статус сервиса

```bash
systemctl --user status printerbot.service
```

### Логи

```bash
# Логи сервиса
journalctl --user -u printerbot.service -f

# Логи бота
tail -f logs/printerbot.log

# Логи обновлений
tail -f logs/update.log
```

## Структура проекта

```
printer-bot/
├── bot/
│   ├── __init__.py
│   └── bot.py              # Основной код бота
├── config/
│   └── config.json.example # Пример конфигурации
├── scripts/
│   ├── deploy.sh           # Скрипт развертывания
│   └── update_bot.sh       # Скрипт обновления
├── logs/
│   ├── printerbot.log      # Логи бота (с ротацией)
│   └── update.log          # Логи обновлений
├── printerbot.service      # systemd unit файл
├── requirements.txt        # Python зависимости
└── README.md               # Документация
```

## Архитектура

- **Библиотека**: python-telegram-bot 20.7
- **Сервис**: systemd user-level
- **Обновления**: Git с тегами через update_bot.sh
- **Логирование**: RotatingFileHandler с ротацией

## Безопасность

- Команды обновления доступны только авторизованным пользователям
- Безопасные обновления через update_bot.sh
- Автоматический перезапуск через systemd

## Устранение неполадок

### Бот не отвечает

1. Проверьте статус сервиса:
   ```bash
   systemctl --user status printerbot.service
   ```

2. Перезапустите сервис:
   ```bash
   systemctl --user restart printerbot.service
   ```

3. Проверьте логи:
   ```bash
   journalctl --user -u printerbot.service -n 50
   ```

### Ошибки обновления

1. Проверьте права доступа к репозиторию
2. Убедитесь, что SSH ключи настроены
3. Проверьте наличие тегов:
   ```bash
   git tag -l
   ```

## Лицензия

MIT License