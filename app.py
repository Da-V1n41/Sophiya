from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
import sounddevice as sd
import vosk
import json
import queue
import words
from skills import *
import voice
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

q = queue.Queue()

model = vosk.Model('vosk-model-uk-v3-lgraph')

device = sd.default.device
samplerate = int(sd.query_devices(device[0], 'input')['default_samplerate'])


def callback(indata, frames, time, status):
    '''Додає семпли в чергу з потоку мікрофона'''
    q.put(bytes(indata))


def recognize(data, vectorizer, clf):
    '''Аналіз розпізнаної мови'''

    # Перевіряємо чи є ім'я бота в data
    trg = words.TRIGGERS.intersection(data.split())
    if not trg:
        return

    # Видаляємо ім'я бота з тексту
    for trigger in trg:
        data = data.replace(trigger, '').strip()

    if not data:
        voice.speaker("Слухаю вас")
        return

    # Отримуємо вектор тексту та порівнюємо
    text_vector = vectorizer.transform([data]).toarray()[0]
    answer = clf.predict([text_vector])[0]

    # Отримуємо ім'я функції з відповіді
    func_name = answer.split()[0]

    # Озвучка відповіді
    voice.speaker(answer.replace(func_name, '').strip())

    # Запуск функції
    if func_name in globals() and callable(globals()[func_name]):
        globals()[func_name]()
    else:
        logger.warning(f"Функція '{func_name}' не знайдена")


def main():
    '''Навчаємо модель та постійно слухаємо мікрофон'''
    voice.speaker("Привіт, готова слухати вас")

    vectorizer = CountVectorizer()
    vectors = vectorizer.fit_transform(list(words.data_set.keys()))

    clf = LogisticRegression()
    clf.fit(vectors, list(words.data_set.values()))

    with sd.RawInputStream(samplerate=samplerate, blocksize=16000, device=device[0],
                           dtype='int16', channels=1, callback=callback):

        rec = vosk.KaldiRecognizer(model, samplerate)
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                data = json.loads(rec.Result())['text']
                if data:
                    recognize(data, vectorizer, clf)


if __name__ == '__main__':
    main()
