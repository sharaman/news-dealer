# Деплой на облачный VPS

## Варианты запуска по расписанию

**Рекомендую: systemd timer** (надёжнее cron, лучше интеграция с логами).

---

## 1. Подготовка VPS (Ubuntu 22.04+)

```bash
# Установка зависимостей
sudo apt update && sudo apt install -y python3.11 python3.11-venv git

# Создание пользователя для сервиса
sudo useradd -m -s /bin/bash newsagent
sudo su - newsagent

# Клонирование проекта
git clone <your-repo> ~/app
cd ~/app
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Конфигурация окружения

```bash
# На VPS создайте .env из примера
cp .env.example .env
nano .env  # заполните все ключи
```

---

## 3. Systemd сервис для MCP-сервера (постоянно работающий)

Создайте `/etc/systemd/system/newsagent-mcp.service`:

```ini
[Unit]
Description=News Agent MCP Server
After=network.target

[Service]
Type=simple
User=newsagent
WorkingDirectory=/home/newsagent/app
EnvironmentFile=/home/newsagent/app/.env
ExecStart=/home/newsagent/app/.venv/bin/python -m src.mcp_server.server
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now newsagent-mcp
```

---

## 4. Systemd timer для агента (по расписанию)

`/etc/systemd/system/newsagent-run.service`:
```ini
[Unit]
Description=News Agent Run
After=newsagent-mcp.service

[Service]
Type=oneshot
User=newsagent
WorkingDirectory=/home/newsagent/app
EnvironmentFile=/home/newsagent/app/.env
ExecStart=/home/newsagent/app/.venv/bin/python -m src.main --publish
StandardOutput=journal
StandardError=journal
```

`/etc/systemd/system/newsagent-run.timer`:
```ini
[Unit]
Description=Run News Agent every morning at 9:00

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now newsagent-run.timer

# Проверить расписание
systemctl list-timers newsagent-run.timer
```

---

## 5. Просмотр логов

```bash
# Логи агента
journalctl -u newsagent-run.service -f

# Логи MCP сервера
journalctl -u newsagent-mcp.service -f

# Запуск вручную для теста
sudo systemctl start newsagent-run.service
```

---

## 6. Обновление кода

Добавьте скрипт `deploy.sh`:

```bash
#!/bin/bash
cd /home/newsagent/app
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart newsagent-mcp
echo "Deployed at $(date)"
```

---

## Минимальные требования VPS

| Параметр | Минимум |
|---|---|
| RAM | 1 GB |
| CPU | 1 vCPU |
| Диск | 10 GB (ChromaDB растёт) |
| OS | Ubuntu 22.04 |

Провайдеры: **Hetzner CX11** (~4€/мес), **DigitalOcean Droplet** ($6/мес), **Timeweb Cloud** (~200₽/мес).

---

## Что важно проверить перед деплоем

1. `TELEGRAM_BOT_TOKEN` и `TELEGRAM_PUBLISH_CHANNEL` заполнены в `.env`
2. `OPENAI_API_KEY` установлен
3. MCP-сервер доступен изнутри VPS (localhost:8000) — наружу открывать не нужно
4. Порт 8000 закрыт в firewall (`sudo ufw deny 8000`)
