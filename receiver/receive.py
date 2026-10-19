"""
Overlay-получатель сообщений (Windows).
Показывает текст в правом нижнем углу экрана на 2 секунды.
Текст отображается поверх всех окон без рамки — только текст.

Особенности:
- При запуске в консоли настраивается экстренная кнопка (любая клавиша или сочетание).
- Затем пользователь задаёт процент прозрачности текста (0% — непрозрачный, 100% — полностью прозрачный).
- После ввода консоль автоматически скрывается, приложение переходит в фоновый режим и размещается в System Tray.
- Экстренная кнопка:
  • Нажатие: текущее сообщение мгновенно исчезает.
  • Удержание: экран чист, новые сообщения отбрасываются.
  • Отпускание: возобновление обычного показа.
- Из иконки в Tray можно показать/скрыть консоль или закрыть приложение.
"""

import asyncio
import websockets
import tkinter as tk
import threading
import queue
import os
import sys
import time
import json
import logging
import ctypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

# Попытка импорта библиотеки keyboard для глобального перехвата клавиш
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except (ImportError, Exception):
    KEYBOARD_AVAILABLE = False

# Попытка импорта pystray и Pillow для работы с системным треем
try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except (ImportError, Exception):
    PYSTRAY_AVAILABLE = False

# URL сервера
SERVER_URL = os.environ.get(
    "RELAY_SERVER_URL",
    "wss://test-message-xc4m.onrender.com/ws/receive"
)

# Путь к файлу конфигурации
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Настройки отображения
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 14
TEXT_COLOR = "#FFFFFF"
DISPLAY_DURATION_MS = 2000  # 2 секунды
MAX_TEXT_WIDTH = 400        # Максимальная ширина текста в пикселях
MARGIN_RIGHT = 20           # Отступ от правого края
MARGIN_BOTTOM = 60          # Отступ от нижнего края (выше панели задач)


def hide_console():
    """Скрыть окно консоли на Windows."""
    try:
        if sys.platform == "win32":
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
    except Exception as e:
        logger.debug(f"Не удалось скрыть консоль: {e}")


def show_console():
    """Показать окно консоли на Windows."""
    try:
        if sys.platform == "win32":
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5
                ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception as e:
        logger.debug(f"Не удалось показать консоль: {e}")


def load_config() -> dict:
    """Загрузить конфигурацию из config.json."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Не удалось прочитать {CONFIG_FILE}: {e}")
    return {}


def save_config(key: str, value):
    """Сохранить параметр в config.json."""
    try:
        data = load_config()
        data[key] = value
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Не удалось сохранить {key} в {CONFIG_FILE}: {e}")


def setup_emergency_hotkey() -> str:
    """
    Запрос выбора экстренной кнопки у пользователя при запуске.
    Пользователь нажимает любую клавишу или сочетание.
    """
    config = load_config()
    saved_key = str(config.get("emergency_hotkey", "")).strip()

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
            save_config("emergency_hotkey", chosen_hotkey)
            print(f"--> Установлена и сохранена новая кнопка: [{chosen_hotkey.upper()}]")
        else:
            chosen_hotkey = saved_key or "f12"
            print(f"--> Выбрана кнопка по умолчанию: [{chosen_hotkey.upper()}]")
    else:
        print("⚠️ Модуль 'keyboard' недоступен или запуск произведён не на Windows.")
        prompt_text = f"Введите название кнопки (Enter для '{saved_key or 'f12'}'): "
        try:
            entered = input(prompt_text).strip().lower()
            chosen_hotkey = entered if entered else (saved_key or "f12")
            save_config("emergency_hotkey", chosen_hotkey)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Выход.")
            sys.exit(0)

    print(f"✅ Экстренная кнопка готова: [{chosen_hotkey.upper()}]")
    print("   • Однократное нажатие — скрыть текущее сообщение")
    print("   • Удержание кнопки   — блокировать новые сообщения")
    print("   • Отпускание кнопки  — возобновить показ новых сообщений")
    print("=" * 60)
    print()

    return chosen_hotkey


def setup_transparency() -> int:
    """
    Запрос прозрачности выводимого текста у пользователя при запуске.
    0 - ноль прозрачности (полная видимость, 100% непрозрачный).
    100 - 100% прозрачности (полная прозрачность).
    """
    config = load_config()
    saved_val = config.get("transparency", 10)
    try:
        default_val = int(saved_val)
    except (ValueError, TypeError):
        default_val = 10

    print("=" * 60)
    print("👁️  НАСТРОЙКА ПРОЗРАЧНОСТИ ТЕКСТА")
    print("=" * 60)
    print("Укажите уровень прозрачности выводимого текста (от 0 до 100):")
    print("   • 0   = 0% прозрачности (полностью непрозрачный / максимальная яркость)")
    print("   • 100 = 100% прозрачности (полная прозрачность / невидим)")
    print(f"Введите значение [Enter для {default_val}%]: ", end="", flush=True)

    try:
        val_str = input().strip()
        if not val_str:
            chosen = default_val
        else:
            chosen = int(val_str)
            if chosen < 0 or chosen > 100:
                print(f"Значение вне диапазона [0..100]. Использовано: {default_val}%")
                chosen = default_val
    except ValueError:
        print(f"Некорректный ввод. Использовано значение: {default_val}%")
        chosen = default_val
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Выход.")
        sys.exit(0)

    save_config("transparency", chosen)
    alpha = (100.0 - chosen) / 100.0
    print(f"--> Установлена прозрачность: {chosen}% (видимость: {int(alpha * 100)}%)")
    print("=" * 60)
    print()
    return chosen


def create_tray_icon_image(size=64):
    """Генерация стильной векторной иконки для системного трея с помощью Pillow."""
    if not PYSTRAY_AVAILABLE:
        return None

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Круглый фон
    draw.ellipse((4, 4, size - 4, size - 4), fill="#1E1E2E")
    # Рамка
    draw.ellipse((4, 4, size - 4, size - 4), outline="#585B70", width=2)
    # Внутренняя акцентная точка статуса (зелёный онлайн)
    draw.ellipse((size // 4, size // 4, size * 3 // 4, size * 3 // 4), fill="#00D26A")

    return image


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
                logger.info(f"🚨 [ЭКСТРЕННАЯ КНОПКА] Зажата [{self.hotkey.upper()}]. Вывод скрыт.")
                if self.on_activate:
                    self.on_activate()
            elif not pressed and self.is_active:
                self.is_active = False
                logger.info(f"🟢 [ЭКСТРЕННАЯ КНОПКА] Отпущена [{self.hotkey.upper()}]. Вывод возобновлён.")
                if self.on_deactivate:
                    self.on_deactivate()

    def is_blocked(self) -> bool:
        """
        Проверка, заблокирован ли вывод в данный момент.
        Синхронизирует флаг с фактическим физическим состоянием клавиши.
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
    """

    def __init__(self, emergency_manager: EmergencyManager = None, transparency_pct: int = 10):
        self.emergency_manager = emergency_manager
        self.transparency_pct = transparency_pct
        # Пересчёт прозрачности (0..100) в alpha (1.0..0.0)
        self.alpha_value = max(0.0, min(1.0, (100.0 - float(transparency_pct)) / 100.0))

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
        self.overlay.attributes('-alpha', 0.0)          # Начинаем полностью скрытым

        # Прозрачный фон для Windows
        self._bg_color = '#010101'
        self.overlay.configure(bg=self._bg_color)
        try:
            self.overlay.attributes('-transparentcolor', self._bg_color)
        except tk.TclError:
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

        self.overlay.withdraw()

    def show_message(self, text: str):
        """Показать сообщение в правом нижнем углу с заданной прозрачностью."""
        if self.emergency_manager and self.emergency_manager.is_blocked():
            logger.info(f"🚫 Экстренный режим активен. Сообщение отброшено: '{text}'")
            return

        if self._hide_timer_id is not None:
            self.overlay.after_cancel(self._hide_timer_id)
            self._hide_timer_id = None

        self.label.config(text=text)
        self.overlay.update_idletasks()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = self.label.winfo_reqwidth() + 20
        win_h = self.label.winfo_reqheight() + 10
        x = screen_w - win_w - MARGIN_RIGHT
        y = screen_h - win_h - MARGIN_BOTTOM

        self.overlay.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.overlay.deiconify()
        # Применяем вычисленный уровень непрозрачности
        self.overlay.attributes('-alpha', self.alpha_value)

        logger.info(f"💬 Показано (прозрачность {self.transparency_pct}%): '{text}'")

        self._hide_timer_id = self.overlay.after(DISPLAY_DURATION_MS, self._hide)

    def _hide(self):
        """Обычное скрытие overlay по таймеру."""
        self._hide_timer_id = None
        self.overlay.attributes('-alpha', 0.0)
        self.overlay.withdraw()

    def emergency_hide(self):
        """Мгновенно скрыть оверлей при нажатии экстренной кнопки."""
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

        # Очищаем очередь от всех накопившихся сообщений
        while not self.msg_queue.empty():
            try:
                self.msg_queue.get_nowait()
            except queue.Empty:
                break

    def check_queue(self):
        """Проверка очереди сообщений каждые 50 мс."""
        if self.emergency_manager and self.emergency_manager.is_blocked():
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


class TrayController:
    """Управление иконкой приложения в системном трее (System Tray)."""

    def __init__(self, overlay: OverlayNotification, emergency_manager: EmergencyManager, transparency_pct: int):
        self.overlay = overlay
        self.emergency_manager = emergency_manager
        self.transparency_pct = transparency_pct
        self.icon = None
        self._console_visible = False

    def toggle_console(self, icon=None, item=None):
        """Переключить видимость консоли."""
        if self._console_visible:
            hide_console()
            self._console_visible = False
            logger.info("Консоль скрыта")
        else:
            show_console()
            self._console_visible = True
            logger.info("Консоль показана")

    def on_quit(self, icon=None, item=None):
        """Завершить приложение."""
        logger.info("👋 Завершение работы программы...")
        if self.icon:
            self.icon.stop()
        if self.overlay and self.overlay.root:
            self.overlay.root.after_idle(self.overlay.root.destroy)

    def start(self):
        """Запуск трей-иконки в фоновом потоке."""
        if not PYSTRAY_AVAILABLE:
            logger.info("ℹ️ pystray недоступен, трей-иконка не создана")
            return

        try:
            image = create_tray_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem("📩 Получатель сообщений", lambda: None, enabled=False),
                pystray.MenuItem(f"🚨 Экстренная: [{self.emergency_manager.hotkey.upper()}]", lambda: None, enabled=False),
                pystray.MenuItem(f"👁️ Прозрачность: {self.transparency_pct}%", lambda: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("🖥️ Показать/Скрыть консоль", self.toggle_console, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("❌ Выход", self.on_quit)
            )

            self.icon = pystray.Icon(
                "TestMessageReceiver",
                image,
                f"Получатель сообщений (Экстренная: {self.emergency_manager.hotkey.upper()}, Прозрачность: {self.transparency_pct}%)",
                menu=menu
            )
            thread = threading.Thread(target=self.icon.run, daemon=True)
            thread.start()
            logger.info("🟢 Иконка в System Tray успешно запущена")
        except Exception as e:
            logger.warning(f"Не удалось инициализировать System Tray: {e}")

    def stop(self):
        """Остановка трей-иконки."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


async def websocket_listener(msg_queue: queue.Queue, emergency_manager: EmergencyManager):
    """Слушатель WebSocket-сообщений."""
    while True:
        try:
            logger.info(f"⏳ Подключение к {SERVER_URL}...")
            async with websockets.connect(SERVER_URL, ping_interval=20) as ws:
                logger.info("✅ Подключено к серверу. Ожидаю сообщений...")

                async for message in ws:
                    message = message.strip()
                    if not message:
                        continue

                    # Если экстренная кнопка зажата — отбрасываем сразу
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

    # 1. Запрос экстренной кнопки
    chosen_hotkey = setup_emergency_hotkey()

    # 2. Запрос процента прозрачности (0 - 100)
    chosen_transparency = setup_transparency()

    # 3. Инициализация менеджера экстренной кнопки
    emergency_manager = EmergencyManager(hotkey=chosen_hotkey)

    # 4. Инициализация графического оверлея
    overlay = OverlayNotification(
        emergency_manager=emergency_manager,
        transparency_pct=chosen_transparency
    )

    # 5. Привязка обратного вызова экстренного скрытия к GUI-потоку
    emergency_manager.on_activate = lambda: overlay.root.after_idle(overlay.emergency_hide)

    # 6. Запуск мониторинга глобальной экстренной клавиши
    emergency_manager.start()

    # 7. Запуск фоновой иконки в системном трее
    tray = TrayController(
        overlay=overlay,
        emergency_manager=emergency_manager,
        transparency_pct=chosen_transparency
    )
    tray.start()

    # 8. Скрытие окна консоли (перемещение в трей)
    print("🚀 Консоль скрывается. Приложение работает в фоне (System Tray)...")
    time.sleep(1.0)
    hide_console()

    # 9. WebSocket в фоновом потоке
    ws_thread = threading.Thread(
        target=start_ws_thread,
        args=(overlay.msg_queue, emergency_manager),
        daemon=True
    )
    ws_thread.start()

    try:
        # 10. Запуск главного цикла Tkinter
        overlay.run()
    finally:
        emergency_manager.stop()
        tray.stop()


if __name__ == "__main__":
    main()
