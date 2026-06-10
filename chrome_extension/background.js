/**
 * Sophia Link Helper — background.js (Manifest V3)
 *
 * WebSocket живе прямо в Service Worker.
 * chrome.alarms кожні 20 секунд не дають SW засинати.
 * При розриві — перепідключення кожні 3 секунди.
 */

const WS_URL = 'ws://127.0.0.1:8765';
let ws = null;
let reconnectTimer = null;

// ---------------------------------------------------------------
// WebSocket — підключення
// ---------------------------------------------------------------
function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING ||
             ws.readyState === WebSocket.OPEN)) {
    return;
  }

  ws = new WebSocket(WS_URL);

  ws.onopen = function () {
    console.log('[Sophia] Підключено до сервера');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };

  ws.onmessage = function (event) {
    let msg;
    try { msg = JSON.parse(event.data); } catch (e) { return; }

    if (msg.action === 'get_links') {
      collectLinks(msg.id);
    }
  };

  ws.onclose = function () {
    console.log('[Sophia] З\'єднання закрито. Перепідключення через 3с...');
    ws = null;
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = function () {
    if (ws) ws.close();
  };
}

// ---------------------------------------------------------------
// Збираємо посилання з активної вкладки
// ---------------------------------------------------------------
function collectLinks(requestId) {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (!tabs || tabs.length === 0) {
      sendBack(requestId, []);
      return;
    }

    chrome.scripting.executeScript(
      { target: { tabId: tabs[0].id }, func: collectLinksFromPage },
      function (results) {
        if (chrome.runtime.lastError || !results || !results[0]) {
          sendBack(requestId, []);
          return;
        }
        sendBack(requestId, results[0].result || []);
      }
    );
  });
}

// ---------------------------------------------------------------
// Функція виконується прямо на сторінці браузера
// ---------------------------------------------------------------
function collectLinksFromPage() {
  // Домени/підрядки які виключаємо з результатів
  var SKIP = [
    '://www.google.com',   // навігація Google (домашня, webhp, imghp тощо)
    'gstatic.com',
    'googleapis.com',
    'accounts.google',
    'webcache.',
    'support.google',
    'policies.google',
    'maps.google',
    'google.com/search?',  // вкладені пошукові запити Google
    'google.com/url?',     // редиректи Google (якщо є)
    'javascript:',
    '#'                    // якорі на тій самій сторінці
  ];
  var seen = {};
  var out  = [];

  document.querySelectorAll('a[href]').forEach(function (a) {
    var href  = a.href;
    var title = (a.innerText || a.title || '').trim()
                  .replace(/\s+/g, ' ').slice(0, 70);

    if (!href || !href.startsWith('http')) return;
    if (seen[href]) return;

    for (var i = 0; i < SKIP.length; i++) {
      if (href.indexOf(SKIP[i]) !== -1) return;
    }

    // YouTube: залишаємо лише посилання на відео (/watch?v=)
    if (href.indexOf('youtube.com') !== -1 && href.indexOf('/watch?v=') === -1) return;

    // Пропускаємо посилання без читабельного тексту
    if (!title) return;

    // Пропускаємо якщо заголовок — лише часова мітка (напр. "16:02", "1:23:45")
    if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(title)) return;

    // Пропускаємо надто короткі заголовки (менше 3 символів)
    if (title.length < 3) return;

    seen[href] = 1;
    out.push({ title: title, href: href });
  });

  return out.slice(0, 15);
}

// ---------------------------------------------------------------
// Відправляємо результат назад до Sophia
// ---------------------------------------------------------------
function sendBack(requestId, links) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'links', id: requestId, links: links }));
  }
}

// ---------------------------------------------------------------
// Аларм кожні 20 секунд — не дає Service Worker засинати
// ---------------------------------------------------------------
chrome.alarms.create('keepAlive', { periodInMinutes: 0.33 });

chrome.alarms.onAlarm.addListener(function (alarm) {
  if (alarm.name === 'keepAlive') {
    // Якщо WebSocket пропав — перепідключаємось
    if (!ws || ws.readyState === WebSocket.CLOSED ||
               ws.readyState === WebSocket.CLOSING) {
      connect();
    }
  }
});

// ---------------------------------------------------------------
// Старт
// ---------------------------------------------------------------
connect();
