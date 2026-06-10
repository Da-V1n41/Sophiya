import threading
import asyncio
import edge_tts
import os
import ctypes
import time
import tempfile
import hashlib
import atexit

from config import DUCK_LEVEL, FADE_DOWN_SEC, FADE_UP_SEC, TTS_CACHE_MAX_MB

_lock = threading.Lock()
_tts_loop = None
_tts_loop_thread = None
_is_speaking = False              # True поки speaker() відтворює звук
_stop_requested = threading.Event()   # сигнал перервати поточне мовлення

# COM ініціалізується один раз на потік (не при кожному виклику)
_com_local = threading.local()

def _ensure_com():
    if not getattr(_com_local, 'initialized', False):
        try:
            import comtypes
            comtypes.CoInitialize()
            _com_local.initialized = True
        except Exception:
            pass


def is_speaking() -> bool:
    """Повертає True якщо Софія зараз говорить (TTS активний)."""
    return _is_speaking


def stop_speech():
    """Перериває поточне мовлення Sophii.

    Виставляє _stop_requested → polling-цикл у _play_audio негайно завершиться,
    speaker() пропустить решту тексту і відновить duck.
    """
    _stop_requested.set()
    try:
        ctypes.windll.winmm.mciSendStringW('stop sophia_tts', None, 0, 0)
    except Exception:
        pass

# Нейронний голос
VOICE = "uk-UA-PolinaNeural"

# --------------------------
# Плавне приглушення медіа під час мовлення (duck)
# --------------------------
# wmplayer.exe НАВМИСНО виключено: MCI (`type mpegvideo`) грає TTS через WMP-інфраструктуру
# Windows і створює сесію під wmplayer.exe → duck понижував би гучність власного TTS.
_MEDIA_APPS = {'chrome.exe', 'msedge.exe', 'spotify.exe',
               'firefox.exe', 'vlc.exe', 'aimp.exe', 'foobar2000.exe'}

# PID поточного Python-процесу — ніколи не приглушуємо себе
_SELF_PID = os.getpid()
_ducked: dict = {}        # pid → (ISimpleAudioVolume, original_volume)
_duck_lock = threading.Lock()
_restore_thread: threading.Thread = None   # відстежуємо потік відновлення
FADE_STEPS    = 14        # кількість кроків фейду


def _smoothstep(t: float) -> float:
    """Плавна S-крива: повільний старт → швидка середина → повільний кінець."""
    return t * t * (3.0 - 2.0 * t)


def _get_media_sessions():
    """Повертає список (ISimpleAudioVolume, pid) для запущених медіа-програм."""
    try:
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        _ensure_com()
        result = []
        for session in AudioUtilities.GetAllSessions():
            if not session.Process:
                continue
            # Ніколи не приглушуємо власний процес (TTS може грати під python.exe)
            if session.Process.pid == _SELF_PID:
                continue
            pname = session.Process.name().lower()
            if pname in ('python.exe', 'pythonw.exe'):
                continue
            if pname not in _MEDIA_APPS:
                continue
            try:
                vol = session._ctl.QueryInterface(ISimpleAudioVolume)
                result.append((vol, session.Process.pid))
            except Exception:
                pass
        return result
    except Exception:
        return []


def _duck_media(enable: bool):
    """
    enable=True  → плавно знижує гучність медіа до DUCK_LEVEL (блокуючий виклик).
    enable=False → плавно відновлює гучність у фоновому потоці (не блокує).

    Ключова особливість: vol-об'єкти зберігаються при duck і ті ж самі
    використовуються при restore — не шукаємо сесії повторно, щоб уникнути
    ситуації коли сесія змінилась і відновлення просто нічого не знаходить.
    """
    global _restore_thread

    if enable:
        # Якщо попереднє відновлення ще не закінчилось — чекаємо,
        # щоб не зберегти вже-зменшену гучність як "оригінальну"
        if _restore_thread is not None and _restore_thread.is_alive():
            _restore_thread.join(timeout=1.5)

        sessions = _get_media_sessions()
        if not sessions:
            return

        # Запам'ятовуємо поточні рівні + зберігаємо vol-об'єкт
        with _duck_lock:
            for vol, pid in sessions:
                if pid in _ducked:
                    continue           # вже приглушено — не перезаписуємо оригінал
                try:
                    cur = vol.GetMasterVolume()
                    if cur > DUCK_LEVEL:
                        _ducked[pid] = (vol, cur)   # зберігаємо об'єкт + рівень
                except Exception:
                    pass

        if not _ducked:
            return

        # Плавне затухання вниз (блокуємо — TTS стартує після завершення)
        step_time = FADE_DOWN_SEC / FADE_STEPS
        for step in range(1, FADE_STEPS + 1):
            t = _smoothstep(step / FADE_STEPS)
            with _duck_lock:
                items = list(_ducked.items())
            for pid, (vol, original) in items:
                try:
                    vol.SetMasterVolume(original + (DUCK_LEVEL - original) * t, None)
                except Exception:
                    pass
            time.sleep(step_time)

    else:
        # Знімаємо копію того, що треба відновити
        with _duck_lock:
            if not _ducked:
                return
            restore_items = list(_ducked.items())   # [(pid, (vol, original)), ...]

        def _do_restore():
            step_time = FADE_UP_SEC / FADE_STEPS
            for step in range(1, FADE_STEPS + 1):
                t = _smoothstep(step / FADE_STEPS)
                for pid, (vol, original) in restore_items:
                    try:
                        vol.SetMasterVolume(DUCK_LEVEL + (original - DUCK_LEVEL) * t, None)
                    except Exception:
                        pass
                time.sleep(step_time)

            # Верифікаційний прохід — якщо COM-об'єкт застарів або Chrome
            # змінив renderer-процес під час мовлення → примусово відновлюємо.
            try:
                fresh_sessions = _get_media_sessions()  # [(vol, pid), ...]
                fresh_by_pid  = {pid: vol for vol, pid in fresh_sessions}

                # Додатково: всі сесії chrome.exe що залишились на DUCK_LEVEL —
                # Chrome може змінити PID renderer'а під час speech, тому ловимо
                # "застряглі" сесії по імені процесу.
                from pycaw.pycaw import AudioUtilities
                _ensure_com()
                stuck_chrome = []
                for session in AudioUtilities.GetAllSessions():
                    if not session.Process:
                        continue
                    if session.Process.name().lower() != 'chrome.exe':
                        continue
                    try:
                        from pycaw.pycaw import ISimpleAudioVolume
                        v = session._ctl.QueryInterface(ISimpleAudioVolume)
                        if v.GetMasterVolume() <= DUCK_LEVEL + 0.05:
                            stuck_chrome.append(v)
                    except Exception:
                        pass

                for pid, (vol_old, original) in restore_items:
                    for try_vol in filter(None, [fresh_by_pid.get(pid), vol_old]):
                        try:
                            cur = try_vol.GetMasterVolume()
                            if abs(cur - original) > 0.03:
                                try_vol.SetMasterVolume(original, None)
                                print(f"[Duck] Примусове відновлення pid={pid}: "
                                      f"{cur*100:.0f}% → {original*100:.0f}%")
                            break
                        except Exception:
                            continue

                # Відновлюємо застряглі Chrome-сесії (нові PID що не були в duck)
                for v in stuck_chrome:
                    try:
                        v.SetMasterVolume(1.0, None)
                        print("[Duck] Відновлено Chrome-сесію з новим PID")
                    except Exception:
                        pass

            except Exception:
                pass

            with _duck_lock:
                for pid, _ in restore_items:
                    _ducked.pop(pid, None)

        _restore_thread = threading.Thread(target=_do_restore, daemon=True)
        _restore_thread.start()

# Папка для кешу TTS
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.tts_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

def _evict_tts_cache():
    """LRU-очистка: видаляє найстаріші .mp3 якщо кеш перевищує TTS_CACHE_MAX_MB."""
    try:
        files = [
            (os.path.getatime(os.path.join(CACHE_DIR, f)),
             os.path.getsize(os.path.join(CACHE_DIR, f)),
             os.path.join(CACHE_DIR, f))
            for f in os.listdir(CACHE_DIR) if f.endswith('.mp3')
        ]
        total_bytes = sum(s for _, s, _ in files)
        max_bytes = TTS_CACHE_MAX_MB * 1024 * 1024

        if total_bytes <= max_bytes:
            return

        # Сортуємо від найстарішого до найновішого
        files.sort(key=lambda x: x[0])
        for atime, size, path in files:
            if total_bytes <= max_bytes:
                break
            try:
                os.remove(path)
                total_bytes -= size
                print(f"[TTS Cache] Видалено старий файл: {os.path.basename(path)}")
            except Exception:
                pass
    except Exception:
        pass


# --------------------------
# Постійний event loop у фоні — asyncio.run() більше не потрібен
# --------------------------
def _get_tts_loop():
    global _tts_loop, _tts_loop_thread
    if _tts_loop is None or not _tts_loop.is_running():
        _tts_loop = asyncio.new_event_loop()
        _tts_loop_thread = threading.Thread(
            target=_tts_loop.run_forever, daemon=True
        )
        _tts_loop_thread.start()
    return _tts_loop


def _get_cache_path(text):
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f'{text_hash}.mp3')


# --------------------------
# Інтонація через нативні параметри edge_tts
# --------------------------
def _prosody_for(text: str) -> tuple:
    """
    Повертає (rate, pitch, volume) залежно від пунктуації:
      ?  → вищий pitch (питальна інтонація)
      !  → швидший rate + вищий pitch (жваво/захоплено)
      .  → базові значення
    """
    stripped = text.strip()
    if stripped.endswith('?'):
        return '+5%', '+10Hz', '+50%'
    if stripped.endswith('!'):
        return '+15%', '+5Hz', '+50%'
    return '+5%', '+0Hz', '+50%'


def _play_audio(filepath):
    """
    Відтворення MP3 через Windows MCI з підтримкою переривання.

    Використовуємо non-blocking 'play' + polling статусу (50 мс), щоб
    stop_speech() міг перервати через виставлення _stop_requested.

    Примітка: wmplayer.exe навмисно виключено з _MEDIA_APPS — саме тому duck
    більше не впливає на TTS-сесію, навіть якщо MCI відкриває її під WMP.
    """
    try:
        abs_path = os.path.abspath(filepath)
        winmm = ctypes.windll.winmm

        winmm.mciSendStringW('close sophia_tts', None, 0, 0)

        err = winmm.mciSendStringW(
            f'open "{abs_path}" type mpegvideo alias sophia_tts', None, 0, 0
        )
        if err != 0:
            print(f"MCI open error: {err}")
            return

        # Встановлюємо гучність до 1000 і даємо коротку паузу щоб команда вступила в силу
        winmm.mciSendStringW('setaudio sophia_tts volume to 1000', None, 0, 0)
        time.sleep(0.02)
        winmm.mciSendStringW('seek sophia_tts to start', None, 0, 0)

        # Non-blocking play — повертає керування одразу
        winmm.mciSendStringW('play sophia_tts', None, 0, 0)

        # Polling status — або поки програється, або поки не запросили зупинку
        buf = ctypes.create_unicode_buffer(64)
        while not _stop_requested.is_set():
            winmm.mciSendStringW('status sophia_tts mode', buf, 64, 0)
            mode = buf.value.lower().strip()
            if mode != 'playing':
                break
            time.sleep(0.05)   # 50 мс — достатньо щоб реагувати швидко

        winmm.mciSendStringW('close sophia_tts', None, 0, 0)

    except Exception as e:
        print(f"Помилка відтворення аудіо: {e}")
        try:
            ctypes.windll.winmm.mciSendStringW('close sophia_tts', None, 0, 0)
        except Exception:
            pass


async def _generate_speech_async(text, output_file, rate='+5%', pitch='+0Hz', volume='+50%'):
    communicate = edge_tts.Communicate(text, VOICE, rate=rate, pitch=pitch, volume=volume)
    await communicate.save(output_file)


def _generate_speech_sync(text, output_file, rate='+5%', pitch='+0Hz', volume='+50%'):
    """Генерує мову через постійний event loop (швидше ніж asyncio.run)"""
    loop = _get_tts_loop()
    future = asyncio.run_coroutine_threadsafe(
        _generate_speech_async(text, output_file, rate, pitch, volume), loop
    )
    future.result(timeout=15)  # Чекаємо результату макс 15с


def _pyttsx3_speak(text: str):
    """Офлайн TTS через pyttsx3 — запасний варіант якщо edge_tts недоступний."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Шукаємо український голос, якщо є
        voices = engine.getProperty('voices')
        for v in voices:
            if 'uk' in v.id.lower() or 'uk' in (v.languages or []):
                engine.setProperty('voice', v.id)
                break
        engine.setProperty('rate', 170)
        engine.say(text)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
    except Exception as e:
        print(f"[TTS pyttsx3] Помилка: {e}")


def speaker(text):
    """Відтворення мови з кешуванням усіх фраз + duck медіа під час мовлення.

    Оптимізація: при cache-miss генерація TTS і fade-down починаються одночасно,
    що приховує затримку edge_tts за час fade (~0.30 с).
    """
    global _is_speaking
    _stop_requested.clear()      # скидаємо прапор переривання
    _is_speaking = True
    try:
        with _lock:
            try:
                print(f"[Софія]: {text}")

                # Просодія залежно від пунктуації; кеш ключується по тексту + параметрах
                rate, pitch, volume = _prosody_for(text)
                cache_key = f"{text}\x00{rate}\x00{pitch}"
                cache_path = _get_cache_path(cache_key)

                _edge_ok = True

                if not os.path.exists(cache_path):
                    # Cache miss: запускаємо генерацію і duck ОДНОЧАСНО
                    import shutil
                    tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir=CACHE_DIR)
                    tmp_path = tmp.name
                    tmp.close()

                    gen_done  = threading.Event()
                    gen_error = [None]   # mutable cell для помилки з потоку

                    def _do_generate():
                        try:
                            _generate_speech_sync(text, tmp_path, rate, pitch, volume)
                        except Exception as e:
                            gen_error[0] = e
                        finally:
                            gen_done.set()

                    gen_thread = threading.Thread(target=_do_generate, daemon=True)
                    gen_thread.start()

                    # Паралельно починаємо duck (займає ~FADE_DOWN_SEC)
                    _duck_media(True)

                    # Чекаємо завершення генерації (якщо ще не готова)
                    gen_done.wait(timeout=15)

                    if gen_error[0] is not None:
                        print(f"[TTS] edge_tts недоступний ({gen_error[0]}), переключаюсь на pyttsx3")
                        _edge_ok = False
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                    else:
                        try:
                            shutil.move(tmp_path, cache_path)
                            _evict_tts_cache()   # LRU: прибираємо якщо кеш завеликий
                        except Exception:
                            cache_path = tmp_path  # програємо з тимчасового

                    # Duck вже активний — одразу грає
                    try:
                        if _edge_ok:
                            _play_audio(cache_path)
                        else:
                            _pyttsx3_speak(text)
                    finally:
                        _duck_media(False)

                else:
                    # Cache hit: стара поведінка (duck → play → restore)
                    _duck_media(True)
                    try:
                        _play_audio(cache_path)
                    finally:
                        _duck_media(False)

            except Exception as e:
                print(f"Помилка відтворення мови: {e}")
                try:
                    _duck_media(False)
                except Exception:
                    pass
    finally:
        _is_speaking = False


# Фрази, які генеруємо заздалегідь щоб перша відповідь була миттєвою
PREWARM_PHRASES = [
    "Привіт! Я Софія, готова слухати.",
    "Слухаю вас",
    "Не зрозуміла, спробуйте ще раз.",
    "Зрозуміла, виконую...",
    "Готово",
    "Добре",
    "Виконую",
    "Відкриваю",
    "Шукаю",
    "До зустрічі! Гарного дня!",
]


def force_restore():
    """
    Негайно відновлює гучність усіх приглушених програм.
    Викликати перед os._exit() щоб не залишати медіа на DUCK_LEVEL.
    """
    global _restore_thread

    # Якщо плавне відновлення вже йде — чекаємо його (макс FADE_UP_SEC + 0.3с)
    if _restore_thread is not None and _restore_thread.is_alive():
        _restore_thread.join(timeout=FADE_UP_SEC + 0.3)

    with _duck_lock:
        if not _ducked:
            return
        items = list(_ducked.items())

    # Спочатку пробуємо кешовані об'єкти, потім свіжі сесії
    try:
        fresh = {pid: vol for vol, pid in _get_media_sessions()}
    except Exception:
        fresh = {}

    for pid, (vol_old, original) in items:
        for try_vol in filter(None, [fresh.get(pid), vol_old]):
            try:
                try_vol.SetMasterVolume(original, None)
                break
            except Exception:
                continue

    with _duck_lock:
        _ducked.clear()


# Страхова сітка: якщо процес завершується будь-яким чином (Ctrl+C, crash,
# root.destroy()) — гарантовано відновлюємо гучність медіа.
atexit.register(force_restore)


def prewarm():
    """Прогріваємо TTS loop і генеруємо кеш частих фраз при старті програми."""
    _get_tts_loop()
    threading.Thread(target=_prewarm_phrases, daemon=True).start()


def _prewarm_phrases():
    """Фоново генерує MP3 для PREWARM_PHRASES щоб вони грали без затримки."""
    for phrase in PREWARM_PHRASES:
        try:
            rate, pitch, volume = _prosody_for(phrase)
            cache_key = f"{phrase}\x00{rate}\x00{pitch}"
            cache_path = _get_cache_path(cache_key)
            if not os.path.exists(cache_path):
                import tempfile, shutil
                tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir=CACHE_DIR)
                tmp_path = tmp.name
                tmp.close()
                _generate_speech_sync(phrase, tmp_path, rate, pitch, volume)
                try:
                    shutil.move(tmp_path, cache_path)
                except Exception:
                    pass
                print(f"[TTS Prewarm] Кешовано: «{phrase[:40]}»")
        except Exception as e:
            print(f"[TTS Prewarm] Помилка для «{phrase[:40]}»: {e}")
