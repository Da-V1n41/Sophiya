"""
browser_bridge.py — WebSocket-міст між Sophiya і розширенням Chrome.

Sophia запускає сервер на ws://127.0.0.1:8765.
Розширення підключається і тримає постійне з'єднання.
"""

import asyncio
import threading
import json
import sys
import time

_loop: asyncio.AbstractEventLoop = None
_connection = None          # поточне WebSocket-з'єднання
_pending_id  = None         # id поточного запиту
_last_links  = None         # результат останнього запиту
_response_event = threading.Event()
_request_counter = 0
_server_ready   = threading.Event()   # сигнал що сервер вже слухає

PORT = 8765


# ------------------------------------------------------------------
# Asyncio-обробник з'єднань
# ------------------------------------------------------------------
async def _handler(websocket):
    global _connection, _last_links, _pending_id

    _connection = websocket
    print('[Bridge] Розширення підключилось')

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            if msg.get('type') == 'links' and msg.get('id') == _pending_id:
                _last_links = msg.get('links', [])
                _response_event.set()

    except Exception:
        pass
    finally:
        if _connection is websocket:
            _connection = None
        print('[Bridge] Розширення відключилось')


async def _serve():
    import websockets
    async with websockets.serve(_handler, '127.0.0.1', PORT):
        print(f'[Bridge] Сервер запущено на ws://127.0.0.1:{PORT}')
        _server_ready.set()
        # Тримаємо сервер живим через нескінченний цикл сну
        while True:
            await asyncio.sleep(3600)


# ------------------------------------------------------------------
# Запуск у фоновому потоці
# ------------------------------------------------------------------
def _thread_main():
    """Виконується в daemon-потоці. Містить увесь asyncio event loop."""
    global _loop

    if sys.platform == 'win32':
        # Python 3.12 + Windows: SelectorEventLoop потрібен для websockets
        _loop = asyncio.SelectorEventLoop()
    else:
        _loop = asyncio.new_event_loop()

    asyncio.set_event_loop(_loop)

    try:
        _loop.run_until_complete(_serve())
    except Exception as e:
        print(f'[Bridge] Помилка сервера: {e}')


def start():
    """Запускає WebSocket-сервер у фоновому потоці та чекає поки він готовий."""
    t = threading.Thread(target=_thread_main, daemon=True)
    t.start()
    # Чекаємо поки сервер реально починає слухати (макс 5 с)
    if not _server_ready.wait(timeout=5.0):
        print('[Bridge] Попередження: сервер не запустився за 5 секунд')


# ------------------------------------------------------------------
# Публічний API — синхронний виклик для skills.py
# ------------------------------------------------------------------
def get_links(timeout: float = 5.0) -> list | None:
    """
    Запитує посилання з активної вкладки браузера.
    Повертає [{title, href}, ...] або None якщо розширення не підключено.
    """
    global _pending_id, _last_links, _request_counter

    if _connection is None:
        return None

    _request_counter += 1
    _pending_id = _request_counter
    _last_links = None
    _response_event.clear()

    asyncio.run_coroutine_threadsafe(
        _connection.send(json.dumps({'action': 'get_links', 'id': _pending_id})),
        _loop
    )

    if _response_event.wait(timeout=timeout):
        return _last_links
    return None


def is_connected() -> bool:
    return _connection is not None
