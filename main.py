"""
Софія — Голосовий Асистент
Запуск: python main.py
"""
import ctypes
import browser_bridge
from gui import SophiyaUI

# Без цього Windows показує іконку Python замість нашої
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Sophiya.AI.v1')
except Exception:
    pass


def main():
    browser_bridge.start()   # запускаємо WebSocket-сервер для Chrome-розширення
    app = SophiyaUI()
    app.run()


if __name__ == "__main__":
    main()
