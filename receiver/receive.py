"""
Overlay-получатель сообщений (Windows).
Показывает текст в правом нижнем углу экрана на 2 секунды.
Текст отображается поверх всех окон без рамки — только текст.

Включает функцию экстренной кнопки (Panic Button):
- При запуске пользователь нажимает любую клавишу или сочетание для сохранения.
- При нажатии: текущее сообщение немедленно исчезает с экрана.
- При удержании: экран остаётся чистым, новые сообщения отбрасываются и не показываются.
- При отпускании: возобновляется обычный показ входящих сообщений.
"""

import asyncio
import websockets
import tkinter as tk
import threading
import queue
import os
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

# Попытка импорта библиотеки keyboard для глобального перехвата клавиш
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except (ImportError, Exception):
    KEYBOARD_AVAILABLE = False

# URL сервера — замените на ваш адрес при необходимости
SERVER_URL = os.environ.get(
    "RELAY_SERVER_URL",
    "wss://test-message-xc4m.onrender.com/ws/receive"
)

# Путь к файлу конфигурации (сохранение настроек экстренной кнопки)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Настройки отображения
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 14
TEXT_COLOR = "#FFFFFF"
DISPLAY_DURATION_MS = 2000  # 2 секунды
MAX_TEXT_WIDTH = 400        # Максимальная ширина текста в пикселях
MARGIN_RIGHT = 20           # Отступ от правого края
MARGIN_BOTTOM = 60          # Отступ от нижнего края (выше панели задач)


def load_saved_hotkey() -> str:
    """Загрузить ранее сохранённую экстренную кнопку из config.json."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get("emergency_hotkey", "")).strip()
    except Exception as e:
        logger.debug(f"Не удалось прочитать {CONFIG_FILE}: {e}")
    return ""


def save_hotkey(hotkey: str):
    """Сохранить экстренную кнопку в config.json."""
    try:
        data = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["emergency_hotkey"] = hotkey
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Не удалось сохранить hotkey в {CONFIG_FILE}: {e}")


def setup_emergency_hotkey() -> str:
    """
    Запрос выбора экстренной кнопки у пользователя при запуске.
    Пользователь нажимает любую клавишу или сочетание.
    """
    saved_key = load_saved_hotkey()

    print("=" * 60)
    print("🚨  НАСТРОЙКА ЭКСТРЕННОЙ КНОПКИ (PANIC BUTTON)")
    print("=" * 60)

    if KEYBOARD_AVAILABLE:
        if saved_key:
            print(f"Ранее сохранённая кнопка: [{saved_key.upper()}]")
            print("Нажмите новую клавишу/сочетание (или Enter, чтобы оставить сохранённую):")
        else:
            print("Нажмите любую клавишу или сочетание клавиш для экстренной кнопки")
            print("(например: F12, Escape, Pause, Ctrl+Q, Alt+X, Grave/Тильда)...")

        print("Ожидание нажатия...")
        try:
            # Читаем нажатие и отпускание клавиши / комбинации
            pressed_hotkey = keyboard.read_hotkey(suppress=False)
        except KeyboardInterrupt:
            print("\n👋 Выход.")
            sys.exit(0)
        except Exception as e:
            logger.warning(f"Ошибка считывания клавиши: {e}")
            pressed_hotkey = ""

        # Если нажат Enter и есть сохранённая кнопка — оставляем её
        if pressed_hotkey.strip().lower() == "enter" and saved_key:
            chosen_hotkey = saved_key
            print(f"--> Выбрана сохранённая кнопка: [{chosen_hotkey.upper()}]")
        elif pressed_hotkey:
            chosen_hotkey = pressed_hotkey.strip().lower()
            save_hotkey(chosen_hotkey)
            print(f"--> Установлена и сохранена новая кнопка: [{chosen_hotkey.upper()}]")
        else:
            chosen_hotkey = saved_key or "f12"
            print(f"--> Выбрана кнопка по умолчанию: [{chosen_hotkey.upper()}]")
    else:
        # Резервный режим (если keyboard недоступен)
        print("⚠️ Модуль 'keyboard' недоступен или запуск произведён не на Windows.")
        prompt_text = f"Введите название кнопки (Enter для '{saved_key or 'f12'}'): "
        try:
            entered = input(prompt_text).strip().lower()
            chosen_hotkey = entered if entered else (saved_key or "f12")
            save_hotkey(chosen_hotkey)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Выход.")
            sys.exit(0)

    print()
    print(f"✅ Экстренная кнопка готова: [{chosen_hotkey.upper()}]")
    print("   • Нажатие:   мгновенно скрыть текущее сообщение с экрана")
    print("   • Удержание: экран остаётся чистым, новые сообщения отбрасываются")
    print("   • Отпускание: возобновление обычного показа")
    print("=" * 60)
    print()

    return chosen_hotkey


class EmergencyManager:
    """
    Менеджер экстренной кнопки.
    Отслеживает нажатие, удержание и отпускание глобального хоткея.
    """

    def __init__(self, hotkey: str, on_activate=None, on_deactivate=None):
        self.hotkey = hotkey.strip().lower()
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate
        self.is_active = False
        self._lock = threading.Lock()
        self._hook = None

    def start(self):
        """Запуск глобального перехвата событий клавиатуры."""
        if KEYBOARD_AVAILABLE:
            try:
                self._hook = keyboard.hook(self._on_key_event, suppress=False)
                logger.info(f"🛡️ Мониторинг экстренной кнопки [{self.hotkey.upper()}] активен")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось запустить глобальный хук keyboard: {e}")

    def stop(self):
        """Остановка перехвата."""
        if KEYBOARD_AVAILABLE and self._hook:
            try:
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None

    def _on_key_event(self, event):
        """Обработка каждого события клавиатуры в реальном времени."""
        try:
            pressed = keyboard.is_pressed(self.hotkey)
        except Exception:
            return

        with self._lock:
            if pressed and not self.is_active:
                self.is_active = True
                logger.info(f"🚨 [ЭКСТРЕННАЯ КНОПКА] Зажата [{self.hotkey.upper()}]. Вывод скрыт и заблокирован.")
                if self.on_activate:
                    self.on_activate()
            elif not pressed and self.is_active:
                self.is_active = False
                logger.info(f"🟢 [ЭКСТРЕННАЯ КНОПКА] Отпущена [{self.hotkey.upper()}]. Вывод разблокирован.")
                if self.on_deactivate:
                    self.on_deactivate()

    def is_blocked(self) -> bool:
        """
        Проверка, заблокирован ли вывод в данный момент.
        Синхронизирует флаг с фактическим удержанием клавиши.
        """
        if not KEYBOARD_AVAILABLE:
            return self.is_active

        try:
            currently_pressed = keyboard.is_pressed(self.hotkey)
        except Exception:
            currently_pressed = False

        with self._lock:
            if currently_pressed != self.is_active:
                self.is_active = currently_pressed
                if self.is_active:
                    logger.info(f"🚨 [ЭКСТРЕННАЯ КНОПКА] Зажата [{self.hotkey.upper()}].")
                    if self.on_activate:
                        self.on_activate()
                else:
                    logger.info(f"🟢 [ЭКСТРЕННАЯ КНОПКА] Отпущена [{self.hotkey.upper()}].")
                    if self.on_deactivate:
                        self.on_deactivate()
            return self.is_active


class OverlayNotification:
    """
    Прозрачное overlay-окно для показа текста в правом нижнем углу экрана.
    
    Работает так:
    - Создаёт невидимое окно с прозрачным фоном
    - При получении сообщения показывает текст поверх всех окон
    - Через DISPLAY_DURATION_MS скрывает текст
    - При срабатывании экстренной кнопки мгновенно скрывается
    """

    def __init__(self, emergency_manager: EmergencyManager = None):
        self.emergency_manager = emergency_manager
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
        self._bg_color = '#010101'
        self.overlay.configure(bg=self._bg_color)
        try:
            self.overlay.attributes('-transparentcolor', self._bg_color)
        except tk.TclError:
            # На некоторых платформах (например, macOS) transparentcolor не поддерживается
            pass

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

    def show_message(self, text: str):
        """Показать сообщение в правом нижнем углу на DISPLAY_DURATION_MS миллисекунд."""
        # Если экстренная кнопка активна — не показываем
        if self.emergency_manager and self.emergency_manager.is_blocked():
            logger.info(f"🚫 Экстренный режим активен. Сообщение отброшено: '{text}'")
            return

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
        """Обычное скрытие overlay по таймеру."""
        self._hide_timer_id = None
        self.overlay.attributes('-alpha', 0.0)
        self.overlay.withdraw()

    def emergency_hide(self):
        """
        Мгновенно скрыть оверлей при нажатии экстренной кнопки.
        Сбрасывает таймер, прячет окно и очищает очередь сообщений.
        """
        if self._hide_timer_id is not None:
            try:
                self.overlay.after_cancel(self._hide_timer_id)
            except Exception:
                pass
            self._hide_timer_id = None

        try:
            self.overlay.attributes('-alpha', 0.0)
            self.overlay.withdraw()
            self.label.config(text="")
        except Exception:
            pass

        # Очищаем все скопившиеся в очереди сообщения
        while not self.msg_queue.empty():
            try:
                self.msg_queue.get_nowait()
            except queue.Empty:
                break

    def check_queue(self):
        """
        Проверяем очередь сообщений из WebSocket-потока.
        Вызывается каждые 50 мс из главного потока tkinter.
        """
        if self.emergency_manager and self.emergency_manager.is_blocked():
            # Пока кнопка зажата — очищаем всё поступившее, не показываем ничего
            while not self.msg_queue.empty():
                try:
                    self.msg_queue.get_nowait()
                except queue.Empty:
                    break
        else:
            try:
                while True:
                    msg = self.msg_queue.get_nowait()
                    if self.emergency_manager and self.emergency_manager.is_blocked():
                        break
                    self.show_message(msg)
            except queue.Empty:
                pass

        self.root.after(50, self.check_queue)

    def run(self):
        """Запуск главного цикла tkinter."""
        self.root.after(50, self.check_queue)
        self.root.mainloop()


async def websocket_listener(msg_queue: queue.Queue, emergency_manager: EmergencyManager):
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
                    if not message:
                        continue

                    # Если экстренная кнопка удерживается — сразу отбрасываем
                    if emergency_manager and emergency_manager.is_blocked():
                        logger.info(f"🚫 [Экстренный режим] Сообщение отброшено: '{message}'")
                        continue

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


def start_ws_thread(msg_queue: queue.Queue, emergency_manager: EmergencyManager):
    """Запуск WebSocket-клиента в отдельном потоке."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_listener(msg_queue, emergency_manager))


def main():
    print("=" * 60)
    print("📥  ПОЛУЧАТЕЛЬ СООБЩЕНИЙ (OVERLAY)")
    print("=" * 60)
    print(f"Сервер: {SERVER_URL}")
    print(f"Шрифт:  {FONT_FAMILY} {FONT_SIZE}px, цвет: {TEXT_COLOR}")
    print(f"Показ:  {DISPLAY_DURATION_MS}мс")
    print("=" * 60)
    print()

    # 1. Запрос и настройка экстренной кнопки перед подключением
    chosen_hotkey = setup_emergency_hotkey()

    # 2. Инициализация менеджера экстренной кнопки
    emergency_manager = EmergencyManager(hotkey=chosen_hotkey)

    # 3. Инициализация графического оверлея
    overlay = OverlayNotification(emergency_manager=emergency_manager)

    # 4. Привязка обратного вызова: при зажатии кнопки мгновенно прячем окно через GUI-поток
    emergency_manager.on_activate = lambda: overlay.root.after_idle(overlay.emergency_hide)

    # 5. Запуск глобального перехватчика экстренной кнопки
    emergency_manager.start()

    # 6. WebSocket в отдельном потоке (tkinter требует главный поток)
    ws_thread = threading.Thread(
        target=start_ws_thread,
        args=(overlay.msg_queue, emergency_manager),
        daemon=True
    )
    ws_thread.start()

    try:
        # 7. Запуск GUI
        overlay.run()
    finally:
        emergency_manager.stop()


if __name__ == "__main__":
    main()
