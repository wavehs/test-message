"""
Overlay-получатель сообщений (Windows).
Показывает текст в правом нижнем углу экрана поверх всех окон.

Особенности:
- Консоль НЕ открывается — всё управление происходит через стильное мини-приложение.
- Мини-приложение позволяет настроить:
  • Экстренную кнопку (Panic Button) для моментального скрытия или блокировки вывода;
  • Прозрачность текста (0% - чёткий белый, 90% - почти прозрачный);
  • Проверку отображения оверлея кнопкой «Проверить (Тест)».
- Приложение автоматически или по нажатию кнопки сворачивается в системный трей (возле часов).
- Из трея двойным кликом или через меню «Открыть настройки» окно можно вызвать в любой момент.
"""

import asyncio
import websockets
import tkinter as tk
from tkinter import ttk
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

# Параметры всплывающего текста
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 14
TEXT_COLOR = "#FFFFFF"
DISPLAY_DURATION_MS = 2000  # 2 секунды
MAX_TEXT_WIDTH = 400
MARGIN_RIGHT = 20
MARGIN_BOTTOM = 60

# Цветовая палитра темной темы мини-приложения
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


def show_console():
    """Показать окно консоли на Windows при необходимости."""
    try:
        if sys.platform == "win32":
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
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
    # Фоновый круг
    draw.ellipse((3, 3, size - 3, size - 3), fill="#181a27")
    draw.ellipse((3, 3, size - 3, size - 3), outline="#454868", width=2)
    # Статусный индикатор в центре
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
    Прозрачное overlay-окно для показа текста в правом нижнем углу экрана.
    """
    def __init__(self, root: tk.Tk, emergency_manager: EmergencyManager = None, transparency_pct: int = 10):
        self.root = root
        self.emergency_manager = emergency_manager
        self.transparency_pct = transparency_pct
        self.alpha_value = max(0.05, min(1.0, (100.0 - float(transparency_pct)) / 100.0))
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
            font=(FONT_FAMILY, FONT_SIZE),
            fg=TEXT_COLOR,
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
        # Если сейчас показывается сообщение — сразу применить новую прозрачность
        if self._hide_timer_id is not None:
            self.overlay.attributes('-alpha', self.alpha_value)

    def show_message(self, text: str):
        """Отобразить текст в правом нижнем углу экрана."""
        if self.emergency_manager and self.emergency_manager.is_blocked():
            logger.info(f"🚫 Экстренный режим активен. Сообщение отброшено: '{text}'")
            return

        if self._hide_timer_id is not None:
            try:
                self.overlay.after_cancel(self._hide_timer_id)
            except Exception:
                pass
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
        self.overlay.attributes('-alpha', self.alpha_value)
        self.overlay.lift()

        logger.info(f"💬 Показано: '{text}' (прозрачность {self.transparency_pct}%)")
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

        # Сброс очереди
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
    Позволяет настраивать параметры и затем сворачивается в трей.
    """
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = load_config()

        # Инициализация параметров из сохранённого конфига
        self.hotkey = str(self.config.get("emergency_hotkey", "f12")).strip().lower() or "f12"
        self.transparency_pct = int(self.config.get("transparency", 10))
        self.auto_minimize_enabled = bool(self.config.get("auto_minimize", True))

        self.is_capturing_key = False
        self._countdown_id = None
        self.countdown_seconds = 5
        self.status_state = "connecting"

        # Создание менеджера экстренной кнопки
        self.emergency_manager = EmergencyManager(hotkey=self.hotkey)

        # Создание графического оверлея
        self.overlay = OverlayNotification(
            root=self.root,
            emergency_manager=self.emergency_manager,
            transparency_pct=self.transparency_pct
        )

        # Обратный вызов паники
        self.emergency_manager.on_activate = lambda: self.root.after_idle(self.overlay.emergency_hide)
        self.emergency_manager.start()

        # Контроллер трея
        self.tray = TrayController(self)

        # Настройка интерфейса
        self._setup_ui()

        # Старт проверки очереди оверлея
        self.overlay.check_queue()

        # Привязка системных событий окна
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self._on_window_unmap)

        # Старт WebSocket клиента
        self._start_ws()

        # Запуск трея
        self.tray.start()

        # Автосворачивание, если включено
        if self.auto_minimize_enabled:
            self._start_countdown()

    def _setup_ui(self):
        """Построение современного темного интерфейса мини-приложения."""
        self.root.title("Получатель сообщений")
        self.root.configure(bg=THEME["bg_window"])

        # Центрирование окна (420x540)
        w, h = 420, 540
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.resizable(False, False)

        # Иконка окна (если Pillow доступен)
        if PYSTRAY_AVAILABLE:
            try:
                icon_img = create_tray_icon_image(size=32, status="connected")
                self._tk_icon = ImageTk.PhotoImage(icon_img)
                self.root.iconphoto(False, self._tk_icon)
            except Exception:
                pass

        # Главный контейнер
        main_frame = tk.Frame(self.root, bg=THEME["bg_window"], padx=18, pady=16)
        main_frame.pack(fill="both", expand=True)

        # -----------------------------
        # 1. Шапка (Header)
        # -----------------------------
        header_frame = tk.Frame(main_frame, bg=THEME["bg_window"])
        header_frame.pack(fill="x", pady=(0, 14))

        title_row = tk.Frame(header_frame, bg=THEME["bg_window"])
        title_row.pack(fill="x")

        title_label = tk.Label(
            title_row,
            text="📩 Получатель сообщений",
            font=(FONT_FAMILY, 13, "bold"),
            fg=THEME["text_title"],
            bg=THEME["bg_window"]
        )
        title_label.pack(side="left")

        self.status_badge = tk.Label(
            title_row,
            text="● Подключение...",
            font=(FONT_FAMILY, 9, "bold"),
            fg=THEME["accent_amber"],
            bg="#2c2214",
            padx=10,
            pady=3,
            relief="flat"
        )
        self.status_badge.pack(side="right")

        sub_label = tk.Label(
            header_frame,
            text="Overlay-уведомления поверх всех окон",
            font=(FONT_FAMILY, 9),
            fg=THEME["text_muted"],
            bg=THEME["bg_window"]
        )
        sub_label.pack(anchor="w", pady=(2, 0))

        # -----------------------------
        # 2. Карточка: Экстренная кнопка
        # -----------------------------
        card_hotkey = tk.Frame(
            main_frame,
            bg=THEME["bg_card"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=14,
            pady=12
        )
        card_hotkey.pack(fill="x", pady=(0, 12))

        ch_title = tk.Label(
            card_hotkey,
            text="🚨 ЭКСТРЕННАЯ КНОПКА (PANIC BUTTON)",
            font=(FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        )
        ch_title.pack(anchor="w", pady=(0, 8))

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
        # Изначально скрыта

        self.hotkey_hint = tk.Label(
            card_hotkey,
            text="• Нажатие: скрыть текущее • Удержание: блокировать новые",
            font=(FONT_FAMILY, 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"],
            justify="left"
        )
        self.hotkey_hint.pack(anchor="w")

        # -----------------------------
        # 3. Карточка: Прозрачность текста
        # -----------------------------
        card_transparency = tk.Frame(
            main_frame,
            bg=THEME["bg_card"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=14,
            pady=12
        )
        card_transparency.pack(fill="x", pady=(0, 12))

        tr_header = tk.Frame(card_transparency, bg=THEME["bg_card"])
        tr_header.pack(fill="x", pady=(0, 6))

        tr_title = tk.Label(
            tr_header,
            text="👁️ ПРОЗРАЧНОСТЬ ТЕКСТА",
            font=(FONT_FAMILY, 9, "bold"),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        )
        tr_title.pack(side="left")

        self.transparency_value_label = tk.Label(
            tr_header,
            text=f"{self.transparency_pct}% (видимость {100 - self.transparency_pct}%)",
            font=(FONT_FAMILY, 9, "bold"),
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
        self.slider.pack(fill="x", pady=(0, 8))

        tr_bottom_row = tk.Frame(card_transparency, bg=THEME["bg_card"])
        tr_bottom_row.pack(fill="x")

        tr_subtext = tk.Label(
            tr_bottom_row,
            text="0% — максимальная яркость, 90% — еле заметный",
            font=(FONT_FAMILY, 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_card"]
        )
        tr_subtext.pack(side="left")

        btn_test = self._create_button(
            tr_bottom_row,
            text="🧪 Тест",
            command=self.test_overlay,
            bg="#2a2e45",
            hover_bg="#3a3f5c",
            padx=10,
            pady=3
        )
        btn_test.pack(side="right")

        # -----------------------------
        # 4. Карточка: Автосворачивание
        # -----------------------------
        card_auto = tk.Frame(
            main_frame,
            bg=THEME["bg_card"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=THEME["border_card"],
            padx=14,
            pady=10
        )
        card_auto.pack(fill="x", pady=(0, 14))

        self.auto_minimize_var = tk.BooleanVar(value=self.auto_minimize_enabled)
        chk_auto = tk.Checkbutton(
            card_auto,
            text="Сворачивать в трей при запуске через 5 сек",
            variable=self.auto_minimize_var,
            font=(FONT_FAMILY, 9),
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
            font=(FONT_FAMILY, 8, "italic"),
            fg=THEME["accent_amber"],
            bg=THEME["bg_card"]
        )
        self.countdown_label.pack(anchor="w", pady=(3, 0))

        # -----------------------------
        # 5. Нижняя панель действий
        # -----------------------------
        self.btn_fold = tk.Button(
            main_frame,
            text="📥 Свернуть в трей",
            font=(FONT_FAMILY, 11, "bold"),
            bg=THEME["accent_green"],
            fg="#FFFFFF",
            activebackground=THEME["accent_green_hover"],
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            pady=9,
            cursor="hand2",
            command=self.hide_to_tray
        )
        self.btn_fold.pack(fill="x", pady=(0, 8))

        footer_text = tk.Label(
            main_frame,
            text="Приложение свернётся в трей возле часов и будет работать в фоне.\nДвойной клик по иконке трея снова откроет это окно.",
            font=(FONT_FAMILY, 8),
            fg=THEME["text_muted"],
            bg=THEME["bg_window"],
            justify="center"
        )
        footer_text.pack()

    def _create_button(self, parent, text, command, bg, hover_bg, padx=12, pady=5):
        """Вспомогательный метод создания стильных кнопок с hover-эффектом."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=(FONT_FAMILY, 9, "bold"),
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

    def _start_countdown(self):
        """Запуск таймера автосворачивания при старте."""
        self.countdown_seconds = 5
        self._tick_countdown()

    def _tick_countdown(self):
        """Один шаг обратного отсчёта автосворачивания."""
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
        """Отмена таймера автосворачивания при любом действии пользователя."""
        if self._countdown_id:
            try:
                self.root.after_cancel(self._countdown_id)
            except Exception:
                pass
            self._countdown_id = None
        self.countdown_label.config(text="")

    def on_toggle_auto_minimize(self):
        """Переключение настройки автосворачивания."""
        enabled = self.auto_minimize_var.get()
        save_config("auto_minimize", enabled)
        if not enabled:
            self.cancel_countdown()
        else:
            self._start_countdown()

    def on_slider_changed(self, val_str):
        """Обработка движения ползунка прозрачности."""
        self.cancel_countdown()
        val = int(val_str)
        self.transparency_pct = val
        self.transparency_value_label.config(text=f"{val}% (видимость {100 - val}%)")
        save_config("transparency", val)
        self.overlay.set_transparency(val)
        if self.tray:
            self.tray.update_info()

    def test_overlay(self):
        """Показ тестового сообщения для наглядной проверки настроек."""
        self.cancel_countdown()
        self.overlay.show_message("Привет! Это тестовое сообщение. Проверка видимости.")

    def start_capture_hotkey(self):
        """Вход в режим захвата новой экстренной клавиши."""
        if not KEYBOARD_AVAILABLE:
            self.hotkey_hint.config(
                text="⚠️ Модуль 'keyboard' недоступен. Хоткей сохранён как 'f12'.",
                fg=THEME["accent_red"]
            )
            return

        self.cancel_countdown()
        self.is_capturing_key = True
        self.emergency_manager.stop()  # Временно останавливаем хук, чтобы не сработало скрытие

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
        """Отмена захвата клавиши."""
        self.is_capturing_key = False
        self.btn_cancel_hotkey.pack_forget()
        self.btn_change_hotkey.pack(side="left", padx=(10, 0))

        self.keycap_label.config(text=f"[ {self.hotkey.upper()} ]", fg=THEME["keycap_text"])
        self.hotkey_hint.config(
            text="• Нажатие: скрыть текущее • Удержание: блокировать новые",
            fg=THEME["text_muted"]
        )
        self.emergency_manager.start()

    def finish_capture_hotkey(self, raw_hotkey: str):
        """Успешный захват новой экстренной клавиши."""
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
        """Обновление индикатора статуса соединения."""
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
        """Свернуть окно в системный трей."""
        self.cancel_countdown()
        self.root.withdraw()
        logger.info("Приложение свёрнуто в системный трей")

    def show_from_tray(self):
        """Развернуть окно настроек из трея."""
        self.root.after_idle(self._restore_window)

    def _restore_window(self):
        """Восстановление окна на передний план."""
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _on_window_unmap(self, event):
        """При сворачивании стандартной кнопкой '-' прячем окно в трей."""
        if event.widget == self.root and self.root.state() == "iconic":
            self.hide_to_tray()

    def quit_app(self):
        """Корректный выход из приложения."""
        logger.info("Завершение работы программы...")
        self.cancel_countdown()
        if self.tray:
            self.tray.stop()
        if self.emergency_manager:
            self.emergency_manager.stop()
        self.root.after_idle(self.root.destroy)

    def _start_ws(self):
        """Запуск WebSocket клиента в отдельном потоке."""
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

                    # Если экстренная кнопка зажата — сразу отбрасываем
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
    """Поток для асинхронного цикла WebSocket."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_listener(msg_queue, emergency_manager, on_status_change, tk_root))


def main():
    """Точка входа."""
    # Гарантированное скрытие консоли
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
