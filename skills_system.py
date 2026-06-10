"""
skills_system.py — системні навички Sophiya.
Час, дата, вікна, програми, папки, автозапуск, системна інформація.
"""
import os
import sys
import time
import datetime
import subprocess
import ctypes
import pyautogui

from config import SPOTIFY_PATH


# ---------------------------------------------------------------------------
# Час і дата
# ---------------------------------------------------------------------------
def current_time():
    now = datetime.datetime.now()
    return f"Зараз {now.strftime('%H:%M')}"


def current_date():
    now = datetime.datetime.now()
    days = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]
    months_ua = {
        1: "січня", 2: "лютого", 3: "березня", 4: "квітня",
        5: "травня", 6: "червня", 7: "липня", 8: "серпня",
        9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня"
    }
    return f"Сьогодні {days[now.weekday()]}, {now.day} {months_ua[now.month]} {now.year} року"


# ---------------------------------------------------------------------------
# Системна гучність (медіаклавіші)
# ---------------------------------------------------------------------------
def volume_up():
    for _ in range(10):
        pyautogui.press('volumeup')
        time.sleep(0.1)
    return "Гучність збільшено"


def volume_down():
    for _ in range(6):
        pyautogui.press('volumedown')
        time.sleep(0.1)
    return "Гучність зменшено"


# ---------------------------------------------------------------------------
# Внутрішній хелпер: клавіші через Windows API (підтримує Win-key)
# ---------------------------------------------------------------------------
def _press_keys(*keys):
    user32 = ctypes.windll.user32
    KEY_MAP = {
        'win': 0x5B, 'shift': 0x10, 'alt': 0x12, 'ctrl': 0x11,
        'd': 0x44, 's': 0x53, 'f4': 0x73, 'down': 0x28, 'tab': 0x09,
    }
    codes = [KEY_MAP.get(k.lower(), 0) for k in keys]
    for c in codes:
        user32.keybd_event(c, 0, 0, 0)
    time.sleep(0.05)
    for c in reversed(codes):
        user32.keybd_event(c, 0, 2, 0)


# ---------------------------------------------------------------------------
# Керування вікнами
# ---------------------------------------------------------------------------
def minimize_all():
    _press_keys('win', 'd')
    return "Ховаю всі вікна"


def restore_windows():
    _press_keys('win', 'd')
    return "Повертаю вікна"


def close_window():
    _press_keys('alt', 'f4')
    return "Закриваю вікно"


def minimize_window():
    _press_keys('win', 'down')
    return "Ховаю вікно"


def screenshot():
    _press_keys('win', 'shift', 's')
    return "Відкриваю інструмент скріншотів"


# ---------------------------------------------------------------------------
# Запуск програм
# ---------------------------------------------------------------------------
def open_notepad():
    subprocess.Popen('notepad.exe')
    return "Відкриваю блокнот"


def open_calculator():
    subprocess.Popen('calc.exe')
    return "Відкриваю калькулятор"


def open_explorer():
    subprocess.Popen('explorer.exe')
    return "Відкриваю провідник"


def open_telegram():
    try:
        subprocess.Popen(r'C:\Users\Andriy\AppData\Roaming\Telegram Desktop\Telegram.exe')
        return "Відкриваю Телеграм"
    except Exception:
        return "Не вдалося запустити Телеграм"


def open_steam():
    try:
        subprocess.Popen(r'C:\Program Files (x86)\Steam\steam.exe')
        return "Відкриваю Стім"
    except Exception:
        return "Не вдалося запустити Стім"


# ---------------------------------------------------------------------------
# Живлення та блокування
# ---------------------------------------------------------------------------
def offpc():
    os.system('shutdown /s /t 30')
    return "Вимикаю комп'ютер через 30 секунд"


def lock_pc():
    ctypes.windll.user32.LockWorkStation()
    return "Блокую комп'ютер"


def cancel_shutdown():
    result = os.system('shutdown /a')
    if result == 0:
        return "Вимкнення скасовано!"
    return "Немає активного вимкнення для скасування."


def goodnight_routine():
    """Вечірній ритуал: зупинити музику + вимкнути комп через 10 хв."""
    try:
        import pyautogui as _pg
        _pg.press('playpause')
    except Exception:
        pass
    os.system('shutdown /s /t 600')
    return (
        "Спокійної ночі! Музику зупинила. "
        "Комп'ютер вимкнеться через 10 хвилин. "
        "Щоб скасувати — скажи 'скасуй вимкнення'."
    )


# ---------------------------------------------------------------------------
# Автозапуск Windows
# ---------------------------------------------------------------------------
def enable_autostart():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'main.py')
        )
        winreg.SetValueEx(key, "Sophiya", 0, winreg.REG_SZ,
                          f'"{sys.executable}" "{script_path}"')
        winreg.CloseKey(key)
        return "Автозапуск увімкнено. Тепер запускатимусь разом з Windows."
    except Exception as e:
        print(f"Помилка автозапуску: {e}")
        return "Не вдалося увімкнути автозапуск."


def disable_autostart():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, "Sophiya")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return "Автозапуск вимкнено."
    except Exception as e:
        print(f"Помилка: {e}")
        return "Не вдалося вимкнути автозапуск."


# ---------------------------------------------------------------------------
# Системна інформація (psutil)
# ---------------------------------------------------------------------------
def system_info():
    try:
        import psutil
    except ImportError:
        return "Встановіть psutil: pip install psutil"
    parts = []
    mem = psutil.virtual_memory()
    parts.append(f"RAM {mem.used / (1024**3):.1f} з {mem.total / (1024**3):.0f} ГБ ({mem.percent:.0f}%)")
    cpu = psutil.cpu_percent(interval=0.5)
    parts.append(f"процесор {cpu:.0f}%")
    batt = psutil.sensors_battery()
    if batt is not None:
        status = "заряджається" if batt.power_plugged else "розряджається"
        parts.append(f"батарея {batt.percent:.0f}% ({status})")
    return ", ".join(parts)


def system_ram():
    try:
        import psutil
        m = psutil.virtual_memory()
        return (f"Оперативна пам'ять: {m.used / (1024**3):.1f} з "
                f"{m.total / (1024**3):.0f} ГБ ({m.percent:.0f}% використано)")
    except ImportError:
        return "Встановіть psutil: pip install psutil"


def system_cpu():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        return f"Процесор завантажений на {cpu:.0f}%"
    except ImportError:
        return "Встановіть psutil: pip install psutil"


def system_battery():
    try:
        import psutil
        batt = psutil.sensors_battery()
        if batt is None:
            return "Батарея не визначена — можливо, стаціонарний ПК"
        status = "заряджається" if batt.power_plugged else "розряджається"
        return f"Батарея: {batt.percent:.0f}%, {status}"
    except ImportError:
        return "Встановіть psutil: pip install psutil"


# ---------------------------------------------------------------------------
# Буфер обміну
# ---------------------------------------------------------------------------
def clipboard_read():
    try:
        import pyperclip
        text = (pyperclip.paste() or "").strip()
        if not text:
            return "Буфер обміну порожній"
        preview = text[:200] + ("..." if len(text) > 200 else "")
        return f"В буфері: {preview}"
    except ImportError:
        return "Встановіть pyperclip: pip install pyperclip"
    except Exception:
        return "Не вдалося прочитати буфер обміну"


# ---------------------------------------------------------------------------
# Відкриття папок
# ---------------------------------------------------------------------------
def _open_folder(path):
    expanded = os.path.expandvars(os.path.expanduser(path))
    if os.path.exists(expanded):
        subprocess.Popen(f'explorer "{expanded}"')
        return "Відкриваю папку"
    return f"Папка не знайдена: {expanded}"


def open_downloads():    return _open_folder(r'~\Downloads')
def open_desktop():      return _open_folder(r'~\Desktop')
def open_documents():    return _open_folder(r'~\Documents')
def open_pictures():     return _open_folder(r'~\Pictures')
def open_videos():       return _open_folder(r'~\Videos')
def open_music_folder(): return _open_folder(r'~\Music')
def open_disk_c():       return _open_folder('C:\\')
def open_disk_d():       return _open_folder('D:\\')
def open_disk_e():       return _open_folder('E:\\')
