# WordArc — durum

Güncelleme: 2026-09-27
Hazırlanan paket: 0.5.3 (`brand.py`)
Dal: master
Git dönüş noktası: 1ac6b5b / v0.5.2

## 0.5.3 — dil değişimi, denetim düzeltmeleri ve temizlik

### Dil değişimi (kullanıcı bildirimi)

Kullanıcının bildirdiği "dil değiştirince programın yapısı bozuluyor" hatası
`%LOCALAPPDATA%\WordArc\logs\wordarc.log` içinde kanıtlandı: 2026-09-27
14:13:22'de ilk hata `wordarc.py:_reopen_settings` üzerinden geliyor,
`SettingsWindow.__init__` → `_meeting_tab` → `_refresh_audio_devices` →
`audio.refresh_devices` → `has_active_capture` zincirinde
`sounddevice.PortAudioError: Invalid stream pointer [PaErrorCode -9988]`.
Durdurulmuş bir PortAudio akışının Python sarmalayıcısı bir süre yaşıyor;
kütüphane altında yeniden kurulunca işaretçisi ölüyor ve `active` sorusu hata
veriyor. Hata pencere kurulumunu yarıda kesiyordu; dil değişimi eski pencereyi
önce kapattığı için ekranda hiç pencere kalmıyordu (logdaki iki sonraki hata,
kullanıcının tepsi menüsünden yeniden denemesi).

Düzeltmeler:

- `audio.has_active_capture()` ölü akış girdisini hata vermek yerine düşürür;
  canlı bir kayıt varsa yine True döner.
- `settings_ui._refresh_audio_devices()` ses taraması hata verse de pencereyi
  düşürmez: kutular olduğu gibi kalır (boş kutu varsayılan satırla dolar),
  tarama hatası loga yazılır.
- `wordarc._reopen_settings()` yeni pencereyi kurmadan eskisini kapatmaz;
  kurulum başarısız olursa kullanıcının açık penceresi yerinde kalır ve hata
  loga yazılır. Başarılı kurulumda eski pencere bir tur sonra `deleteLater` ile
  serbest bırakılır (eskiden her dil değişiminde bir pencere birikiyordu).
- Yeni `settings_ui.WindowView`: konum, boyut, ekran, aktif sekme, Ayarlar
  bölümü ve büyütülmüş durumu yeni pencereye taşınır; eskiden pencere açılış
  boyutuna ve ilk sekmeye dönüyordu.
- `_fit_on_screen()` büyütülmüş/tam ekran pencereye dokunmaz; eskiden sekme
  değiştirmek bile büyütülmüş pencereyi eski boyutuna düşürüyordu.
- Dil, Ayarlar sekmesindeki kutudan kaydedildiğinde de pencere yeni dilde
  yeniden kurulur (kutu ipucu güncellendi); eskiden pencere eski dilde kalırken
  tepsi menüsü yeni dile geçiyordu.
- Dil değişimi tepsi menüsünü de yeniler.
- Çalışan iş parçacıkları (model listesi, bağlantı testi, model indirme) dil
  değişiminden sonra silinen pencereye sinyal gönderip çökebiliyordu; artık
  `_deliver()` ile korunuyor.
- Qt'nin kendi metinleri (metin alanı menüleri, standart diyalog düğmeleri)
  yalnız başlıktaki düğmeden kuruluyordu; artık her dil değişiminde kurulur.
- Kapanış zamanlayıcısı koşulsuz `settings_window = None` yapıyordu; arada açılan
  yeni pencere kaybolabiliyordu, artık yalnız kuyruğa alındığı pencereyi düşürür.

### Denetim bulguları ve düzeltmeleri

Üç paralel salt-okunur tarama (ses/transkripsiyon hattı, altyapı modülleri, büyük
çekirdek dosyalar) yapıldı; her bulgu satır numarası ve akış iziyle doğrulandı.

- `worker.py` — "durdur" isteği yutuluyordu: `except api.ApiError` bloğu
  `api.Cancelled`'ı (alt sınıf) da yakaladığı için iptal "cleanup başarısız"
  uyarısına dönüşüyor, akış durmayıp ham metni yapıştırıyordu. Artık
  `except api.Cancelled: raise`.
- `worker.py` — yapıştırma hata verirse pano geri yüklenmiyordu (`press()`
  patlayınca `copy_bytes(previous)` atlanıyordu); yapıştırma yolu bayrakla
  dayanıklı hale getirildi.
- `paste.py` — `EmptyClipboard()` `GlobalAlloc`'tan sonra çağrılıyordu ve
  `GlobalLock` başarısız olursa handle sızıyordu; sıra düzeltildi, handle
  serbest bırakılıyor.
- `meeting.py` — özet hatası koşulsuz `status='failed'` yazıp `'transcribed'`
  durumunu eziyordu; tekrar denemede tüm ses baştan transkribe ediliyordu. Artık
  transkript varsa durum korunur (yalnız hiç transkript yokken 'failed').
- `meeting.py` — UTF-8 olmayan bir belge `UnicodeDecodeError` (ValueError)
  fırlatıp iş parçacığını sessizce öldürüyordu; yakalama listesine eklendi.
- `config.py` — bozuk/UTF-8 olmayan ayar dosyası ve yanlış tipte değerler pencere
  açılmadan uygulamayı düşürüyordu. Artık okunamayan dosyanın kopyası
  `config.json.corrupt` olarak saklanır, tipte uymayan değer varsayılanına düşer
  ve uyarı loga yazılır.
- `config.py` — silinemeyen toplantı dosyaları sessizce yutuluyordu; artık loga
  yazılır.
- `wordarc.py` — eski marka göçü (`brand_migration.migrate`) günlük kurulmadan
  önce çalışıyor ve korumasızdı: beklenmeyen bir hata penceresiz ve logsuz açılış
  demekti. Sarıldı, uyarısı loga düşer.
- `diagnostics.py` — `threading.excepthook` eklendi: iş parçacığında ölen bir hata
  artık logda iz bırakır.
- `hotkey.py` — `nativeEvent` içindeki `except Exception: pass` kısayol hatalarını
  hiçbir iz bırakmadan yutuyordu; artık loga yazılır. Kullanılmayan
  `_lock`/`_names` alanları ve `threading` importu kaldırıldı.

### Temizlik

- Yeniden üretilebilir PyInstaller ara çıktıları ve sha256 ile birebir aynı olduğu
  kanıtlanan model kopyaları silindi: `build/` 2,4 GB → 545 MB. Kanıt:
  `%TEMP%\temizle-wordarc-20260927-150819-b7c1\silinenler.txt` (silinenlerin
  listesi + `model.bin` sha256 karşılaştırması). Güncel sürüm ara çıktısı, probe,
  kanıt logları ve `dist/` teslim paketi korundu.
- Kaynak: ölü kod (`mic_status`/`monitor_status` blokları, `_section_card`'ın hiç
  yerleşime girmeyen açıklama etiketi), kullanılmayan `hotkey` alanları/importu,
  kullanılmayan 4 çeviri anahtarı ve yinelenen ayırıcı yorum.

Doğrulama: 280 test geçti, 1 atlandı (önceki 271 + 9 yeni test); `compileall` ve
modül yükleme denetimi temiz; `pip_audit` bilinen açık bulmadı; SBOM üretildi.
Yeni testler ölü akışı, taraması hata veren pencere kurulumunu, yeniden kurulumun
başarısız olması durumunu, durum taşımayı, büyütülmüş pencereyi, iptal sırasında
durmayı, yapıştırma hatasında pano geri yüklemeyi, özet hatasında transkript
durumunun korunmasını, bozuk/yanlış tipte ayar dosyasını ve kapanış
zamanlayıcısını kapsar. Gerçek Qt platformunda (pencere ekrana basılmadan) uçtan
uca denendi: ölü akış varken dil değişimi pencereyi düşürmüyor, konum/boyut/sekme
korunuyor, tepsi menüsü ve Qt metinleri yeni dile geçiyor; kutudan dil kaydı da
pencereyi yerinde yeniden kuruyor.

Paket: dist/WordArc-0.5.3.exe + dist/WordArc-0.5.3.bat.
EXE SHA256: 3a40980222ae558038c5e18515c1c7c4f8d65383f4625cc9f02490f74299959a.
Frozen smoke: `WordArc-0.5.3.exe --version` → `WordArc version 0.5.3` (offscreen,
kullanıcı ekranına pencere basılmadan).

Yedek 2026-09-27: yerel commit + v0.5.3 etiketi tamamlandı; `origin/master` ve
`v0.5.3` etiketi açık yetkiyle push edildi (uzak sha'lar doğrulandı).

## 0.5.2 — yerel model indirme

- HTTPS üzerinden dosya boyutu ve SHA256/Git nesne özeti doğrulanarak indirilir. Turbo bağlantısı güncel dropbox-dash deposuna gider; mevcut kurulum klasörleri korunur.
- İndirme alanı yüzde, indirilen/toplam boyut, hız, kalan süre ve dosya bilgisini gösterir.
- Durdur ve yeniden indir akışı aynı depo revizyonundaki kısmi dosyaları kullanır; geçici hatalarda yeniden dener. Sunucu aralık isteğini desteklemezse güvenli biçimde baştan indirir.
- İndirme hatası arayüz yenilemesinde kaybolmaz. Başarı bildiriminin hatalı metot çağrısı düzeltildi.
- Yerel Whisper yalnız sesi yazıya çevirir. Temizleme açıksa metin Gemini'ye gönderilir; kapalıysa ham transkript kullanılır. Bu bilgi yerel model seçiminin yanında görünür.

Doğrulama: 257 test geçti, 1 test atlandı; modül yükleme ve bağımlılık denetimi başarılı. Yeni testler iptal/devam, Range isteğini yok sayan sunucu, bozuk sağlama toplamı ve arayüz hata/ilerleme durumlarını kapsar. Yerel model klasörü ve gerçek kullanıcı ayarları izole tutuldu.

Canlı ağ kontrolü: base modelinin tamamı indirildi (147882941 bayt), doğrulandı ve WhisperModel olarak yüklendi. small ve large-v3-turbo metadata/config bağlantıları ile model.bin aralık istekleri başarılı; bu iki büyük modelin tamamı indirilmedi. Gerçek mikrofon kaydı ve canlı Gemini temizleme bu değişiklikte denenmedi.

Yeni indirme alanı Türkçe açık/koyu temalarda normal ve dar pencerede yerel Qt görüntüleriyle kontrol edildi. İngilizce karşılıklar eklendi; önceki tasarım incelemesi docs/design-review.md içinde.

Paket: dist/WordArc-0.5.2.exe + dist/WordArc-0.5.2.bat.
EXE SHA256: 040552e13cb512597f2f969226c9a6c2a89c56bb9ba4061916460c45efb3c379.

Yedek 2026-09-26: commit + v0.5.2 etiketi + push tamamlandı.

## Önceki tasarım ve seçim düzeltmeleri

Dört sekme ortak çalışma alanı tasarımına geçti. 18 seçim alanı aynı aramalı pencereyi açar; düzenlenebilir alanlarda metne tıklama da pencereyi açar. Gelişmiş alan açılırken kaydırma alanı yeniden hesaplanır. Pencere kayıt düğmeleri mevcut denetleyicileri kullanır; pencere diktesi sonucu panoya alınır, otomatik yapıştırılmaz. Ctrl+Space davranışı korunur.

Paket doğrulaması: izole konsol EXE'sinde dört sekme ve seçim yönlendirmeleri açıldı. Aynı pakette base modeli yeni, izole klasöre gerçekten indirildi ve WhisperModel yüklendi (FROZEN DOWNLOAD OK). Dağıtım EXE'si ile doğrulama EXE'sinin brand/localspeech/settings_ui/theme/i18n modülleri bytecode olarak aynı bulundu.
