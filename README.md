# 📨 Test Message — Отправка сообщений Mac → Windows

Система для отправки текстовых сообщений с MacBook на Windows через интернет.  
Сообщения появляются на Windows как плавающий текст в правом нижнем углу экрана на 2 секунды.

## Архитектура

```
MacBook (CLI) → [Интернет] → Relay-сервер (Render) → [Интернет] → Windows (Overlay)
```

## Быстрый старт

### 1. Деплой сервера на Render

1. Залей проект на GitHub
2. Зайди на [render.com](https://render.com) → New → Web Service
3. Подключи репозиторий
4. Настройки:
   - **Root Directory**: `server`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
5. Запомни URL: `https://your-app.onrender.com`

### 2. Настройка отправителя (macOS)

```bash
cd sender
pip install -r requirements.txt

# Указываем URL сервера
export RELAY_SERVER_URL="wss://your-app.onrender.com/ws/send"

# Запускаем
python send.py
```

### 3. Настройка получателя (Windows)

```powershell
cd receiver
pip install -r requirements.txt

# Указываем URL сервера
set RELAY_SERVER_URL=wss://your-app.onrender.com/ws/receive

# Запускаем
python receive.py
```

## Использование

1. На Windows запусти `receive.py` — он подключится к серверу и будет ждать сообщений
2. На Mac запусти `send.py` — пиши текст и жми Enter
3. Текст появится на Windows в правом нижнем углу на 2 секунды

## Локальный тест

Можно проверить работу без деплоя:

```bash
# Терминал 1 — сервер
cd server
pip install -r requirements.txt
uvicorn main:app --port 8000

# Терминал 2 — отправитель
cd sender
pip install -r requirements.txt
RELAY_SERVER_URL="ws://localhost:8000/ws/send" python send.py

# Терминал 3 — получатель (на Windows или для теста на Mac)
cd receiver
pip install -r requirements.txt
RELAY_SERVER_URL="ws://localhost:8000/ws/receive" python receive.py
```

## Настройки получателя

В файле `receiver/receive.py` можно изменить:

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `FONT_FAMILY` | `Segoe UI` | Шрифт текста |
| `FONT_SIZE` | `14` | Размер шрифта |
| `TEXT_COLOR` | `#FFFFFF` | Цвет текста |
| `DISPLAY_DURATION_MS` | `2000` | Время показа (мс) |
| `MAX_TEXT_WIDTH` | `400` | Макс. ширина текста (px) |

## 🚨 Экстренная кнопка (Panic Button)

При каждом запуске получателя (`receive.py` или `run.bat`) программа предлагает назначить или подтвердить экстренную клавишу:
- **Выбор клавиши**: можно нажать любую клавишу (например, `F12`, `Esc`, `Pause`, `~`) или сочетание (`Ctrl+Q`, `Alt+X`).
- **Быстрый старт**: если клавиша уже настраивалась ранее, достаточно нажать `Enter`, чтобы использовать предыдущую.
- **Однократное нажатие**: немедленно скрывает текущее отображаемое на экране сообщение.
- **Удержание кнопки**: пока кнопка зажата, экран остаётся чистым, а все поступающие в этот момент сообщения отбрасываются и не сохраняются.
- **Отпускание кнопки**: показ возобновляется в обычном режиме для последующих входящих сообщений.


## Структура

```
test-message/
├── server/              # Relay-сервер
│   ├── main.py
│   ├── requirements.txt
│   └── Procfile
├── sender/              # CLI-отправитель (macOS)
│   ├── send.py
│   └── requirements.txt
├── receiver/            # Overlay-получатель (Windows)
│   ├── receive.py
│   └── requirements.txt
└── README.md
```
