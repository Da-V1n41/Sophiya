"""
skills_media.py — медіа-навички Sophiya.
Spotify, треки, гучність, перемотування.
"""
import os
import time
import threading
import subprocess
import ctypes
import ctypes.wintypes
import pyautogui

from config import SPOTIFY_PATH


# ---------------------------------------------------------------------------
# Внутрішній хелпер: знаходить і активує вікно за ключовими словами
# ---------------------------------------------------------------------------
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)


def _find_and_activate_window(*search_terms):
    """
    Шукає перше видиме вікно, в назві якого є одне зі *search_terms.
    Якщо знайдено — виводить на передній план і повертає заголовок.
    """
    user32 = ctypes.windll.user32
    result = {'hwnd': 0, 'title': ''}

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if any(s.lower() in title.lower() for s in search_terms):
            result['hwnd'] = hwnd
            result['title'] = title
            return False
        return True

    cb = _EnumWindowsProc(_callback)
    user32.EnumWindows(cb, 0)

    if result['hwnd']:
        user32.ShowWindow(result['hwnd'], 9)   # SW_RESTORE
        try:
            user32.SetForegroundWindow(result['hwnd'])
        except Exception:
            pass
        time.sleep(0.25)

    return result['title']


# ---------------------------------------------------------------------------
# Поточний трек
# ---------------------------------------------------------------------------
def current_track_info():
    """Повертає назву поточного треку через Windows Media Session API або заголовки вікон."""
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
        )
        from voice import _get_tts_loop
        import asyncio

        async def _get():
            sessions = await MediaManager.request_async()
            session = sessions.get_current_session()
            if not session:
                return None, None
            props = await session.try_get_media_properties_async()
            if props:
                return props.title or '', props.artist or ''
            return None, None

        loop = _get_tts_loop()
        future = asyncio.run_coroutine_threadsafe(_get(), loop)
        title, artist = future.result(timeout=3)
        if title:
            return f"Зараз грає: {title}{' — ' + artist if artist else ''}"
        return "Наразі нічого не грає"

    except ImportError:
        pass
    except Exception as e:
        print(f"[MediaSession] {e}")

    # Fallback: заголовки вікон
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | '
             'Select-Object -ExpandProperty MainWindowTitle'],
            capture_output=True, text=True, timeout=3, creationflags=0x08000000
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and line.lower() not in ('spotify', ''):
                for suffix in [' - Spotify', ' | Spotify']:
                    if line.endswith(suffix):
                        return f"Зараз грає: {line[:-len(suffix)]}"
            if '- YouTube' in line:
                title = line.split('- YouTube')[0].strip()
                if title:
                    return f"Зараз грає: {title} (YouTube)"
        return "Наразі нічого не грає"
    except Exception:
        return "Не вдалося визначити трек"


# ---------------------------------------------------------------------------
# Очікування зміни треку після перемикання
# ---------------------------------------------------------------------------
def _wait_for_track_change(old_info: str, max_sec: float = 5.0) -> str | None:
    """Чекає поки Spotify оновить трек. Повертає нову назву або None."""
    step = 0.4
    elapsed = 0.0
    while elapsed < max_sec:
        time.sleep(step)
        elapsed += step
        info = current_track_info()
        if info.startswith('Зараз грає:') and info != old_info:
            return info
    return None


# ---------------------------------------------------------------------------
# Основні медіа-команди
# ---------------------------------------------------------------------------
def pausa():
    pyautogui.press('playpause')
    return "Готово"


def next_track():
    old = current_track_info()
    pyautogui.press('nexttrack')
    info = _wait_for_track_change(old)
    return f"Наступна. {info}" if info else "Наступна пісня"


def prev_track():
    old = current_track_info()
    pyautogui.press('prevtrack')
    info = _wait_for_track_change(old)
    return f"Попередня. {info}" if info else "Попередня пісня"


def space():
    pyautogui.press("space")
    return "Натиснула"


def music():
    """Запускає Spotify і через 5 секунд натискає play — в окремому потоці."""
    def _launch():
        try:
            subprocess.Popen(SPOTIFY_PATH)
            time.sleep(5)
            pyautogui.press("space")
        except Exception:
            pass
    threading.Thread(target=_launch, daemon=True).start()
    return "Запускаю музику"


def open_spotify():
    try:
        subprocess.Popen(SPOTIFY_PATH)
        return "Відкриваю Спотіфай"
    except Exception:
        return "Не вдалося запустити Спотіфай"


# ---------------------------------------------------------------------------
# Гучність Spotify (Ctrl+Up/Down — не чіпає системну)
# ---------------------------------------------------------------------------
def spotify_volume_up():
    title = _find_and_activate_window('Spotify')
    if not title:
        return "Spotify не запущений"
    pyautogui.hotkey('ctrl', 'up')
    return "Гучніше в Spotify"


def spotify_volume_down():
    title = _find_and_activate_window('Spotify')
    if not title:
        return "Spotify не запущений"
    pyautogui.hotkey('ctrl', 'down')
    return "Тихіше в Spotify"


# ---------------------------------------------------------------------------
# Перемотування (YouTube / браузерні плеєри)
# ---------------------------------------------------------------------------
def seek_forward():
    title = _find_and_activate_window('YouTube', 'youtube.com')
    if title:
        pyautogui.press('l')       # +10 секунд у YouTube
        return "Перемотую вперед"
    title2 = _find_and_activate_window('Chrome', 'Firefox', 'Edge', 'Opera', 'Brave')
    if title2:
        pyautogui.press('right')
        return "Перемотую вперед"
    return "Не знайшов активний відеоплеєр"


def seek_backward():
    title = _find_and_activate_window('YouTube', 'youtube.com')
    if title:
        pyautogui.press('j')       # −10 секунд у YouTube
        return "Перемотую назад"
    title2 = _find_and_activate_window('Chrome', 'Firefox', 'Edge', 'Opera', 'Brave')
    if title2:
        pyautogui.press('left')
        return "Перемотую назад"
    return "Не знайшов активний відеоплеєр"
