"""
Софія — Голосовий Асистент
Запуск: python main.py
"""
import browser_bridge
from gui import SophiyaUI


def main():
    browser_bridge.start()   # запускаємо WebSocket-сервер для Chrome-розширення
    app = SophiyaUI()
    app.run()


if __name__ == "__main__":
    main()
