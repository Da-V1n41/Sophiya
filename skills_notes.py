"""
skills_notes.py — нотатки, псевдоніми, пам'ять Sophiya.
"""
import os
import sys
import json
import datetime
import webbrowser
import subprocess

from config import SPOTIFY_PATH


# ---------------------------------------------------------------------------
# Загальна інформація про асистента
# ---------------------------------------------------------------------------
def about_me():
    return (
        "Привіт! Я Софія, твій голосовий помічник. "
        "Я можу розповісти погоду, сказати час і дату, "
        "відкрити браузер, ютуб, увімкнути музику, "
        "змінити гучність, знайти щось в інтернеті. "
        "А в режимі штучного інтелекту я можу відповісти на будь-яке питання. "
        "Просто скажи Софія і свою команду."
    )


# ---------------------------------------------------------------------------
# Псевдоніми (aliases.json)
# ---------------------------------------------------------------------------
ALIASES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aliases.json')

_DEFAULT_ALIASES = {
    "робота": "code",
    "пошта": "https://gmail.com",
    "чат": r"C:\Users\Andriy\AppData\Roaming\Telegram Desktop\Telegram.exe",
    "ігри": r"C:\Program Files (x86)\Steam\steam.exe",
    "музика": SPOTIFY_PATH,
    "таблиця": "excel",
    "документ": "winword",
    "дискорд": r"C:\Users\Andriy\AppData\Local\Discord\Update.exe --processStart Discord.exe",
}

# Ініціалізуємо файл при першому запуску модуля
if not os.path.exists(ALIASES_FILE):
    try:
        with open(ALIASES_FILE, 'w', encoding='utf-8') as _f:
            json.dump(_DEFAULT_ALIASES, _f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_aliases() -> dict:
    try:
        if os.path.exists(ALIASES_FILE):
            with open(ALIASES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return dict(_DEFAULT_ALIASES)


def _save_aliases(aliases: dict):
    try:
        with open(ALIASES_FILE, 'w', encoding='utf-8') as f:
            json.dump(aliases, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def open_alias(name: str):
    """Відкриває програму/сайт за псевдонімом. Повертає None якщо псевдонім не знайдено."""
    aliases = _load_aliases()
    target = aliases.get(name.lower())
    if not target:
        return None
    try:
        if target.startswith('http'):
            webbrowser.open(target)
        elif target.endswith('.exe') or '\\' in target:
            subprocess.Popen(target)
        else:
            subprocess.Popen(target, shell=True)
        return f"Відкриваю {name}"
    except Exception as e:
        print(f"Псевдонім помилка: {e}")
        return f"Не вдалося відкрити {name}"


# ---------------------------------------------------------------------------
# Пам'ять / нотатки (memory.json)
# ---------------------------------------------------------------------------
MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory.json')


def _load_memory() -> dict:
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_memory(data: dict):
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def memory_save(text: str) -> str:
    if not text.strip():
        return "Що саме запам'ятати?"
    memory = _load_memory()
    timestamp = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    note_id = str(len(memory) + 1)
    memory[note_id] = {'text': text.strip(), 'date': timestamp}
    _save_memory(memory)
    return f"Запам'ятала: {text.strip()}"


def memory_list() -> str:
    memory = _load_memory()
    if not memory:
        return "Поки нічого не запам'ятала."
    items = [f"{k}. {v['text']}" for k, v in memory.items()]
    return "Ось що я пам'ятаю: " + "; ".join(items)


def memory_clear() -> str:
    _save_memory({})
    return "Пам'ять очищено."


def memory_forget(text: str) -> str:
    memory = _load_memory()
    if not memory:
        return "Пам'ять і так порожня."
    # За номером
    num = ''.join(filter(str.isdigit, text))
    if num and num in memory:
        removed = memory.pop(num)
        _save_memory(memory)
        return f"Забула: {removed['text']}"
    # За ключовим словом
    text_lower = text.lower().strip()
    for key, val in list(memory.items()):
        if text_lower in val['text'].lower():
            removed = memory.pop(key)
            _save_memory(memory)
            return f"Забула: {removed['text']}"
    return "Не знайшла що саме забути."
