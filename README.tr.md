# WordArc — Windows için sesle yazma

> English: [README.md](./README.md)

**`Ctrl+Space` bas, konuş, tekrar bas. Metin çalıştığın yere düşer — temizlenmiş olarak.**

WordArc bir Windows dikte ve yazıya çevirme aracıdır. Mikrofonunu (toplantı modunda sistem sesini de) kaydeder, yerelde veya Gemini üzerinden yazıya çevirir, sonucu bir yapay zekâ temizleme turundan geçirir ve odağındaki pencereye yapıştırır. Bulut panosu yok, hesap yok, sesin arka planda yüklenmesi yok.

![WordArc · Dikte](./docs/screenshots/01-dikte.png)

---

## İçindekiler

- [Ne yapar](#ne-yapar)
- [Ekranlar, tek tek](#ekranlar-tek-tek)
  - [1. Dikte](#1-dikte)
  - [2. Toplantı](#2-toplantı)
  - [3. Ses dosyası](#3-ses-dosyası)
  - [4. Seslendir](#4-seslendir)
  - [5. Ekran görüntüsü](#5-ekran-görüntüsü)
  - [6. Ayarlar](#6-ayarlar)
  - [7. Koyu tema](#7-koyu-tema)
  - [8. İngilizce arayüz](#8-i̇ngilizce-arayüz)
- [Kurulum](#kurulum)
- [Komut satırı](#komut-satırı)
- [Kaynaktan derleme](#kaynaktan-derleme)
- [Konuşma motorları](#konuşma-motorları)
- [Veri ve gizlilik](#veri-ve-gizlilik)
- [Proje yapısı](#proje-yapısı)
- [Sorun giderme](#sorun-giderme)
- [Lisans](#lisans)

---

## Ne yapar

| Yetenek | Ayrıntı |
|---|---|
| **Bas-konuş dikte** | `Ctrl+Space` başlatır/durdurur; `Escape` yazıya çevirmeden siler |
| **Toplantı modu** | mikrofon + WASAPI loopback ile sistem sesi, tutanaklık çıktı |
| **Ses dosyası çevirisi** | ffmpeg'in okuduğu her dosya, zaman damgası ve `.srt` dışa aktarımı |
| **Sesli okuma** | hız ve biçim kontrollü metin okuma, dosyaya kaydedilebilir |
| **Ekran görüntüsü** | `Ctrl+Alt+S` alan seçimi, "bunu sesli oku", pano, PNG/JPEG |
| **Temizleme turu** | yapay zekâ dolgu sözcüklerini atar, noktalama düzeltir, anlamı korur |
| **Yerel veya bulut** | CPU/CUDA/Vulkan üzerinde whisper ya da Gemini — mod bazında sen seçersin |
| **İki dilli arayüz** | Türkçe ve İngilizce, koyu / açık / sistem temaları |

---

## Ekranlar, tek tek

### 1. Dikte

![Dikte](./docs/screenshots/01-dikte.png)

Varsayılan sekme, tek düğme etrafında kurulu.

**Sol panel — kayıt**
- `Kaydı başlat` — kaydı başlatır. Aynı işlem `Ctrl+Space` ile global olarak bağlıdır; yani herhangi bir uygulamanın içine dikte edebilirsin.
- **Mikrofon** seçici ve yenile düğmesi; oturum sırasında takılan kulaklık yeniden başlatmadan görünür.
- **Konuşma dili** — dikte modelinin dili.
- **Kısayol** alanı — global kısayol, değiştirilebilir.
- **Transkripti bir modelle temizle** — açıkken ham metin yapıştırılmadan önce temizleme isteminden geçer.
- **Metni odaktaki pencereye yapıştır** — kapalıyken sonuç WordArc'ta kalır, elle kopyalarsın.

**Sağ panel — sonuç**
- `Gelişmiş` — model, istem dili, çalıştırma bazlı geçersiz kılmalar.
- `Son dikte` — nihai metin, kopyalamadan önce düzenlenebilir.
- `Geçmiş` — önceki dikteler; varsayılan kapalı.

`Panoya kopyala` metni kopyalar. `Kaydet` sekmenin ayarlarını yazar.

**Neden iki adım.** Kayıt ve yazıya çevirme ayrıdır: önce kayıt biter, sonra çeviri çalışır, sonra temizleme çalışır. Temizleme başarısız olursa ham transkript elinde kalır — WordArc, cila adımı bozuldu diye çeviriyi asla atmaz.

### 2. Toplantı

![Toplantı](./docs/screenshots/02-toplanti.png)

Kimseye ekran paylaşma ricası etmeden bir görüşmenin iki tarafını da kaydeder.

**Sol panel**
- `Kaydı başlat` — toplantı kaydını başlatır/durdurur.
- **Mikrofon** — `Diktedekiyle aynı` veya belirli bir cihaz.
- **Toplantı ses kaynağı** — `Geçerli çıkış`, duyduğunu WASAPI loopback ile yakalar; karşı taraf kulaklıkta olsa bile kaydedilir.

**Sağ panel**
- `Tutanaklar` — kayıt başına bir girdi, zaman damgalı.
- `Gelişmiş` — yalnız bu toplantı için model ve istem geçersiz kılmaları.
- Transkript önizlemesi, düzenlenebilir.
- `Panoya kopyala`, `Tutanağı çıkar`, `Klasörü aç`, `Seçiliyi sil`, `Yenile`.

**Ses işleme.** Kayıt `%LOCALAPPDATA%\WordArc\` altına yazılır ve başarılı çeviriden sonra varsayılan olarak silinir. Çeviri başarısız olursa ses kalır, tekrar deneyebilirsin — hiçbir şey sessizce atılmaz.

### 3. Ses dosyası

![Ses dosyası](./docs/screenshots/03-ses-dosyasi.png)

Canlı kayıt yerine var olan bir kaydı yazıya çevirir.

**Sol panel**
- `Ortak AI ayarlarını aç` — paylaşılan model ayarlarına atlar.
- Geçerli model salt okunur gösterilir (ekran görüntüsünde `gemini-3.5-flash-lite`).
- `Seçenekler` ve `Temizleme kuralları` alt sekmeleri.
- `Dosya seç` — ses dosyasını seçer.
- **Zaman damgası ekle** — her parçanın başına başlangıç anını yazar.
- **Sonrasında temizleme modelinden geçir** — diktedeki aynı cila turu.

**Sağ panel**
- `Yazıya çevir`, `Durdur` — durdurma işbirlikçidir; kısmi transkript korunur.
- Transkript kutusu.
- `Panoya kopyala`, `'.txt' olarak kaydet`, `'.srt' olarak kaydet` — altyazı dışa aktarımı zaman damgalarını kullanır.

Uzun dosyalar akış halinde işlenir: ilerleme çubuğu ilerler ve kısmi metin dosya hâlâ işlenirken görünür, ilk dakikalar yanlışsa erken durdurabilirsin.

### 4. Seslendir

![Seslendir](./docs/screenshots/04-seslendir.png)

Aynı pencerede metin okuma.

- **Okunacak metin** — yapıştır veya yaz.
- **Biçim** — `opus` ve paketteki diğer kodlayıcılar.
- **Hız** — `1x` ve katları.
- `Sesli oku`, `Durdur`.
- `Sesi kaydet...` — üretilen konuşmayı dosyaya yazar.

Ses modelleri derlemeye gömülüdür; bu sekme çevrimdışı çalışır.

### 5. Ekran görüntüsü

![Ekran görüntüsü](./docs/screenshots/05-ekran-goruntusu.png)

Ekrandakini yakala ve kullan.

- `Alan seç...` — global `Ctrl+Alt+S` ile aynı işlem.
- `Sese çevir ve oku` — yakalanan görüntüyü OCR'dan geçirip sesli okur.
- `Bu ekranı yakala`, `Etkin pencereyi yakala`.
- **Kısayol** alanı — global yakalama kısayolu.
- **Kayıt klasörü** ve `Klasör seç...`, görüntü biçimi seçici (`PNG`).

Yakalamalar yerelde kalır. Sesli okuma yolunda hiçbir şey yüklenmez — OCR kendi makinede çalışır.

### 6. Ayarlar

![Ayarlar](./docs/screenshots/06-ayarlar.png)

Solda dört kategori, her birinin kendi paneli.

**Ses ve modeller**
- **Nerede çalışsın** — `Bulut (Gemini)` veya yerel motor.
- **Bulut modeli** — çeviri modeli, `Model listesini çek` düğmesiyle.
- **Temizleme modeli** — cila turu için ayrı model; temizlemede ucuz, çeviride daha iyi bir model kullanabilirsin.
- **Düşünme** — `Modelin kendi varsayılanı`, ya da zorla açık/kapalı.
- **Açıklama** — dikte ve toplantı temizlemesinin ortak sistem talimatı. Bunu düzenlemek metnin ne kadar agresif yeniden yazılacağını değiştirir.

**Metin ve terimler** — özel sözlük ve değiştirmeler; böylece isimler ve jargon çeviriden sağ çıkar.

**API anahtarları** — Windows Credential Manager'da `WordArc/GeminiApiKey` olarak tutulur, `config.json` içine asla yazılmaz.

**Uygulama** — tema, dil, başlangıç davranışı, tepsi davranışı.

`Kaydet` ayarları yazar. Çalışan bir kaydı etkileyen değişiklikler bir sonraki kayıtta geçerli olur, kaydın ortasında asla.

### 7. Koyu tema

![Koyu tema — dikte](./docs/screenshots/07-koyu-tema-dikte.png)

![Koyu tema — toplantı](./docs/screenshots/08-koyu-tema-toplanti.png)

Koyu varsayılandır. Her panel, tablo, durum rengi ve pasif durum iki tema için de çizilir; tema değişince yerleşim kaymaz. `Sistem` Windows ayarını izler.

### 8. İngilizce arayüz

![İngilizce arayüz](./docs/screenshots/09-english-dictation.png)

Üst çubuktaki dil anahtarı yalnız etiketleri değil tüm arayüzü değiştirir — pencereler, hata mesajları ve temizleme istemleri dahil. Dil değiştirmek uygulamayı yeniden başlatmaz, kaydı kesmez.

---

## Kurulum

1. `WordArc-<sürüm>.exe` dosyasını [Releases](https://github.com/zeitgeist-c/WordArc/releases/latest) sayfasından indir.
2. Çalıştır. `Program Files\WordArc` altına yönetici izniyle kurulur; kurulum yaklaşık 500 MB.
3. İlk açılışta Ayarlar açılır. Gemini API anahtarını gir veya yerel model seç.
4. `Ctrl+Space` bas, konuş, tekrar bas.

GPU desteği istek üzerine indirilir — temel kurulum CUDA kütüphanesi taşımaz. NVIDIA kartında GPU cihazı ilk seçildiğinde CUDA çalışma zamanı iner; AMD'de paketteki whisper.cpp Vulkan motoru ayrı bir GGML model indirmesiyle kullanılır. Daha önce indirilmiş CPU veya CUDA ağırlıkları diskte kalır ve çalışmaya devam eder.

## Komut satırı

```powershell
python wordarc.py             # Ayarlar'ı aç, tepsi servisini çalışır tut
python wordarc.py background  # arka planda çalış (Windows başlangıcı)
python wordarc.py toggle      # kaydı başlat / durdur
python wordarc.py cancel      # geçerli kaydı sil
python wordarc.py meeting     # toplantı kaydını başlat / bitir
python wordarc.py settings    # ayar penceresini aç
python wordarc.py quit        # uygulamayı kapat
```

Tek örnek yerel IPC ile zorlanır: WordArc açıkken `toggle` çalıştırmak ikinci bir süreç başlatmaz, çalışan sürece ulaşır.

## Kaynaktan derleme

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-lock.txt -r requirements-dev.txt
python wordarc.py
```

Kontrol ve paketleme:

```powershell
.\check.ps1
.\build.ps1
```

`check.ps1` pytest, `compileall` ve tüm modüller üzerinde içe aktarma kontrolü çalıştırır. `build.ps1` sabitlenmiş FFmpeg ikilisini doğrular, testleri çalıştırır, bağımlılıkları denetler, `sbom.json` üretir, deterministik simgeyi çizer, TTS ağırlıklarını pakete gömer ve PyInstaller + Inno Setup ile kurulum paketini üretir.

`build.ps1 -Cuda` ek olarak NVIDIA DLL setini hazırlar ve doğrular; bu anahtar olmadan paket yalnız CPU ve Vulkan motorlarını taşır.

## Konuşma motorları

| Motor | Nerede çalışır | Not |
|---|---|---|
| **Gemini** | bulut | API anahtarı gerekir; uzun toplantılarda en hızlı |
| **faster-whisper (CPU)** | yerel | varsayılan yerel yol, GPU gerekmez |
| **faster-whisper (CUDA)** | yerel GPU | istek üzerine iner, yalnız NVIDIA |
| **whisper.cpp Vulkan** | yerel GPU | 0.6.9'dan beri AMD yolu, ayrı GGML model |

`Otomatik` sırasıyla CUDA, Vulkan, CPU seçer. Bir GPU motoru kayıt ortasında çökerse otomatik çalıştırma aynı sesi CPU'da tekrar dener; açık AMD/NVIDIA seçiminde önce onay istenir. Yerel yollarda ses makineden çıkmaz.

## Veri ve gizlilik

- Ayarlar: `%APPDATA%\WordArc\config.json`
- Kayıtlar, toplantılar, tanılama, indirilen modeller: `%LOCALAPPDATA%\WordArc\` — konuşma modelleri `whisper`, GPU çalışma zamanı `cuda` altında. Kurulum ve kaldırma bu klasörlere dokunmaz.
- Gemini anahtarı: Windows Credential Manager, `WordArc/GeminiApiKey`.
- Geçmiş varsayılan **kapalı**. Açıldığında yerel düz metin dosyalarıdır.
- Başarılı toplantı sesi varsayılan olarak silinir.
- Telemetri yok. Tek ağ çağrıları: model listesi, bulut motoru seçtiğinde çeviri isteği ve güncelleme denetimi.

## Proje yapısı

```text
wordarc.py             tepsi uygulaması, CLI, tek örnek IPC
worker.py              dikte hattı
meeting.py             toplantı hattı
audio.py, audio_capture.py   mikrofon ve WASAPI loopback kaydı
settings_ui.py         altı sekmeli pencere
screenshot_capture.py  alan ve tam ekran yakalama, yerel önizleme
hotkey.py              global kısayollar
api.py, temizleme      Gemini istemcisi ve cila turu
filetranscribe.py      ses dosyası çevirisi
livespeech.py          sesli okuma
engine_discovery.py    yerel model keşfi ve seçimi
cuda_*.py, cuda_libs.py  CUDA algılama, kurtarma ve DLL hazırlığı
brand.py, theme.py, i18n.py  kimlik, tema, Türkçe/İngilizce metinler
assets/brand           kanonik SVG kaynakları ve simge derlemesi
tools/                 paketleme, doğrulama ve ekran görüntüsü araçları
tests/                 pytest paketi
```

## Sorun giderme

- **`Ctrl+Space` bir şey yapmıyor** — başka bir uygulama kısayolu tutuyor. Dikte sekmesinden değiştir veya serbest bırak, sonra `python wordarc.py restart`.
- **Toplantıda karşı taraf sesi yok** — loopback kaydı etkin bir çıkış cihazı ister. Windows ses ayarlarını ve toplantı ses kaynağının `Geçerli çıkış` olduğunu kontrol et.
- **Anahtar reddedildi** — Ayarlar'dan yeniden gir; anahtar yalnız Credential Manager'da tutulduğu için Windows profil sıfırlaması onu siler.
- **GPU motoru geç aşamada hata veriyor** — otomatik çalıştırma CPU'da tekrar dener; açık GPU seçiminde geri düşmeden önce onay ister. Vulkan'sız CPU paketi, yeniden indirme olmadan indirilmiş GGML ağırlıklarını kullanabilir.
- **Temizleme boş metin döndürüyor** — boş temizleme sonucu asla yapıştırılmaz ve başarı sayılmaz; ham transkript korunur.

## Lisans

GPL-3.0. Özgün Linux projesi [yusufipk](https://github.com/yusufipk/dikte) tarafından oluşturuldu.
