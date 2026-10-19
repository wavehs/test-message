"""
Overlay-получатель сообщений (Windows).
Показывает текст поверх всех окон без рамок.

Особенности:
- Консоль НЕ открывается — всё управление происходит через стильное мини-приложение.
- Вкладка «⚡ Основное»:
  • Экстренная кнопка (Panic Button) для моментального скрытия или блокировки вывода;
  • Прозрачность текста (0% - чёткий, 90% - почти прозрачный);
  • Автосворачивание в трей при запуске.
- Вкладка «🎨 Вид текста»:
  • Выбор расположения на экране (Снизу справа, Снизу слева, Сверху справа, Сверху слева, Снизу по центру, Сверху по центру, По центру);
  • Выбор шрифта (Segoe UI, Arial, Calibri, Consolas, Verdana, Tahoma, Georgia и др.);
  • Выбор размера шрифта (10 - 36 px);
  • Выбор цвета текста (палитра быстрого выбора + пипетка любого цвета);
  • Живое превью текста в реальном времени + кнопка проверки на экране («Тест»).
- Приложение автоматически или по нажатию кнопки сворачивается в системный трей (возле часов).
- Из трея двойным кликом или через меню «Открыть настройки» окно можно вызвать в любой момент.
"""

import asyncio
import websockets
import tkinter as tk
from tkinter import colorchooser
import threading
import queue
import os
import sys
import time
import json
import logging
import ctypes

# 1. Попытка скрыть консоль немедленно (если запуск был через python.exe)
if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


# 2. Безопасные потоки вывода при запуске через pythonw.exe (где stdout/stderr равны None)
class SafeWriter:
    """Безопасный перехватчик вывода, предотвращающий падение pythonw."""
    def __init__(self, target):
        self.target = target

    def write(self, s):
        if self.target and hasattr(self.target, "write"):
            try:
                self.target.write(s)
            except Exception:
                pass

    def flush(self):
        if self.target and hasattr(self.target, "flush"):
            try:
                self.target.flush()
            except Exception:
                pass


if sys.stdout is None:
    sys.stdout = SafeWriter(None)
if sys.stderr is None:
    sys.stderr = SafeWriter(None)

# 3. Настройка логирования в файл receiver.log и в консоль (если доступна)
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receiver.log")
log_handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")]
if sys.stdout and hasattr(sys.stdout, "write"):
    log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers
)
logger = logging.getLogger("Receiver")

# 4. Попытка импорта глобального перехвата клавиш
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except (ImportError, Exception):
    KEYBOARD_AVAILABLE = False
    logger.info("Модуль keyboard недоступен (актуален для Windows с правами пользователя).")

# 5. Попытка импорта pystray и Pillow для работы с System Tray
try:
    import pystray
    from PIL import Image, ImageDraw, ImageTk
    PYSTRAY_AVAILABLE = True
except (ImportError, Exception):
    PYSTRAY_AVAILABLE = False
    logger.info("Модули pystray или Pillow недоступны. Работа в трее будет ограничена.")

# Конфигурация по умолчанию
SERVER_URL = os.environ.get(
    "RELAY_SERVER_URL",
    "wss://test-message-xc4m.onrender.com/ws/receive"
)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Параметры отображения по умолчанию
DEFAULT_FONT_FAMILY = "Segoe UI"
DEFAULT_FONT_SIZE = 14
DEFAULT_TEXT_COLOR = "#FFFFFF"
DEFAULT_POSITION = "bottom-right"
DISPLAY_DURATION_MS = 2000  # 2 секунды
MAX_TEXT_WIDTH = 450
MARGIN_RIGHT = 20
MARGIN_LEFT = 20
MARGIN_BOTTOM = 60
MARGIN_TOP = 40

# Доступные шрифты
AVAILABLE_FONTS = [
    "Segoe UI",
    "Arial",
    "Calibri",
    "Consolas",
    "Verdana",
    "Tahoma",
    "Georgia",
    "Comic Sans MS",
    "Impact",
    "Trebuchet MS"
]

# Доступные расположения на экране
POSITION_NAMES = {
    "bottom-right": "Снизу справа (по умолчанию)",
    "bottom-left": "Снизу слева",
    "top-right": "Сверху справа",
    "top-left": "Сверху слева",
    "bottom-center": "Снизу по центру",
    "top-center": "Сверху по центру",
    "center": "По центру экрана",
}
POSITION_KEYS = list(POSITION_NAMES.keys())

# Палитра быстрых цветов
PRESET_COLORS = [
    ("#FFFFFF", "Белый"),
    ("#00FF66", "Зелёный неон"),
    ("#FFE600", "Жёлтый"),
    ("#00E5FF", "Голубой"),
    ("#FF2A85", "Розовый"),
    ("#FF8800", "Оранжевый"),
    ("#FF3333", "Красный"),
    ("#B388FF", "Фиолетовый"),
]

# Цветовая палитра темной темы интерфейса
THEME = {
    "bg_window": "#13141f",
    "bg_card": "#1c1e2e",
    "bg_card_inner": "#25283d",
    "border_card": "#2d324d",
    "accent_blue": "#3b82f6",
    "accent_blue_hover": "#2563eb",
    "accent_green": "#10b981",
    "accent_green_hover": "#059669",
    "accent_amber": "#f59e0b",
    "accent_red": "#ef4444",
    "text_title": "#f8fafc",
    "text_body": "#e2e8f0",
    "text_muted": "#94a3b8",
    "keycap_bg": "#282c44",
    "keycap_border": "#3e4466",
    "keycap_text": "#38bdf8",
    "tab_active_bg": "#3b82f6",
    "tab_inactive_bg": "#1e2030",
}


def hide_console():
    """Скрыть окно консоли на Windows."""
    try:
        if sys.platform == "win32":
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def load_config() -> dict:
    """Загрузить настройки из config.json."""
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


def create_tray_icon_image(size=64, status="connected"):
    """Генерация иконки для системного трея."""
    if not PYSTRAY_AVAILABLE:
        return None
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, size - 3, size - 3), fill="#181a27")
    draw.ellipse((3, 3, size - 3, size - 3), outline="#454868", width=2)
    if status == "connected":
        dot_color = "#10b981"  # Зелёный
    elif status == "connecting":
        dot_color = "#f59e0b"  # Оранжевый
    else:
        dot_color = "#ef4444"  # Красный
    margin = size // 4
    draw.ellipse((margin, margin, size - margin, size - margin), fill=dot_color)
    return image


class EmergencyManager:
    """
    Менеджер экстренной кнопки (Panic Button).
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
        if KEYBOARD_AVAILABLE and not self._hook:
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

    def set_hotkey(self, new_hotkey: str):
        """Смена горячей клавиши с перезапуском хука."""
        with self._lock:
            self.hotkey = new_hotkey.strip().lower()
            self.is_active = False
        if self._hook:
            self.stop()
            self.start()
        logger.info(f"🔄 Экстренная кнопка обновлена: [{self.hotkey.upper()}]")

    def _on_key_event(self, event):
        """Обработка событий клавиатуры."""
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
        """Проверка, заблокирован ли вывод в данный момент."""
        if not KEYBOARD_AVAILABLE:
            return self.is_active

        try:
            currently_pressed = keyboard.is_pressed(self.hotkey)
        except Exception:
            currently_pressed = False

        with self._lock:
            if currently_pressed != self.is_active:
                self.is_active = currently_pressed
                if self.is_active and self.on_activate:
                    self.on_activate()
                elif not self.is_active and self.on_deactivate:
                    self.on_deactivate()
            return self.is_active


class OverlayNotification:
    """
    Прозрачное overlay-окно для показа текста поверх всех окон.
    Поддерживает настройку расположения, шрифта, размера и цвета.
    """
    def __init__(self, root: tk.Tk, emergency_manager: EmergencyManager = None,
                 transparency_pct: int = 10, font_family: str = DEFAULT_FONT_FAMILY,
                 font_size: int = DEFAULT_FONT_SIZE, text_color: str = DEFAULT_TEXT_COLOR,
                 position: str = DEFAULT_POSITION):
        self.root = root
        self.emergency_manager = emergency_manager
        self.transparency_pct = transparency_pct
        self.alpha_value = max(0.05, min(1.0, (100.0 - float(transparency_pct)) / 100.0))
        self.font_family = font_family
        self.font_size = font_size
        self.text_color = text_color
        self.position = position

        self.msg_queue = queue.Queue()
        self._hide_timer_id = None
        self._setup_overlay()

    def _setup_overlay(self):
        """Создание всплывающего окна."""
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)       # Без рамок
        self.overlay.attributes('-topmost', True)  # Поверх всех окон
        self.overlay.attributes('-alpha', 0.0)

        self._bg_color = '#010101'
        self.overlay.configure(bg=self._bg_color)
        try:
            self.overlay.attributes('-transparentcolor', self._bg_color)
        except tk.TclError:
            pass

        self.label = tk.Label(
            self.overlay,
            text="",
            font=(self.font_family, self.font_size),
            fg=self.text_color,
            bg=self._bg_color,
            wraplength=MAX_TEXT_WIDTH,
            justify='right'
        )
        self.label.pack(padx=10, pady=5)
        self.overlay.withdraw()

    def set_transparency(self, pct: int):
        """Обновить уровень прозрачности."""
        self.transparency_pct = pct
        self.alpha_value = max(0.05, min(1.0, (100.0 - float(pct)) / 100.0))
        if self._hide_timer_id is not None:
            self.overlay.attributes('-alpha', self.alpha_value)

    def update_style(self, font_family=None, font_size=None, text_color=None, position=None):
        """Обновить шрифт, размер, цвет и расположение текста."""
        if font_family is not None:
            self.font_family = font_family
        if font_size is not None:
            self.font_size = font_size
        if text_color is not None:
            self.text_color = text_color
        if position is not None:
            self.position = position

        self.label.config(
            font=(self.font_family, self.font_size),
            fg=self.text_color
        )

    def show_message(self, text: str):
        """Отобразить текст на экране в выбранной позиции."""
        if self.emergency_manager and self.emergency_manager.is_blocked():
            logger.info(f"🚫 Экстренный режим активен. Сообщение отброшено: '{text}'")
            return

        if self._hide_timer_id is not None:
            try:
                self.overlay.after_cancel(self._hide_timer_id)
            except Exception:
                pass
            self._hide_timer_id = None

        self.label.config(
            text=text,
            font=(self.font_family, self.font_size),
            fg=self.text_color
        )
        self.overlay.update_idletasks()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = self.label.winfo_reqwidth() + 24
        win_h = self.label.winfo_reqheight() + 12

        pos = self.position
        if pos == "bottom-left":
            x = MARGIN_LEFT
            y = screen_h - win_h - MARGIN_BOTTOM
            justify = "left"
        elif pos == "top-right":
            x = screen_w - win_w - MARGIN_RIGHT
            y = MARGIN_TOP
            justify = "right"
        elif pos == "top-left":
            x = MARGIN_LEFT
            y = MARGIN_TOP
            justify = "left"
        elif pos == "bottom-center":
            x = max(0, (screen_w - win_w) // 2)
            y = screen_h - win_h - MARGIN_BOTTOM
            justify = "center"
        elif pos == "top-center":
            x = max(0, (screen_w - win_w) // 2)
            y = MARGIN_TOP
            justify = "center"
        elif pos == "center":
            x = max(0, (screen_w - win_w) // 2)
            y = max(0, (screen_h - win_h) // 2)
            justify = "center"
        else:  # bottom-right (по умолчанию)
            x = screen_w - win_w - MARGIN_RIGHT
            y = screen_h - win_h - MARGIN_BOTTOM
            justify = "right"

        self.label.config(justify=justify)
        self.overlay.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.overlay.deiconify()
        self.overlay.attributes('-alpha', self.alpha_value)
        self.overlay.lift()

        logger.info(f"💬 Показано: '{text}' (поз: {pos}, шрифт: {self.font_family} {self.font_size}px, цвет: {self.text_color})")
        self._hide_timer_id = self.overlay.after(DISPLAY_DURATION_MS, self._hide)

    def _hide(self):
        """Скрытие по истечении времени."""
        self._hide_timer_id = None
        self.overlay.attributes('-alpha', 0.0)
        self.overlay.withdraw()

    def emergency_hide(self):
        """Мгновенное скрытие при панике."""
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

        while not self.msg_queue.empty():
            try:
                self.msg_queue.get_nowait()
            except queue.Empty:
                break

    def check_queue(self):
        """Периодическая проверка очереди входящих сообщений."""
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


class TrayController:
    """Управление иконкой приложения в System Tray."""
    def __init__(self, app_window):
        self.app = app_window
        self.icon = None
        self._status = "connecting"

    def _get_status_text(self):
        if self._status == "connected":
            return "🟢 Онлайн"
        elif self._status == "connecting":
            return "🟡 Подключение..."
        return "🔴 Офлайн"

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(f"📩 Получатель: {self._get_status_text()}", lambda: None, enabled=False),
            pystray.MenuItem("⚙️ Открыть настройки", lambda: self.app.show_from_tray(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"🚨 Экстренная: [{self.app.hotkey.upper()}]", lambda: None, enabled=False),
            pystray.MenuItem(f"👁️ Прозрачность: {self.app.transparency_pct}%", lambda: None, enabled=False),
            pystray.MenuItem(f"📍 Позиция: {POSITION_NAMES.get(self.app.position, self.app.position)}", lambda: None, enabled=False),
            pystray.MenuItem("🧪 Проверить overlay (тест)", lambda: self.app.test_overlay()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Выход из программы", lambda: self.app.quit_app())
        )

    def start(self):
        if not PYSTRAY_AVAILABLE:
            return
        try:
            image = create_tray_icon_image(status=self._status)
            self.icon = pystray.Icon(
                "TestMessageReceiver",
                image,
                f"Получатель сообщений [{self.app.hotkey.upper()}]",
                menu=self._build_menu()
            )
            threading.Thread(target=self.icon.run, daemon=True).start()
            logger.info("🟢 System Tray иконка успешно запущена")
        except Exception as e:
            logger.warning(f"Не удалось инициализировать System Tray: {e}")

    def update_info(self, status=None):
        if status:
            self._status = status
        if self.icon:
            try:
                self.icon.icon = create_tray_icon_image(status=self._status)
                self.icon.menu = self._build_menu()
                self.icon.title = f"Получатель сообщений ({self._get_status_text()}) [{self.app.hotkey.upper()}]"
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


class MiniAppWindow:
    """
    Главное окно мини-приложения (Control Panel).
    Содержит вкладки настроек и сворачивается в трей.
    """
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = load_config()

        # Инициализация параметров
        self.hotkey = str(self.config.get("emergency_hotkey", "f12")).strip().lower() or "f12"
        self.transparency_pct = int(self.config.get("transparency", 10))
        self.auto_minimize_enabled = bool(self.config.get("auto_minimize", True))
        self.font_family = str(self.config.get("font_family", DEFAULT_FONT_FAMILY))
        self.font_size = int(self.config.get("font_size", DEFAULT_FONT_SIZE))
        self.text_color = str(self.config.get("text_color", DEFAULT_TEXT_COLOR))
        self.position = str(self.config.get("position", DEFAULT_POSITION))

        self.is_capturing_key = False
        self._countdown_id = None
        self.countdown_seconds = 5
        self.status_state = "connecting"
        self.active_tab = "main"

        # Создание менеджера экстренной кнопки
        self.emergency_manager = EmergencyManager(hotkey=self.hotkey)

        # Создание графического оверлея
        self.overlay = OverlayNotification(
            root=self.root,
            emergency_manager=self.emergency_manager,
            transparency_pct=self.transparency_pct,
            font_family=self.font_family,
            font_size=self.font_size,
            text_color=self.text_color,
            position=self.position
        )

        self.emergency_manager.on_activate = lambda: self.root.after_idle(self.overlay.emergency_hide)
        self.emergency_manager.start()

        # Контроллер трея
        self.tray = TrayController(self)

        # Настройка интерфейса
        self._setup_ui()

        # Старт проверки очереди
        self.overlay.check_queue()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self._on_window_unmap)

        # Старт WebSocket клиента
        self._start_ws()

        # Запуск трея
        self.tray.start()

        # Автосворачивание при старте
        if self.auto_minimize_enabled:
            self._start_countdown()

    def _setup_ui(self):
        """Построение интерфейса мини-приложения с вкладками."""
        self.root.title("Получатель сообщений")
        self.root.configure(bg=THEME["bg_window"])

        # Центрирование окна (450x600)
        w, h = 450, 600
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.resizable(False, False)

        # Иконка окна
        if PYSTRAY_AVAILABLE:
            try:
                icon_img = create_tray_icon_image(size=32, status="connected")
                self._tk_icon = ImageTk.PhotoImage(icon_img)
                self.root.iconphoto(False, self._tk_icon)
            except Exception:
                pass

        # Главный контейнер
        container = tk.Frame(self.root, bg=THEME["bg_window"], padx=16, pady=14)
        container.pack(fill="both", expand=True)

        # -----------------------------
        # 1. Шапка (Header)
        # -----------------------------
        header_frame = tk.Frame(container, bg=THEME["bg_window"])
        header_frame.pack(fill="x", pady=(0, 10))

        title_row = tk.Frame(header_frame, bg=THEME["bg_window"])
        title_row.pack(fill="x")

        title_label = tk.Label(
            title_row,
            text="📩 Получатель сообщений",
            font=(DEFAULT_FONT_FAMILY, 13, "bold"),
            fg=THEME["text_title"],
            bg=THEME["bg_window"]
        )
        title_label.pack(side="left")

        self.status_badge = tk.Label(
            title_row,
            text="● Подключение...",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["accent_amber"],
            bg="#2c2214",
            padx=10,
            pady=3,
            relief="flat"
        )
        self.status_badge.pack(side="right")

        # -----------------------------
        # 2. Навигация по вкладкам (Tabs)
        # -----------------------------
        tab_bar = tk.Frame(container, bg=THEME["bg_window"])
        tab_bar.pack(fill="x", pady=(0, 10))

        self.btn_tab_main = tk.Button(
            tab_bar,
            text="⚡ Основное",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            bg=THEME["tab_active_bg"],
            fg="#FFFFFF",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=lambda: self._switch_tab("main")
        )
        self.btn_tab_main.pack(side="left", padx=(0, 6))

        self.btn_tab_style = tk.Button(
            tab_bar,
            text="🎨 Вид текста (шрифт, цвет, позиция)",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            bg=THEME["tab_inactive_bg"],
            fg=THEME["text_muted"],
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=lambda: self._switch_tab("style")
        )
        self.btn_tab_style.pack(side="left")

        # Контейнер для сменяемого контента вкладок
        self.tab_content_area = tk.Frame(container, bg=THEME["bg_window"])
        self.tab_content_area.pack(fill="both", expand=True)

        # -----------------------------
        # ВКЛАДКА 1: ОСНОВНОЕ
        # -----------------------------
        self.tab_main_frame = tk.Frame(self.tab_content_area, bg=THEME["bg_window"])

        # Карточка 1: Экстренная кнопка
        card_hotkey = self._create_card(self.tab_main_frame)
        card_hotkey.pack(fill="x", pady=(0, 10))

        tk.Label(
            card_hotkey,
            text="🚨 ЭКСТРЕННАЯ КНОПКА (PANIC BUTTON)",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(anchor="w", pady=(0, 8))

        kh_row = tk.Frame(card_hotkey, bg=THEME["bg_card"])
        kh_row.pack(fill="x", pady=(0, 6))

        self.keycap_label = tk.Label(
            kh_row,
            text=f"[ {self.hotkey.upper()} ]",
            font=("Consolas", 11, "bold"),
            bg=THEME["keycap_bg"],
            fg=THEME["keycap_text"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["keycap_border"],
            padx=12,
            pady=4
        )
        self.keycap_label.pack(side="left")

        self.btn_change_hotkey = self._create_button(
            kh_row,
            text="Изменить",
            command=self.start_capture_hotkey,
            bg=THEME["accent_blue"],
            hover_bg=THEME["accent_blue_hover"]
        )
        self.btn_change_hotkey.pack(side="left", padx=(10, 0))

        self.btn_cancel_hotkey = self._create_button(
            kh_row,
            text="Отмена",
            command=self.cancel_capture_hotkey,
            bg="#374151",
            hover_bg="#4b5563"
        )

        self.hotkey_hint = tk.Label(
            card_hotkey,
            text="• Нажатие: моментально скрыть • Удержание: блокировать новые",
            font=(DEFAULT_FONT_FAMILY, 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"],
            justify="left"
        )
        self.hotkey_hint.pack(anchor="w")

        # Карточка 2: Прозрачность текста
        card_transparency = self._create_card(self.tab_main_frame)
        card_transparency.pack(fill="x", pady=(0, 10))

        tr_header = tk.Frame(card_transparency, bg=THEME["bg_card"])
        tr_header.pack(fill="x", pady=(0, 6))

        tk.Label(
            tr_header,
            text="👁️ ПРОЗРАЧНОСТЬ ТЕКСТА",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(side="left")

        self.transparency_value_label = tk.Label(
            tr_header,
            text=f"{self.transparency_pct}% (видимость {100 - self.transparency_pct}%)",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["keycap_text"],
            bg=THEME["bg_card"]
        )
        self.transparency_value_label.pack(side="right")

        self.slider = tk.Scale(
            card_transparency,
            from_=0,
            to=90,
            orient="horizontal",
            showvalue=0,
            bg=THEME["bg_card"],
            fg=THEME["text_title"],
            troughcolor=THEME["bg_card_inner"],
            activebackground=THEME["accent_blue"],
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            command=self.on_slider_changed
        )
        self.slider.set(self.transparency_pct)
        self.slider.pack(fill="x", pady=(0, 6))

        tr_bottom_row = tk.Frame(card_transparency, bg=THEME["bg_card"])
        tr_bottom_row.pack(fill="x")

        tk.Label(
            tr_bottom_row,
            text="0% — полная яркость, 90% — почти прозрачный",
            font=(DEFAULT_FONT_FAMILY, 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(side="left")

        btn_test_tr = self._create_button(
            tr_bottom_row,
            text="🧪 Тест",
            command=self.test_overlay,
            bg="#2a2e45",
            hover_bg="#3a3f5c",
            padx=10,
            pady=3
        )
        btn_test_tr.pack(side="right")

        # Карточка 3: Автосворачивание
        card_auto = self._create_card(self.tab_main_frame)
        card_auto.pack(fill="x", pady=(0, 10))

        self.auto_minimize_var = tk.BooleanVar(value=self.auto_minimize_enabled)
        chk_auto = tk.Checkbutton(
            card_auto,
            text="Сворачивать в трей при запуске через 5 сек",
            variable=self.auto_minimize_var,
            font=(DEFAULT_FONT_FAMILY, 9),
            fg=THEME["text_body"],
            bg=THEME["bg_card"],
            activebackground=THEME["bg_card"],
            activeforeground=THEME["text_body"],
            selectcolor=THEME["bg_card_inner"],
            command=self.on_toggle_auto_minimize
        )
        chk_auto.pack(anchor="w")

        self.countdown_label = tk.Label(
            card_auto,
            text="",
            font=(DEFAULT_FONT_FAMILY, 8, "italic"),
            fg=THEME["accent_amber"],
            bg=THEME["bg_card"]
        )
        self.countdown_label.pack(anchor="w", pady=(3, 0))

        # -----------------------------
        # ВКЛАДКА 2: ВИД ТЕКСТА
        # -----------------------------
        self.tab_style_frame = tk.Frame(self.tab_content_area, bg=THEME["bg_window"])

        # Карточка: Расположение на экране
        card_pos = self._create_card(self.tab_style_frame)
        card_pos.pack(fill="x", pady=(0, 10))

        tk.Label(
            card_pos,
            text="📍 РАСПОЛОЖЕНИЕ ТЕКСТА НА ЭКРАНЕ",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(anchor="w", pady=(0, 6))

        self.pos_var = tk.StringVar(value=POSITION_NAMES.get(self.position, POSITION_NAMES["bottom-right"]))
        self.pos_menu = tk.OptionMenu(
            card_pos,
            self.pos_var,
            *list(POSITION_NAMES.values()),
            command=self.on_position_selected
        )
        self._style_option_menu(self.pos_menu)
        self.pos_menu.pack(fill="x")

        # Карточка: Шрифт и размер
        card_font = self._create_card(self.tab_style_frame)
        card_font.pack(fill="x", pady=(0, 10))

        font_header = tk.Frame(card_font, bg=THEME["bg_card"])
        font_header.pack(fill="x", pady=(0, 4))

        tk.Label(
            font_header,
            text="🔤 ШРИФТ И РАЗМЕР",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(side="left")

        self.font_size_label = tk.Label(
            font_header,
            text=f"{self.font_size} px",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["keycap_text"],
            bg=THEME["bg_card"]
        )
        self.font_size_label.pack(side="right")

        font_row = tk.Frame(card_font, bg=THEME["bg_card"])
        font_row.pack(fill="x", pady=(0, 6))

        self.font_family_var = tk.StringVar(value=self.font_family)
        self.font_menu = tk.OptionMenu(
            font_row,
            self.font_family_var,
            *AVAILABLE_FONTS,
            command=self.on_font_family_selected
        )
        self._style_option_menu(self.font_menu)
        self.font_menu.pack(fill="x")

        # Ползунок размера
        self.size_slider = tk.Scale(
            card_font,
            from_=10,
            to=36,
            orient="horizontal",
            showvalue=0,
            bg=THEME["bg_card"],
            fg=THEME["text_title"],
            troughcolor=THEME["bg_card_inner"],
            activebackground=THEME["accent_blue"],
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            command=self.on_font_size_changed
        )
        self.size_slider.set(self.font_size)
        self.size_slider.pack(fill="x", pady=(2, 0))

        # Карточка: Цвет текста
        card_color = self._create_card(self.tab_style_frame)
        card_color.pack(fill="x", pady=(0, 10))

        color_header = tk.Frame(card_color, bg=THEME["bg_card"])
        color_header.pack(fill="x", pady=(0, 6))

        tk.Label(
            color_header,
            text="🎨 ЦВЕТ ТЕКСТА",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(side="left")

        # Плашка текущего выбранного цвета
        self.color_swatch = tk.Label(
            color_header,
            text=f"  {self.text_color.upper()}  ",
            font=("Consolas", 9, "bold"),
            bg=self.text_color,
            fg="#000000" if self._is_light_color(self.text_color) else "#FFFFFF",
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["border_card"]
        )
        self.color_swatch.pack(side="right")

        # Палитра быстрых кружков/кнопок
        swatch_row = tk.Frame(card_color, bg=THEME["bg_card"])
        swatch_row.pack(fill="x", pady=(0, 6))

        for hex_code, name in PRESET_COLORS:
            btn_c = tk.Button(
                swatch_row,
                bg=hex_code,
                activebackground=hex_code,
                relief="flat",
                bd=0,
                width=3,
                height=1,
                cursor="hand2",
                command=lambda c=hex_code: self.set_custom_color(c)
            )
            btn_c.pack(side="left", padx=2)

        btn_pick_color = self._create_button(
            card_color,
            text="🖌️ Выбрать любой цвет...",
            command=self.open_color_picker,
            bg=THEME["bg_card_inner"],
            hover_bg="#353a54",
            padx=10,
            pady=4
        )
        btn_pick_color.pack(fill="x")

        # Карточка: Превью текста
        card_preview = self._create_card(self.tab_style_frame)
        card_preview.pack(fill="x", pady=(0, 10))

        preview_header = tk.Frame(card_preview, bg=THEME["bg_card"])
        preview_header.pack(fill="x", pady=(0, 4))

        tk.Label(
            preview_header,
            text="👁️ ПРЕВЬЮ ОФОРМЛЕНИЯ",
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        ).pack(side="left")

        btn_test_style = self._create_button(
            preview_header,
            text="🧪 Тест на экране",
            command=self.test_overlay,
            bg="#2a2e45",
            hover_bg="#3a3f5c",
            padx=10,
            pady=2
        )
        btn_test_style.pack(side="right")

        self.preview_box = tk.Label(
            card_preview,
            text="Пример сообщения #123",
            font=(self.font_family, min(self.font_size, 20)),
            fg=self.text_color,
            bg="#08080c",
            padx=10,
            pady=8,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["border_card"]
        )
        self.preview_box.pack(fill="x")

        # Отображаем первую вкладку по умолчанию
        self.tab_main_frame.pack(fill="both", expand=True)

        # -----------------------------
        # 3. Нижняя панель действий (Общая)
        # -----------------------------
        bottom_frame = tk.Frame(container, bg=THEME["bg_window"])
        bottom_frame.pack(fill="x", side="bottom", pady=(8, 0))

        self.btn_fold = tk.Button(
            bottom_frame,
            text="📥 Свернуть в трей",
            font=(DEFAULT_FONT_FAMILY, 11, "bold"),
            bg=THEME["accent_green"],
            fg="#FFFFFF",
            activebackground=THEME["accent_green_hover"],
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            pady=8,
            cursor="hand2",
            command=self.hide_to_tray
        )
        self.btn_fold.pack(fill="x", pady=(0, 4))

        footer_text = tk.Label(
            bottom_frame,
            text="Приложение свернётся в трей возле часов и будет работать в фоне.\nДвойной клик по иконке трея снова откроет это окно.",
            font=(DEFAULT_FONT_FAMILY, 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_window"],
            justify="center"
        )
        footer_text.pack()

    def _switch_tab(self, tab_name: str):
        """Переключение между вкладками «Основное» и «Вид текста»."""
        self.cancel_countdown()
        self.active_tab = tab_name
        if tab_name == "main":
            self.tab_style_frame.pack_forget()
            self.tab_main_frame.pack(fill="both", expand=True)
            self.btn_tab_main.config(bg=THEME["tab_active_bg"], fg="#FFFFFF")
            self.btn_tab_style.config(bg=THEME["tab_inactive_bg"], fg=THEME["text_muted"])
        else:
            self.tab_main_frame.pack_forget()
            self.tab_style_frame.pack(fill="both", expand=True)
            self.btn_tab_style.config(bg=THEME["tab_active_bg"], fg="#FFFFFF")
            self.btn_tab_main.config(bg=THEME["tab_inactive_bg"], fg=THEME["text_muted"])
            self._update_preview_box()

    def _create_card(self, parent):
        """Создание карточки в едином стиле."""
        return tk.Frame(
            parent,
            bg=THEME["bg_card"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=12,
            pady=10
        )

    def _style_option_menu(self, menu_widget):
        """Стилизация выпадающего списка OptionMenu под темную тему."""
        menu_widget.config(
            bg=THEME["bg_card_inner"],
            fg=THEME["text_title"],
            activebackground=THEME["border_card"],
            activeforeground=THEME["text_title"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            font=(DEFAULT_FONT_FAMILY, 9),
            cursor="hand2"
        )
        menu_widget["menu"].config(
            bg=THEME["bg_card_inner"],
            fg=THEME["text_title"],
            activebackground=THEME["accent_blue"],
            activeforeground="#FFFFFF",
            font=(DEFAULT_FONT_FAMILY, 9),
            relief="flat",
            bd=1
        )

    def _create_button(self, parent, text, command, bg, hover_bg, padx=12, pady=5):
        """Вспомогательный метод создания стильных кнопок с hover-эффектом."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=(DEFAULT_FONT_FAMILY, 9, "bold"),
            bg=bg,
            fg="#FFFFFF",
            activebackground=hover_bg,
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=padx,
            pady=pady,
            cursor="hand2"
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def _is_light_color(self, hex_color: str) -> bool:
        """Определяет, светлый ли цвет (для контрастности текста на плашке)."""
        try:
            hex_str = hex_color.lstrip("#")
            if len(hex_str) == 6:
                r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
                luminance = (0.299 * r + 0.587 * g + 0.114 * b)
                return luminance > 160
        except Exception:
            pass
        return True

    def _update_preview_box(self):
        """Обновление блока предварительного просмотра в настройках."""
        if hasattr(self, "preview_box"):
            self.preview_box.config(
                font=(self.font_family, min(self.font_size, 20)),
                fg=self.text_color
            )

    # -----------------------------
    # Обработчики изменений параметров текста
    # -----------------------------
    def on_position_selected(self, val_name):
        """Выбор расположения текста на экране."""
        self.cancel_countdown()
        # Ищем ключ позиции по отображаемому имени
        for key, name in POSITION_NAMES.items():
            if name == val_name:
                self.position = key
                break
        save_config("position", self.position)
        self.overlay.update_style(position=self.position)
        if self.tray:
            self.tray.update_info()

    def on_font_family_selected(self, font_name):
        """Выбор шрифта."""
        self.cancel_countdown()
        self.font_family = font_name
        save_config("font_family", font_name)
        self.overlay.update_style(font_family=font_name)
        self._update_preview_box()

    def on_font_size_changed(self, size_str):
        """Изменение размера шрифта ползунком."""
        self.cancel_countdown()
        size = int(size_str)
        self.font_size = size
        self.font_size_label.config(text=f"{size} px")
        save_config("font_size", size)
        self.overlay.update_style(font_size=size)
        self._update_preview_box()

    def set_custom_color(self, hex_color: str):
        """Установка цвета текста."""
        self.cancel_countdown()
        self.text_color = hex_color
        save_config("text_color", hex_color)
        self.color_swatch.config(
            text=f"  {hex_color.upper()}  ",
            bg=hex_color,
            fg="#000000" if self._is_light_color(hex_color) else "#FFFFFF"
        )
        self.overlay.update_style(text_color=hex_color)
        self._update_preview_box()

    def open_color_picker(self):
        """Вызов диалога выбора цвета."""
        self.cancel_countdown()
        picked = colorchooser.askcolor(color=self.text_color, title="Выберите цвет текста")
        if picked and picked[1]:
            self.set_custom_color(picked[1])

    # -----------------------------
    # Таймер автосворачивания
    # -----------------------------
    def _start_countdown(self):
        self.countdown_seconds = 5
        self._tick_countdown()

    def _tick_countdown(self):
        if not self.auto_minimize_var.get() or self.is_capturing_key:
            self.countdown_label.config(text="")
            return

        if self.countdown_seconds > 0:
            self.countdown_label.config(
                text=f"⏳ Автоматическое сворачивание через {self.countdown_seconds} сек... (нажмите настройку для отмены)"
            )
            self.countdown_seconds -= 1
            self._countdown_id = self.root.after(1000, self._tick_countdown)
        else:
            self.countdown_label.config(text="")
            self.hide_to_tray()

    def cancel_countdown(self):
        if self._countdown_id:
            try:
                self.root.after_cancel(self._countdown_id)
            except Exception:
                pass
            self._countdown_id = None
        if hasattr(self, "countdown_label"):
            self.countdown_label.config(text="")

    def on_toggle_auto_minimize(self):
        enabled = self.auto_minimize_var.get()
        save_config("auto_minimize", enabled)
        if not enabled:
            self.cancel_countdown()
        else:
            self._start_countdown()

    def on_slider_changed(self, val_str):
        self.cancel_countdown()
        val = int(val_str)
        self.transparency_pct = val
        self.transparency_value_label.config(text=f"{val}% (видимость {100 - val}%)")
        save_config("transparency", val)
        self.overlay.set_transparency(val)
        if self.tray:
            self.tray.update_info()

    def test_overlay(self):
        """Показ тестового оверлея с текущими настройками шрифта, цвета, позиции и прозрачности."""
        self.cancel_countdown()
        pos_display = POSITION_NAMES.get(self.position, self.position)
        self.overlay.show_message(f"Тест: {self.font_family} {self.font_size}px ({pos_display})")

    # -----------------------------
    # Настройка хоткея
    # -----------------------------
    def start_capture_hotkey(self):
        if not KEYBOARD_AVAILABLE:
            self.hotkey_hint.config(
                text="⚠️ Модуль 'keyboard' недоступен. Хоткей сохранён как 'f12'.",
                fg=THEME["accent_red"]
            )
            return

        self.cancel_countdown()
        self.is_capturing_key = True
        self.emergency_manager.stop()

        self.btn_change_hotkey.pack_forget()
        self.btn_cancel_hotkey.pack(side="left", padx=(10, 0))

        self.keycap_label.config(text="[ ... ]", fg=THEME["accent_amber"])
        self.hotkey_hint.config(
            text="⏳ Нажмите любую клавишу или сочетание на клавиатуре...",
            fg=THEME["accent_amber"]
        )

        def worker():
            try:
                pressed = keyboard.read_hotkey(suppress=False)
                if pressed and self.is_capturing_key:
                    self.root.after_idle(lambda: self.finish_capture_hotkey(pressed))
            except Exception as e:
                logger.warning(f"Ошибка считывания клавиши: {e}")
                self.root.after_idle(self.cancel_capture_hotkey)

        threading.Thread(target=worker, daemon=True).start()

    def cancel_capture_hotkey(self):
        self.is_capturing_key = False
        self.btn_cancel_hotkey.pack_forget()
        self.btn_change_hotkey.pack(side="left", padx=(10, 0))

        self.keycap_label.config(text=f"[ {self.hotkey.upper()} ]", fg=THEME["keycap_text"])
        self.hotkey_hint.config(
            text="• Нажатие: моментально скрыть • Удержание: блокировать новые",
            fg=THEME["text_muted"]
        )
        self.emergency_manager.start()

    def finish_capture_hotkey(self, raw_hotkey: str):
        chosen = raw_hotkey.strip().lower()
        if chosen:
            self.hotkey = chosen
            save_config("emergency_hotkey", chosen)
            self.emergency_manager.set_hotkey(chosen)
            if self.tray:
                self.tray.update_info()

        self.is_capturing_key = False
        self.btn_cancel_hotkey.pack_forget()
        self.btn_change_hotkey.pack(side="left", padx=(10, 0))

        self.keycap_label.config(text=f"[ {self.hotkey.upper()} ]", fg=THEME["keycap_text"])
        self.hotkey_hint.config(
            text=f"✅ Установлена кнопка [{self.hotkey.upper()}]. Мониторинг активен.",
            fg=THEME["accent_green"]
        )
        self.emergency_manager.start()

    def set_connection_status(self, status: str):
        self.status_state = status
        if status == "connected":
            self.status_badge.config(text="● Онлайн", fg="#34d399", bg="#0a3e29")
        elif status == "connecting":
            self.status_badge.config(text="● Подключение...", fg="#fbbf24", bg="#2c2214")
        else:
            self.status_badge.config(text="● Офлайн", fg="#f87171", bg="#3a1414")

        if self.tray:
            self.tray.update_info(status)

    def hide_to_tray(self):
        self.cancel_countdown()
        self.root.withdraw()
        logger.info("Приложение свёрнуто в системный трей")

    def show_from_tray(self):
        self.root.after_idle(self._restore_window)

    def _restore_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _on_window_unmap(self, event):
        if event.widget == self.root and self.root.state() == "iconic":
            self.hide_to_tray()

    def quit_app(self):
        logger.info("Завершение работы программы...")
        self.cancel_countdown()
        if self.tray:
            self.tray.stop()
        if self.emergency_manager:
            self.emergency_manager.stop()
        self.root.after_idle(self.root.destroy)

    def _start_ws(self):
        ws_thread = threading.Thread(
            target=start_ws_thread,
            args=(self.overlay.msg_queue, self.emergency_manager, self.set_connection_status, self.root),
            daemon=True
        )
        ws_thread.start()


async def websocket_listener(msg_queue: queue.Queue, emergency_manager: EmergencyManager, on_status_change, tk_root: tk.Tk):
    """Фоновый клиент WebSocket с автопереподключением."""
    def notify_status(st):
        if on_status_change and tk_root:
            try:
                tk_root.after_idle(lambda: on_status_change(st))
            except Exception:
                pass

    while True:
        try:
            notify_status("connecting")
            logger.info(f"⏳ Подключение к {SERVER_URL}...")
            async with websockets.connect(SERVER_URL, ping_interval=20) as ws:
                logger.info("✅ Успешно подключено к серверу.")
                notify_status("connected")

                async for message in ws:
                    message = message.strip()
                    if not message:
                        continue

                    if emergency_manager and emergency_manager.is_blocked():
                        logger.info(f"🚫 [Экстренный режим] Сообщение отброшено: '{message}'")
                        continue

                    logger.info(f"📩 Получено сообщение: '{message}'")
                    msg_queue.put(message)

        except websockets.exceptions.ConnectionClosedError:
            logger.warning("⚠️ Соединение разорвано. Переподключение через 5 сек...")
            notify_status("connecting")
            await asyncio.sleep(5)
        except Exception as e:
            logger.warning(f"❌ Ошибка соединения: {e}. Повтор через 5 сек...")
            notify_status("disconnected")
            await asyncio.sleep(5)


def start_ws_thread(msg_queue: queue.Queue, emergency_manager: EmergencyManager, on_status_change, tk_root: tk.Tk):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_listener(msg_queue, emergency_manager, on_status_change, tk_root))


def main():
    hide_console()

    root = tk.Tk()
    app = MiniAppWindow(root)

    try:
        root.mainloop()
    finally:
        if app.tray:
            app.tray.stop()
        if app.emergency_manager:
            app.emergency_manager.stop()


if __name__ == "__main__":
    main()
