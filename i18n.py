"""Tiny translation helper.

Source strings are English; Turkish translations live in the TR table below.
No gettext, no .mo files; the string table is small enough to keep in code.
"""

import os

_lang = "tr"


def resolve(code):
    """'auto' -> language guessed from the locale environment."""
    if code in ("tr", "en"):
        return code
    env = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
           or os.environ.get("LANG") or "")
    if not env:
        return "tr"
    return "tr" if env.lower().startswith("tr") else "en"


def set_language(code):
    global _lang
    _lang = resolve(code)


def language():
    return _lang


def t(text, **kwargs):
    out = TR.get(text, text) if _lang == "tr" else text
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
    # --- tray ---------------------------------------------------------
    "Start recording": "Kaydı başlat",
    "Stop and transcribe": "Kaydı bitir ve yaz",
    "Working…": "İşleniyor…",
    "Cancel recording": "Kaydı iptal et",
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
    "Unexpected error: {error}": "Beklenmeyen hata: {error}",

    # --- audio / paste errors -----------------------------------------
    "Could not open the microphone.": "Mikrofon açılamadı.",
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
    "Dictation and meetings — in one flow.":
        "Dikte ve toplantılar — tek akışta.",
    "Keep running in the system tray when the window is closed":
        "Pencere kapatıldığında sistem tepsisinde çalışmaya devam et",
    "When disabled, the title-bar close button, Escape and Alt+F4 quit WordArc.":
        "Kapalıyken başlık çubuğundaki X, Escape ve Alt+F4 WordArc'ı tamamen kapatır.",
    "Keys are tried from top to bottom and stored only in Windows Credential Manager.":
        "Anahtarlar yukarıdan aşağıya denenir ve yalnız Windows Kimlik Bilgisi Yöneticisi'nde saklanır.",
    "API keys": "API anahtarları",
    "Add API": "API ekle",
    "Edit API": "API'yi düzenle",
    "Edit": "Düzenle",
    "Remove": "Kaldır",
    "Move up": "Yukarı taşı",
    "Move down": "Aşağı taşı",
    "Default API": "Varsayılan API",
    "Backup API {number}": "Yedek API {number}",
    "Gemini API key": "Gemini API anahtarı",
    "This API key is already listed.": "Bu API anahtarı zaten listede.",
    "Default API did not respond; trying API {number}...":
        "Varsayılan API yanıt vermedi; API {number} deneniyor...",
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
    "System": "Sistem",
    "Dictation, meetings and agents — in one flow.":
        "Dikte, toplantı ve ajanlar — tek akışta.",
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
    "Review and retry meeting summaries.":
        "Toplantı özetlerini inceleyin ve yeniden deneyin.",
    "Transcribe an existing recording.":
        "Var olan bir kaydı yazıya çevirin.",
    "Choose global keyboard shortcuts.":
        "Genel klavye kısayollarını seçin.",
    "Control local plaintext transcript retention.":
        "Yerel açık metin döküm saklamayı yönetin.",
    "Saved successfully.": "Başarıyla kaydedildi.",
    "Interface language": "Arayüz dili",
    "Automatic (system)": "Otomatik (sistem)",
    "Turkish": "Türkçe",
    "English": "İngilizce",
    "Restart WordArc for the language change to reach every window.":
        "Dil değişikliğinin her pencereye işlemesi için WordArc'ı yeniden başlat.",
    "Microphone": "Mikrofon",
    "Default microphone": "Varsayılan mikrofon",
    "Speech language": "Konuşma dili",
    "Detect automatically": "Otomatik algıla",
    "German": "Almanca",
    "French": "Fransızca",
    "Spanish": "İspanyolca",
    "Arabic": "Arapça",
    "Paste the text into the focused window": "Metni odaktaki pencereye yapıştır",
    "Paste key": "Yapıştırma tuşu",
    "Terminals usually want ctrl+shift+v. Change this if pasting does nothing.":
        "Terminaller genelde ctrl+shift+v ister. Yapıştırma çalışmıyorsa bunu değiştir.",
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
    "Prefixes every segment with [mm:ss]. Uses whisper-1 on whichever provider "
    "you picked, the only model that returns segment times.":
        "Her bölümün başına [dd:ss] koyar. Bölüm zamanı döndüren tek model olan "
        "whisper-1, seçtiğin sağlayıcı üzerinden kullanılır.",
    "Run the cleanup model afterwards": "Sonrasında temizleme modelinden geçir",
    "With its own rules, under Cleanup rules: written for subtitles, so the "
    "lines keep their place and nothing is shortened.":
        "Kendi kurallarıyla, Temizleme kuralları sekmesinin altında: altyazı için "
        "yazılmıştır, satırlar yerinde kalır ve hiçbir şey kısaltılmaz.",
    "Transcribe": "Yazıya çevir",
    "Stop": "Durdur",
    "Copy": "Panoya kopyala",
    "Save as .txt": "'.txt' olarak kaydet",
    "Save as .srt": "'.srt' olarak kaydet",
    "Subtitles, timed from the segments. Needs the timestamps option.":
        "Altyazı; zamanlaması bölüm damgalarından gelir. Zaman damgası seçeneği "
        "işaretliyken çalışır.",
    "No timestamped lines to turn into subtitles.":
        "Altyazıya çevrilecek zaman damgalı satır yok.",
    "Save transcript": "Transkripti kaydet",
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
    "A meeting is recorded from two devices at once: your microphone and "
    "whatever comes out of your speakers. Nothing has to guess who was "
    "speaking, because the two never share a channel.":
        "Toplantı iki aygıttan aynı anda kaydedilir: mikrofonun ve hoparlöründen "
        "çıkan ses. Kimin konuştuğunun tahmin edilmesi gerekmez, çünkü ikisi hiç "
        "aynı kanala girmez.",
    "Sound": "Ses",
    "Same as dictation": "Diktedekiyle aynı",
    "Current output": "Geçerli çıkış",
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
}
