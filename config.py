"""
config.py — централізована конфігурація Sophiya.
Читає config.json і експортує константи для всіх модулів.
Не імпортує нічого з проєкту — чистий standalone модуль.
"""
import os
import json

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


_CONFIG = _load_config()

# Загальні налаштування
DEBUG            = _CONFIG.get('debug', False)
SPOTIFY_PATH     = _CONFIG.get('spotify_path', r'C:\Users\Andriy\AppData\Roaming\Spotify\Spotify.exe')
MISTRAL_API_KEY  = _CONFIG.get('mistral_api_key', '')

# Приглушення медіа під час мовлення
DUCK_LEVEL       = float(_CONFIG.get('duck_level', 0.25))
FADE_DOWN_SEC    = float(_CONFIG.get('fade_down_sec', 0.30))
FADE_UP_SEC      = float(_CONFIG.get('fade_up_sec', 0.50))

# TTS кеш
TTS_CACHE_MAX_MB = int(_CONFIG.get('tts_cache_max_mb', 100))

# VAD і поведінка
INACTIVITY_MIN   = int(_CONFIG.get('inactivity_minutes', 30))
VAD_THRESHOLD    = int(_CONFIG.get('vad_threshold', 300))
