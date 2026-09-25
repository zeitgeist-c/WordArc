"""Which of the three offered models actually reads this dictation best.

The sizes and speeds in the settings box are claims; this is the measurement
behind them. Same audio, same settings, three models, scored against the
sentence that was really spoken — including whether the model invented words
the speaker never said, which is the failure that makes a transcript unusable.
"""
import difflib
import os
import sys
import time
import unicodedata
import wave

MODELS = (sys.argv[1] if len(sys.argv) > 1
          else r"C:\Users\user\AppData\Local\hermes\cache\scratch\wa-final")
AUDIO = (sys.argv[2] if len(sys.argv) > 2
         else r"C:\Users\user\AppData\Local\hermes\cache\scratch\wa-bench\real16k.wav")

sys.path.insert(0, r"C:\Users\user\projects\WordArc")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import localspeech  # noqa: E402

# What was said, taken from the script that made the sample. Turkish
# diacritics matter: a model that drops them is not usable in a Turkish
# document, so the scoring counts them as mistakes. This is the hard take on
# purpose — a product name in Latin letters, two acronyms, a number spelled out
# in words, and a closing question, which is where the models differ.
TRUTH = ("Merhaba, bugün sizlerle WordArc projesinin yerel ses tanıma "
         "özelliğini konuşacağız. Bu cümle Türkçe karakterleri, noktalama "
         "işaretlerini ve yabancı kelimeleri bir arada içeriyor. Örneğin "
         "API, GPU, transkripsiyon, model, değişken gibi sözcükler geçiyor. "
         "Sayıları da deneyelim: üç, yirmi beş, bin iki yüz kırk. Son olarak "
         "soru cümlesi: yarın toplantı saat kaçta başlıyor?")

# A number said in words and the same number written as digits are one
# statement, not two, so both sides are read as digits before comparing.
NUMBERS = {"uc": "3", "yirmi bes": "25", "bin iki yuz kirk": "1240"}


def _fold(text):
    """Lowercase, accents off, dotless i as i — so "API" and "apı" are one word
    said out loud and the case a model picks is not a mistake."""
    flat = []
    for ch in unicodedata.normalize("NFKD", text.lower()):
        if unicodedata.combining(ch):
            continue
        flat.append("i" if ch in "ıi" else ch)
    return "".join(c for c in flat if c.isalnum() or c == " ")


def _words(text):
    """The words to compare: punctuation gone, number words as digits."""
    return [NUMBERS.get(w, w) for w in _fold(text).split()]


def _score(got):
    """(right, wrong, invented): how much of what was said came back intact,
    how much came back wrong or missing, and how much was never said."""
    truth, heard = _words(TRUTH), _words(got)
    wrong = extra = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, truth, heard).get_opcodes():
        if tag == "replace":
            wrong += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            wrong += i2 - i1
        elif tag == "insert":
            extra += j2 - j1
    return len(truth) - wrong, wrong, extra


def main():
    with wave.open(AUDIO, "rb") as w:
        seconds = w.getnframes() / w.getframerate()
    total = len(_words(TRUTH))
    print(f"audio: {AUDIO}  ({seconds:.1f}s, difficult take, {total} words)")
    print(f"truth: {TRUTH}\n")

    for name in ("base", "small", "large-v3-turbo"):
        if not localspeech.state(name, where=MODELS).installed:
            print(f"[{name}] downloading...", flush=True)
            localspeech.download(name, where=MODELS, on_progress=lambda *_: None)
        size = localspeech.state(name, where=MODELS).size
        t0 = time.monotonic()
        # The windowed form, because what matters is not only the text but how
        # the model divided the take up.
        segments = localspeech.transcribe(
            name, AUDIO, language="tr", with_segments=True, where=MODELS)
        took = time.monotonic() - t0
        result = " ".join(text for _, _, text in segments)
        right, wrong, extra = _score(result)
        print(f"[{name:15}] {localspeech.human_size(size):>7}  {took:5.1f}s  "
              f"{seconds / took:4.1f}x realtime   {right}/{total} words right"
              f"   {wrong} wrong   {extra} invented")
        print(f"{'':18}{result}\n")


if __name__ == "__main__":
    main()
