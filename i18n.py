"""Tiny translation helper.

Source strings are English; per-language translations live in the TABLES
below (Turkish first, the rest follow). No gettext, no .mo files; the string
tables are small enough to keep in code.

Contract (13-language task):
- Fresh profiles start in English; the OS locale never overrides that.
- The saved explicit choice persists across updates and restarts.
- Unknown codes fall back to English at runtime, but a fallback hit at
  release time means that language is NOT done.
"""

import os

from i18n_tables import (
    DE1 as _DE1, DE2 as _DE2, DE3 as _DE3, DE4 as _DE4, DE5 as _DE5, DE6 as _DE6, DE7 as _DE7, ES1 as _ES1, ES2 as _ES2, ES3 as _ES3, ES4 as _ES4, ES5 as _ES5, ES6 as _ES6, ES7 as _ES7, FR1 as _FR1, FR2 as _FR2, FR3 as _FR3, FR4 as _FR4, FR5 as _FR5, FR6 as _FR6, FR7 as _FR7, IT1 as _IT1, IT2 as _IT2, IT3 as _IT3, IT4 as _IT4, IT5 as _IT5, IT6 as _IT6, IT7 as _IT7, PB1 as _PB1, PB2 as _PB2, PB3 as _PB3, PB4 as _PB4, PB5 as _PB5, PB6 as _PB6, PB7 as _PB7, RU1 as _RU1, RU2 as _RU2, RU3 as _RU3, RU4 as _RU4, RU5 as _RU5, RU6 as _RU6, RU7 as _RU7, PL1 as _PL1, PL2 as _PL2, PL3 as _PL3, PL4 as _PL4, PL5 as _PL5, PL6 as _PL6, PL7 as _PL7, NL1 as _NL1, NL2 as _NL2, NL3 as _NL3, NL4 as _NL4, NL5 as _NL5, NL6 as _NL6, NL7 as _NL7, ZH1 as _ZH1, ZH2 as _ZH2, ZH3 as _ZH3, ZH4 as _ZH4, ZH5 as _ZH5, ZH6 as _ZH6, ZH7 as _ZH7, JA1 as _JA1, JA2 as _JA2, JA3 as _JA3, JA4 as _JA4, JA5 as _JA5, JA6 as _JA6, JA7 as _JA7, KO1 as _KO1, KO2 as _KO2, KO3 as _KO3, KO4 as _KO4, KO5 as _KO5, KO6 as _KO6, KO7 as _KO7,
)

# Code + self-name label. English first and default; flags are never used
# as language identifiers.
LANGUAGES = [
    ("en", "English"),
    ("tr", "Türkçe"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("pt-BR", "Português (Brasil)"),
    ("ru", "Русский"),
    ("pl", "Polski"),
    ("nl", "Nederlands"),
    ("zh-CN", "简体中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
]

CODES = {code for code, _ in LANGUAGES}

_lang = "en"


def resolve(code):
    """Known code -> itself; legacy 'auto'/unknown -> English default."""
    if code in CODES:
        return code
    return "en"


def set_language(code):
    global _lang
    _lang = resolve(code)


def language():
    return _lang


def t(text, **kwargs):
    table = TABLES.get(_lang)
    out = table.get(text, text) if table else text
    return out.format(**kwargs) if kwargs else out


# Turkish suffixes follow the vowels of the word they attach to, so "Claude'a"
# but "Codex'e". A name dropped into a sentence through t() cannot be inflected
# by the sentence, so it arrives already inflected. English takes the name as it
# is and puts the preposition in the sentence, where it belongs.
_TR_CASES = {
    "dative": {"Claude": "Claude'a", "Codex": "Codex'e", "Gemini": "Gemini'ye"},
    "accusative": {"Claude": "Claude'u", "Codex": "Codex'i", "Gemini": "Gemini'yi"},
}


def name(text, case=""):
    if _lang != "tr" or not case:
        return text
    return _TR_CASES.get(case, {}).get(text, text)


TR = {
    "cancelled": "İptal edildi",
    "Preparing installation. Approve the Windows permission request; this window stays open until setup is ready.": "Kurulum hazırlanıyor. Windows izin isteğini onaylayın; kurulum hazır olana kadar bu pencere açık kalır.",
    "Search WordArc, Hermes and model caches first, then user folders and local drives. Choose a model; shared files stay in place.": "Önce WordArc, Hermes ve model önbellekleri, ardından kullanıcı klasörleri ve yerel diskler taranır. Modelinizi seçin; ortak dosyalar yerinde kalır.",
    "not_checked": "Henüz kontrol edilmedi",
    "Could not save settings": "Ayarlar kaydedilemedi",
    "Close": "Kapat",
    "Show scan details": "Tarama ayrıntılarını göster",
    "This computer": "Bu bilgisayar",
    "Find engines and models…": "Motor ve model bul…",
    "Find local speech models": "Bilgisayardaki ses modellerini bul",
    "Your models, already on this computer": "Modelleriniz zaten bilgisayarınızda olabilir",
    "Search WordArc, Hermes, Hugging Face and your user folders. Choose a model and where it runs; shared files stay in place.": "WordArc, Hermes, Hugging Face ve kullanıcı klasörleriniz taranır. Modelinizi ve çalışacağı aygıtı seçin; ortak dosyalar yerinde kalır.",
    "Preparing scan…": "Tarama hazırlanıyor…",
    "Scan progress": "Tarama ilerlemesi",
    "Discovered models": "Bulunan modeller",
    "Scan details and inaccessible locations appear here.": "Tarama ayrıntıları ve erişilemeyen konumlar burada görünür.",
    "Search another folder…": "Başka klasörde ara…",
    "Scan again": "Yeniden tara",
    "Stop scan": "Taramayı durdur",
    "Use this model": "Bu modeli kullan",
    "Searching for existing engines and models…": "Bilgisayardaki motor ve modeller aranıyor…",
    "Scan stopped. You can scan again or choose another folder.": "Tarama durduruldu. Yeniden tarayabilir veya başka klasör seçebilirsiniz.",
    "Searching… {count} models found · {files} entries checked": "Aranıyor… {count} model bulundu · {files} öğe kontrol edildi",
    "Checking CPU, CUDA and Vulkan… {done}/{total}": "CPU, CUDA ve Vulkan kontrol ediliyor… {done}/{total}",
    "{models} models found · {choices} choices available": "{models} model bulundu · {choices} kullanım seçeneği",
    "Unavailable": "Kullanılamıyor",
    "Native engines: {count}": "Doğrulanan yerel motor: {count}",
    "Validate on selection": "Seçildiğinde doğrulanacak",
    "Files found": "Dosyalar bulundu",
    "Backend unavailable": "Uygun motor kullanılamıyor",
    "Search limit reached. Some locations were not checked; select a specific folder to continue.": "Tarama sınırına ulaşıldı. Bazı konumlar kontrol edilemedi; devam etmek için belirli bir klasör seçebilirsiniz.",
    "No compatible models found. Search another folder or download a model in Settings.": "Uyumlu model bulunamadı. Başka bir klasörde arayın veya Ayarlar'dan model indirin.",
    "Choose a folder to search": "Aranacak klasörü seçin",
    "Stopping scan…": "Tarama durduruluyor…",
    "Validating the selected model and engine…": "Seçtiğiniz model ve motor doğrulanıyor…",
    "Could not use this model: {error}": "Bu model kullanılamadı: {error}",
    "Disconnect": "Bağlantıyı kaldır",
    "Disconnect this shared model? Its files stay available to Hermes and other applications.": "Bu ortak modelin bağlantısı kaldırılsın mı? Dosyalar Hermes ve diğer uygulamalar için yerinde kalır.",
    "ready": "Hazır",
    "unavailable": "Kullanılamıyor",
    "unverified": "Bulundu; seçimde doğrulanacak",
    "denied": "Erişim engellendi",
    "timeout": "Zaman aşımı",
    "incompatible": "Uyumsuz",
    "missing": "Bulunamadı",
    "error": "Kontrol hatası",
    "CPU (whisper.cpp model)": "CPU (whisper.cpp modeli)",
    "Vulkan model needs downloading; the existing CPU model remains available in Automatic mode.": "Vulkan modeli indirilmeli; Otomatik modda mevcut CPU modeli kullanılmaya devam eder.",
    "AMD GPU (Vulkan)": "AMD ekran kartı (Vulkan)",
    "Vulkan could not start": "Vulkan başlatılamadı",
    "No usable AMD Vulkan device was found. Check the AMD driver.": "Kullanılabilir AMD Vulkan cihazı bulunamadı. AMD ekran kartı sürücüsünü kontrol edin.",
    "The Vulkan engine is missing. Scan, select or download it in Settings.": "Vulkan motoru bulunamadı. Ayarlar'dan tarayın, seçin veya indirin.",
    "The model is installed, but the Vulkan engine is missing. Download the engine to continue.": "Model kurulu, ancak Vulkan motoru eksik. Devam etmek için motoru indirin.",
    "Vulkan engine: {path}": "Vulkan motoru: {path}",
    "Vulkan engine ready. Hover here to see its location.": "Vulkan motoru hazır. Konumunu görmek için burada bekleyin.",
    "Vulkan engine": "Vulkan motoru",
    "Scan for engine": "Motoru tara",
    "Select engine…": "Motor seç…",
    "Select Vulkan engine": "Vulkan motorunu seçin",
    "Select a compatible whisper-cli.exe with Vulkan support.": "Vulkan destekli, uyumlu bir whisper-cli.exe seçin.",
    "Download engine": "Motoru indir",
    "Re-download": "Yeniden indir",
    "Download {name} again? The current model stays available until the replacement is verified.": "{name} modeli yeniden indirilsin mi? Yeni dosya doğrulanana kadar mevcut model kullanılabilir kalır.",
    "The Vulkan model {name} is not installed yet. Download it in Settings.": "Vulkan için {name} modeli henüz kurulu değil. Ayarlar'dan indirin.",
    "Vulkan reads 16 kHz, 16-bit WAV audio.": "Vulkan motoru 16 kHz, 16 bit WAV kaydı okur.",
    "Vulkan transcription failed: {error}": "Vulkan yazıya çevirme hatası: {error}",
    "Vulkan did not initialize a GPU backend.": "Vulkan motoru GPU üzerinde başlatılamadı.",
    "Vulkan failed; using CPU for this session: {error}": "Vulkan çalışmadı; bu oturumda CPU kullanılıyor: {error}",
    "Automatic uses NVIDIA CUDA, then AMD Vulkan, then CPU. AMD Vulkan needs a separate model download. An explicit GPU choice asks before switching to CPU after a failure.": "Otomatik seçim önce NVIDIA CUDA'yı, ardından AMD Vulkan'ı, ardından CPU'yu kullanır. AMD Vulkan için model ayrıca indirilir. GPU elle seçildiğinde hata sonrası CPU'ya geçmeden önce onay sorulur.",
    "CUDA could not start": "CUDA başlatılamadı",
    "Switch to CPU, save this setting and retry this recording?": "CPU'ya geçilsin, bu ayar kaydedilsin ve bu kayıt yeniden işlensin mi?",
    "CUDA libraries are missing or cannot load (packaging/dependency problem): {libraries}": "CUDA kitaplıkları eksik veya yüklenemiyor (paketleme/bağımlılık sorunu): {libraries}",
    "CTranslate2 CUDA initialization failed: {error}": "CTranslate2 CUDA başlatma hatası: {error}",
    "No usable NVIDIA GPU/driver was found (CUDA devices: {count}).": "Kullanılabilir NVIDIA GPU/sürücü bulunamadı (CUDA cihazı: {count}).",
    "CTranslate2/local engine could not load: {error}": "CTranslate2/yerel motor yüklenemedi: {error}",
    "CUDA initialization failed: {error}": "CUDA başlatılamadı: {error}",
    "CUDA transcription failed: {error}": "CUDA yazıya çevirme hatası: {error}",
    "Gemini did not finish the response ({reason}).": "Gemini yanıtı tamamlayamadı ({reason}).",
    "No speech content remains after cleanup.": "Temizleme sonrasında konuşma içeriği kalmadı.",
    "Controls": "Kontroller",
    "Details": "Ayrıntılar",
    "Audio and models": "Ses ve modeller",
    "Text and terms": "Metin ve terimler",
    "Use typed value": "Yazdığım değeri kullan",
    "Text": "Metin",
    "Yes": "Evet",
    "No": "Hayır",
    "OK": "Tamam",

    # --- tray ---------------------------------------------------------
    "Start recording": "Kaydı başlat",
    "Starting WordArc…": "WordArc açılıyor…",
    "Stop and transcribe": "Kaydı bitir ve yaz",
    "Working…": "İşleniyor…",
    "Cancel": "İptal",
    "Color": "Renk",
    "Undo": "Geri al",
    "Reset drawing": "Çizimi sıfırla",
    "Add text": "Metin ekle",
    "Text:": "Metin:",
    "Cancel recording": "Kaydı iptal et",
    "Cancel": "İptal",
    "Settings…": "Ayarlar…",
    "Restart": "Yeniden başlat",
    "Quit": "Çık",
    "WordArc: ready": "WordArc: hazır",
    "WordArc: recording": "WordArc: kaydediyor",
    "WordArc: working": "WordArc: işleniyor",

    # --- overlay / pipeline -------------------------------------------
    "Transcribing…": "Yazıya çevriliyor…",
    "Cleaning up…": "Temizleniyor…",
    "Pasting…": "Yapıştırılıyor…",
    "Pasted": "Yapıştırıldı",
    "Copied": "Panoya kopyalandı",
    "{action}: {preview}": "{action}: {preview}",
    "Cleanup skipped: {error}": "Temizleme atlandı: {error}",
    "Pasted raw, cleanup failed: {error}": "Ham metin yapıştırıldı, temizleme başarısız: {error}",
    "WordArc: cleanup failed": "WordArc: temizleme başarısız",
    "{service} rejected the API key (HTTP {code}). Open Settings and check it.":
        "{service} API anahtarını reddetti (HTTP {code}). Ayarlar'ı açıp kontrol et.",
    "{service} says the account is out of credit (HTTP 402).":
        "{service} hesapta kredi kalmadığını söylüyor (HTTP 402).",
    "{service} is rate limiting you (HTTP 429). Try again in a moment.":
        "{service} hız sınırı uyguluyor (HTTP 429). Birazdan tekrar dene.",
    "No speech detected": "Ses algılanmadı",
    "No speech detected ({level} dB)": "Ses algılanmadı ({level} dB)",
    "Discarded a stock phrase: “{text}”": "Kalıp cümle atıldı: “{text}”",
    "Discard stock phrases models invent for near-silent audio":
        "Sessize yakın seste modelin uydurduğu kalıp cümleleri at",
    "Whisper answers silence with things like “Thanks for watching”.":
        "Whisper sessizliğe “Altyazı M.K.” gibi şeylerle karşılık verir.",
    "Speech also has to rise {margin} dB above the recording's own noise "
    "floor, so this absolute floor rarely needs touching. Lower it if quiet "
    "speech gets dropped; raise it if noise still gets through.":
        "Konuşmanın ayrıca kaydın kendi gürültü tabanının {margin} dB üstüne "
        "çıkması gerekir; bu mutlak taban nadiren değiştirilir. Kısık konuşma "
        "eleniyorsa düşür, gürültü hâlâ geçiyorsa yükselt.",
    "Recording too short, speak for at least 0.3 s": "Ses çok kısa, en az 0,3 saniye konuş",
    "Live transcription failed.": "Canlı yazı başarısız oldu.",
    "Live (Gemini)": "Canlı (Gemini)",
    "Live transcript mode": "Canlı yazı modu",
    "Smart": "Akıllı",
    "Verbatim": "Birebir",
    "Smart removes filler words while you speak. Verbatim keeps "
    "every word, including fillers.": "Akıllı, konuşurken dolgu kelimelerini temizler. "
    "Birebir, dolgular dahil her kelimeyi aynen tutar.",
    "Live uses {model}; it cannot be changed. The model under "
    "Transcript cleanup tidies the text afterwards.":
        "Canlı, {model} kullanır; değiştirilemez. Ardından metni, "
        "\"Transkripti temizleme\" altındaki model düzenler.",
    "Sound wave style": "Ses dalgası biçimi",
    "Bars": "Çubuklar",
    "Spectrum": "Frekans",
    "Wave": "Dalga",
    "Capsules": "Kapsüller",
    "How the sound wave is drawn on the recording indicator. "
    "Spectrum and Capsules glow as you speak louder; Wave is a single "
    "flowing line.":
        "Ses dalgasının kayıt göstergesinde nasıl çizileceği. Frekans ve "
        "Kapsüller yüksek sesle konuştukça parlar; Dalga tek akıcı çizgidir.",
    "Live transcription stops at 8 minutes.": "Canlı yazı 8 dakikada durur.",
    "Connecting to live transcription…": "Canlı yazıya bağlanılıyor…",
    "Finishing live transcription…": "Canlı yazı tamamlanıyor…",
    "Unexpected error: {error}": "Beklenmeyen hata: {error}",

    # --- audio / paste errors -----------------------------------------
    "Could not open the microphone.": "Mikrofon açılamadı.",
    "Could not open the microphone: {error}": "Mikrofon açılamadı: {error}",
    "The sound device stopped responding.": "Ses aygıtı yanıt vermeyi durdurdu.",
    "Could not start recording: {error}": "Kayıt başlatılamadı: {error}",
    "Could not start the system loopback": "Sistem ses döngüsü başlatılamadı",
    "Could not open the clipboard.": "Pano açılamadı.",
    "Could not copy to clipboard: {error}": "Panoya kopyalanamadı: {error}",
    "Could not copy to the clipboard.": "Panoya kopyalanamadı.",
    "Could not send the paste keystroke.": "Yapıştırma tuşu gönderilemedi.",
    "Unknown key: {key}": "Bilinmeyen tuş: {key}",
    "Could not send the paste keystroke: {error}": "Yapıştırma tuşu gönderilemedi: {error}",
    "Paste failed: {error}": "Yapıştırma başarısız: {error}",

    # --- api errors ----------------------------------------------------
    "{service} API key is empty. Add it in Settings.":
        "{service} API anahtarı boş. Ayarlar'dan gir.",
    "Gemini API key is empty. Add it in Settings.":
        "Gemini API anahtarı boş. Ayarlar'dan gir.",
    "Transcript came back empty.": "Transkript boş döndü.",
    "The cleanup model returned an empty reply.": "Temizleme modeli boş yanıt döndü.",
    "Gemini returned no candidates.": "Gemini yanıt döndürmedi.",
    "Gemini returned an empty reply.": "Gemini boş yanıt döndürdü.",
    "Could not connect: {reason}": "Bağlantı kurulamadı: {reason}",
    "Could not parse the response: {error}": "Yanıt çözümlenemedi: {error}",
    "The selected Gemini model is unavailable. Open Settings and choose gemini-3.5-flash-lite or gemini-3.6-flash.":
        "Seçili Gemini modeli kullanılamıyor. Ayarlar'ı açıp gemini-3.5-flash-lite veya gemini-3.6-flash seçin.",
    "Gemini did not provide a file upload URL.": "Gemini dosya yükleme adresi vermedi.",
    "Gemini returned an invalid uploaded file.": "Gemini geçersiz bir yüklenen dosya yanıtı verdi.",
    "Gemini could not process the uploaded audio file.": "Gemini yüklenen ses dosyasını işleyemedi.",
    "Gemini did not finish processing the uploaded audio file.": "Gemini ses dosyasını zamanında işleyemedi.",

    # --- settings: tabs and general ------------------------------------
    "WordArc Settings": "WordArc Ayarları",
    "General": "Genel",
    "API and models": "API ve modeller",
    "Cleanup rules": "Temizleme kuralları",
    "Audio file": "Ses dosyası",
    "Shortcut": "Kısayol",
    "The key that starts and stops dictation.":
        "Dikteyi başlatıp durduran tuş.",
    "Where your voice comes in.": "Sesin nereden girdiği.",
    "Where the finished text goes.": "Bitmiş metnin nereye gittiği.",
    "How long a recording may run, and what is kept.":
        "Kaydın süresi ve nelerin saklandığı.",
    "An optional second pass that tidies the transcript.":
        "Transkripti toparlayan isteğe bağlı ikinci tur.",
    "Advanced": "Gelişmiş",
    "History": "Geçmiş",
    "Save": "Kaydet",
    "Theme": "Tema",
    "Tasks": "Görevler",
    "Records": "Kayıtlar",
    "Common": "Ortak",
    "Shared AI": "Ortak AI",
    "Settings": "Ayarlar",
    "Application": "Uygulama",
    "Search settings…": "Ayarlarda ara…",
    "No settings found": "Eşleşen ayar bulunamadı",
    "Record, transcribe and paste spoken text.":
        "Konuşmayı kaydedin, yazıya çevirin ve yapıştırın.",
    "Review and control locally stored transcripts.":
        "Yerelde saklanan dökümleri inceleyin ve yönetin.",
    "Gemini access and models shared by every task.":
        "Bütün görevlerin kullandığı Gemini erişimi ve modeller.",
    "Language, startup and appearance behavior.":
        "Dil, başlangıç ve görünüm davranışı.",
    "Open shared AI settings": "Ortak AI ayarlarını aç",
    "Transcription: {transcribe} · Cleanup: {cleanup}":
        "Transkripsiyon: {transcribe} · Temizleme: {cleanup}",
    "System instruction shared by dictation and optional agent or meeting cleanup.":
        "Dikte ile isteğe bağlı ajan ve toplantı temizlemesinin ortak sistem talimatı.",
    "Names and terms": "İsimler ve terimler",
    "Permissions are chosen separately for every command.":
        "İzinler her komut için ayrıca seçilir.",
    "Write access is chosen separately for every command.":
        "Yazma erişimi her komut için ayrıca seçilir.",
    "Audio file cleanup instruction": "Ses dosyası temizleme talimatı",
    "Store dictation and agent history on this computer":
        "Dikte ve ajan geçmişini bu bilgisayarda sakla",
    "Start": "Başlatma",
    "Sound": "Ses",
    "Output": "Çıktı",
    "Recording": "Kayıt",
    "Cleanup": "Temizleme",
    "Gemini": "Gemini",
    "Interface": "Arayüz",
    "Startup": "Başlangıç",
    "Support": "Destek",
    "Storage": "Saklama",
    "Options": "Seçenekler",
    "Agent instruction": "Ajan talimatı",
    "Minutes instruction": "Tutanak talimatı",
    "Cleanup instruction": "Temizleme talimatı",
    "Start WordArc when Windows starts":
        "Windows başladığında WordArc'ı başlat",
    "Starts WordArc for this Windows user without administrator permission.":
        "WordArc'ı yönetici izni istemeden bu Windows kullanıcısı için başlatır.",
    "Keep running in the system tray when the window is closed":
        "Pencere kapatıldığında sistem tepsisinde çalışmaya devam et",
    "When disabled, the title-bar close button, Escape and Alt+F4 quit WordArc.":
        "Kapalıyken başlık çubuğundaki X, Escape ve Alt+F4 WordArc'ı tamamen kapatır.",
    "API keys": "API anahtarları",
    "Add API": "API ekle",
    "Edit API": "API'yi düzenle",
    "Edit": "Düzenle",
    "Remove": "Kaldır",
    "Move up": "Yukarı taşı",
    "Move down": "Aşağı taşı",
    "Gemini API key": "Gemini API anahtarı",
    "This API key is already listed.": "Bu API anahtarı zaten listede.",
    "last used: {when}": "son kullanım: {when}",
    "not used yet": "henüz kullanılmadı",
    "API {used} did not respond; trying API {number}...":
        "API {used} yanıt vermedi; API {number} deneniyor...",
    "All configured Gemini APIs failed.":
        "Yapılandırılmış tüm Gemini API'leri başarısız oldu.",
    "All configured Gemini APIs failed. Last error: {error}":
        "Yapılandırılmış tüm Gemini API'leri başarısız oldu. Son hata: {error}",
    "Store dictation history on this computer":
        "Dikte geçmişini bu bilgisayarda sakla",
    "  ·  legacy Agent record: {question}":
        "  ·  eski Ajan kaydı: {question}",
    "System instruction shared by dictation and optional meeting cleanup.":
        "Dikte ile isteğe bağlı toplantı temizlemesinin ortak sistem talimatı.",
    "Dark": "Koyu",
    "Light": "Açık",
    "Core behavior, audio input and appearance.":
        "Temel davranış, ses girişi ve görünüm.",
    "Gemini credentials and model choices.":
        "Gemini kimlik bilgileri ve model seçimleri.",
    "Control how spoken text is polished.":
        "Konuşma metninin nasıl düzenleneceğini belirleyin.",
    "Run spoken requests with explicit permissions.":
        "Sesli istekleri açık izinlerle çalıştırın.",
    "Capture microphone and system audio reliably.":
        "Mikrofon ve sistem sesini güvenilir biçimde kaydedin.",
    "Capture a screen region or the full display, then copy or save it.":
        "Ekranın bir bölgesini veya tamamını yakalayın; ardından kopyalayın ya da kaydedin.",
    "Select a screen region or capture the whole display.":
        "Ekranın bir bölgesini seçin veya tamamını yakalayın.",
    "Select a region or capture the active screen.":
        "Bir alan seçin veya etkin ekranı yakalayın.",
    "Capture a region on the active screen, then copy or save it.":
        "Etkin ekranda alan seçin, ardından kopyalayın veya kaydedin.",
    "Capture and save a screenshot from the active screen.":
        "Etkin ekrandan görüntü alın ve kaydedin.",
    "Capture this screen": "Bu ekranı yakala",
    "Capture active window": "Etkin pencereyi yakala",
    "Capture a region, write on it, then copy or save it.":
        "Bölge seç, üzerine yaz, sonra kopyala ya da kaydet.",
    "Pen": "Kalem",
    "Line": "Çizgi",
    "Arrow": "Ok",
    "Rectangle": "Dikdörtgen",
    "Ellipse": "Elips",
    "Highlight": "Vurgu",
    "Step": "Adım",
    "Blur": "Bulanık",
    "Pixelate": "Mozaik",
    "Width": "Kalınlık",
    "Fill": "Dolu",
    "Redo": "Yinele",
    "Edit text": "Metni düzenle",
    "Font": "Yazı tipi",
    "Size": "Boyut",
    "Bold": "Kalın yazı",
    "Italic": "Eğik",
    "Underline": "Altı çizili",
    "No active window is available for capture.": "Yakalanacak etkin pencere bulunamadı.",
    "Choose where new screenshots are saved by default.":
        "Yeni ekran görüntülerinin kaydedileceği varsayılan konumu seçin.",
    "Leave empty to use the Pictures/WordArc folder.":
        "Boş bırakırsanız Resimler/WordArc klasörü kullanılır.",
    "Screenshot": "Ekran görüntüsü",
    "Capture and save a screenshot.": "Ekran görüntüsü alın ve kaydedin.",
    "Screenshot failed: {error}": "Ekran görüntüsü alınamadı: {error}",
    "Screenshots": "Ekran görüntüleri",
    "PNG image (*.png)": "PNG görüntüsü (*.png)",
    "JPEG image (*.jpg *.jpeg)": "JPEG görüntüsü (*.jpg *.jpeg)",
    "Screenshot options": "Ekran görüntüsü ayarları",
    "Capture": "Yakalama",
    "Capture screenshot": "Ekran görüntüsü al",
    "Capture shortcut": "Ekran görüntüsü kısayolu",
    "Press shortcut keys…": "Kısayol tuşlarına basın…",
    "Press the keys now…": "Şimdi tuşlara bas…",
    "Press Save to apply.": "Etkinleştirmek için Kaydet'e bas.",
    "Clear": "Temizle",
    "Windows reserves this combination: {shortcut}":
        "Windows bu kombinasyonu kullanıyor: {shortcut}",
    "This key combination cannot be assigned.":
        "Bu tuş kombinasyonu atanamıyor.",
    "Select area…": "Alan seç…",
    "Capture full screen": "Tüm ekranı yakala",
    "Select screenshot area": "Ekran görüntüsü alanını seçin",
    "Extract text (OCR)": "Metni ayıkla (OCR)",
    "Updates": "Güncellemeler",
    "Newer versions of WordArc.": "WordArc'ın yeni sürümleri.",
    "Check for updates": "Güncellemeleri denetle",
    "Download and install": "İndir ve kur",
    "Running version {version}.": "Kullanılan sürüm: {version}.",
    "Up to date — version {version}. Last check: {time}.": "Güncel — sürüm {version}. Son denetim: {time}.",
    "Checking…": "Denetleniyor…",
    "New version {version} is ready to download ({size} MB).": "Yeni sürüm {version} indirmeye hazır ({size} MB).",
    "You are on the newest version ({version}).": "En yeni sürümdesin ({version}).",
    "Downloading update… {done} / {total} MB": "Güncelleme iniyor… {done} / {total} MB",
    "Verifying the download…": "İndirilen dosya doğrulanıyor…",
    "Version {version} is ready. WordArc will restart to finish.": "{version} sürümü hazır. Bitirmek için WordArc yeniden başlayacak.",
    "Update available": "Güncelleme var",
    "Version {version} is out. Check it from Settings ▸ Updates.": "{version} sürümü çıktı. Ayarlar ▸ Güncellemeler bölümünden denetleyebilirsin.",
    "Updates are only available in the installed program.": "Güncelleme yalnız kurulu programda çalışır.",
    "Could not check for updates": "Güncelleme denetlenemedi",
    "Update": "Güncelleme",
    "Version {version} downloaded. WordArc is restarting.": "{version} indirildi. WordArc yeniden başlıyor.",
    "Update failed": "Güncelleme başarısız",
    "Update server could not be reached.": "Güncelleme sunucusuna ulaşılamadı.",
    "The update server returned an invalid response.": "Güncelleme sunucusu geçersiz yanıt verdi.",
    "Could not check for updates. Please try again.": "Güncellemeler denetlenemedi. Lütfen yeniden deneyin.",
    "Update check timed out. Please try again.": "Güncelleme denetimi zaman aşımına uğradı. Lütfen yeniden deneyin.",
    "The update download was interrupted.": "Güncelleme indirmesi yarıda kesildi.",
    "The download ended before the file was complete.": "İndirme dosya tamamlanmadan bitti.",
    "The checksum of the downloaded file does not match.": "İndirilen dosyanın sağlama toplamı uyuşmuyor.",
    "The newest release has no {asset} asset.": "Yayınlanan en yeni sürümde {asset} dosyası yok.",
    "Version number not understood: {version}": "Sürüm numarası anlaşılamadı: {version}",
    "No readable text found in the capture.":
        "Alınan görüntüde okunabilir metin bulunamadı.",
    "Text extracted — copied to the clipboard.":
        "Metin ayıklandı — panoya kopyalandı.",
    "Could not read text from the capture.":
        "Alınan görüntüden metin okunamadı.",
    "Drag to select · Esc to cancel": "Alanı seçmek için sürükleyin · İptal için Esc",
    "Drag handles to adjust · double-click to confirm":
        "Kenar tutamaçlarıyla ayarlayın · onaylamak için çift tıklayın",
    "Copy image": "Görüntüyü kopyala",
    "Save image…": "Görüntüyü kaydet…",
    "Save screenshot": "Ekran görüntüsünü kaydet",
    "PNG image (*.png);;JPEG image (*.jpg *.jpeg)":
        "PNG görüntüsü (*.png);;JPEG görüntüsü (*.jpg *.jpeg)",
    "Could not write the image file.": "Görüntü dosyası yazılamadı.",
    "No screen is available for capture.": "Yakalanabilecek ekran bulunamadı.",
    "Windows could not capture the screen.": "Windows ekran görüntüsünü alamadı.",
    "Screen has an invalid size.": "Ekran boyutu geçersiz.",
    "Select an area at least 2 × 2 pixels.": "En az 2 × 2 piksellik bir alan seçin.",

    "Choose folder…": "Klasör seç…",
    "Choose screenshot folder": "Ekran görüntüsü klasörünü seçin",
    "Save folder": "Kayıt klasörü",
    "Image format": "Görüntü biçimi",
    "Review and retry meeting summaries.":
        "Toplantı özetlerini inceleyin ve yeniden deneyin.",
    "Transcribe an existing recording.":
        "Var olan bir kaydı yazıya çevirin.",
    "Choose global keyboard shortcuts.":
        "Genel klavye kısayollarını seçin.",
    "Control local plaintext transcript retention.":
        "Yerel açık metin döküm saklamayı yönetin.",
    "Settings saved": "Ayarlar kaydedildi",
    "Interface language": "Arayüz dili",
    "Automatic (system)": "Otomatik (sistem)",
    "Turkish": "Türkçe",
    "English": "İngilizce",
    "Applies as soon as you save: the window is rebuilt in that language.":
        "Kaydettiğin anda geçerli olur: pencere o dilde yeniden kurulur.",
    "Microphone": "Mikrofon",
    "Default microphone": "Varsayılan mikrofon",
    "Built-in": "Dahili",
    "Speech language": "Konuşma dili",
    "Detect automatically": "Otomatik algıla",
    "German": "Almanca",
    "French": "Fransızca",
    "Spanish": "İspanyolca",
    "Arabic": "Arapça",
    "Paste the text into the focused window": "Metni odaktaki pencereye yapıştır",
    "Paste key": "Yapıştırma tuşu",
    "Terminals usually want Ctrl+Shift+V. Change this if pasting does nothing.":
        "Terminaller genelde Ctrl+Shift+V ister. Yapıştırma çalışmıyorsa bunu değiştir.",
    "Restore the previous clipboard after pasting":
        "Yapıştırdıktan sonra eski pano içeriğini geri koy",
    "Indicator corner": "Gösterge köşesi",
    "bottom-left": "sol-alt",
    "bottom-right": "sağ-alt",
    "top-left": "sol-üst",
    "top-right": "sağ-üst",
    "Longest recording": "En uzun kayıt",
    " s": " sn",
    "Skip silent recordings (don't call the API)":
        "Sessiz kayıtları atla (API'ye gönderme)",
    "Silence threshold": "Sessizlik eşiği",
    "Keep audio files (%LOCALAPPDATA%\\WordArc\\recordings)":
        "Ses kayıtlarını sakla (%LOCALAPPDATA%\\WordArc\\recordings)",

    # --- settings: api --------------------------------------------------
    "Keys": "Anahtarlar",
    "Speech to text": "Sesi yazıya çevirme",
    "Transcript cleanup": "Transkripti temizleme",
    "API key": "API anahtarı",
    "Model": "Model",
    "AIza… (falls back to GEMINI_API_KEY)": "AIza… (boşsa GEMINI_API_KEY kullanılır)",
    "Google Gemini": "Google Gemini",
    "Test": "Test et",
    "Trying…": "Deneniyor…",
    "Connection works. {count} models visible.":
        "Bağlantı tamam. {count} model görünüyor.",
    "Clean the transcript with a model": "Transkripti bir modelle temizle",
    "Thinking": "Düşünme",
    "Model's own default": "Modelin kendi varsayılanı",
    "Off": "Kapalı",
    "Minimal": "En az",
    "Low": "Düşük",
    "Medium": "Orta",
    "High": "Yüksek",
    "Very high": "Çok yüksek",
    "Maximum": "En yüksek",
    "How long a thinking model may reason before it answers. Cleanup is a light "
    "job, so more thinking mostly costs time and tokens. Models that cannot "
    "think ignore this.":
        "Düşünebilen bir modelin yanıtlamadan önce ne kadar düşüneceği. Temizleme "
        "hafif bir iş, fazla düşünmenin çoğunlukla getirisi süre ve token. "
        "Düşünemeyen modeller bunu yok sayar.",
    "Fetch model list": "Model listesini çek",
    "Fetching model list…": "Model listesi çekiliyor…",
    "Could not fetch the list: {error}": "Liste alınamadı: {error}",
    "{count} models loaded.": "{count} model yüklendi.",
    "Key works, no spending limit set.": "Anahtar çalışıyor, harcama sınırı yok.",
    "Key works. Used {usage} of {limit}.":
        "Anahtar çalışıyor. {limit} sınırının {usage} kadarı kullanılmış.",

    # --- settings: prompt ------------------------------------------------
    "System instruction given to the cleanup model. This is where you decide "
    "how much it may touch your words.":
        "Temizleme modeline verilen sistem talimatı. Ne kadar müdahale edeceğini "
        "burada belirlersin.",
    "Dictation": "Dikte",
    "Used instead when an audio or video file is cleaned up. It is written for "
    "subtitles: lines stay where they are, nothing is shortened, and misheard "
    "words are repaired from the context.":
        "Bir ses ya da video dosyası temizlenirken bunun yerine bu kullanılır. "
        "Altyazı için yazılmıştır: satırlar yerinde kalır, hiçbir şey kısaltılmaz, "
        "yanlış duyulan kelimeler bağlamdan düzeltilir.",
    "Reset to default": "Varsayılana döndür",
    "Names and terms you say often (optional). They go to the transcription "
    "model as a hint, and to the cleanup model as a glossary, so it can repair "
    "the ones that still come out wrong.":
        "Sık kullandığın isimler ve terimler (isteğe bağlı). Transkripsiyon "
        "modeline ipucu, temizleme modeline sözlük olarak gider; böylece yanlış "
        "çıkanları düzeltebilir.",

    # --- settings: audio file --------------------------------------------
    "Transcribe an existing audio or video file with the same models.":
        "Var olan bir ses ya da video dosyasını aynı modellerle yazıya çevir.",
    "Choose file…": "Dosya seç…",
    "No file selected": "Dosya seçilmedi",
    "Select an audio file": "Bir ses dosyası seç",
    "Audio and video files": "Ses ve video dosyaları",
    "All files": "Tüm dosyalar",
    "Add timestamps": "Zaman damgası ekle",
    "Prefixes every chunk with [mm:ss], so the transcript can be "
    "saved as subtitles (.srt).":
        "Her parçanın başına [dd:ss] koyar, transkript altyazı (.srt) "
        "olarak kaydedilebilir.",
    "The selected file no longer exists.": "Seçili dosya artık yok.",
    "No speech was heard on {sides}. The recording is kept.":
        "{sides} tarafında hiç konuşma duyulmadı. Kayıt saklanıyor.",
    "The audio held no recognisable speech. The recording is kept.":
        "Seste tanınabilir konuşma yoktu. Kayıt saklanıyor.",
    "Unnamed audio device": "Adsız ses aygıtı",
    "Language": "Dil",
    "Error": "Hata",
    "Run the cleanup model afterwards": "Sonrasında temizleme modelinden geçir",
    "With its own rules, under Cleanup rules: written for subtitles, so the "
    "lines keep their place and nothing is shortened.":
        "Kendi kurallarıyla, Temizleme kuralları sekmesinin altında: altyazı için "
        "yazılmıştır, satırlar yerinde kalır ve hiçbir şey kısaltılmaz.",
    "Transcribe": "Yazıya çevir",
    "Stop": "Durdur",
    "Stop reading": "Okumayı durdur",
    "Copy": "Panoya kopyala",
    "Save as .txt": "'.txt' olarak kaydet",
    "Save as .srt": "'.srt' olarak kaydet",
    "Subtitles, timed from the segments. Needs the timestamps option.":
        "Altyazı; zamanlaması bölüm damgalarından gelir. Zaman damgası seçeneği "
        "işaretliyken çalışır.",
    "No timestamped lines to turn into subtitles.":
        "Altyazıya çevrilecek zaman damgalı satır yok.",
    "Save transcript": "Transkripti kaydet",
    "Pick an audio or video file to transcribe.":
        "Yazıya çevrilecek ses veya video dosyasını seç.",
    "How the transcript should look.": "Transkriptin nasıl görüneceği.",
    "The finished text.": "Bitmiş metin.",
    "Your Gemini API keys, used one after another.":
        "Gemini API anahtarları sırayla kullanılır.",
    "The local model {name} is not installed yet. Download it in Settings.":
        "{name} modeli henüz kurulu değil. Ayarlar'dan indir.",
    "The local speech engine is missing. Reinstall WordArc to get it back.":
        "Yerel ses motoru eksik. Geri gelmesi için WordArc'ı yeniden kur.",
    "The download helper is missing. Reinstall WordArc to get it back.":
        "İndirme yardımcısı eksik. Geri gelmesi için WordArc'ı yeniden kur.",
    "Could not load the local model: {error}":
        "Yerel model yüklenemedi: {error}",
    "Unknown local model: {name}": "Bilinmeyen yerel model: {name}",
    "Local transcription failed: {error}":
        "Yerel yazıya çevirme başarısız: {error}",
    "The recording was empty.": "Kayıt boştu.",
    "The local model reads {rate} kHz audio, but this recording is {actual} kHz.":
        "Yerel model {rate} kHz ses okur, ama bu kayıt {actual} kHz.",
    "The local model reads 16-bit audio.": "Yerel model 16 bit ses okur.",
    "The model that turns speech into text.":
        "Konuşmayı yazıya çeviren model.",
    "Local model": "Yerel model",
    "Cloud model": "Bulut modeli",
    "Cloud (Gemini)": "Bulut (Gemini)",
    "Local (this computer)": "Yerel (bu bilgisayar)",
    "Download": "İndir",
    "quick, 141 MB": "hızlı, 141 MB",
    "middle, 464 MB": "orta, 464 MB",
    "hardest audio, 1,5 GB": "en zor ses, 1,5 GB",
    "Local transcribes on this computer and sends no audio anywhere. "
    "Cloud and Live use Gemini and need an API key: Cloud types up a "
    "recording after it ends, Live streams your speech as you speak "
    "and shows the words while you are still talking.":
        "Yerel, sesi bu bilgisayarda yazıya çevirir ve hiçbir yere göndermez. "
        "Bulut ve Canlı, Gemini kullanır ve API anahtarı ister: Bulut, kayıt "
        "bittikten sonra yazıya çevirir; Canlı ise konuşurken akıtır ve "
        "kelimeleri sen daha konuşurken gösterir.",
    "Measured on Turkish dictation. base is quick and the smallest download; "
    "small is in between; large-v3-turbo reads hardest audio most reliably and "
    "never invents a closing sentence.":
        "Türkçe dikte üzerinde ölçüldü. base hızlı ve indirmesi en küçük; small "
        "arasında; large-v3-turbo en zor sesi en güvenilir okur ve kapanış "
        "cümlesi uydurmaz.",
    "{name} is installed ({size}) and ready.":
        "{name} kurulu ({size}) ve hazır.",
    "{name} is not downloaded yet — {size}. Downloaded once, it works "
    "offline after that.":
        "{name} henüz indirilmedi — {size}. Bir kez indirildikten sonra "
        "internetsiz de çalışır.",
    "Downloading {name}…": "{name} indiriliyor…",
    "Automatic": "Otomatik",
    "Device": "Cihaz",
    "Install": "Kur",
    "Installing…": "Kuruluyor…",
    "Automatic uses the Nvidia GPU when its driver and CUDA runtime "
    "answer, otherwise the CPU. Forcing Nvidia GPU fails with a clear "
    "message when CUDA is missing instead of silently using the CPU.":
        "Otomatik, sürücüsü ve CUDA çalışması yanıt veren Nvidia GPU'yu "
        "kullanır, yoksa CPU'ya geçer. Nvidia GPU'ya zorlamak, CUDA yokken "
        "sessizce CPU'ya geçmek yerine açık bir hata verir.",
    "The local engine needs {packages}. Install them "
    "automatically and continue with the setup?":
        "Yerel motor için {packages} gerekli. Otomatik kurulup kuruluma "
        "devam edilsin mi?",
    "GPU support is not downloaded yet. Install it from Settings, Speech "
    "to text, or switch the device to Automatic.":
        "GPU desteği henüz indirilmedi. Ayarlar, Ses ve modellerden kurun "
        "ya da cihazı Otomatik'e alın.",
    "GPU support ({size}) is not installed yet. Download it "
    "first, then the {name} model? Answering No downloads "
    "only the model for CPU use.":
        "GPU desteği ({size}) henüz kurulu değil. Önce o, sonra {name} "
        "modeli indirilsin mi? Hayır derseniz yalnız model iner, CPU ile "
        "kullanılır.",
    "{name} is installed ({size}) and ready. GPU support "
    "({cuda_size}) can be downloaded; until then the model "
    "runs on CPU.":
        "{name} kurulu ({size}) ve hazır. GPU desteği ({cuda_size}) "
        "indirilebilir; o zamana kadar model CPU ile çalışır.",
    "GPU support ready.": "GPU desteği hazır.",
    "GPU support": "GPU desteği",
    "GPU support has no verified build yet.":
        "GPU desteğinin doğrulanmış yapısı henüz yok.",
    "The GPU support file is damaged. Try again.":
        "GPU desteği dosyası bozuk. Yeniden deneyin.",
    "The GPU support file is incomplete. Try again.":
        "GPU desteği dosyası eksik. Yeniden deneyin.",
    "Nvidia GPU was requested, but no usable CUDA device was "
    "found. Check the driver and the CUDA runtime, or switch the "
    "device back to Automatic.":
        "Nvidia GPU istendi, ama kullanılabilir CUDA cihazı bulunamadı. "
        "Sürücüyü ve CUDA çalışmasını denetle ya da cihazı Otomatik'e al.",
    "Could not install the local speech engine: {error}":
        "Yerel ses motoru kurulamadı: {error}",
    "Could not download {name}: {error}": "{name} indirilemedi: {error}",
    "Delete the downloaded {name} model? {size} goes back to the disk. "
    "Nothing else is touched.":
        "İndirilen {name} modeli silinsin mi? {size} diskte yerine geri "
        "gelir. Başka hiçbir şeye dokunulmaz.",
    "The model that tidies transcripts.": "Transkripti toparlayan model.",
    "Words the models should spell right.":
        "Modellerin doğru yazması gereken kelimeler.",
    "Language and appearance.": "Dil ve görünüm.",
    "What happens when Windows and WordArc start.":
        "Windows ve WordArc açıldığında ne olacağı.",
    "When something breaks.": "Bir şey bozulduğunda.",
    "Text files": "Metin dosyaları",
    "Subtitle files": "Altyazı dosyaları",
    "Converting audio…": "Ses dönüştürülüyor…",
    "Splitting into {count} chunks…": "{count} parçaya bölünüyor…",
    "Transcribing chunk {index}/{count}…": "{index}/{count} parça yazıya çevriliyor…",
    "Done: {chars} characters.": "Bitti: {chars} karakter.",
    "Stopped.": "Durduruldu.",
    "Waiting for permission…": "İzin bekleniyor…",
    "Agent permission": "Ajan izni",
    "How may the agent handle this command?": "Ajan bu komutu nasıl ele alabilir?",
    "Read only": "Salt okunur",
    "Allow changes once": "Değişikliklere bir kez izin ver",
    "Choose a valid working directory in Settings before allowing changes.":
        "Değişiklik izni vermeden önce Ayarlar'dan geçerli bir çalışma klasörü seçin.",
    "Failed: {error}": "Başarısız: {error}",
    "ffmpeg not found. Install it to transcribe files.":
        "ffmpeg bulunamadı. Dosya çevirmek için kur.",
    "Could not read the file: {error}": "Dosya okunamadı: {error}",
    "Saved: {path}": "Kaydedildi: {path}",

    # --- settings: shortcut ------------------------------------------------
    "Install as a Windows shortcut": "Windows kısayolu olarak kur",
    "Remove": "Kaldır",
    "Active shortcut: {shortcut}": "Etkin kısayol: {shortcut}",
    "No shortcut set.": "Kısayol yok.",
    "Works the moment you save — no logout needed. The key does not reach the "
    "focused application.":
        "Kaydeder kaydetmez çalışır — oturumu yenilemek gerekmez. Tuş odaktaki "
        "uygulamaya iletilmez.",
    "The shortcut is registered with Windows and takes effect immediately.":
        "Kısayol Windows'a kaydedilir ve anında etkili olur.",
    "Shortcut conflict": "Kısayol çakışması",
    "{shortcut} is assigned to both {first} and {second}.":
        "{shortcut}, hem {first} hem de {second} için atanmış. Farklı tuşlar seçin.",
    "{shortcut} is also used by:\n\n{list}\n\nInstall anyway?":
        "{shortcut} şu girdilerde de kullanılıyor:\n\n{list}\n\nYine de kurulsun mu?",
    "Shortcut saved: {shortcut}\nKWin only reads this file at startup, so it "
    "will not fire until you log out and back in. To use it right away, turn on "
    "the built-in listener.":
        "Kısayol kaydedildi: {shortcut}\nKWin bu dosyayı yalnızca açılışta okuduğu için "
        "oturumu yeniden açana kadar tetiklenmez. Hemen kullanmak istersen "
        "yerleşik dinleyiciyi aç.",
    "Could not parse the shortcut: {shortcut}": "Kısayol çözümlenemedi: {shortcut}",
    "Could not register the shortcut. Another program may already be using it: {shortcut}":
        "Kısayol kaydedilemedi. Başka bir program kullanıyor olabilir: {shortcut}",

    # --- settings: history --------------------------------------------------
    "Copy selected to clipboard": "Seçiliyi panoya kopyala",
    "Delete selected": "Seçiliyi sil",
    "Clear history": "Geçmişi temizle",
    "Store dictation history on this computer": "Dikte geçmişini bu bilgisayarda sakla",
    "Open diagnostics folder": "Tanılama klasörünü aç",
    "Meeting minutes and transcripts are stored as readable text files under %LOCALAPPDATA%\\WordArc\\meetings.":
        "Toplantı tutanakları ve dökümleri %LOCALAPPDATA%\\WordArc\\meetings altında okunabilir metin dosyaları olarak saklanır.",
    "Reload": "Yenile",
    "{ts}  ({duration} s)": "{ts}  ({duration} sn)",
    "Keep at most": "En fazla",
    " entries": " kayıt",
    "no limit": "sınırsız",
    "Once the history passes this many entries, the oldest one is dropped "
    "every time a new one arrives. Set it to 0 to keep everything.":
        "Geçmiş bu sayıyı aştıktan sonra, her yeni kayıt geldiğinde en eski kayıt "
        "silinir. Hepsini tutmak için 0 yaz.",
    "Delete the {count} selected entries?": "Seçili {count} kayıt silinsin mi?",
    "Delete the whole history? This cannot be undone.":
        "Geçmişin tamamı silinsin mi? Bu geri alınamaz.",

    # --- asking Claude Code -------------------------------------------------
    "Ask {name}": "{name} sor",
    "Stop and ask {name}": "Kaydı bitir ve {name} sor",
    "Start a new conversation": "Yeni konuşma başlat",
    "Start a new conversation now": "Şimdi yeni konuşma başlat",
    "Stop {name}": "{name} durdur",
    "Stopping…": "Durduruluyor…",
    "Stopped.": "Durduruldu.",
    "{name} starts fresh next time.": "{name} bir sonrakine sıfırdan başlayacak.",
    "WordArc: talking to {name}": "WordArc: {name} ile konuşuyor",
    "WordArc: recording for {name}": "WordArc: {name} için kaydediyor",
    "Asking {name}…": "{name} soruluyor…",
    "{name}: {preview}": "{name}: {preview}",
    "{name} answered, but: {error}": "{name} cevapladı, ama: {error}",
    "WordArc: {name} could not do all of it": "WordArc: {name} her şeyi yapamadı",
    "Running a command…": "Komut çalıştırıyor…",
    "Reading…": "Okuyor…",
    "Looking through files…": "Dosyalara bakıyor…",
    "Searching the files…": "Dosyalarda arıyor…",
    "Editing a file…": "Dosya düzenliyor…",
    "Writing a file…": "Dosya yazıyor…",
    "Searching the web…": "İnternette arıyor…",
    "Reading a web page…": "Web sayfası okuyor…",
    "Handing it to a subagent…": "Alt ajana devrediyor…",
    "Planning…": "Planlıyor…",
    "Using {name}…": "{name} kullanıyor…",
    "Thinking…": "Düşünüyor…",
    "{binary} not found. Install it, or pick another provider under "
    "Settings → Agent.":
        "{binary} bulunamadı. Kur ya da Ayarlar → Ajan sekmesinden başka bir "
        "sağlayıcı seç.",
    "Could not run {binary}: {error}": "{binary} çalıştırılamadı: {error}",
    "{service} exited with code {code}.": "{service} {code} koduyla çıktı.",
    "It did not finish within {seconds} seconds.":
        "{seconds} saniye içinde bitmedi.",
    "Claude ended with an error.": "Claude bir hatayla sonlandı.",
    "Codex ended with an error.": "Codex bir hatayla sonlandı.",
    "{service} answered with nothing.": "{service} boş cevap verdi.",
    "It was not allowed to use: {tools}": "Şunları kullanmasına izin yoktu: {tools}",
    "The model returned an empty reply.": "Model boş cevap döndürdü.",

    # --- settings: the agent ------------------------------------------------
    "Agent": "Ajan",
    "This shortcut records the same way dictation does, but the transcript is "
    "not what gets pasted. It goes to an agent as a command, and what comes "
    "back is pasted instead: the answer to a question, or a sentence saying "
    "what was done. Claude Code and Codex run as the session you would have "
    "opened yourself, with your skills, your connected services and your "
    "account.":
        "Bu kısayol dikte ile aynı şekilde kaydeder, ama yapıştırılan şey "
        "transkript değildir. Transkript bir ajana komut olarak gider ve yerine "
        "oradan döneni yapıştırılır: bir sorunun cevabı ya da ne yapıldığını "
        "söyleyen bir cümle. Claude Code ve Codex, kendi açacağın oturumun "
        "aynısı olarak çalışır: skill'lerinle, bağlı servislerinle ve kendi "
        "hesabınla.",
    "How it runs": "Nasıl çalışıyor",
    "Runs on": "Şunun üstünde çalışır",
    "Where it runs": "Nerede çalışsın",
    "More thinking is slower, and you are standing in front of the screen while "
    "it happens. Worth it for a job that has to be worked out rather than "
    "looked up.":
        "Daha çok düşünmek daha yavaştır ve bu sırada ekranın başında bekliyor "
        "olursun. Bakılıp bulunacak değil, çözülmesi gereken işler için değer.",
    "Claude Code": "Claude Code",
    "Codex": "Codex",
    "Codex's own default": "Codex'in kendi varsayılanı",
    "Sandbox": "Kum havuzu",
    "Read anything, write in the working directory":
        "Her şeyi okusun, çalışma dizinine yazsın",
    "Read only": "Yalnızca okusun",
    "No sandbox at all": "Kum havuzu hiç olmasın",
    "Needs no program installed, only an API key.":
        "Kurulu bir programa değil, yalnızca bir API anahtarına ihtiyaç duyar.",
    "{binary} is not on your PATH, so this cannot run yet. Install it, or pick "
    "another one above.":
        "{binary} PATH'te değil, dolayısıyla bu henüz çalışamaz. Kur ya da "
        "yukarıdan başka birini seç.",
    "The conversation": "Konuşma",
    "The answer": "Cevap",
    "Found: {path}": "Bulundu: {path}",
    "No shortcut set. The tray menu asks it too.":
        "Kısayol yok. Tepsi menüsünden de sorulabilir.",
    "A name like “sonnet” always means the newest model of that line. Opus "
    "thinks harder and answers slower, which is felt here more than anywhere "
    "else: you are standing in front of the screen.":
        "“sonnet” gibi bir ad her zaman o serinin en yenisini seçer. Opus daha "
        "çok düşünür ve daha geç cevaplar; bu da en çok burada hissedilir, "
        "çünkü ekranın başında bekliyorsun.",
    "Permissions": "İzinler",
    "Decide on its own, with the safety checks on":
        "Kendi karar versin, güvenlik denetimleri açık",
    "Allow everything": "Her şeye izin ver",
    "Only what needs no permission": "Yalnızca izin gerektirmeyenler",
    "Working directory": "Çalışma dizini",
    "Choose…": "Seç…",
    "The directory the command runs in, which decides which project's "
    "instructions and files it can see. Your own skills and services are there "
    "whichever one it is.":
        "Komutun içinde çalıştığı dizin; hangi projenin talimatlarını ve "
        "dosyalarını göreceğini bu belirler. Kendi skill'lerin ve servislerin "
        "hangi dizin olursa olsun oradadır.",
    "Give up after": "Şu süreden sonra vazgeç",
    "A command still running after this is given up on. The tray menu can stop "
    "one earlier.":
        "Bu süreden sonra hâlâ süren komuttan vazgeçilir. Tepsi menüsünden daha "
        "erken de durdurulabilir.",
    "Carry on for": "Şu kadar süre sürsün",
    "every command on its own": "her komut ayrı",
    "Commands within this long of each other are one conversation, so “and move "
    "that to Thursday” knows what “that” is. After it, the next command starts "
    "fresh.":
        "Birbirinden bu kadar süre içinde gelen komutlar tek bir konuşmadır; "
        "böylece “onu perşembeye al” dediğinde “o”nun ne olduğu bilinir. Bu "
        "sürenin ardından bir sonraki komut sıfırdan başlar.",
    "No conversation going.": "Süren bir konuşma yok.",
    "Last used {minutes} min ago.": "En son {minutes} dk önce kullanıldı.",
    "Paste it into the focused window": "Odaktaki pencereye yapıştır",
    "It is copied to the clipboard either way.": "Panoya her hâlükârda kopyalanır.",
    "Clean the transcript up before sending it": "Göndermeden önce transkripti temizle",
    "Off by default: Claude reads through “erm” and “you know” without help, "
    "and cleanup costs an API call and a second or two.":
        "Varsayılan olarak kapalı: Claude “eee” ve “hani”yi yardımsız da okur, "
        "temizlik ise bir API çağrısına ve bir iki saniyeye mal olur.",
    "Told to the agent alongside every command, on top of whatever your own "
    "configuration already says.":
        "Her komutla birlikte ajana söylenir, kendi yapılandırmanın zaten "
        "söylediklerinin üstüne eklenir.",
    "  ·  asked Claude: {question}": "  ·  Claude'a soruldu: {question}",

    # --- meetings: tray and pipeline ---------------------------------------
    "Record a meeting": "Toplantı kaydet",
    "End the meeting and write it up": "Toplantıyı bitir ve tutanağı çıkar",
    "Writing the meeting up…": "Tutanak çıkarılıyor…",
    "Discard the meeting": "Toplantıyı iptal et",
    "Ending the meeting…": "Toplantı bitiriliyor…",
    "WordArc: in a meeting": "WordArc: toplantıda",
    "WordArc: in a meeting ({time})": "WordArc: toplantıda ({time})",
    "WordArc: writing the meeting up": "WordArc: tutanak çıkarıyor",
    "Meeting recorded, writing it up…": "Toplantı kaydedildi, tutanak çıkarılıyor…",
    "Meeting written up: {title}": "Tutanak hazır: {title}",
    "WordArc: the meeting is written up": "WordArc: tutanak hazır",
    "Meeting failed: {error}": "Toplantı başarısız: {error}",
    "WordArc: the meeting could not be written up": "WordArc: tutanak çıkarılamadı",
    "{error}\n\nThe recording has been kept. Settings → Meeting can try again.":
        "{error}\n\nSes kaydı duruyor. Ayarlar → Toplantı üzerinden yeniden "
        "denenebilir.",
    "Recording saved. The previous meeting is still being written up, so start "
    "this one from Settings → Meeting when it is done.":
        "Kayıt saklandı. Önceki toplantının tutanağı hâlâ çıkarılıyor; bu kaydı o "
        "bitince Ayarlar → Toplantı üzerinden başlat.",
    "The recording stopped on its own; the sound device may have gone away. "
    "Keeping what was captured.":
        "Kayıt kendiliğinden durdu, ses aygıtı çekilmiş olabilir. O ana kadar "
        "kaydedilen saklanıyor.",
    "ffmpeg not found. Install it to record a meeting.":
        "ffmpeg bulunamadı. Toplantı kaydı için kur.",
    "Could not work out which speaker output to record. Pick one in "
    "Settings → Meeting.":
        "Hangi ses çıkışının kaydedileceği anlaşılamadı. Ayarlar → Toplantı "
        "sekmesinden seç.",
    "Nothing was recorded: {error}": "Hiçbir şey kaydedilmedi: {error}",
    "Transcribing {side}: {index}/{count}…":
        "{side} yazıya çevriliyor: {index}/{count}…",
    "you": "sen",
    "the others": "karşı taraf",
    "Cleaning up {index}/{count}…": "Temizleniyor {index}/{count}…",
    "Writing the minutes…": "Tutanak yazılıyor…",
    "Neither side of the recording had any speech in it.":
        "Kaydın iki tarafında da konuşma yok.",
    "This recording is not a two-channel meeting.":
        "Bu kayıt iki kanallı bir toplantı kaydı değil.",
    "The recording is gone: {path}": "Ses kaydı yerinde yok: {path}",
    "Meeting": "Toplantı",
    "Transcript": "Transkript",
    "{minutes} min": "{minutes} dk",
    "{hours} h {minutes} min": "{hours} sa {minutes} dk",

    # --- settings: meeting --------------------------------------------------
    "Minutes": "Tutanaklar",
    "Your microphone plus whatever comes out of your speakers.":
        "Mikrofonun ve hoparlörden çıkan ses birlikte.",
    "Labels for the two sides of the conversation.":
        "Konuşmanın iki tarafının etiketleri.",
    "The model that turns the transcript into minutes.":
        "Transkripti tutanağa çeviren model.",
    "How long a meeting may run, and what is kept.":
        "Toplantı süresi ve nelerin saklandığı.",
    "A meeting is recorded from two devices at once: your microphone and "
    "whatever comes out of your speakers. Nothing has to guess who was "
    "speaking, because the two never share a channel.":
        "Toplantı iki aygıttan aynı anda kaydedilir: mikrofonun ve hoparlöründen "
        "çıkan ses. Kimin konuştuğunun tahmin edilmesi gerekmez, çünkü ikisi hiç "
        "aynı kanala girmez.",
    "Sound": "Ses",
    "Same as dictation": "Diktedekiyle aynı",
    "Current output": "Geçerli çıkış",
    "Meeting audio source": "Toplantı ses kaynağı",
    "The other participants": "Karşı tarafın sesi",
    "Wear headphones if you can. Through speakers your microphone hears the "
    "other side as well, and although a line that lands on both channels at "
    "once is dropped again, the repair is never as clean as not needing it.":
        "Yapabiliyorsan kulaklık tak. Hoparlörde mikrofonun karşı tarafı da "
        "duyar; aynı anda iki kanala birden düşen satır ayıklanıyor ama bu "
        "onarım, hiç gerekmemesi kadar temiz olmuyor.",
    "Who is talking": "Kimler konuşuyor",
    "Me": "Ben",
    "Other side": "Karşı taraf",
    "You": "Sen",
    "The other end": "Karşı taraf",
    "Expected": "Beklenen kişiler",
    "One name per line": "Her satıra bir isim",
    "Everyone on the far end shares one label: they reach you as a single mixed "
    "signal. The names go to the transcription model so they come out spelled "
    "right, and to the minutes, which may use one for a line only when the "
    "conversation itself makes clear who was speaking.":
        "Karşı taraftaki herkes tek bir etiketi paylaşır; sana tek bir karışım "
        "olarak gelirler. İsimler, doğru yazılsınlar diye transkripsiyon modeline "
        "ve tutanağa gider; tutanak bir satıra ancak konuşmanın kendisi kimin "
        "konuştuğunu açık ediyorsa isim yazar.",
    "Unlike cleanup, this one is worth some thinking: it has to hold a whole "
    "meeting in its head and work out what was actually decided.":
        "Temizlemenin aksine burada düşünmenin karşılığı var: model bütün "
        "toplantıyı aklında tutup neyin gerçekten karara bağlandığını çıkarmak "
        "zorunda.",
    "Clean the transcript up first": "Önce transkripti temizle",
    "Runs the cleanup model over the transcript before the minutes are written, "
    "keeping the timestamps and the speaker labels.":
        "Tutanak yazılmadan önce transkripti temizleme modelinden geçirir; zaman "
        "damgaları ve konuşmacı etiketleri korunur.",
    "Recording": "Kayıt",
    " min": " dk",
    "Longest meeting": "En uzun toplantı",
    "Keep the recording after the minutes are written":
        "Tutanak çıktıktan sonra ses kaydını sakla",
    "A run that fails keeps its recording either way, so it can be tried again "
    "from the Meeting tab. This is about the ones that worked.":
        "Başarısız olan bir işlemin kaydı zaten saklanır, Toplantı sekmesinden "
        "yeniden denenebilsin diye. Buradaki ayar başarıyla bitenler için.",
    "none": "yok",
    "Type a key combination first.": "Önce bir tuş kombinasyonu yaz.",
    "No shortcut set. The tray menu starts a meeting too.":
        "Kısayol yok. Toplantıyı tepsi menüsünden de başlatabilirsin.",
    "System instruction given to the minutes model.":
        "Tutanak modeline verilen sistem talimatı.",
    "Pick a meeting to read it.": "Okumak için bir toplantı seç.",
    "Write it up": "Tutanağı çıkar",
    "Open the folder": "Klasörü aç",
    "waiting to be written up": "tutanak bekliyor",
    "transcript ready, minutes missing": "transkript hazır, tutanak eksik",
    "failed": "başarısız",
    "Nothing has been written yet.": "Henüz bir şey yazılmadı.",
    "Done: {title}": "Bitti: {title}",
    "This one is being written up right now.": "Bunun tutanağı şu anda çıkarılıyor.",
    "Delete this meeting, its minutes and its recording?":
        "Bu toplantı, tutanağı ve ses kaydı silinsin mi?",

    # --- ic tasarim + dil temizligi -----------------------------------
    "File": "Dosya",
    "Models, language, startup and appearance.":
        "Modeller, dil, başlangıç ve görünüm.",
    "Stored only in Windows Credential Manager.":
        "Yalnız Windows Kimlik Bilgisi Yöneticisi'nde saklanır.",
}

TR.update({
    "Latest dictation": "Son dikte", "Your next dictation appears here.": "Bir sonraki dikten burada görünecek.",
    "Ready": "Hazır", "Recording…": "Kaydediliyor…",
    "Artificial intelligence": "Yapay zekâ", "API keys": "API anahtarları", "Application": "Uygulama",
    "Search…": "Ara…", "Select": "Seç", "No matches": "Eşleşme bulunamadı",
})

TR["Copied raw, cleanup failed: {error}"] = "Ham metin kopyalandı, temizleme başarısız: {error}"

TR.update({
    "No dictation history yet.": "Henüz dikte geçmişi yok.",
    "No meetings yet.": "Henüz toplantı yok.",
    "Add an API key to use cloud models.": "Bulut modellerini kullanmak için API anahtarı ekle.",
})

TR.update({
    "Not enough disk space for the local model.": "Yerel model için yeterli disk alanı yok.",
    "Audio stays on this computer. Cleanup sends the text to Gemini when enabled.": "Ses bu bilgisayarda kalır. Temizleme açıkken metin Gemini’ye gönderilir.",
    "Audio stays on this computer. Cleanup is off; the raw transcript is used.": "Ses bu bilgisayarda kalır. Temizleme kapalı; ham metin kullanılır.",
    "Connecting…": "Bağlanıyor…", "Calculating…": "Hesaplanıyor…", "{seconds} s": "{seconds} sn",
    "{done} / {total} · {speed}/s · Remaining: {eta}": "{done} / {total} · {speed}/sn · Kalan: {eta}",
    "Verifying files…": "Dosyalar doğrulanıyor…", "Retrying connection…": "Bağlantı yeniden deneniyor…",
    "Download stopped. Press Download to resume.": "İndirme durduruldu. Devam etmek için İndir'e bas.",
    "Model ready: {name}": "Model hazır: {name}",
})

TR.update({
    "Academic English": "Akademik İngilizce",
    "Checking local speech device…": "Yerel ses aygıtı kontrol ediliyor…",
    "Could not check the local speech device.": "Yerel ses aygıtı kontrol edilemedi.",
    "Game English": "Oyun İngilizcesi",
    "Translating…": "Çevriliyor…",
    "Translate dictation to English": "Dikteyi İngilizceye çevir",
})

TR.update({
    # Reading aloud (Speak tab, EMA Lightning Turkish TTS).
    "Speak": "Seslendir",
    "Read Turkish text aloud with a small local voice.": "Türkçe metni küçük bir yerel sesle okut.",
    "Read aloud": "Sesli oku",
    "Save audio…": "Sesi kaydet…",
    "Format": "Biçim",
    "Speed": "Hız",
    "Reading aloud": "Sesli okuma",
    "Default format": "Varsayılan biçim",
    "Default speed": "Varsayılan hız",
    "Play automatically when ready": "Hazır olunca kendiliğinden çal",
    "Read-selection shortcut": "Seçimi okuma kısayolu",
    "Stop shortcut": "Durdurma kısayolu",
    "Model status": "Model durumu",
    "Reading part {done} of {total}…": "Bölüm okunuyor {done}/{total}…",
    "Reading stopped.": "Okuma durduruldu.",
    "There is no readable text.": "Okunacak metin yok.",
    "Downloading the Turkish voice model (~34 MB)…": "Türkçe ses modeli indiriliyor (~34 MB)…",
    "Voice model download failed.": "Ses modeli indirilemedi.",
    "Voice engine needs onnxruntime: {error}": "Ses motoru için onnxruntime gerekli: {error}",
    "Model download needs huggingface_hub: {error}": "Model indirmek için huggingface_hub gerekli: {error}",
    "Audio export failed: {error}": "Ses dışa aktarılamadı: {error}",
    "Reading finished: {name}": "Okuma bitti: {name}",
    "Voice model ready.": "Ses modeli hazır.",
    "Already reading…": "Zaten bir okuma sürüyor…",
    "Could not read the selection.": "Seçim okunamadı.",
    "Reading the selection…": "Seçim okunuyor…",
    "Recent readings": "Son okumalar",
    "No readings yet.": "Henüz okuma yok.",
    "Text to read": "Okunacak metin",
    "Reading…": "Okunuyor…",
    "Save audio": "Sesi kaydet",
    "Audio files": "Ses dosyaları",
    "Downloads on first read (~34 MB).": "İlk okumada indirilir (~34 MB).",
    "Turkish text-to-speech on the Speak tab.": "Sekmedeki Türkçe metin seslendirme.",
    "The Turkish text to read aloud.": "Sesli okunacak Türkçe metin.",
    "Audio files saved from this tab.": "Bu sekmeden kaydedilen ses dosyaları.",
    "PDF reading needs pymupdf.": "PDF okumak için pymupdf gerekli.",
    "Unsupported file type: {suffix}": "Desteklenmeyen dosya türü: {suffix}",
    "Reading file {done} of {total}: {name}": "Dosya okunuyor {done}/{total}: {name}",
    "Files": "Dosyalar",
    "Recent": "Son okumalar",
    "Text and PDF files to turn into audio, in order.": "Sese çevrilecek metin ve PDF dosyaları, sırayla.",
    "Add files…": "Dosya ekle…",
    "Convert all to audio": "Tümünü sese çevir",
    "Clear list": "Listeyi temizle",
    "Text and PDF files": "Metin ve PDF dosyaları",
    "Convert to audio and read": "Sese çevir ve oku",
    "Reading the capture…": "Görüntü okunuyor…",
    "Audio output timed out.": "Ses çıkışı zaman aşımına uğradı.",
})

# Per-language tables. English is the source language: no table needed,
# t() returns the source text. Every other language maps source -> translation.
# Tables filled in beyond Turkish are added by the 13-language rollout;
# a missing entry falls back to English at runtime (and fails release gate A).
def _merge(*parts):
    m = {}
    for p in parts:
        m.update(p or {})
    return m


TABLES = {
    "tr": TR,
    "de": _merge(_DE1, _DE2, _DE3, _DE4, _DE5, _DE6, _DE7),
    "es": _merge(_ES1, _ES2, _ES3, _ES4, _ES5, _ES6, _ES7),
    "fr": _merge(_FR1, _FR2, _FR3, _FR4, _FR5, _FR6, _FR7),
    "it": _merge(_IT1, _IT2, _IT3, _IT4, _IT5, _IT6, _IT7),
    "pt-BR": _merge(_PB1, _PB2, _PB3, _PB4, _PB5, _PB6, _PB7),
    "ru": _merge(_RU1, _RU2, _RU3, _RU4, _RU5, _RU6, _RU7),
    "pl": _merge(_PL1, _PL2, _PL3, _PL4, _PL5, _PL6, _PL7),
    "nl": _merge(_NL1, _NL2, _NL3, _NL4, _NL5, _NL6, _NL7),
    "zh-CN": _merge(_ZH1, _ZH2, _ZH3, _ZH4, _ZH5, _ZH6, _ZH7),
    "ja": _merge(_JA1, _JA2, _JA3, _JA4, _JA5, _JA6, _JA7),
    "ko": _merge(_KO1, _KO2, _KO3, _KO4, _KO5, _KO6, _KO7),
}
