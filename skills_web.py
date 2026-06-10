"""
skills_web.py — веб-навички Sophiya.
Браузер, пошук, погода, новини, жарти, ранковий брифінг.
"""
import sys
import webbrowser
import subprocess

from config import SPOTIFY_PATH

try:
    import requests
except ImportError:
    requests = None


# ---------------------------------------------------------------------------
# Браузер та пошук
# ---------------------------------------------------------------------------
def youtube():
    webbrowser.open('https://www.youtube.com', new=2)
    return "Відкриваю Ютуб"


def browser():
    webbrowser.open('https://www.google.com', new=2)
    return "Відкриваю браузер"


def search():
    webbrowser.open('https://www.google.com')
    return "Відкриваю пошук Google"


def search_yt():
    webbrowser.open('https://www.youtube.com')
    return "Відкриваю пошук на Ютубі"


def saver():
    return "Функція завантаження відео поки не підтримується в GUI"


def offBot():
    sys.exit()


# ---------------------------------------------------------------------------
# Погода
# ---------------------------------------------------------------------------
def _detect_city():
    """Автовизначення міста за IP-адресою."""
    try:
        geo = requests.get('http://ip-api.com/json/?fields=city,lat,lon', timeout=3).json()
        return geo.get('city', 'Sanok'), geo.get('lat'), geo.get('lon')
    except Exception:
        return 'Sanok', None, None


def weather():
    if not requests:
        return "Модуль requests не встановлено"
    try:
        city, lat, lon = _detect_city()
        if lat and lon:
            params = {
                'lat': lat, 'lon': lon,
                'units': 'metric', 'lang': 'uk',
                'appid': 'f8b4247f3d19e69685f242af04743a36'
            }
        else:
            params = {
                'q': city, 'units': 'metric', 'lang': 'uk',
                'appid': 'f8b4247f3d19e69685f242af04743a36'
            }
        response = requests.get('https://api.openweathermap.org/data/2.5/weather', params=params)
        response.raise_for_status()
        w = response.json()
        city_name = w.get('name', city)
        desc = w['weather'][0]['description']
        temp = round(w['main']['temp'])
        feels = round(w['main']['feels_like'])
        return f"Зараз у {city_name}: {desc}, {temp} градусів, відчувається як {feels}"
    except Exception:
        return "Не вдалося отримати погоду"


# ---------------------------------------------------------------------------
# Новини (Google RSS)
# ---------------------------------------------------------------------------
def news():
    if not requests:
        return "Модуль requests не встановлено"
    try:
        import xml.etree.ElementTree as ET
        url = 'https://news.google.com/rss?hl=uk&gl=UA&ceid=UA:uk'
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = root.findall('.//item')[:3]
        if not items:
            return "Не вдалося знайти новини"
        headlines = []
        for i, item in enumerate(items, 1):
            title = item.find('title').text
            title = title.rsplit(' - ', 1)[0] if ' - ' in title else title
            headlines.append(f"{i}. {title}")
        return "Головні новини: " + "; ".join(headlines)
    except Exception as e:
        print(f"Помилка новин: {e}")
        return "Не вдалося отримати новини"


# ---------------------------------------------------------------------------
# Розваги
# ---------------------------------------------------------------------------
def coin_flip():
    import random
    return f"{random.choice(['Орел', 'Решка'])}!"


def random_number():
    import random
    return f"Випало число {random.randint(1, 100)}"


def joke():
    import random
    jokes = [
        "Вчора помив вікна — тепер у мене світанок на дві години раніше!",
        "Лікар питає: — Де болить? — Скрізь! — Покажіть де саме. — Ось, торкаюся носа — болить, торкаюся коліна — болить. — Зрозумів. У вас зламаний палець.",
        "Програміст виходить в магазин. Дружина каже: купи батон хліба, і якщо будуть яйця — візьми десяток. Він повернувся з десятьма батонами.",
        "Чому програмісти плутають Хелловін і Різдво? Тому що Oct 31 = Dec 25.",
        "Студент на іспиті: — Я знаю цей матеріал, просто не можу згадати. Викладач: — Добре, коли згадаєте — приходьте.",
        "Дзвонить телефон. — Алло! — Алло! — Говоріть! — Ви вже говорите. — Що? — Нічого. — Добре. — Бувайте. — До побачення.",
        "Оголошення: продам годинник дідуся. Він не поспішає, не відстає, стоїть.",
        "Вчитель: — Коли народився Шевченко? Учень: — Не знаю. Вчитель: — Тому що ти не читаєш! Учень: — А ви теж не знали б, якби не прочитали!",
        "Чоловік приходить до лікаря: — У мене проблеми з пам'яттю. — Давно це у вас? — Що давно?",
        "Синоптик каже: — Завтра опадів не передбачається, але якщо піде дощ — це буде дощ.",
        "Я вчора цілий день шукав окуляри. Знайшов їх на носі. Дивився прямо крізь них.",
        "Дитина: — Мамо, а як роблять дітей? Мама: — Коли двоє людей дуже люблять одне одного... Дитина: — Зрозуміло. А Майнкрафт краще.",
        "На прийомі у психолога: — Мені здається, мене всі ігнорують. Психолог: — Наступний!",
        "Зустрілись два сусіди. Один питає: — Ти чув, що вчора сусіда машину вкрали? — Та ну? — Правда! Прямо з гаража. — І що поліція? — Шукає машину. — А гараж? — Теж украли.",
    ]
    return random.choice(jokes)


# ---------------------------------------------------------------------------
# Ранковий брифінг і ритуал
# ---------------------------------------------------------------------------
def morning_briefing():
    """Погода + перша новина — короткий підсумок дня."""
    parts = []
    w = weather()
    if w and "Не вдалося" not in w and "не встановлено" not in w:
        parts.append(w)
    if requests:
        try:
            import xml.etree.ElementTree as ET
            resp = requests.get('https://news.google.com/rss?hl=uk&gl=UA&ceid=UA:uk', timeout=5)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = root.findall('.//item')
            if items:
                title = (items[0].find('title').text or '').rsplit(' - ', 1)[0].strip()
                if title:
                    parts.append(f"Головна новина: {title}")
        except Exception:
            pass
    return ". ".join(parts) if parts else "Не вдалося отримати інформацію про день"


def morning_routine():
    """Ранковий ритуал: час + погода + топ-2 новини + запуск Spotify у фоні."""
    from skills_system import current_time   # локальний імпорт — без циклічних залежностей

    parts = ["Доброго ранку!"]

    t = current_time()
    if t:
        parts.append(t)

    w = weather()
    if w and "Не вдалося" not in w and "не встановлено" not in w:
        parts.append(w)

    if requests:
        try:
            import xml.etree.ElementTree as ET
            resp = requests.get('https://news.google.com/rss?hl=uk&gl=UA&ceid=UA:uk', timeout=5)
            root = ET.fromstring(resp.content)
            items = root.findall('.//item')[:2]
            headlines = []
            for item in items:
                title = (item.find('title').text or '').rsplit(' - ', 1)[0].strip()
                if title:
                    headlines.append(title)
            if headlines:
                parts.append("Головні новини: " + "; ".join(headlines))
        except Exception:
            pass

    try:
        subprocess.Popen(SPOTIFY_PATH)
    except Exception:
        pass

    return ". ".join(parts)
