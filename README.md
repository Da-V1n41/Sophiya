# 🎙️ Sophia — Україномовний голосовий асистент

Голосовий асистент для Windows з підтримкою офлайн-розпізнавання мовлення, синтезу мови українською та інтеграцією штучного інтелекту.

---

## ✨ Можливості

| Категорія | Команди |
|-----------|---------|
| **Медіа** | Spotify (пауза, наступний/попередній трек, гучність), YouTube |
| **Система** | час, дата, гучність ПК, скріншот, виключення, блокування, автозапуск |
| **Браузер** | пошук Google, відкрити сайт, зберегти сторінку (Chrome-розширення) |
| **Інформація** | погода, новини, курс валют, жарт, випадкове число |
| **Нотатки** | пам'ять (зберегти/переглянути/очистити), псевдоніми команд |
| **AI-режим** | розмова з Mistral AI (вмикається командою «ШІ режим») |

---

## 🛠️ Технології

- **Python 3.12**
- **CustomTkinter** — GUI (темна тема)
- **SpeechRecognition + Vosk** — розпізнавання мовлення (онлайн + офлайн)
- **Microsoft Edge-TTS** — синтез мови (`uk-UA-PolinaNeural`)
- **Mistral AI API** — обробка природної мови / AI-режим
- **WebSocket** — Chrome-розширення для роботи з браузером

---

## 🚀 Встановлення

### 1. Клонувати репозиторій

```bash
git clone https://github.com/Da-V1n41/Sophiya.git
cd Sophiya
```

### 2. Створити та активувати віртуальне середовище

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Встановити залежності

```bash
pip install -r requirements.txt
pip install edge-tts customtkinter
```

### 4. Завантажити Vosk-модель для офлайн-розпізнавання

Завантажте модель з [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models):

- **Мала (рекомендовано):** `vosk-model-small-uk-v3-lgraph` (~50 МБ)
- **Велика (точніша):** `vosk-model-uk-v3` (~300 МБ)

Розпакуйте папку в корінь проєкту:
```
Sophiya/
├── vosk-model-uk/       ← сюди
├── gui.py
├── main.py
...
```

### 5. Налаштувати конфігурацію

```bash
copy config.example.json config.json
```

Відкрийте `config.json` і заповніть:

```json
{
  "mistral_api_key": "ВАШ_КЛЮЧ_MISTRAL",
  "spotify_path": "C:\\Users\\ІМ'Я_КОРИСТУВАЧА\\AppData\\Roaming\\Spotify\\Spotify.exe"
}
```

Отримати безкоштовний API ключ Mistral: [console.mistral.ai](https://console.mistral.ai)

### 6. Запустити

```bash
python main.py
```

---

## 🗣️ Використання

**Слово-активатор:** `Софія` / `Софійка` / `Софа`

| Приклад команди | Дія |
|-----------------|-----|
| `Яка зараз погода?` | Погода в поточному місті |
| `Включи наступний трек` | Spotify → наступна пісня |
| `Знайди відео котики` | Відкрити YouTube пошук |
| `Котра година?` | Озвучити поточний час |
| `Зроби скріншот` | Зберегти знімок екрана |
| `ШІ режим` | Увімкнути режим розмови з AI |
| `Тихо` / `Замовкни` | Перервати мовлення |

---

## 📁 Структура проєкту

```
Sophiya/
├── main.py              # Точка входу
├── gui.py               # Інтерфейс (CustomTkinter)
├── voice.py             # TTS (Edge-TTS) + VAD
├── skills.py            # Головний роутер команд
├── skills_media.py      # Spotify, YouTube, медіа
├── skills_system.py     # Система, файли, ПК
├── skills_web.py        # Браузер, погода, новини
├── skills_notes.py      # Пам'ять, нотатки, аліаси
├── config.py            # Зчитування конфігурації
├── user_profile.py      # Профіль користувача
├── browser_bridge.py    # WebSocket для Chrome
├── words.py             # Слова-активатори
├── chrome_extension/    # Chrome-розширення (JS)
├── dataset.json         # Навчальний датасет фраз
├── aliases.json         # Псевдоніми команд
├── config.example.json  # Шаблон конфігурації
└── requirements.txt     # Python залежності
```

---

## ⚙️ Конфігурація (`config.json`)

| Параметр | За замовчуванням | Опис |
|----------|-----------------|------|
| `mistral_api_key` | `""` | API ключ Mistral AI |
| `spotify_path` | — | Шлях до Spotify.exe |
| `duck_level` | `0.25` | Гучність медіа під час мовлення (0–1) |
| `tts_cache_max_mb` | `100` | Ліміт кешу TTS у МБ |
| `inactivity_minutes` | `30` | Хвилин до авто-вимкнення мікрофона |
| `vad_threshold` | `300` | Поріг активації VAD |
| `debug` | `false` | Детальне логування |

---

## 📋 Вимоги

- Windows 10 / 11
- Python 3.12+
- Мікрофон
- Інтернет (для Google STT, Mistral AI, погоди, новин)
- Офлайн-режим STT доступний через Vosk (без інтернету)
