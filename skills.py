import os
import json
import uuid
import webbrowser
import sys
import subprocess
import functools

# --------------------------
# Конфіг (читається з config.py → config.json)
# --------------------------
from config import DEBUG, SPOTIFY_PATH, MISTRAL_API_KEY

# --------------------------
# Субмодулі навичок
# --------------------------
from skills_media import (
    current_track_info, _wait_for_track_change, _find_and_activate_window,
    pausa, next_track, prev_track, space, music, open_spotify,
    spotify_volume_up, spotify_volume_down, seek_forward, seek_backward,
)
from skills_system import (
    current_time, current_date, volume_up, volume_down,
    _press_keys, minimize_all, restore_windows, close_window, minimize_window,
    screenshot, open_notepad, open_calculator, open_explorer,
    open_telegram, open_steam, offpc, lock_pc,
    cancel_shutdown, goodnight_routine,
    enable_autostart, disable_autostart,
    system_info, system_ram, system_cpu, system_battery,
    clipboard_read, _open_folder,
    open_downloads, open_desktop, open_documents, open_pictures,
    open_videos, open_music_folder, open_disk_c, open_disk_d, open_disk_e,
)
from skills_web import (
    youtube, browser, search, search_yt, saver, offBot,
    _detect_city, weather, news, coin_flip, random_number, joke,
    morning_briefing, morning_routine,
)
from skills_notes import (
    about_me,
    ALIASES_FILE, _DEFAULT_ALIASES, _load_aliases, _save_aliases, open_alias,
    MEMORY_FILE, _load_memory, _save_memory,
    memory_save, memory_list, memory_clear, memory_forget,
)

import speech_recognition as sr
import voice
from voice import speaker
import time
import yt_dlp
import pyautogui
import datetime
import threading
import re
import ctypes
import ctypes.wintypes
from difflib import SequenceMatcher
try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral

try:
    import requests
except ImportError:
    requests = None

# --------------------------
# Керування гучністю системи (щоб мікрофон не ловив YouTube/музику)
# --------------------------
HAS_PYCAW = False  # Більше не мьютимо — просто фільтруємо по імені "Софія"

# --------------------------
# Постійні нагадування (зберігаються між перезапусками)
# --------------------------
REMINDERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reminders.json')


def _load_reminders():
    try:
        with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_reminders(reminders: list):
    try:
        with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(reminders, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Reminders] Помилка збереження: {e}")


def _remove_reminder(rid: str):
    reminders = _load_reminders()
    reminders = [r for r in reminders if r.get('id') != rid]
    _save_reminders(reminders)


# --------------------------
# Нечітке порівняння рядків (покращене)
# --------------------------
def fuzzy_match(text, phrase, threshold=0.7):
    """Перевіряє чи text містить phrase з допуском на помилки розпізнавання"""
    if phrase in text:
        return True

    phrase_words = phrase.split()
    text_words = text.split()

    if len(phrase_words) == 1:
        for tw in text_words:
            if SequenceMatcher(None, tw, phrase_words[0]).ratio() >= threshold:
                return True
        return False

    for i in range(len(text_words) - len(phrase_words) + 1):
        window = " ".join(text_words[i:i + len(phrase_words)])
        if SequenceMatcher(None, window, phrase).ratio() >= threshold:
            return True

    return False


@functools.lru_cache(maxsize=512)
def match_score(text, phrase):
    """Повертає числовий скор збігу (0.0 - 1.0). Чим вище — тим краще збіг.
    Результати кешуються — повторні виклики з тими ж аргументами миттєві.
    """
    if not text or not phrase:
        return 0.0

    # Точне входження — максимальний бонус
    if phrase in text:
        return 0.95 + min(0.05, len(phrase) / 100)

    phrase_words = phrase.split()
    text_words = text.split()

    if len(phrase_words) == 1:
        best = 0.0
        for tw in text_words:
            ratio = SequenceMatcher(None, tw, phrase_words[0]).ratio()
            best = max(best, ratio)
        return best

    # Скользяще вікно
    best = 0.0
    for i in range(len(text_words) - len(phrase_words) + 1):
        window = " ".join(text_words[i:i + len(phrase_words)])
        ratio = SequenceMatcher(None, window, phrase).ratio()
        best = max(best, ratio)

    return best


# --------------------------
# Фрази для перемикання режиму ШІ
# --------------------------
AI_ON_PHRASES = [
    "увімкни штучний інтелект",
    "увімкни ші",
    "включи ші",
    "включи штучний інтелект",
    "запусти ші",
    "запусти штучний інтелект",
    "активуй ші",
    "режим ші",
    "розумний режим",
    "думай сама",
    "ввімкни ші",
    "умкни ші",
]

AI_OFF_PHRASES = [
    "вимкни ші",
    "вимкни штучний інтелект",
    "звичайний режим",
    "вийди з ші",
    "вийти з ші",
    "стоп ші",
    "простий режим",
    "перестань думати",
    "вимкни розумний режим",
    "вікни ші",
    "вимкни розумний",
]

STOP_PHRASES = [
    "стоп",
    "зупинись",
    "замовкни",
    "досить",
    "тихо",
]

EXIT_PHRASES = [
    "вимкнись",
    "вимкни себе",
    "закрийся",
    "закрий себе",
    "вийди",
    "до побачення",
    "бувай",
    "вихід",
    "завершись",
    "завершити роботу",
    "йди спати",
]

RESTART_PHRASES = [
    "перезапустись",
    "перезапусти себе",
    "перезавантажся",
    "перезавантажись",
    "рестарт",
    "перезапуск",
    "restart",
]

# Карта функцій → сайт (для анафори "знайди там X")
# Ключ — ім'я функції (__name__), значення — метадані сайту
_FUNC_SITE_MAP: dict[str, dict] = {
    'youtube':   {'name': 'YouTube', 'search_url': 'https://www.youtube.com/results?search_query={}'},
    'search_yt': {'name': 'YouTube', 'search_url': 'https://www.youtube.com/results?search_query={}'},
    'browser':   {'name': 'Google',  'search_url': 'https://www.google.com/search?q={}'},
    'search':    {'name': 'Google',  'search_url': 'https://www.google.com/search?q={}'},
    'github':    {'name': 'GitHub',  'search_url': 'https://github.com/search?q={}'},
    'wikipedia': {'name': 'Wikipedia', 'search_url': 'https://uk.wikipedia.org/w/index.php?search={}'},
}

# Імена, на які відгукується асистент
TRIGGER_NAMES = {
    'софія', 'софійка', 'софа', 'софію', 'софії', 'софіє', 'софі',
    'sofiya', 'sofia', 'sophiya', 'sophia',
}


def extract_command_after_name(text):
    """Видаляє ім'я бота з тексту і повертає команду, або None якщо імені немає"""
    words = text.lower().split()
    for i, word in enumerate(words):
        # Перевірка точна або fuzzy на ім'я
        for name in TRIGGER_NAMES:
            if word == name or SequenceMatcher(None, word, name).ratio() >= 0.75:
                # Повертаємо все після імені
                command = ' '.join(words[i + 1:]).strip()
                return command if command else ''
    return None


# --------------------------
# Клас українського асистента
# --------------------------
class UkrainianAIAssistant:
    RECAL_INTERVAL = 300   # секунд між автоперекалібруваннями (5 хв)
    def __init__(self):
        # Ініціалізація Mistral (ключ з config.py → config.json)
        if not MISTRAL_API_KEY:
            print("[Config] УВАГА: mistral_api_key не знайдено в config.json")
        self.client = Mistral(api_key=MISTRAL_API_KEY)
        self.model = "mistral-tiny"
        self.use_ai = False
        self.is_listening = False
        self.recognizer = sr.Recognizer()
        self._calibrated_threshold = 150
        self._is_busy = False
        self._last_spoke_time = 0.0        # залишаємо для сумісності
        self._last_recal_time  = 0.0       # час останнього перекалібрування
        self._last_command_time = 0.0      # час останньої успішної команди (для інактивності)

        # HTTP сесія для Google Speech
        self._http_session = requests.Session() if requests else None

        # Vosk офлайн модель (завантажується один раз)
        self._vosk_model = None
        self._vosk_rec = None
        threading.Thread(target=self._load_vosk, daemon=True).start()

        # Остання відповідь (для команди "повтори")
        self.last_response = ""

        # Контекст для "знову" / "відкрий його"
        self._last_opened_func = None   # func() → останній запуск програми/URL
        self._last_opened_name = ""     # людська назва
        self._last_search = None        # (query, engine) — останній пошук

        # Результати для "відкрий N-ту силку"
        self._last_links: list = []

        # Персональний профіль (зберігається між сесіями)
        import user_profile as _up
        self._profile: dict = _up.load()

        # Реакція на час доби — зберігаємо поточний слот щоб вітати лише раз
        # при зміні (ранок→вечір→ніч). Починаємо з '' щоб start_listening
        # ініціалізував правильний слот після свого вітання.
        self._greeted_time_slot: str = ''

        # Анафорний контекст сесії
        self._ctx_site:   dict | None = None  # {'name': str, 'search_url': str} — для "знайди там"
        self._ctx_search: dict | None = None  # {'query': str, 'engine': str}    — для "знайди ще"
        self._ctx_topic:  str  | None = None  # тема для "розкажи більше"

        # Підтвердження небезпечних дій
        self._pending_confirm: dict | None = None   # {'func', 'label', 'expires'}

        # Cooldown: час останнього виклику для кожної навички
        self._skill_last_called: dict = {}          # func → timestamp


        # Callback для оновлення UI (встановлюється з gui.py)
        self.on_status_change = None   # fn(status_text)
        self.on_message = None         # fn(sender, text)
        self.on_mode_change = None     # fn(is_ai)
        self.on_listening_change = None  # fn(is_listening)
        self.on_status_bar = None        # fn(engine_name)

        # Контекст розмови для ШІ
        self.conversation_history = [
            {"role": "system", "content": (
                "Ти — Софія, голосовий помічник. "
                "Правила: "
                "1. Відповідай ТІЛЬКИ українською. "
                "2. Максимум 1-2 речення. Твої відповіді озвучуються голосом — будь дуже лаконічною. "
                "3. НІКОЛИ не використовуй емодзі, смайлики, зірочки (**), хештеги або markdown. "
                "4. Давай просту, чисту відповідь без зайвих слів."
            )}
        ]

    # Небезпечні функції: вимагають голосового підтвердження перед виконанням.
    # cached_property — будується один раз на першому зверненні,
    # коли offpc/memory_clear вже визначені на рівні модуля.
    @functools.cached_property
    def _dangerous_funcs(self) -> dict:
        return {
            offpc:        "Вимкнення комп'ютера",
            memory_clear: "Очищення всієї пам'яті",
        }

    def _notify(self, event, *args):
        cb = getattr(self, f'on_{event}', None)
        if cb:
            try:
                cb(*args)
            except Exception:
                pass

    # --------------------------
    # Анафора — розуміння "там", "ще X", "про нього", "розкажи більше"
    # --------------------------

    def _extract_topic(self, text: str) -> str | None:
        """Витягує основну тему з тексту команди (для "розкажи більше")."""
        SKIP = {
            'знайди', 'пошукай', 'шукай', 'покажи', 'відкрий', 'розкажи',
            'що', 'таке', 'про', 'мені', 'будь', 'ласка', 'як', 'чому',
            'коли', 'де', 'скажи', 'поясни', 'дай', 'інформацію', 'хто',
        }
        words = [w for w in text.lower().split() if w not in SKIP and len(w) > 2]
        return ' '.join(words[:5]) if words else None

    def _resolve_anaphora(self, text: str) -> tuple[str, str | None]:
        """
        Розкриває займенникові посилання в команді.

        Повертає (new_text, result):
          • result is None  → продовжити обробку з new_text
          • result is str   → дія виконана, озвучити result і зупинитись

        Що підтримується:
          "знайди там X" / "пошукай там X"  → шукає на останньому сайті
          "знайди ще X"                      → продовжує той самий движок пошуку
          "розкажи про нього/неї/це"         → підставляє _ctx_topic
        """
        tl = text.lower().strip()

        # --- «там / туди / на ньому / на тому сайті» → шукаємо на останньому сайті ---
        THERE = ['там', 'туди', 'на ньому', 'на ній', 'в ньому', 'в ній',
                 'на тому сайті', 'на тому ж сайті', 'там же']
        SEARCH_VERBS = ['знайди', 'пошукай', 'шукай', 'покажи']

        if self._ctx_site:
            site = self._ctx_site
            for verb in SEARCH_VERBS:
                for there in THERE:
                    # «знайди там X»
                    if tl.startswith(f'{verb} {there} '):
                        query = tl[len(f'{verb} {there} '):].strip()
                        if query:
                            webbrowser.open(site['search_url'].format(query))
                            msg = f"Шукаю «{query}» на {site['name']}"
                            self._ctx_search = {'query': query, 'engine': site['name']}
                            self._ctx_topic  = self._extract_topic(query)
                            print(f"[Анафора] там → {site['name']}: «{query}»")
                            return text, msg
                    # «знайди X там»
                    if tl.startswith(f'{verb} ') and any(tl.endswith(f' {t}') for t in THERE):
                        for there2 in THERE:
                            suffix = f' {there2}'
                            if tl.endswith(suffix):
                                query = tl[len(f'{verb} '):len(tl) - len(suffix)].strip()
                                if query:
                                    webbrowser.open(site['search_url'].format(query))
                                    msg = f"Шукаю «{query}» на {site['name']}"
                                    self._ctx_search = {'query': query, 'engine': site['name']}
                                    self._ctx_topic  = self._extract_topic(query)
                                    print(f"[Анафора] X там → {site['name']}: «{query}»")
                                    return text, msg

        # --- «знайди ще X» / «пошукай ще X» → продовжуємо той самий движок ---
        if self._ctx_search:
            engine = self._ctx_search['engine']
            for prefix in ['знайди ще ', 'пошукай ще ', 'ще знайди ', 'також знайди ']:
                if tl.startswith(prefix):
                    query = tl[len(prefix):].strip()
                    if query:
                        if engine == 'YouTube':
                            resolved = f'знайди на ютубі {query}'
                        else:
                            resolved = f'знайди {query}'
                        print(f"[Анафора] ще → {engine}: «{query}»")
                        return resolved, None

        # --- «розкажи про нього/неї/це/них/їх» → підставляємо тему ---
        PRONOUN_MAP = {
            'про нього': 'про', 'про неї': 'про', 'про це': 'про',
            'про них': 'про', 'про їх': 'про', 'про нього детальніше': 'детальніше про',
        }
        if self._ctx_topic:
            for pronoun, verb in PRONOUN_MAP.items():
                if pronoun in tl:
                    resolved = tl.replace(pronoun, f'{verb} {self._ctx_topic}').strip()
                    print(f"[Анафора] займенник «{pronoun}» → «{self._ctx_topic}»")
                    return resolved, None

        return text, None   # нічого не змінилось

    def _one_shot_ai(self, prompt: str) -> str | None:
        """Один запит до Mistral без збереження в conversation_history."""
        try:
            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    self.conversation_history[0],           # system prompt
                    {'role': 'user', 'content': prompt},
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AI one-shot] Помилка: {e}")
            return None

    # --------------------------
    # Vosk офлайн розпізнавання
    # --------------------------
    def _load_vosk(self):
        """Завантажує Vosk модель у фоні при старті"""
        try:
            from vosk import Model, KaldiRecognizer
            import json as _json

            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vosk-model-uk')
            if not os.path.exists(model_path):
                print("[Vosk] Модель не знайдена — офлайн режим недоступний")
                return

            self._vosk_model = Model(model_path)
            self._vosk_rec = KaldiRecognizer(self._vosk_model, 16000)
            print("[Vosk] Модель завантажена — офлайн режим готовий")
        except Exception as e:
            print(f"[Vosk] Помилка завантаження: {e}")

    def _recognize_offline(self, audio):
        """Розпізнає аудіо через Vosk (без інтернету)"""
        try:
            import json as _json
            from vosk import KaldiRecognizer

            if self._vosk_model is None:
                return None

            rec = KaldiRecognizer(self._vosk_model, 16000)
            rec.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
            result = _json.loads(rec.FinalResult())
            text = result.get('text', '').strip()
            return text if text else None
        except Exception as e:
            print(f"[Vosk] Помилка розпізнавання: {e}")
            return None

    # --------------------------
    # Stop-листенер: слухає "тихо/замовкни" під час мовлення Sophii
    # --------------------------
    # Слова, що перериють поточне мовлення. Підмножина STOP_PHRASES.
    _INTERRUPT_WORDS = ('тихо', 'замовкни', 'мовчи', 'стоп',
                        'досить', 'годі', 'припини')

    def _listen_for_interrupt(self, source, _voice):
        """Швидко слухає під час _is_speaking. Якщо чує стоп-слово → перериває.

        Використовує Vosk (офлайн) для миттєвого розпізнавання без мережі.
        Echo-фільтр: відкидає текст, що збігається з last_response (Sophia сама себе чує).
        """
        # Vosk ще не завантажився — просто чекаємо
        if self._vosk_model is None:
            time.sleep(0.05)
            return

        try:
            # Короткий запис: ~0.4с очікування початку фрази, ≤1.2с самої фрази
            old_pause  = self.recognizer.pause_threshold
            old_phrase = self.recognizer.phrase_threshold
            self.recognizer.pause_threshold  = 0.3
            self.recognizer.phrase_threshold = 0.05
            try:
                audio = self.recognizer.listen(source, timeout=0.4, phrase_time_limit=1.2)
            finally:
                self.recognizer.pause_threshold  = old_pause
                self.recognizer.phrase_threshold = old_phrase
        except sr.WaitTimeoutError:
            return
        except Exception:
            time.sleep(0.05)
            return

        # Sophia вже могла закінчити поки ми слухали — тоді це звичайна команда,
        # хай головний цикл нормально її обробляє
        if not _voice._is_speaking:
            return

        # Quick VAD: якщо звуку зовсім мало — пропускаємо
        if not self._has_speech_pattern(audio):
            return

        text = self._recognize_offline(audio)
        if not text:
            return

        text_lower = text.lower().strip()

        # Echo-фільтр: якщо це шматок того, що Sophia щойно сказала → ігноруємо
        last = (self.last_response or '').lower()
        if last and (text_lower in last or
                     SequenceMatcher(None, text_lower, last[:len(text_lower)+5]).ratio() > 0.7):
            return

        # Перевіряємо стоп-слово
        for word in self._INTERRUPT_WORDS:
            if word in text_lower:
                _voice.stop_speech()
                self._notify('status_change', 'Перервано')
                if DEBUG: print(f"[Interrupt] Зупинено через '{word}' (почула: «{text}»)")
                return

    # --------------------------
    # VAD: перевірка чи є мовлення у аудіо
    # --------------------------
    def _has_speech_pattern(self, audio):
        """
        Три рівні VAD — всі три мають бути True:

        1. Абсолютний поріг (peak_rms):
           Пік RMS у кліпі повинен значно перевищувати фоновий шум.
           Тихий фон з паузами має низький пік → відхиляємо.

        2. Динаміка (dynamic_ratio):
           Відношення max_rms / mean_rms — мовлення різке (≥ 2.5×),
           рівномірний фон близький до 1.

        3. Розподіл тиші (quiet_ratio):
           Частка «тихих» фреймів (< 25% від піку) — мовлення ≥ 22%,
           стаціонарний звук < 10%.
        """
        try:
            import audioop
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            chunk_size = 1600  # 0.1 с при 16000 Гц, 16-біт
            chunks = [raw[i:i + chunk_size] for i in range(0, len(raw) - chunk_size, chunk_size)]
            if len(chunks) < 5:
                return True  # Занадто короткий — пропускаємо аналіз

            rms_vals = [audioop.rms(c, 2) for c in chunks]
            max_rms  = max(rms_vals)
            mean_rms = sum(rms_vals) / len(rms_vals)

            # --- Рівень 1: абсолютний поріг ---
            # Мінімальний пік = max(300, ambient * 2.5)
            # _calibrated_threshold відкалібровано під поточний фон
            speech_floor = max(300, self._calibrated_threshold * 2.5)
            peak_ok = max_rms >= speech_floor

            # --- Рівень 2: динаміка (пік / середнє) ---
            dynamic_ratio = max_rms / mean_rms if mean_rms > 0 else 1.0
            dynamic_ok = dynamic_ratio >= 2.5   # мовлення різке, фон рівний

            # --- Рівень 3: розподіл тиші ---
            quiet_threshold = max_rms * 0.25
            quiet_count = sum(1 for r in rms_vals if r < quiet_threshold)
            quiet_ratio = quiet_count / len(rms_vals)
            quiet_ok = quiet_ratio >= 0.22

            has_speech = peak_ok and dynamic_ok and quiet_ok
            print(
                f"[VAD] пік={max_rms:.0f}(поріг={speech_floor:.0f}) "
                f"динаміка={dynamic_ratio:.1f}x "
                f"тиша={quiet_ratio:.0%} "
                f"→ {'✓ мовлення' if has_speech else '✗ фон'}"
            )
            return has_speech
        except Exception:
            return True  # При помилці — пропускаємо до Google

    # --------------------------
    # Перевірка луни власного мовлення
    # --------------------------
    def _is_echo(self, text: str) -> bool:
        """
        Повертає True якщо розпізнаний текст схожий на останню відповідь Софії.
        Захищає від ситуації коли мікрофон ловить звук з колонок.
        """
        if not self.last_response:
            return False
        t = text.lower().strip()
        r = self.last_response.lower().strip()
        # Точне входження
        if t in r or r in t:
            return True
        # Нечітке порівняння
        score = SequenceMatcher(None, t, r).ratio()
        return score > 0.55

    # --------------------------
    # Слухання голосу (Google API)
    # --------------------------
    def _ask_confirmation(self, question):
        """Питає так/ні і повертає True/False"""
        speaker(question)
        self._notify('message', 'Софія', question)

        time.sleep(0.5)

        try:
            with sr.Microphone(sample_rate=16000) as source:
                self._notify('status_change', 'Так чи ні?')
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
            answer = self.recognizer.recognize_google(audio, language="uk-UA").lower()
            self._notify('message', 'Ви', answer)
            return any(w in answer for w in ['так', 'да', 'ага', 'точно', 'вірно', 'правильно', 'угу', 'ну да', 'давай', 'так так'])
        except Exception:
            return False

    # --------------------------
    # Основний цикл команд (скорінгова система)
    # --------------------------
    # Слова-підтвердження та скасування
    _CONFIRM_WORDS = {'так', 'підтверджую', 'давай', 'ок', 'погоджуюсь', 'виконуй'}
    _DENY_WORDS    = {'ні', 'скасуй', 'відміни', 'відмінити', 'не треба', 'стоп', 'зупинись'}
    # Таймаут очікування підтвердження (секунди)
    _CONFIRM_TIMEOUT = 15.0

    # Cooldown між повторними викликами однієї навички (секунди)
    # Захищає від подвійного розпізнавання одного слова ("пауза пауза")
    _SKILL_COOLDOWN = 1.5
    # Навички без cooldown — їх можна викликати будь-коли підряд
    _NO_COOLDOWN = {next_track, prev_track, seek_forward, seek_backward,
                   volume_up, volume_down, spotify_volume_up, spotify_volume_down}

    # ------------------------------------------------------------------
    # Варіативність відповідей: префікс → список варіантів
    # Оригінал включено кілька разів → зберігається ~40-50% часу
    # ------------------------------------------------------------------
    _RESPONSE_VARIANTS: dict = {
        'Відкриваю ': ['Відкриваю ', 'Відкриваю ', 'Зараз відкрию ', 'Запускаю '],
        'Запускаю ':  ['Запускаю ',  'Запускаю ',  'Зараз запускаю ', 'Відкриваю '],
        'Включаю ':   ['Включаю ',   'Вмикаю ',    'Зараз увімкну '],
        'Вмикаю ':    ['Вмикаю ',    'Включаю ',   'Запускаю '],
        'Шукаю':      ['Шукаю',      'Шукаю',      'Зараз знайду', 'Дивлюся —'],
        'Готово':     ['Готово',     'Зроблено!',  'Ось!',          'Будь ласка!'],
        'Відкрив ':   ['Відкрив ',   'Відкрив ',   'Ось — '],
    }

    # ------------------------------------------------------------------
    # Емоційні реакції: (набір тригерів, список відповідей)
    # ------------------------------------------------------------------
    _EMOTIONAL_REACTIONS: list = [
        (
            {'дякую', 'спасибі', 'дуже дякую', 'велике дякую', 'щиро дякую', 'дякую тобі'},
            ['Радо допомогти!', 'Завжди будь ласка!', 'Для мене це задоволення!', 'Немає за що!'],
        ),
        (
            {'ти класна', 'ти молодець', 'добре зробила', 'гарна робота', 'ти чудова',
             'ти найкраща', 'ти супер', 'ти розумна'},
            ['Приємно чути!', 'Стараюся!', 'Дякую — це дуже приємно!', 'Намагаюся бути корисною!'],
        ),
        (
            {'вибач', 'перепрошую', 'вибачте', 'пробач'},
            ['Нічого страшного!', 'Все добре!', 'Не переймайся!', 'Все гаразд!'],
        ),
        (
            {'як ти', 'як справи', 'ти добре', 'як ти себе почуваєш', 'як ти сьогодні'},
            ['Дякую, що питаєш! Готова до роботи.', 'Чудово! Завжди готова допомагати.',
             'Все добре, дякую!'],
        ),
        (
            {'привіт', 'хай', 'вітання', 'добрий ранок', 'доброго ранку',
             'добрий день', 'доброго дня', 'добрий вечір'},
            ['Привіт! Слухаю.', 'Вітаю! Чим можу допомогти?', 'Привіт! Готова до роботи.'],
        ),
    ]

    def process_command(self, text, skip_name_check=False):
        if not text:
            return

        # --- ПРІОРИТЕТ: очікуємо підтвердження небезпечної дії ---
        # Спрацьовує навіть без імені "Софія" — щоб просте "так" теж проходило.
        if self._pending_confirm is not None:
            if time.time() > self._pending_confirm['expires']:
                # Час вийшов — скасовуємо автоматично
                self._pending_confirm = None
                msg = "Час вийшов. Дію скасовано."
                self._notify('message', 'Софія', msg)
                speaker(msg)
            else:
                # Витягуємо команду (знімаємо ім'я якщо є)
                raw = text.strip().lower()
                after_name = extract_command_after_name(raw)
                check = after_name if after_name is not None else raw

                if check in self._CONFIRM_WORDS or any(check.startswith(w) for w in self._CONFIRM_WORDS):
                    pending = self._pending_confirm
                    self._pending_confirm = None
                    print(f"[Confirm] Підтверджено: {pending['label']}")
                    try:
                        result = pending['func']()
                        if result:
                            self.last_response = result
                            self._notify('message', 'Софія', result)
                            speaker(result)
                    except Exception as e:
                        print(f"[Confirm] Помилка при виконанні: {e}")
                    return

                elif check in self._DENY_WORDS or any(check.startswith(w) for w in self._DENY_WORDS):
                    self._pending_confirm = None
                    msg = "Скасовано."
                    self._notify('message', 'Софія', msg)
                    speaker(msg)
                    return

                else:
                    # Нова команда — скасовуємо очікування і обробляємо далі
                    self._pending_confirm = None

        if skip_name_check:
            text = text.strip()
            # Якщо користувач все одно сказав "Софія ..." — знімаємо ім'я
            maybe = extract_command_after_name(text)
            if maybe is not None and maybe != '':
                text = maybe
        else:
            # Голосовий ввід — перевіряємо ім'я "Софія"
            command = extract_command_after_name(text)
            if command is None:
                self._notify('status_change', 'Слухаю... (скажіть "Софія" + команду)')
                return

            if command == '':
                speaker("Слухаю вас")
                self._notify('status_change', 'Чекаю команду...')
                return

            text = command
        if DEBUG: print(f"[DEBUG] Команда після імені: '{text}'")

        # --- Навчання імені ---
        import user_profile as _up
        _learned_name = _up.extract_name(text)
        if _learned_name:
            _up.set_name(self._profile, _learned_name)
            msg = f"Приємно познайомитись, {_learned_name}! Буду пам'ятати."
            self.last_response = msg
            self._notify('message', 'Софія', msg)
            speaker(msg)
            return

        # --- Реакція на бездіяльність (>30 хв без команд) ---
        _INACTIVITY_THRESHOLD = 1800
        if self._last_command_time > 0 and (time.time() - self._last_command_time) > _INACTIVITY_THRESHOLD:
            import random as _rnd_ia
            _back_msg = _rnd_ia.choice([
                "О, ти повернувся! Все добре?",
                "Давно тебе не чула! Радий тебе чути.",
                "О, привіт! Я вже думала ти забув про мене.",
                "Нарешті! Трохи нудьгувала без тебе.",
            ])
            self._notify('message', 'Софія', _back_msg)
            speaker(_back_msg)
        self._last_command_time = time.time()

        # --- Реакція на зміну часового слоту ---
        self._maybe_greet_time_of_day()

        # --- Емоційні реакції ---
        import random as _rnd
        _tl = text.lower().strip()
        for _triggers, _responses in self._EMOTIONAL_REACTIONS:
            if _tl in _triggers or any(
                _tl == t or _tl.startswith(t + ' ')
                for t in _triggers
            ):
                msg = _rnd.choice(_responses)
                self.last_response = msg
                self._notify('message', 'Софія', msg)
                speaker(msg)
                return

        # --- Анафора: розкриваємо займенники і контекстні посилання ---
        text, anaphora_result = self._resolve_anaphora(text)
        if anaphora_result is not None:
            # Дія вже виконана всередині _resolve_anaphora (напр. відкрив URL)
            self.last_response = anaphora_result
            self._notify('message', 'Софія', anaphora_result)
            speaker(anaphora_result)
            return

        text_lower_check = text.lower().strip()

        # --- «Розкажи більше / детальніше / що ще» → one-shot AI про останню тему ---
        _MORE_PHRASES = [
            'розкажи більше', 'розкажи детальніше', 'розкажи докладніше',
            'що ще', 'і що ще', 'продовж', 'детальніше', 'докладніше',
            'розкажи ще', 'що ще можеш сказати', 'цікаво більше',
        ]
        if any(text_lower_check == p or text_lower_check.startswith(p + ' ')
               for p in _MORE_PHRASES):
            if self._ctx_topic:
                self._notify('status_change', 'Думаю...')
                prompt = f"Коротко (2-4 речення) розкажи більше про: {self._ctx_topic}"
                answer = self._one_shot_ai(prompt)
                if answer:
                    self.last_response = answer
                    self._notify('message', 'Софія', answer)
                    speaker(self._clean_for_speech(answer))
                else:
                    speaker("Не вдалося отримати більше інформації.")
            else:
                speaker("Не знаю про що розповісти — спочатку задайте питання.")
            return

        # --- 1. Завжди перевіряємо: перемикання режиму ШІ та стоп ---
        candidates = []

        # Якщо є точний збіг у skill map — exit/stop не додаємо до кандидатів,
        # щоб "вимкни комп'ютер" не плутати з "вимкнись" (fuzzy 0.857 ≥ 0.80).
        _text_stripped = text.strip()
        _has_exact_skill = self._exact_skill_map.get(_text_stripped.lower()) is not None

        for phrase in AI_ON_PHRASES:
            score = match_score(text, phrase)
            if score >= 0.80:
                candidates.append((score, 'ai_on', phrase))

        for phrase in AI_OFF_PHRASES:
            score = match_score(text, phrase)
            if score >= 0.80:
                candidates.append((score, 'ai_off', phrase))

        if not _has_exact_skill:
            for phrase in STOP_PHRASES:
                score = match_score(_text_stripped, phrase)
                if score >= 0.80:
                    candidates.append((score, 'stop', phrase))

            for phrase in EXIT_PHRASES:
                score = match_score(_text_stripped, phrase)
                if score >= 0.80:
                    candidates.append((score, 'exit', phrase))

            for phrase in RESTART_PHRASES:
                score = match_score(_text_stripped, phrase)
                if score >= 0.80:
                    candidates.append((score, 'restart', phrase))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_type, best_data = candidates[0]
            if DEBUG: print(f"[DEBUG] Збіг режиму: type={best_type}, score={best_score:.2f}")

            if best_type == 'ai_on':
                self.use_ai = True
                self._notify('mode_change', True)
                self._notify('message', 'Софія', 'Штучний інтелект активовано')
                speaker("Штучний інтелект активовано. Можете питати що завгодно.")
                return

            elif best_type == 'ai_off':
                self.use_ai = False
                self._notify('mode_change', False)
                self.conversation_history = self.conversation_history[:1]
                self._notify('message', 'Софія', 'Звичайний режим')
                speaker("Повертаюся у звичайний режим")
                return

            elif best_type == 'stop':
                self._notify('status_change', 'Зупинено')
                return

            elif best_type == 'exit':
                def _do_exit():
                    self._notify('message', 'Софія', 'До зустрічі! Вимикаюсь.')
                    speaker("До зустрічі! Гарного дня!")
                    self.stop_listening()
                    import voice as _v_exit
                    _v_exit.force_restore()   # відновити гучність медіа перед виходом
                    import os
                    os._exit(0)
                self._pending_confirm = {
                    'func':    _do_exit,
                    'label':   'Закрити Sofiya',
                    'expires': time.time() + self._CONFIRM_TIMEOUT,
                }
                msg = "Ви впевнені? Закрити програму. Скажіть «так» для підтвердження."
                self._notify('message', 'Софія', msg)
                speaker(msg)
                return

            elif best_type == 'restart':
                msg = 'Перезапускаюсь, зачекайте!'
                self._notify('message', 'Софія', msg)
                speaker(msg)
                self.stop_listening()
                import voice as _v_r
                _v_r.force_restore()
                # Визначаємо точку входу відносно розташування skills.py
                _here = os.path.dirname(os.path.abspath(__file__))
                _entry = None
                for _candidate in ('main.py', 'gui.py'):
                    _p = os.path.join(_here, _candidate)
                    if os.path.exists(_p):
                        _entry = _p
                        break
                if _entry is None:
                    _entry = os.path.abspath(sys.argv[0])
                # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP — новий процес повністю
                # незалежний від батьківського, не закривається разом з ним.
                _flags = (subprocess.DETACHED_PROCESS
                          | subprocess.CREATE_NEW_PROCESS_GROUP)
                subprocess.Popen(
                    [sys.executable, _entry],
                    cwd=_here,
                    creationflags=_flags,
                    close_fds=True,
                )
                import os as _os
                _os._exit(0)

        text_lower = text.lower().strip()

        # --- 2. Повтори ---
        repeat_phrases = ['повтори', 'повтори що сказала', 'скажи ще раз', 'не почув', 'не почула']
        if any(text_lower == p or text_lower.startswith(p) for p in repeat_phrases):
            if self.last_response:
                self._notify('message', 'Софія', self.last_response)
                speaker(self.last_response)
            else:
                msg = "Поки нічого не казала."
                self._notify('message', 'Софія', msg)
                speaker(msg)
            return

        # --- Контекст: "знову" / "відкрий його" / "запусти ще раз" ---
        context_triggers = [
            'знову', 'ще раз', 'відкрий його', 'відкрий її',
            'відкрий це знову', 'запусти ще раз', 'відчини його', 'повтори дію',
        ]
        if text_lower in context_triggers or any(text_lower.startswith(t) for t in context_triggers):
            if self._last_opened_func:
                try:
                    result = self._last_opened_func()
                    msg = result or f"Відкриваю {self._last_opened_name} знову"
                    self.last_response = msg
                    self._notify('message', 'Софія', msg)
                    speaker(msg)
                except Exception:
                    speaker(f"Не вдалося повторити дію")
            else:
                speaker("Поки нічого не відкривала.")
            return

        # --- 2. Пам'ять (запам'ятай.../забудь...) ---
        memory_prefixes = ["запам'ятай", "запамятай", "запиши", "нотатка"]
        forget_prefixes = ["забудь", "видали нотатку", "видали запис"]
        for prefix in memory_prefixes:
            if text_lower.startswith(prefix):
                note_text = text_lower[len(prefix):].strip()
                result = memory_save(note_text)
                self._notify('message', 'Софія', result)
                speaker(result)
                return
        for prefix in forget_prefixes:
            if text_lower.startswith(prefix):
                what = text_lower[len(prefix):].strip()
                result = memory_forget(what)
                self._notify('message', 'Софія', result)
                speaker(result)
                return

        # --- Псевдоніми: управління ---
        if any(text_lower.startswith(p) for p in ['додай псевдонім', 'новий псевдонім', 'створи псевдонім']):
            # "додай псевдонім робота це code"
            for pref in ['додай псевдонім', 'новий псевдонім', 'створи псевдонім']:
                if text_lower.startswith(pref):
                    rest = text_lower[len(pref):].strip()
                    break
            matched_sep = None
            for sep in [' це ', ' = ', ' відкриває ', ' запускає ', ' як ']:
                if sep in rest:
                    matched_sep = sep
                    break
            if matched_sep:
                name, target = rest.split(matched_sep, 1)
                name, target = name.strip(), target.strip()
                if name and target:
                    aliases = _load_aliases()
                    aliases[name] = target
                    _save_aliases(aliases)
                    result = f"Додала псевдонім: '{name}'"
                    self._notify('message', 'Софія', result)
                    speaker(result)
                    return
            result = "Скажіть: додай псевдонім [назва] це [дія]. Наприклад: додай псевдонім робота це code"
            self._notify('message', 'Софія', result)
            speaker(result)
            return

        if any(text_lower.startswith(p) for p in ['видали псевдонім', 'прибери псевдонім', 'видали аліас']):
            for pref in ['видали псевдонім', 'прибери псевдонім', 'видали аліас']:
                if text_lower.startswith(pref):
                    name = text_lower[len(pref):].strip()
                    break
            if name:
                aliases = _load_aliases()
                if name in aliases:
                    del aliases[name]
                    _save_aliases(aliases)
                    result = f"Псевдонім '{name}' видалено."
                else:
                    result = f"Псевдонім '{name}' не знайдено."
                self._notify('message', 'Софія', result)
                speaker(result)
                return

        if any(text_lower.startswith(p) for p in ['покажи псевдоніми', 'список псевдонімів',
                                                    'які псевдоніми', 'мої псевдоніми', 'покажи аліаси']):
            aliases = _load_aliases()
            if not aliases:
                result = "Псевдонімів поки немає. Скажіть: додай псевдонім [назва] це [дія]."
            else:
                items = [f"'{k}'" for k in list(aliases.keys())[:6]]
                result = "Мої псевдоніми: " + ", ".join(items)
            self._notify('message', 'Софія', result)
            speaker(result)
            return

        # --- Точна гучність ---
        volume_result = self._handle_set_volume(text_lower)
        if volume_result:
            self._notify('message', 'Софія', volume_result)
            speaker(volume_result)
            return

        # --- Будильник (точний час HH:MM) ---
        alarm_result = self._handle_alarm(text_lower)
        if alarm_result:
            self._notify('message', 'Софія', alarm_result)
            speaker(alarm_result)
            return

        # --- Таймер / Нагадування ---
        timer_result = self._handle_timer(text_lower)
        if timer_result:
            self._notify('message', 'Софія', timer_result)
            speaker(timer_result)
            return

        # --- Вимкнення через час ---
        shutdown_result = self._handle_shutdown_timer(text_lower)
        if shutdown_result:
            self._notify('message', 'Софія', shutdown_result)
            speaker(shutdown_result)
            return

        # --- Калькулятор ---
        calc_result = self._handle_calculator(text_lower)
        if calc_result:
            self._notify('message', 'Софія', calc_result)
            speaker(calc_result)
            return

        # --- 3. Пошук з голосовим запитом (перед link_open — має вищий пріоритет) ---
        search_result = self._handle_search(text)
        if search_result:
            self._notify('message', 'Софія', search_result)
            speaker(search_result)
            return

        # --- 3. Відкрити посилання з браузера ("відкрий першу силку") ---
        link_result = self._handle_open_link(text_lower)
        if link_result is not None:
            self.last_response = link_result
            self._notify('message', 'Софія', link_result)
            speaker(link_result)
            return

        # --- Фактичні питання → one-shot AI (без переключення режиму) ---
        # Охоплює "що таке X", "розкажи про X", "чому X", а також
        # результат анафори "розкажи про [topic] детальніше".
        _KNOWLEDGE_STARTS = [
            'що таке ', 'що це ', 'хто такий ', 'хто така ', 'хто такі ',
            'як працює ', 'як влаштован', 'розкажи про ', 'поясни про ',
            'поясни ', 'що означає ', 'навіщо ', 'чому ', 'де знаходиться ',
            'коли виник', 'з чого складається ',
        ]
        for _kp in _KNOWLEDGE_STARTS:
            if text_lower.startswith(_kp):
                self._ctx_topic = self._extract_topic(text_lower)
                self._notify('status_change', 'Думаю...')
                _answer = self._one_shot_ai(f"Коротко (2-4 речення) українською:\n{text}")
                if _answer:
                    self.last_response = _answer
                    self._notify('message', 'Софія', _answer)
                    speaker(self._clean_for_speech(_answer))
                else:
                    speaker("Не вдалося отримати відповідь.")
                return

        # --- 3. Режим ШІ → все йде до Mistral ---
        if self.use_ai:
            self._notify('status_change', 'Думаю...')
            answer = self.generate_response(text)
            if answer:
                self.last_response = answer
                self._notify('message', 'Софія', answer)
                clean = self._clean_for_speech(answer)
                speaker(clean)
                self._ctx_topic = self._extract_topic(text)
            else:
                self._notify('message', 'Софія', 'Не вдалося згенерувати відповідь')
                speaker("Не вдалося згенерувати відповідь")
            return

        # --- 3. Звичайний режим → навички + прості відповіді ---
        candidates = []

        # ── Крок 1: точний збіг O(1) — перемагає будь-який fuzzy ──
        exact_func = self._exact_skill_map.get(text_lower)
        if exact_func:
            if DEBUG: print(f"[DEBUG] Точний збіг: '{text_lower}'")
            candidates.append((1.0, 'skill', (text_lower, exact_func)))
        else:
            # ── Крок 2: точне входження тригера в текст (швидко) ──
            for trigger, func in self._skill_map_list:
                if trigger in text_lower:
                    word_bonus = len(trigger.split()) * 0.02
                    candidates.append((0.95 + word_bonus, 'skill', (trigger, func)))

            # ── Крок 3: fuzzy тільки якщо точних збігів немає ──
            if not candidates:
                for trigger, func in self._skill_map_list:
                    score = match_score(text_lower, trigger)
                    if score >= 0.70:
                        word_bonus = len(trigger.split()) * 0.02
                        candidates.append((score + word_bonus, 'skill', (trigger, func)))

        simple = self._score_simple_queries(text)
        if simple:
            s_score, s_answer = simple
            if s_score >= 0.75:
                candidates.append((s_score, 'simple', s_answer))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_type, best_data = candidates[0]
            if DEBUG: print(f"[DEBUG] Найкращий збіг: type={best_type}, score={best_score:.2f}, data={best_data}")

            if best_type == 'skill':
                trigger, func = best_data

                # Небезпечна дія → просимо підтвердження
                danger_label = self._dangerous_funcs.get(func)
                if danger_label:
                    self._pending_confirm = {
                        'func':    func,
                        'label':   danger_label,
                        'expires': time.time() + self._CONFIRM_TIMEOUT,
                    }
                    msg = f"Ви впевнені? {danger_label}. Скажіть «так» для підтвердження."
                    self._notify('message', 'Софія', msg)
                    speaker(msg)
                    return

                # --- Cooldown: захист від подвійного розпізнавання ---
                if func not in self._NO_COOLDOWN:
                    _last = self._skill_last_called.get(func, 0)
                    if time.time() - _last < self._SKILL_COOLDOWN:
                        if DEBUG: print(f"[Cooldown] Пропуск '{trigger}' — повтор за {time.time()-_last:.2f}s")
                        return
                self._skill_last_called[func] = time.time()

                try:
                    result = func()
                    if result:
                        self.last_response = result
                        self._notify('message', 'Софія', result)
                        speaker(self._vary_response(result))
                    # Зберігаємо контекст якщо це відкриття чогось
                    _open_verbs = ('відкрий', 'запусти', 'відтвори', 'включи', 'увімкни')
                    if any(trigger.startswith(v) for v in _open_verbs):
                        self._last_opened_func = func
                        self._last_opened_name = trigger
                    # Оновлюємо анафорний контекст сайту (для "знайди там X")
                    site_info = _FUNC_SITE_MAP.get(func.__name__)
                    if site_info:
                        self._ctx_site = site_info
                        print(f"[Ctx] Сайт: {site_info['name']}")
                        import user_profile as _up
                        _up.record_site_open(self._profile, site_info['name'])
                except Exception as e:
                    print(f"Помилка навички: {e}")
                return

            elif best_type == 'simple':
                self.last_response = best_data
                self._notify('message', 'Софія', best_data)
                speaker(best_data)
                self._ctx_topic = self._extract_topic(text)
                return

        # --- Псевдоніми: відкрити за назвою ---
        # Спрацьовує лише якщо жодна навичка не підійшла
        _alias_prefixes = ['відкрий ', 'запусти ', 'відчини ', 'увімкни ']
        _alias_checked = False
        for _ap in _alias_prefixes:
            if text_lower.startswith(_ap):
                _alias_name = text_lower[len(_ap):].strip()
                _alias_result = open_alias(_alias_name)
                if _alias_result:
                    self.last_response = _alias_result
                    self._notify('message', 'Софія', _alias_result)
                    speaker(_alias_result)
                    return
                _alias_checked = True
                break  # Знайшли префікс, але псевдоніму немає

        # Спробуємо весь текст як псевдонім напряму ("музика", "пошта", "робота")
        if not _alias_checked:
            _alias_result = open_alias(text_lower)
            if _alias_result:
                self.last_response = _alias_result
                self._notify('message', 'Софія', _alias_result)
                speaker(_alias_result)
                return

        # --- Резервна перевірка команд вікон (лише якщо нічого не знайшли вище) ---
        # Порог 0.75 — вищий щоб не плутати з "відкрий диск/папку"
        window_commands = [
            (['згорни все', 'згорнеш все', 'сховай все', 'мінімізуй все',
              'покажи робочий стіл', 'звони все'], minimize_all),
            (['розгорни все', 'розгорни вікна', 'поверни вікна',
              'розгорніть вікна', 'розгромив вікна'], restore_windows),
            (['згорни вікно', 'згорнеш вікно', 'сховай вікно',
              'звони вікно', 'звони вікна', 'згорни вікна', 'згорнеш вікна'], minimize_window),
            (['закрий вікно', 'закрий це вікно'], close_window),
        ]
        for phrases, func in window_commands:
            best = max(match_score(text_lower, p) for p in phrases)
            if best >= 0.75:
                result = func()
                if result:
                    self.last_response = result
                    self._notify('message', 'Софія', result)
                    speaker(result)
                return

        # Нічого не знайшли — логуємо для аналізу
        self._log_unrecognized(text_lower)
        self._notify('message', 'Софія', "Не зрозуміла команду. Спробуйте ще раз.")
        speaker("Не зрозуміла, спробуйте ще раз.")

    # --------------------------
    # Логування невпізнаних команд
    # --------------------------
    _LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'unrecognized.log')

    def _log_unrecognized(self, text: str):
        """Записує невпізнану команду в лог-файл з часткою і топ-3 найближчими тригерами."""
        try:
            # Знаходимо найближчі тригери (для підказки що додати)
            scores = sorted(
                ((match_score(text, t), t) for t, _ in self._skill_map_list),
                reverse=True
            )[:3]
            hints = ', '.join(f'"{t}"({s:.2f})' for s, t in scores if s > 0.4)

            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            line = f"{ts} | {text}"
            if hints:
                line += f"  →  близько: {hints}"
            line += "\n"

            with open(self._LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception:
            pass

    # --------------------------
    # Карта навичок (повна, з варіантами вимови)
    # --------------------------
    @functools.cached_property
    def _exact_skill_map(self) -> dict:
        """Словник trigger→func для миттєвого O(1) точного збігу.
        Будується один раз при першому зверненні.
        """
        return {trigger: func for trigger, func in self._skill_map_list}

    @functools.cached_property
    def _skill_map_list(self) -> list:
        """Список (trigger, func) — будується один раз, далі кешується."""
        return self._get_skill_map()

    def _get_skill_map(self):
        return [
            # Музика — включення (багато варіантів!)
            ('включи музику', music),
            ('увімкни музику', music),
            ('запусти музику', music),
            ('поставь музику', music),
            ('постав музику', music),
            ('грай музику', music),
            ('відтвори музику', music),
            # Музика — пауза/стоп
            ('зупини музику', pausa),
            ('вимкни музику', pausa),
            ('постав на паузу', pausa),
            ('поставь на паузу', pausa),
            ('пауза', pausa),
            ('плей', pausa),
            ('play', pausa),
            # Наступний трек
            ('наступна пісня', next_track),
            ('наступний трек', next_track),
            ('інша пісня', next_track),
            ('переключи пісню', next_track),
            # Пошук (обробляється окремо в process_command)
            # залишаємо тут тільки для скорінгу — функції не викликаються
            # Ютуб
            ('відкрий ютуб', youtube),
            ('запусти ютуб', youtube),
            ('покажи ютуб', youtube),
            ('відкрий youtube', youtube),
            ('запусти youtube', youtube),
            # Браузер
            ('відкрий браузер', browser),
            ('запусти браузер', browser),
            ('відкрий інтернет', browser),
            ('відкрий гугл', browser),
            # Погода
            ('яка погода', weather),
            ('яка погода на вулиці', weather),
            ('скільки градусів', weather),
            ('скільки градусів на вулиці', weather),
            ('яка температура', weather),
            ('яка температура на вулиці', weather),
            ('що з погодою', weather),
            ('що там на вулиці', weather),
            ('що на вулиці', weather),
            # Гучність
            ('гучніше', volume_up),
            ('дай гучніше', volume_up),
            ('збільши звук', volume_up),
            ('збільш гучність', volume_up),
            ('голосніше', volume_up),
            ('додай звук', volume_up),
            ('тихіше', volume_down),
            ('зменши звук', volume_down),
            ('зменш гучність', volume_down),
            ('приглуши', volume_down),
            # Час
            ('котра година', current_time),
            ('яка година', current_time),
            ('який час', current_time),
            ('скільки часу', current_time),
            # Дата
            ('яка дата', current_date),
            ('який день', current_date),
            ('скажи дату', current_date),
            ('яке сьогодні число', current_date),
            ('який сьогодні день', current_date),
            # Клавіші
            ('натисни спейс', space),
            ('натисни пробіл', space),
            # Про себе
            ('розкажи про себе', about_me),
            ('хто ти така', about_me),
            ('що ти вмієш', about_me),
            ('що ти можеш', about_me),
            ('які твої можливості', about_me),
            ('представся', about_me),
            # Керування вікнами
            # Згорнути все
            ('згорни все', minimize_all),
            ('сховай все', minimize_all),
            ('мінімізуй все', minimize_all),
            ('покажи робочий стіл', minimize_all),
            ('звони все', minimize_all),
            # Розгорнути все
            ('розгорни все', restore_windows),
            ('розгорни вікна', restore_windows),
            ('поверни вікна', restore_windows),
            ('розгорніть вікна', restore_windows),
            ('розгромив вікна', restore_windows),
            # Згорнути поточне вікно
            ('згорни вікно', minimize_window),
            ('сховай вікно', minimize_window),
            ('звони вікно', minimize_window),
            ('звони вікна', minimize_window),
            # Закрити вікно
            ('закрий вікно', close_window),
            ('закрий це', close_window),
            ('зроби скріншот', screenshot),
            ('скріншот', screenshot),
            ('скрін', screenshot),
            ('знімок екрану', screenshot),
            # Запуск програм
            ('відкрий блокнот', open_notepad),
            ('запусти блокнот', open_notepad),
            ('відкрий калькулятор', open_calculator),
            ('запусти калькулятор', open_calculator),
            ('відкрий провідник', open_explorer),
            ('відкрий файли', open_explorer),
            ('відкрий телеграм', open_telegram),
            ('запусти телеграм', open_telegram),
            ('відкрий telegram', open_telegram),
            ('запусти telegram', open_telegram),
            ('відкрий стім', open_steam),
            ('запусти стім', open_steam),
            ('відкрий steam', open_steam),
            ('запусти steam', open_steam),
            ('відкрий спотіфай', open_spotify),
            ('запусти спотіфай', open_spotify),
            ('відкрий spotify', open_spotify),
            ('запусти spotify', open_spotify),
            # Папки
            ('відкрий завантаження', open_downloads),
            ('відкрий загрузки', open_downloads),
            ('відкрий downloads', open_downloads),
            ('відкрий робочий стіл', open_desktop),
            ('відкрий десктоп', open_desktop),
            ('відкрий документи', open_documents),
            ('відкрий зображення', open_pictures),
            ('відкрий картинки', open_pictures),
            ('відкрий фото', open_pictures),
            ('відкрий відео', open_videos),
            ('відкрий музику папку', open_music_folder),
            ('відкрий диск с', open_disk_c),
            ('відкрий диск ц', open_disk_c),
            ('відкрий диск це', open_disk_c),
            ('відкрий диск сі', open_disk_c),
            ('відкрий диск c', open_disk_c),
            ('відкрий диск d', open_disk_d),
            ('відкрий диск д', open_disk_d),
            ('відкрий диск ді', open_disk_d),
            ('відкрий диск де', open_disk_d),
            ('відкрий диск е', open_disk_e),
            ('відкрий диск e', open_disk_e),
            ('відкрий диск і', open_disk_e),
            # Пам'ять
            ('що ти памятаєш', memory_list),
            ("що ти пам'ятаєш", memory_list),
            ('що запамятала', memory_list),
            ("що запам'ятала", memory_list),
            ('покажи нотатки', memory_list),
            ('мої нотатки', memory_list),
            ('очисти память', memory_clear),
            ("очисти пам'ять", memory_clear),
            ('забудь все', memory_clear),
            # Попередній трек
            ('попередня пісня', prev_track),
            ('попередній трек', prev_track),
            ('поверни пісню', prev_track),
            # Перемотування
            ('перемотай вперед', seek_forward),
            ('вперед', seek_forward),
            ('перемотай назад', seek_backward),
            ('назад', seek_backward),
            # Автозапуск
            ('увімкни автозапуск', enable_autostart),
            ('додай в автозапуск', enable_autostart),
            ('вимкни автозапуск', disable_autostart),
            ('прибери з автозапуску', disable_autostart),
            # Система
            ('вимкни комп', offpc),
            ("вимкни комп'ютер", offpc),
            ('заблокуй компютер', lock_pc),
            ("заблокуй комп'ютер", lock_pc),
            ('заблокуй екран', lock_pc),
            ('заблокуй', lock_pc),
            ('завантаж відео', saver),
            # Монета
            ('підкинь монету', coin_flip),
            ('орел чи решка', coin_flip),
            ('кинь монету', coin_flip),
            ('монету', coin_flip),
            # Випадкове число
            ('назви число', random_number),
            ('випадкове число', random_number),
            ('рандомне число', random_number),
            # Жарти
            ('розкажи анекдот', joke),
            ('розкажи жарт', joke),
            ('пожартуй', joke),
            ('анекдот', joke),
            ('жарт', joke),
            ('розсміши мене', joke),
            # Повтори
            ('повтори', lambda: self.last_response if self.last_response else "Поки нічого не казала."),
            ('повтори що сказала', lambda: self.last_response if self.last_response else "Поки нічого не казала."),
            ('скажи ще раз', lambda: self.last_response if self.last_response else "Поки нічого не казала."),
            # Поточний трек
            ('що зараз грає', current_track_info),
            ('яка пісня грає', current_track_info),
            ('яка пісня', current_track_info),
            ('що грає', current_track_info),
            ('назва пісні', current_track_info),
            ('який трек', current_track_info),
            # Гучність Spotify (окремо від системної)
            ('гучніше спотіфай', spotify_volume_up),
            ('гучніше в спотіфай', spotify_volume_up),
            ('збільш гучність спотіфай', spotify_volume_up),
            ('тихіше спотіфай', spotify_volume_down),
            ('тихіше в спотіфай', spotify_volume_down),
            ('зменш гучність спотіфай', spotify_volume_down),
            # Контекст
            ('знову', lambda: None),
            ('ще раз', lambda: None),
            # Новини
            ('новини', news),
            ('що нового', news),
            ('що нового в україні', news),
            ('розкажи новини', news),
            ('покажи новини', news),
            ('останні новини', news),
            ('головні новини', news),
            ('що відбувається', news),
            # Системна інформація
            ('стан системи', system_info),
            ('системна інформація', system_info),
            ('завантаження системи', system_info),
            ('скільки ram', system_ram),
            ('скільки оперативки', system_ram),
            ('скільки пам яті', system_ram),
            ("скільки пам'яті", system_ram),
            ('стан пам яті', system_ram),
            ('завантаження процесора', system_cpu),
            ('скільки cpu', system_cpu),
            ('скільки процесор', system_cpu),
            ('як процесор', system_cpu),
            ('заряд батареї', system_battery),
            ('скільки заряду', system_battery),
            ('батарея', system_battery),
            ('скільки відсотків батареї', system_battery),
            # Буфер обміну
            ('що в буфері', clipboard_read),
            ('прочитай буфер', clipboard_read),
            ('вміст буфера', clipboard_read),
            ('що скопійовано', clipboard_read),
            ('що в clipboard', clipboard_read),
            # Ранковий брифінг
            ('що сьогодні', morning_briefing),
            ('ранковий брифінг', morning_briefing),
            ('що на сьогодні', morning_briefing),
            ('розкажи що сьогодні', morning_briefing),
            # Ранковий ритуал
            ('доброго ранку', morning_routine),
            ('добрий ранок', morning_routine),
            ('починаємо ранок', morning_routine),
            # Вечірній ритуал
            ('на добраніч', goodnight_routine),
            ('добраніч', goodnight_routine),
            ('на ніч', goodnight_routine),
            ('лягаю спати', goodnight_routine),
            # Скасування вимкнення
            ('скасуй вимкнення', cancel_shutdown),
            ('відміни вимкнення', cancel_shutdown),
            ('не вимикай', cancel_shutdown),
            ('скасуй shutdown', cancel_shutdown),
        ]

    # --------------------------
    # Скорінг простих відповідей
    # --------------------------
    def _profile_summary(self) -> str:
        """Коротке резюме того що Sofiya знає про користувача."""
        import user_profile as _up
        p = self._profile
        parts = []
        if p.get('name'):
            parts.append(f"вас звати {p['name']}")
        streak = _up.get_streak(p)
        if streak >= 2:
            parts.append(f"ви вже {streak} дні поспіль зі мною")
        fav = _up.get_favorite_site(p)
        if fav:
            parts.append(f"найчастіше відкриваєте {fav}")
        cmds = p.get('total_cmds', 0)
        if cmds >= 10:
            parts.append(f"разом виконали {cmds} команд")
        if not parts:
            return "Поки знаю про вас небагато — ми тільки знайомимось."
        return "Я знаю що " + ", ".join(parts) + "."

    def _score_simple_queries(self, question):
        """Повертає (score, answer) або None"""
        question_lower = question.lower()
        now = datetime.datetime.now()
        days_ua = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]

        # Персоналізовані відповіді залежно від профілю
        import user_profile as _up
        _name = self._profile.get('name')
        _fav  = _up.get_favorite_site(self._profile)

        simple_answers = {
            "як справи": "Дякую, все добре! А у вас?",
            "як твої справи": "Працюю, не переживай!",
            "хто ти": "Я Софія, ваш голосовий помічник",
            "що ти вмієш": "Я можу розповісти погоду, час, дату, відкрити браузер, ютуб, музику. А в режимі ШІ — відповідаю на будь-які питання!",
            "дякую": "Будь ласка! Рада допомогти!",
            "привіт": f"Привіт, {_name}! Чим можу допомогти?" if _name else "Привіт! Як я можу допомогти?",
            "до побачення": "До зустрічі! Гарного дня!",
            "як тебе звати": "Мене звати Софія!",
            "розкажи анекдот": "Вчора помив вікна — тепер у мене світанок на дві години раніше!",
            "що робиш": "Чекаю на вашу команду!",
            "як мене звати": f"Вас звати {_name}!" if _name else "Ви ще не представились. Скажіть «мене звати [ім'я]».",
            "ти мене пам'ятаєш": f"Звичайно! Вас звати {_name}." if _name else "Ви поки не представились.",
            "що ти про мене знаєш": self._profile_summary(),
            "мій улюблений сайт": f"Схоже, найчастіше ви відкриваєте {_fav}." if _fav else "Ще не знаю — відкрийте кілька сайтів.",
        }

        best_score = 0.0
        best_answer = None

        for query, answer in simple_answers.items():
            score = match_score(question_lower, query)
            if score > best_score:
                best_score = score
                best_answer = answer

        if best_answer and best_score >= 0.75:
            return (best_score, best_answer)
        return None

    # --------------------------
    # Таймер / Нагадування
    # --------------------------
    def _handle_set_volume(self, text):
        """Встановлює гучність на конкретний відсоток"""
        prefixes = [
            'постав гучність на', 'поставь гучність на',
            'встанови гучність на', 'зроби гучність', 'гучність на',
            'постав звук на', 'поставь звук на',
            'звук на', 'гучність',
        ]
        matched = None
        for p in prefixes:
            if text.startswith(p):
                matched = text[len(p):].strip()
                break
        if matched is None:
            return None

        # Витягуємо число
        nums = re.findall(r'\d+', matched)
        if not nums:
            return "Скажіть відсоток, наприклад: постав гучність на 50 відсотків."
        percent = int(nums[0])
        percent = max(0, min(100, percent))

        try:
            from pycaw.pycaw import AudioUtilities
            from voice import _ensure_com
            _ensure_com()
            dev = AudioUtilities.GetSpeakers()
            dev.EndpointVolume.SetMasterVolumeLevelScalar(percent / 100.0, None)
            return f"Гучність встановлена на {percent} відсотків"
        except Exception as e:
            print(f"Помилка гучності: {e}")
            return "Не вдалося змінити гучність"

    def _handle_timer(self, text):
        """Обробляє таймер і нагадування"""
        timer_prefixes = ['постав таймер', 'таймер на', 'засіч', 'відлік', 'таймер']
        remind_prefixes = [
            'нагадай через', 'нагадай мені через',
            'нагадай за', 'нагадай мені за',
            'нагадуй через', 'нагадуй за',
            'нагадай',
        ]

        is_timer = any(text.startswith(p) for p in timer_prefixes)
        is_remind = any(text.startswith(p) for p in remind_prefixes)

        if not is_timer and not is_remind:
            return None

        # Витягуємо число і одиницю часу
        numbers = re.findall(r'(\d+)', text)
        if not numbers:
            # Спроба зі словами
            word_nums = {
                'одну': 1, 'одна': 1, 'одну': 1, 'один': 1,
                'дві': 2, 'два': 2, 'три': 3, 'чотири': 4,
                'п\'ять': 5, 'пять': 5, 'шість': 6, 'сім': 7,
                'вісім': 8, 'дев\'ять': 9, 'десять': 10,
                'пів': 0.5, 'півтори': 1.5,
                'п\'ятнадцять': 15, 'пятнадцять': 15,
                'двадцять': 20, 'тридцять': 30,
            }
            amount = None
            for word, num in word_nums.items():
                if word in text:
                    amount = num
                    break
            if amount is None:
                return "Скажіть скільки хвилин. Наприклад: таймер на 5 хвилин."
        else:
            amount = float(numbers[0])

        # Визначаємо одиницю
        if 'годин' in text:
            seconds = int(amount * 3600)
            unit_text = f"{int(amount)} годин"
        elif 'секунд' in text:
            seconds = int(amount)
            unit_text = f"{int(amount)} секунд"
        else:
            # За замовчуванням — хвилини
            seconds = int(amount * 60)
            unit_text = f"{int(amount)} хвилин"

        # Витягуємо текст нагадування
        reminder_text = ""
        if is_remind:
            # Прибираємо префікс (найдовший спочатку щоб не обрізати неправильно)
            parts = text
            for prefix in sorted(remind_prefixes, key=len, reverse=True):
                if parts.startswith(prefix):
                    parts = parts[len(prefix):]
                    break
            # Прибираємо "за/через + число + одиницю"
            parts = re.sub(r'(за|через)?\s*\d+\s*(годин\w*|хвилин\w*|секунд\w*)', '', parts)
            # Прибираємо словесні числа + одиниці
            parts = re.sub(r'\d+', '', parts)
            for unit in ['годин', 'година', 'хвилин', 'хвилина', 'секунд', 'секунда', 'хвилину', 'за', 'через']:
                parts = parts.replace(unit, '')
            reminder_text = parts.strip()

        # Формуємо фінальне повідомлення
        if reminder_text:
            fire_msg = f"Нагадування: {reminder_text}"
        else:
            fire_msg = f"Таймер на {unit_text} завершився!"

        # Зберігаємо нагадування у файл (відновлюється після перезапуску)
        rid = str(uuid.uuid4())
        fire_at = time.time() + seconds
        reminders = _load_reminders()
        reminders.append({'id': rid, 'fire_at': fire_at, 'message': fire_msg})
        _save_reminders(reminders)

        # Запускаємо таймер в окремому потоці
        def _timer_thread(_rid=rid, _secs=seconds, _msg=fire_msg):
            time.sleep(_secs)
            _remove_reminder(_rid)
            self._notify('message', 'Софія', _msg)
            # Windows toast-сповіщення (якщо plyer встановлено)
            try:
                from plyer import notification
                notification.notify(
                    title='Софія',
                    message=_msg,
                    app_name='Sophiya',
                    timeout=10,
                )
            except Exception:
                pass
            speaker(_msg)

        threading.Thread(target=_timer_thread, daemon=True).start()

        if reminder_text:
            return f"Добре, нагадаю через {unit_text}: {reminder_text}"
        else:
            return f"Таймер на {unit_text} запущено!"

    # --------------------------
    # Будильник на точний час HH:MM
    # --------------------------
    def _handle_alarm(self, text: str):
        """Встановлює/скасовує/перелічує будильники на конкретний час HH:MM.

        Підтримувані форми:
          • будильник на 7:30 / будильник о 22:00
          • постав будильник на 7 30
          • розбудь мене о 6:45
          • скасуй будильник [о 7:30]   — конкретний або всі
          • які будильники / мої будильники
        """
        alarm_list_kw = [
            'які будильники', 'список будильників',
            'покажи будильники', 'мої будильники',
        ]
        alarm_cancel_prefixes = [
            'скасуй будильник', 'скасувати будильник',
            'видали будильник', 'прибери будильник',
            'вимкни будильник', 'зупини будильник',
            'скасуй всі будильники', 'видали всі будильники',
        ]
        alarm_set_prefixes = [
            'постав будильник', 'встанови будильник', 'поставити будильник',
            'будильник на', 'будильник о',
            'розбудь мене о', 'розбудь о',
            'прокинутись о', 'прокинь мене о', 'прокинь о',
        ]

        # --- Список ---
        if any(text == kw or text.startswith(kw) for kw in alarm_list_kw):
            alarms = [r for r in _load_reminders() if r.get('type') == 'alarm']
            if not alarms:
                return "Будильників немає."
            times = sorted(r['alarm_time'] for r in alarms)
            return "Будильники: " + ", ".join(times)

        # --- Скасування ---
        is_cancel = any(text.startswith(p) for p in alarm_cancel_prefixes)
        if is_cancel:
            m = re.search(r'\b(\d{1,2})[:\s](\d{2})\b', text)
            reminders = _load_reminders()
            if m:
                hh, mm = int(m.group(1)), int(m.group(2))
                target = f"{hh:02d}:{mm:02d}"
                before_len = len(reminders)
                reminders = [r for r in reminders
                             if not (r.get('type') == 'alarm'
                                     and r.get('alarm_time') == target)]
                _save_reminders(reminders)
                return (f"Будильник на {target} скасовано."
                        if len(reminders) < before_len
                        else f"Будильника на {target} не знайдено.")
            else:
                alarms = [r for r in reminders if r.get('type') == 'alarm']
                if not alarms:
                    return "Будильників немає."
                _save_reminders([r for r in reminders if r.get('type') != 'alarm'])
                n = len(alarms)
                return f"Скасовано {n} будильник{'ів' if n > 1 else ''}."

        # --- Встановлення ---
        is_set = any(text.startswith(p) for p in alarm_set_prefixes)
        if not is_set and 'будильник' not in text:
            return None

        # Парсимо час ─────────────────────────────────────────────────
        # 1) "7:30" або "07:30"
        hh = mm = None
        m = re.search(r'\b(\d{1,2}):(\d{2})\b', text)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
        else:
            # 2) "7 30", "7 год 30 хвилин"
            m2 = re.search(r'\b(\d{1,2})\s+(?:год(?:ин[аи])?\s+)?(\d{2})\b', text)
            if m2:
                hh, mm = int(m2.group(1)), int(m2.group(2))
            else:
                # 3) Тільки година: "будильник на 7" → 7:00
                m3 = re.search(r'\b(\d{1,2})\b', text)
                if m3:
                    hh, mm = int(m3.group(1)), 0

        if hh is None:
            if is_set:
                return "На котру годину встановити будильник? Наприклад: будильник на 7:30."
            return None

        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return "Неправильний час. Вкажіть від 0:00 до 23:59."

        # Визначаємо момент спрацювання ────────────────────────────────
        now = datetime.datetime.now()
        alarm_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if alarm_dt <= now:
            alarm_dt += datetime.timedelta(days=1)

        seconds          = (alarm_dt - now).total_seconds()
        alarm_time_str   = f"{hh:02d}:{mm:02d}"
        fire_msg         = f"Будильник! Час {alarm_time_str}. Прокидайся!"

        # Зберігаємо ───────────────────────────────────────────────────
        rid = str(uuid.uuid4())
        reminders = _load_reminders()
        reminders.append({
            'id':         rid,
            'fire_at':    time.time() + seconds,
            'message':    fire_msg,
            'type':       'alarm',
            'alarm_time': alarm_time_str,
        })
        _save_reminders(reminders)

        # Фоновий потік ─────────────────────────────────────────────────
        def _alarm_thread(_rid=rid, _secs=seconds, _msg=fire_msg, _t=alarm_time_str):
            time.sleep(_secs)
            _remove_reminder(_rid)
            self._notify('message', 'Софія', _msg)
            try:
                from plyer import notification
                notification.notify(title='Будильник', message=_t,
                                    app_name='Sophiya', timeout=15)
            except Exception:
                pass
            # Повторюємо тричі щоб точно почули
            for _ in range(3):
                speaker(_msg)
                time.sleep(2.0)

        threading.Thread(target=_alarm_thread, daemon=True).start()

        tomorrow = alarm_dt.date() > now.date()
        suffix = " (завтра)" if tomorrow else ""
        return f"Будильник на {alarm_time_str} встановлено{suffix}."

    # --------------------------
    # Вимкнення через заданий час
    # --------------------------
    def _handle_shutdown_timer(self, text):
        """'вимкни через 2 години' / 'вимкни через 30 хвилин' → shutdown з підтвердженням"""
        prefixes = [
            'вимкни через', "вимкни комп'ютер через", 'вимкни комп через',
            'вимкни пк через', 'shutdown через',
        ]
        if not any(text.startswith(p) for p in prefixes):
            return None

        numbers = re.findall(r'(\d+)', text)
        if not numbers:
            return None
        amount = int(numbers[0])

        if 'годин' in text:
            seconds = amount * 3600
            unit = f"{amount} годин"
        elif 'секунд' in text:
            seconds = amount
            unit = f"{amount} секунд"
        else:
            seconds = amount * 60
            unit = f"{amount} хвилин"

        def _do_shutdown():
            os.system(f'shutdown /s /t {seconds}')
            return f"Вимикаю комп'ютер через {unit}. Щоб скасувати — скажи 'скасуй вимкнення'."

        self._pending_confirm = {
            'func':    _do_shutdown,
            'label':   f"Вимкнення через {unit}",
            'expires': time.time() + self._CONFIRM_TIMEOUT,
        }
        return f"Вимкнути комп'ютер через {unit}? Підтвердіть: 'так' або 'скасуй'."

    # --------------------------
    # Калькулятор
    # --------------------------
    def _handle_calculator(self, text):
        """Обробляє математичні запити"""
        calc_prefixes = ['скільки буде', 'скільки це', 'порахуй', 'обчисли', 'калькулятор']
        is_calc = any(text.startswith(p) for p in calc_prefixes)

        # Також ловимо прямі приклади типу "2 плюс 2"
        has_math_words = any(w in text for w in ['плюс', 'мінус', 'помножити', 'поділити', 'множити', 'ділити'])

        if not is_calc and not has_math_words:
            return None

        # Витягуємо математичний вираз
        expr = text
        for prefix in calc_prefixes:
            expr = expr.replace(prefix, '')

        # Заміняємо слова на математичні оператори
        replacements = [
            ('помножити на', '*'), ('помножити', '*'), ('множити на', '*'), ('множити', '*'),
            ('поділити на', '/'), ('поділити', '/'), ('ділити на', '/'), ('ділити', '/'),
            ('плюс', '+'), ('додати', '+'), ('додай', '+'),
            ('мінус', '-'), ('відняти', '-'), ('відняй', '-'),
            ('в квадраті', '**2'), ('в кубі', '**3'),
            ('на', '*'),  # "2 на 3" = множення (в кінці, щоб не зламати інші)
        ]
        for word, op in replacements:
            expr = expr.replace(word, op)

        # Прибираємо все крім цифр, операторів, крапок, дужок
        expr = re.sub(r'[^\d+\-*/().%]', ' ', expr).strip()
        expr = re.sub(r'\s+', '', expr)  # Прибираємо пробіли

        if not expr or not any(c.isdigit() for c in expr):
            return "Не зрозуміла вираз. Скажіть, наприклад: скільки буде 145 помножити на 12."

        try:
            # Безпечне обчислення (без eval небезпечних виразів)
            allowed = set('0123456789+-*/.()% ')
            if not all(c in allowed for c in expr):
                return "Не можу обчислити цей вираз."

            result = eval(expr)

            # Форматування результату
            if isinstance(result, float):
                if result == int(result):
                    result = int(result)
                else:
                    result = round(result, 4)

            return f"{result}"
        except ZeroDivisionError:
            return "На нуль ділити не можна!"
        except Exception:
            return "Не вдалося обчислити. Спробуйте інакше."

    # --------------------------
    # Голосовий пошук
    # --------------------------
    def _handle_search(self, text):
        """Перевіряє чи це пошуковий запит і шукає в Google/YouTube"""
        text_lower = text.lower().strip()

        # Префікси для Google
        google_prefixes = [
            'знайди в інтернеті', 'пошук в інтернеті', 'знайди в інтернет',
            'загугли', 'пошукай', 'знайди', 'шукай', 'погугли',
            'пошук', 'знайди мені',
        ]

        # Префікси для YouTube
        yt_prefixes = [
            'знайди в ютубі', 'пошук на ютубі', 'знайди на ютубі',
            'пошукай на ютубі', 'знайди на youtube', 'пошук на youtube',
            'покажи на ютубі', 'знайди відео',
        ]

        # YouTube пошук (перевіряємо першим бо довші фрази)
        for prefix in sorted(yt_prefixes, key=len, reverse=True):
            if text_lower.startswith(prefix):
                query = text_lower[len(prefix):].strip()
                if query:
                    webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
                    self._ctx_site   = _FUNC_SITE_MAP['youtube']
                    self._ctx_search = {'query': query, 'engine': 'YouTube'}
                    self._ctx_topic  = self._extract_topic(query)
                    return f"Шукаю на YouTube: {query}"
                return self._search_with_voice("YouTube")

        # Google пошук
        for prefix in sorted(google_prefixes, key=len, reverse=True):
            if text_lower.startswith(prefix):
                query = text_lower[len(prefix):].strip()
                if query:
                    webbrowser.open(f"https://www.google.com/search?q={query}")
                    self._ctx_site   = _FUNC_SITE_MAP['search']
                    self._ctx_search = {'query': query, 'engine': 'Google'}
                    self._ctx_topic  = self._extract_topic(query)
                    return f"Шукаю: {query}"
                return self._search_with_voice("Google")

        return None

    def _search_with_voice(self, engine="Google"):
        """Питає що шукати і виконує пошук"""
        speaker("Що шукаємо?")
        self._notify('message', 'Софія', 'Що шукаємо?')
        try:
            with sr.Microphone(sample_rate=16000) as source:
                self._notify('status_change', 'Слухаю запит...')
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                self.recognizer.pause_threshold = 1.2
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)

            query = self.recognizer.recognize_google(audio, language="uk-UA")
            self._notify('message', 'Ви', query)

            # Скасування пошуку
            cancel_words = ['скасувати', 'скасуй', 'відміни', 'відмінити', 'стоп', 'нічого', 'не треба']
            if any(w in query.lower() for w in cancel_words):
                return "Пошук скасовано."

            if engine == "YouTube":
                webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
                self._ctx_site   = _FUNC_SITE_MAP['youtube']
            else:
                webbrowser.open(f"https://www.google.com/search?q={query}")
                self._ctx_site   = _FUNC_SITE_MAP['search']
            self._ctx_search = {'query': query, 'engine': engine}
            self._ctx_topic  = self._extract_topic(query)
            return f"Шукаю на {engine}: {query}"
        except sr.WaitTimeoutError:
            return "Не почула запит"
        except sr.UnknownValueError:
            return "Не вдалося розпізнати запит"
        except Exception:
            return "Помилка пошуку"


    # --------------------------
    # Відкриття посилань через Chrome-розширення (WebSocket-міст)
    # --------------------------
    _ORDINALS = {
        'першу': 1, 'перший': 1, 'перше': 1, 'першій': 1, 'перша': 1, 'першого': 1,
        'другу': 2, 'другий': 2, 'друге': 2, 'другій': 2, 'друга': 2, 'другого': 2,
        'третю': 3, 'третій': 3, 'третє': 3, 'третя': 3, 'третього': 3,
        'четверту': 4, 'четвертий': 4, 'четверте': 4, 'четверта': 4,
        "п'яту": 5, "п'ятий": 5, "п'яте": 5, "п'ята": 5,
        'шосту': 6, 'шостий': 6, 'шосте': 6, 'шоста': 6,
        'сьому': 7, 'сьомий': 7, 'сьоме': 7, 'сьома': 7,
        'восьму': 8, 'восьмий': 8, 'восьме': 8, 'восьма': 8,
        "дев'яту": 9, "дев'ятий": 9, "дев'яте": 9, "дев'ята": 9,
        'десяту': 10, 'десятий': 10, 'десяте': 10, 'десята': 10,
    }
    _LINK_WORDS = {
        'силку', 'силка', 'силки', 'посилання', 'результат', 'результати',
        'лінк', 'лінку', 'сайт', 'сторінку', 'сторінка',
        'відео', 'ролик', 'ролику', 'ролика',
    }

    def _handle_open_link(self, text_lower: str):
        """
        'відкрий першу силку'  → відкриває 1-й результат з поточної вкладки браузера
        'покажи всі силки'     → перераховує знайдені посилання
        """
        import browser_bridge

        words = text_lower.split()

        # Перевіряємо чи є слово-тригер для посилань
        if not any(w in self._LINK_WORDS for w in words):
            return None

        # Окрема перевірка: якщо сказали тільки "відкрий браузер" — не чіпаємо
        _VIDEO_WORDS = {'відео', 'ролик', 'ролику', 'ролика'}
        _is_video_cmd = any(w in _VIDEO_WORDS for w in words)
        # "відкрий браузер" і схожі — не наш обробник
        if not _is_video_cmd and 'браузер' in words:
            return None

        # 'покажи всі силки'
        if any(w in text_lower for w in ('всі', 'список', 'перелік', 'всіх')):
            return self._list_browser_links()

        # Визначаємо порядковий номер
        n = None
        for word in words:
            if word in self._ORDINALS:
                n = self._ORDINALS[word]
                break
            if word.isdigit():
                n = int(word)
                break
        if n is None:
            n = 1

        # --- Беремо посилання з поточної вкладки браузера ---
        if not browser_bridge.is_connected():
            return (
                "Розширення для браузера не підключено. "
                "Переконайтесь що Chrome відкритий і розширення Sophia встановлено."
            )

        links = browser_bridge.get_links(timeout=5.0)

        if not links:
            return "Не знайшла посилань на поточній сторінці."

        self._last_links = links

        idx = n - 1
        if idx >= len(links):
            return f"На сторінці лише {len(links)} посилань."

        item  = links[idx]
        title = item.get('title', '').strip()
        url   = item.get('href', '').strip()

        if not url:
            return "Не вдалося отримати посилання."

        webbrowser.open(url)
        short = (title[:60] + '…') if len(title) > 60 else title
        return f"Відкриваю {n}: {short}"

    def _list_browser_links(self):
        """Перераховує посилання з поточної вкладки браузера."""
        import browser_bridge

        if not browser_bridge.is_connected():
            return "Розширення для браузера не підключено."

        links = browser_bridge.get_links(timeout=5.0)
        if not links:
            return "Не знайшла посилань на сторінці."

        self._last_links = links
        lines = [f"{i}. {r.get('title', '')[:55]}" for i, r in enumerate(links, 1)]
        self._notify('message', 'Софія', "\n".join(lines))

        spoken = ". ".join(
            f"{i}. {r.get('title', '')[:45]}"
            for i, r in enumerate(links[:3], 1)
        )
        return f"Знайшла {len(links)} посилань: {spoken}. Скажіть номер."

    # --------------------------
    # Генерація відповіді через Mistral (з контекстом)
    # --------------------------
    def generate_response(self, question):
        try:
            self.conversation_history.append({"role": "user", "content": question})

            # Тримаємо останні 10 повідомлень + system prompt
            messages = self.conversation_history[:1] + self.conversation_history[-10:]

            response = self.client.chat.complete(
                model=self.model,
                messages=messages
            )
            answer = response.choices[0].message.content

            self.conversation_history.append({"role": "assistant", "content": answer})
            # Обмежуємо розмір: system prompt + максимум 20 повідомлень
            if len(self.conversation_history) > 21:
                self.conversation_history = (
                    self.conversation_history[:1] + self.conversation_history[-20:]
                )
            return answer
        except Exception as e:
            print(f"Помилка генерації: {e}")
            return None

    # --------------------------
    # Очищення тексту для озвучки
    # --------------------------
    @staticmethod
    def _clean_for_speech(text):
        """Прибирає емодзі, markdown, зірочки — залишає чистий текст для голосу"""
        # Прибрати markdown bold/italic: **текст**, *текст*, __текст__
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
        # Прибрати markdown заголовки: ## текст
        text = re.sub(r'#+\s*', '', text)
        # Прибрати markdown списки: - текст, * текст
        text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
        # Прибрати емодзі (Unicode emoji ranges)
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"  # смайли
            "\U0001F300-\U0001F5FF"   # символи
            "\U0001F680-\U0001F6FF"   # транспорт
            "\U0001F1E0-\U0001F1FF"   # прапори
            "\U00002702-\U000027B0"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002600-\U000026FF"
            "\U0000FE00-\U0000FE0F"
            "\U0000200D"
            "]+", flags=re.UNICODE
        )
        text = emoji_pattern.sub('', text)
        # Прибрати зайві пробіли
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # --------------------------
    # Старт/зупинка слухання
    # --------------------------
    def _play_beep(self):
        """Короткий звуковий сигнал при початку слухання"""
        try:
            import winsound
            # 800Hz, 150ms — короткий "дінь"
            winsound.Beep(800, 150)
        except Exception:
            pass

    def start_listening(self):
        self.is_listening = True
        self._notify('listening_change', True)

        # Прогріваємо TTS loop заздалегідь — перша фраза без затримки
        from voice import prewarm
        threading.Thread(target=prewarm, daemon=True).start()

        # Калібрування мікрофона при запуску
        self._notify('status_change', 'Калібрую мікрофон...')
        try:
            with sr.Microphone(sample_rate=16000) as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                self._calibrated_threshold = max(150, self.recognizer.energy_threshold * 1.2)
                if DEBUG: print(f"[DEBUG] Поріг: {self._calibrated_threshold:.0f}")
        except Exception:
            self._calibrated_threshold = 150

        self._notify('status_change', 'Асистент активний')

        # Відновлюємо нагадування що були встановлені до перезапуску
        threading.Thread(target=self._restore_reminders, daemon=True).start()

        # Персоналізоване вітання
        import user_profile as _up
        _up.record_session(self._profile)
        greeting_text = _up.build_greeting(self._profile)
        _up.mark_greeted_today(self._profile)

        speaker(greeting_text)
        self._notify('message', 'Софія', greeting_text)
        self._last_spoke_time = time.time()

        # Запам'ятовуємо слот старту — щоб перша команда не повторила вітання
        self._greeted_time_slot = self._current_time_slot()

        # Якщо ім'я невідоме і вже ≥ 3 сесії — один раз запитати
        if (not self._profile.get('name')
                and not self._profile.get('asked_name')
                and len(self._profile.get('sessions', [])) >= 3):
            import threading as _t
            def _ask_name():
                time.sleep(1.5)   # невелика пауза після вітання
                q = "До речі, як вас звати?"
                speaker(q)
                self._notify('message', 'Софія', q)
                self._profile['asked_name'] = True
                _up.save(self._profile)
            _t.Thread(target=_ask_name, daemon=True).start()

        self._start_simple_loop()

        self._notify('listening_change', False)
        self._notify('status_change', 'Асистент зупинено')

    # --------------------------
    # Основний цикл слухання (VAD + Google)
    # --------------------------
    def _start_simple_loop(self):
        """Стандартний режим: постійно слухає, фільтрує VAD, надсилає в Google"""
        import voice as _voice
        try:
            with sr.Microphone(sample_rate=16000) as source:
                self.recognizer.energy_threshold = self._calibrated_threshold
                self.recognizer.dynamic_energy_threshold = False
                self.recognizer.pause_threshold    = 0.7   # 1.2 → 0.7: швидше кінець фрази
                self.recognizer.phrase_threshold   = 0.1
                self.recognizer.non_speaking_duration = 0.4  # 0.8 → 0.4

                while self.is_listening:

                    # ── Поки Софія говорить — slim-листенер для переривання ──
                    if _voice._is_speaking:
                        self._listen_for_interrupt(source, _voice)
                        continue

                    # ── Поки іде розпізнавання — чекаємо (але НЕ блокуємо мікрофон) ──
                    if self._is_busy:
                        time.sleep(0.05)
                        continue

                    try:
                        self._notify('status_change', 'Слухаю...')
                        audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=6)

                        if not self.is_listening:
                            break

                        # Якщо під час запису Софія почала говорити — відкидаємо аудіо
                        if _voice._is_speaking:
                            print("[MIC] Відкидаю — Софія говорить")
                            continue

                        if not self._has_speech_pattern(audio):
                            print("[VAD] Пропуск — фоновий звук")
                            continue

                        self._is_busy = True
                        self._notify('status_change', 'Розпізнаю...')
                        audio_copy = sr.AudioData(audio.frame_data, audio.sample_rate, audio.sample_width)
                        threading.Thread(
                            target=self._recognize_and_handle,
                            args=(audio_copy,),
                            daemon=True
                        ).start()

                    except sr.WaitTimeoutError:
                        self._notify('status_change', 'Тиша... Слухаю далі')
                        # ── Адаптивне калібрування під час тиші ──
                        # Ідеальний момент: listen() щойно повернув контроль,
                        # потік мікрофона вільний, конфліктів немає
                        now = time.time()
                        if now - self._last_recal_time >= self.RECAL_INTERVAL:
                            self._last_recal_time = now
                            try:
                                old = self.recognizer.energy_threshold
                                self.recognizer.adjust_for_ambient_noise(
                                    source, duration=0.5)
                                new = max(150,
                                          self.recognizer.energy_threshold * 1.1)
                                self.recognizer.energy_threshold = new
                                self._calibrated_threshold = new
                                if abs(new - old) > 15:
                                    print(f"[CAL] Поріг: {old:.0f} → {new:.0f}")
                            except Exception:
                                pass

                    except Exception as e:
                        if self.is_listening:
                            print(f"Помилка слухання: {e}")
                        self._is_busy = False
        except Exception as e:
            print(f"Помилка мікрофона: {e}")

    def _recognize_and_handle(self, audio, skip_name_check=False):
        """Розпізнає аудіо і обробляє команду (Google → Vosk як резерв)"""
        try:
            # Спроба 1: Google Speech API (онлайн)
            text = self.recognizer.recognize_google(audio, language="uk-UA")

            # Перевірка луни — чи не є це відлуння останньої відповіді Софії?
            if self._is_echo(text):
                print(f"[Echo] Ігнорую луну: '{text}'")
                return

            self._notify('status_bar', 'Google API')
            print(f"Розпізнано (Google): {text}")
            self._notify('message', 'Ви', text)
            self._process_with_interim(text.lower(), skip_name_check=skip_name_check)

        except sr.RequestError:
            # Немає інтернету → переходимо на Vosk
            print("[Vosk] Google недоступний, використовую офлайн...")
            self._notify('status_change', 'Офлайн режим...')

            if self._vosk_model is None:
                self._notify('message', 'Софія', 'Немає інтернету та офлайн модель не завантажена.')
                speaker('Немає підключення до інтернету.')
                return

            text = self._recognize_offline(audio)
            if text:
                self._notify('status_bar', 'Vosk (офлайн)')
                print(f"Розпізнано (Vosk): {text}")
                self._notify('message', 'Ви', f"[офлайн] {text}")
                self._process_with_interim(text.lower(), skip_name_check=skip_name_check)
            else:
                self._notify('status_change', 'Не розпізнано')

        except sr.UnknownValueError:
            self._notify('status_change', 'Не розпізнано')
        except Exception as e:
            print(f"Помилка розпізнавання: {e}")
        finally:
            self._last_spoke_time = time.time()  # cooldown після відповіді
            self._is_busy = False

    # ------------------------------------------------------------------
    # Реакція на зміну часового слоту (ранок / вечір / ніч)
    # ------------------------------------------------------------------
    _TIME_SLOT_PHRASES: dict = {
        'morning': [
            "Добрий ранок! Чим можу допомогти?",
            "Гарного ранку! Слухаю вас.",
            "Доброго ранку! Що сьогодні робимо?",
        ],
        'evening': [
            "Добрий вечір! Слухаю.",
            "Вечір добрий! Чим можу допомогти?",
            "Гарного вечора! Слухаю вас.",
        ],
        'night': [
            "Пізно вже, але слухаю.",
            "Глибока ніч — але я тут.",
            "Вже далеко за північ, але слухаю.",
        ],
    }

    @staticmethod
    def _current_time_slot() -> str:
        h = datetime.datetime.now().hour
        if 6 <= h < 10:
            return 'morning'
        if 10 <= h < 18:
            return 'day'
        if 18 <= h < 23:
            return 'evening'
        return 'night'

    def _vary_response(self, text: str) -> str:
        """Замінює нудний префікс відповіді на випадковий варіант."""
        import random
        for prefix, variants in self._RESPONSE_VARIANTS.items():
            if text.startswith(prefix):
                rest = text[len(prefix):]
                chosen = random.choice(variants)
                # Якщо після префіксу тільки пунктуація — не дублюємо її
                return chosen + rest if rest.strip('.,!? ') else chosen.rstrip('.,!? ') + rest
        return text

    def _maybe_greet_time_of_day(self) -> None:
        """Якщо часовий слот змінився — вимовляє коротке вітання (раз за слот)."""
        import random
        slot = self._current_time_slot()
        if slot == self._greeted_time_slot or slot == 'day':
            return
        phrases = self._TIME_SLOT_PHRASES.get(slot, [])
        if not phrases:
            return
        self._greeted_time_slot = slot
        msg = random.choice(phrases)
        self._notify('message', 'Софія', msg)
        speaker(msg)

    def _process_with_interim(self, text, skip_name_check=False):
        """
        Викликає process_command і, якщо обробка займає > 0.5 с,
        промовляє «Зрозуміла, виконую...» поки команда ще виконується.

        Умови для проміжної фрази (всі мають бути True):
          1. В тексті є ім'я Софії
          2. Минуло > 0.5 с без відповіді
          3. Sofiya НЕ говорить прямо зараз (_is_speaking = False)
             — якщо говорить, то відповідь вже пішла, і ми б тільки
               поставили «Зрозуміла» в чергу на після неї.
        """
        INTERIM_DELAY = 0.5
        INTERIM_PHRASE = "Зрозуміла, виконую..."

        import voice as _v

        # Якщо імені немає — проміжна відповідь не потрібна
        has_name = extract_command_after_name(text) is not None

        # Перемикання треків оголошує назву самостійно — "Зрозуміла" тільки заважає
        _no_interim_triggers = ('наступна пісня', 'наступний трек', 'інша пісня',
                                'переключи пісню', 'попередня пісня', 'попередній трек',
                                'поверни пісню')
        _cmd = extract_command_after_name(text) or text
        if any(_cmd.strip().startswith(t) or _cmd.strip() == t for t in _no_interim_triggers):
            self.process_command(text, skip_name_check=skip_name_check)
            return

        done_event = threading.Event()

        def _interim_timer():
            if not done_event.wait(timeout=INTERIM_DELAY):
                # Перевіряємо чи ще актуально:
                # _v.is_speaking() == True означає відповідь вже грає →
                # «Зрозуміла» стане в чергу і прозвучить ПІСЛЯ реальної відповіді
                if has_name and not done_event.is_set() and not _v.is_speaking():
                    speaker(INTERIM_PHRASE)

        timer_thread = threading.Thread(target=_interim_timer, daemon=True)
        timer_thread.start()

        try:
            self.process_command(text, skip_name_check=skip_name_check)
        finally:
            done_event.set()

    def stop_listening(self):
        self.is_listening = False

    def _restore_reminders(self):
        """Відновлює нагадування з файлу після перезапуску. Пропускає вже минулі."""
        reminders = _load_reminders()
        now = time.time()
        active = []
        for r in reminders:
            remaining = r.get('fire_at', 0) - now
            if remaining <= 0:
                print(f"[Reminders] Пропущено (час минув): {r['message']}")
                continue
            active.append(r)
            _rid, _secs, _msg = r['id'], remaining, r['message']

            _is_alarm = r.get('type') == 'alarm'

            def _t(_rid=_rid, _secs=_secs, _msg=_msg, _alarm=_is_alarm):
                time.sleep(_secs)
                _remove_reminder(_rid)
                self._notify('message', 'Софія', _msg)
                try:
                    from plyer import notification
                    notification.notify(
                        title='Будильник' if _alarm else 'Софія',
                        message=_msg, app_name='Sophiya',
                        timeout=15 if _alarm else 10)
                except Exception:
                    pass
                repeats = 3 if _alarm else 1
                for _ in range(repeats):
                    speaker(_msg)
                    if _alarm:
                        time.sleep(2.0)

            threading.Thread(target=_t, daemon=True).start()
            print(f"[Reminders] Відновлено: «{_msg}» через {remaining:.0f}с")

        _save_reminders(active)  # прибираємо вже минулі з файлу

