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

## 🎛️ Мини-приложение, Экстренная кнопка (Panic Button) и Трей

Консоль теперь **вообще не открывается**! Запуск происходит через бесшумный лаунчер `run.vbs` (или `receive.pyw`), открывающий аккуратное мини-приложение:

1. **Экстренная кнопка (Panic Button)**:
   - В мини-приложении отображается текущая кнопка (по умолчанию `[ F12 ]`).
   - Нажмите **«Изменить»**, затем любую клавишу или сочетание на клавиатуре (`F12`, `Escape`, `Pause`, `Ctrl+Q` и т.д.).
   - **Однократное нажатие**: немедленно скрывает текущее отображаемое на экране сообщение.
   - **Удержание кнопки**: экран остаётся чистым, все входящие сообщения отбрасываются.
   - **Отпускание кнопки**: показ возобновляется для последующих сообщений.

2. **Настройка прозрачности**:
   - Ползунок от `0%` (максимальная яркость / 100% видимость) до `90%` (еле заметный текст).
   - Кнопка **«🧪 Тест»** сразу выводит пробный текст в углу экрана, чтобы оценить видимость.

3. **Сворачивание в System Tray**:
   - Кнопка **«📥 Свернуть в трей»** прячет мини-приложение в область уведомлений.
   - Опция **«Сворачивать в трей при запуске»** автоматически сворачивает окно через 5 секунд.
   - Двойной клик по иконке в трее (или пункт «⚙️ Открыть настройки») возвращает окно на экран.
   - При нажатии на крестик `X` приложение не завершается, а сворачивается в трей. Выйти можно через пункт меню трея «❌ Выход из программы».

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
│   ├── run.vbs          # Запуск БЕЗ консоли (рекомендуется)
│   ├── run.bat          # Быстрый bat-лаунчер
│   ├── install.bat      # Установка библиотек
│   ├── receive.pyw      # Прямой запуск pythonw
│   ├── receive.py       # Основной код мини-приложения и оверлея
│   └── requirements.txt # Зависимости (websockets, keyboard, pystray, pillow)
└── README.md
```
