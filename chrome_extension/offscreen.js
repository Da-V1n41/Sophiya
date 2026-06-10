/**
 * offscreen.js — виконується в offscreen-документі (персистентний в MV3).
 * Тримає постійне WebSocket-з'єднання з Sophia Python-сервером.
 * При розриві — автоматично перепідключається кожні 3 секунди.
 */

const WS_URL = 'ws://localhost:8765';
let ws = null;
let reconnectTimer = null;

function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING ||
             ws.readyState === WebSocket.OPEN)) {
    return;
  }

  ws = new WebSocket(WS_URL);

  ws.onopen = function () {
    console.log('[Sophia] Підключено до сервера');
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = function (event) {
    let msg;
    try { msg = JSON.parse(event.data); } catch (e) { return; }

    if (msg.action === 'get_links') {
      // Просимо background зібрати посилання з активної вкладки
      chrome.runtime.sendMessage(
        { action: 'get_links_from_tab', id: msg.id },
        function (response) {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type:  'links',
              id:    msg.id,
              links: (response && response.links) ? response.links : []
            }));
          }
        }
      );
    }
  };

  ws.onclose = function () {
    console.log('[Sophia] З\'єднання закрито. Перепідключення через 3с...');
    ws = null;
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = function () {
    ws.close();
  };
}

connect();
