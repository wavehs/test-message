"""
Overlay-получатель сообщений (Windows).
Показывает текст в правом нижнем углу экрана на 2 секунды.
Текст отображается поверх всех окон без рамки — только текст.
"""

import asyncio
import websockets
import tkinter as tk
import threading
import queue
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

# URL сервера — замени YOUR-APP на реальное имя после деплоя на Render
SERVER_URL = os.environ.get(
    "RELAY_SERVER_URL",
    "wss://test-message-xc4m.onrender.com/ws/receive"
)

# Настройки отображения
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 14
TEXT_COLOR = "#FFFFFF"
DISPLAY_DURATION_MS = 2000  # 2 секунды
MAX_TEXT_WIDTH = 400  # Максимальная ширина текста в пикселях
MARGIN_RIGHT = 20  # Отступ от правого края
MARGIN_BOTTOM = 60  # Отступ от нижнего края (выше панели задач)


class OverlayNotification:
    """
    Прозрачное overlay-окно для показа текста в правом нижнем углу экрана.
    
    Работает так:
    - Создаёт невидимое окно с прозрачным фоном
    - При получении сообщения показывает текст поверх всех окон
    - Через 2 секунды скрывает текст
    - Окно не перехватывает клики мыши
    """

    def __init__(self):
        self.msg_queue = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()  # Скрываем главное окно
        self._hide_timer_id = None
        self._setup_overlay()

    def _setup_overlay(self):
        """Создание и настройка overlay-окна."""
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)            # Без рамки и заголовка
        self.overlay.attributes('-topmost', True)       # Поверх всех окон
        self.overlay.attributes('-alpha', 0.0)          # Начинаем полностью прозрачным

        # Прозрачный фон — Windows-специфичная фича
        # Используем необычный цвет, чтобы не совпадал с текстом
        self._bg_color = '#010101'
        self.overlay.configure(bg=self._bg_color)
        self.overlay.attributes('-transparentcolor', self._bg_color)

        # Текстовая метка
        self.label = tk.Label(
            self.overlay,
            text="",
            font=(FONT_FAMILY, FONT_SIZE),
            fg=TEXT_COLOR,
            bg=self._bg_color,
            wraplength=MAX_TEXT_WIDTH,
            justify='right'
        )
        self.label.pack(padx=10, pady=5)

        self.overlay.withdraw()  # Скрываем до первого сообщения

    def show_message(self, text):
        """Показать сообщение в правом нижнем углу на DISPLAY_DURATION_MS миллисекунд."""
        # Отменяем предыдущий таймер скрытия, если есть
        if self._hide_timer_id is not None:
            self.overlay.after_cancel(self._hide_timer_id)
            self._hide_timer_id = None

        # Обновляем текст
        self.label.config(text=text)
        self.overlay.update_idletasks()

        # Вычисляем позицию — правый нижний угол
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = self.label.winfo_reqwidth() + 20
        win_h = self.label.winfo_reqheight() + 10
        x = screen_w - win_w - MARGIN_RIGHT
        y = screen_h - win_h - MARGIN_BOTTOM

        self.overlay.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.overlay.deiconify()
        self.overlay.attributes('-alpha', 0.9)

        logger.info(f"💬 Показано: '{text}'")

        # Запланировать скрытие
        self._hide_timer_id = self.overlay.after(DISPLAY_DURATION_MS, self._hide)

    def _hide(self):
        """Скрыть overlay."""
        self._hide_timer_id = None
        self.overlay.attributes('-alpha', 0.0)
        self.overlay.withdraw()

    def check_queue(self):
        """
        Проверяем очередь сообщений из WebSocket-потока.
        Вызывается каждые 100 мс из главного потока tkinter.
        """
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self.show_message(msg)
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def run(self):
        """Запуск main loop tkinter."""
        self.root.after(100, self.check_queue)
        self.root.mainloop()


async def websocket_listener(msg_queue: queue.Queue):
    """
    Подключаемся к relay-серверу и слушаем входящие сообщения.
    При разрыве соединения автоматически переподключаемся.
    """
    while True:
        try:
            logger.info(f"⏳ Подключение к {SERVER_URL}...")
            async with websockets.connect(SERVER_URL, ping_interval=20) as ws:
                logger.info("✅ Подключено к серверу. Ожидаю сообщений...")

                async for message in ws:
                    message = message.strip()
                    if message:
                        logger.info(f"📩 Получено: '{message}'")
                        msg_queue.put(message)

        except websockets.exceptions.ConnectionClosedError:
            logger.warning("⚠️ Соединение разорвано. Переподключение через 5 сек...")
            await asyncio.sleep(5)
        except ConnectionRefusedError:
            logger.warning("❌ Сервер недоступен. Повтор через 5 сек...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.warning(f"❌ Ошибка: {e}. Повтор через 5 сек...")
            await asyncio.sleep(5)


def start_ws_thread(msg_queue: queue.Queue):
    """Запуск WebSocket-клиента в отдельном потоке."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_listener(msg_queue))


def main():
    print("=" * 50)
    print("📥  ПОЛУЧАТЕЛЬ СООБЩЕНИЙ (OVERLAY)")
    print("=" * 50)
    print(f"Сервер: {SERVER_URL}")
    print(f"Шрифт:  {FONT_FAMILY} {FONT_SIZE}px, цвет: {TEXT_COLOR}")
    print(f"Показ:  {DISPLAY_DURATION_MS}мс")
    print("=" * 50)
    print()

    overlay = OverlayNotification()

    # WebSocket в отдельном потоке (tkinter требует главный поток)
    ws_thread = threading.Thread(
        target=start_ws_thread,
        args=(overlay.msg_queue,),
        daemon=True
    )
    ws_thread.start()

    overlay.run()


if __name__ == "__main__":
    main()
