"""
user_profile.py — Персональний профіль користувача між сесіями Sofiya.

Що зберігається:
  name          — ім'я користувача (None поки не представився)
  sessions      — список {date, hour} останніх 90 сесій
  site_opens    — лічильник відкриттів по сайтах
  total_cmds    — загальна кількість команд
  first_seen    — дата першої сесії
  greeted_today — дата останнього вітання (щоб не вітати двічі за день)
  asked_name    — чи вже запитували ім'я (щоб не питати щоразу)
"""

import json
import os
import datetime
from collections import Counter

PROFILE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_profile.json')

_DEFAULT: dict = {
    'name':          None,
    'sessions':      [],
    'site_opens':    {},
    'total_cmds':    0,
    'first_seen':    None,
    'greeted_today': None,
    'asked_name':    False,
}


# ------------------------------------------------------------------
# Завантаження / збереження
# ------------------------------------------------------------------

def load() -> dict:
    try:
        if os.path.exists(PROFILE_FILE):
            with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {**_DEFAULT, **data}
    except Exception:
        pass
    return dict(_DEFAULT)


def save(profile: dict) -> None:
    try:
        with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ------------------------------------------------------------------
# Запис подій
# ------------------------------------------------------------------

def record_session(profile: dict) -> dict:
    """Записує нову сесію (викликати на старті прослуховування)."""
    now   = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d')

    if not profile.get('first_seen'):
        profile['first_seen'] = today

    sessions: list = profile.setdefault('sessions', [])
    sessions.append({'date': today, 'hour': now.hour})
    profile['sessions'] = sessions[-90:]   # зберігаємо лише останні 90
    save(profile)
    return profile


def record_site_open(profile: dict, site_name: str) -> dict:
    """Збільшує лічильник відкриттів сайту."""
    profile.setdefault('site_opens', {})[site_name] = \
        profile['site_opens'].get(site_name, 0) + 1
    save(profile)
    return profile


def record_command(profile: dict) -> None:
    """Збільшує лічильник команд (у пам'яті; зберігати з record_session)."""
    profile['total_cmds'] = profile.get('total_cmds', 0) + 1


def set_name(profile: dict, name: str) -> dict:
    """Зберігає ім'я користувача."""
    profile['name']       = name.strip().capitalize()
    profile['asked_name'] = True
    save(profile)
    return profile


# ------------------------------------------------------------------
# Аналітика
# ------------------------------------------------------------------

def get_streak(profile: dict) -> int:
    """Скільки днів поспіль (включаючи сьогодні) є сесії."""
    dates  = sorted({s['date'] for s in profile.get('sessions', [])}, reverse=True)
    today  = datetime.date.today()
    streak = 0
    for i, d in enumerate(dates):
        if d == (today - datetime.timedelta(days=i)).strftime('%Y-%m-%d'):
            streak += 1
        else:
            break
    return max(streak, 1)


def get_usual_hour(profile: dict) -> int | None:
    """Найчастіший час доби за останніми 30 сесіями (None якщо даних < 7)."""
    sessions = profile.get('sessions', [])
    if len(sessions) < 7:
        return None
    hours = [s['hour'] for s in sessions[-30:]]
    most  = Counter(hours).most_common(1)
    return most[0][0] if most else None


def get_favorite_site(profile: dict) -> str | None:
    """Назва найчастіше відкриваного сайту."""
    opens = profile.get('site_opens', {})
    return max(opens, key=opens.get) if opens else None


def already_greeted_today(profile: dict) -> bool:
    today = datetime.date.today().strftime('%Y-%m-%d')
    return profile.get('greeted_today') == today


def mark_greeted_today(profile: dict) -> dict:
    profile['greeted_today'] = datetime.date.today().strftime('%Y-%m-%d')
    save(profile)
    return profile


# ------------------------------------------------------------------
# Побудова вітання
# ------------------------------------------------------------------

def build_greeting(profile: dict) -> str:
    """
    Будує персоналізоване вітання.

    Приклади:
      "Добрий ранок, Андрію! Вже третій день поспіль о цій порі."
      "Добрий вечір! Готова слухати."
      "Привіт! Я Софія, готова слухати."   ← перша сесія
      "Добраніч, Андрію... Пізно вже, але слухаю."
    """
    now      = datetime.datetime.now()
    hour     = now.hour
    name     = profile.get('name')
    sessions = profile.get('sessions', [])
    streak   = get_streak(profile)
    usual_h  = get_usual_hour(profile)
    total    = len(sessions)

    # Частина доби
    if 5 <= hour < 12:
        base = "Добрий ранок"
    elif 12 <= hour < 18:
        base = "Добрий день"
    elif 18 <= hour < 23:
        base = "Добрий вечір"
    else:
        base = "Привіт"

    greeting = f"{base}, {name}!" if name else f"{base}!"

    # Глибока ніч — особливий коментар
    if hour >= 23 or hour < 5:
        return f"{greeting} Пізно вже, але слухаю."

    # Перша сесія взагалі
    if total <= 1:
        return f"{greeting} Я Софія, готова слухати."

    # Збираємо суфіксні підказки
    hints: list[str] = []

    if streak == 2:
        hints.append("другий день поспіль")
    elif streak == 3:
        hints.append("вже третій день поспіль")
    elif streak >= 4:
        days = _ua_days(streak)
        hints.append(f"вже {streak} {days} поспіль")

    # «о цій порі» — якщо поточна година ≈ звична і стрік ≥ 2
    if usual_h is not None and streak >= 2 and abs(hour - usual_h) <= 1:
        hints.append("о цій порі")

    if hints:
        suffix = " ".join(hints).capitalize()
        return f"{greeting} {suffix}."

    return f"{greeting} Готова слухати."


def _ua_days(n: int) -> str:
    """Відмінювання слова «день» для числа n."""
    if 11 <= n % 100 <= 14:
        return "днів"
    r = n % 10
    if r == 1:
        return "день"
    if 2 <= r <= 4:
        return "дні"
    return "днів"


# ------------------------------------------------------------------
# Розпізнавання імені з тексту команди
# ------------------------------------------------------------------

def extract_name(text: str) -> str | None:
    """
    Повертає ім'я якщо фраза — представлення, інакше None.
    Підтримує: "мене звати X", "моє ім'я X", "мене можна називати X",
               "я X" (тільки одне слово ≥ 3 символів, щоб не ловити "я хочу...")
    """
    tl = text.lower().strip()
    patterns = [
        "мене звати ",
        "моє ім'я ",
        "моє ім я ",   # Google може транскрибувати апостроф як пробіл
        "моє імя ",
        "мене можна називати ",
        "звати мене ",
        "я ",
    ]
    for p in patterns:
        if tl.startswith(p):
            rest  = text[len(p):].strip()
            words = rest.split()
            if not words:
                continue
            candidate = words[0].strip('.,!?').capitalize()
            # Тільки одне слово з букв (3–20 символів)
            if 3 <= len(candidate) <= 20 and candidate.isalpha():
                # Для "я X" — відхиляємо якщо сам кандидат — дієслово або
                # прислівник (тобто "я хочу", "я можу", "я вже" тощо)
                if p == "я ":
                    NON_NAMES = {
                        'хочу', 'можу', 'маю', 'думаю', 'знаю', 'йду', 'іду',
                        'не', 'вже', 'ще', 'дуже', 'трохи', 'тут', 'там',
                        'добре', 'погано', 'готовий', 'готова', 'втомився',
                        'втомилась', 'голодний', 'голодна', 'зайнятий',
                    }
                    if candidate.lower() in NON_NAMES:
                        continue
                return candidate
    return None
