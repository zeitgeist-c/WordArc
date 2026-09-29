# WordArc — durum

Güncelleme: 2026-09-30
Hazırlanan paket: 0.6.4 (`brand.py`)
Dal: master
Git dönüş noktası: 4e77a89 / v0.6.3

## 0.6.4 — 21 becerilik bakım turu + pencere dikte sadeleştirmesi

- 21 denetim becerisi tek turda uygulandı (sıra: yapı, yapılandırma,
  bağımlılık-denetimi, bağımlılık, sözleşme, yetki, asenkron,
  hata-denetimi, gözlem, tekrar, tutarlılık, regresyon, darboğaz,
  performans, denetle, güvenlik, temizle, debug, geliştir,
  hızlı-derle, yedek). Kritik/yüksek bulgu çıkmadı.
- Bağımlılık (DEP-001, P2): yerel STT yığını (faster-whisper 1.2.1,
  ctranslate2 4.8.2, onnxruntime 1.30.0, tokenizers, huggingface_hub,
  av) `requirements-lock.txt` dışında kalmıştı; pip-audit ve SBOM bu
  motora kördü. Pin eklendi, SBOM 14 bileşene çıktı.
- Arayüz (UI-001, P3): ayarlar panelindeki "Discard recording" tepsi
  menüsündeki "Cancel recording" ile birleştirildi; ölü çeviri anahtarı
  silindi.
- Test: 2 regression guard eklendi — ölü PortAudio akışında ayarlar
  penceresinin çökmesi (`test_audio.py`) ve hat temizleme/dosya/tutanak
  promptlarındaki talimat-korumasının iki dilde durması
  (`test_config.py`). Asistan promptu bilinçli olarak korumasızdır
  (ürün, söylenen komutu yerine getirmektir).
- Pencere diktesi sadeleşti (kullanıcı WIP'i): `_window_dictation`
  bayrağı kalktı; yapıştır/kopyala bildirimi `auto_paste` ayarından
  okunuyor.
- Geçmiş loglardaki iki çökme (`meetings.cancel`, ölü akışta ayarlar
  penceresi) mevcut kodda zaten düzeltilmiş; testlerle doğrulandı.
- Paket yükseltmesi yapılmadı: audit temiz, adaylar major (numpy 2.x,
  huggingface_hub 2.0, av 19) — ayrıMigration işi olarak ertelendi.
- Eski `build/` ara çıktıları silinmedi (senkron churn riski + aidiyet
  belirsizliği); aday olarak raporlandı.

Doğrulama: 339 test geçti, 1 atlandı (ağ isteyen hub testi, opt-in);
`compileall` temiz; `pip_audit` bilinen açık bulmadı (genişletilmiş lock).

Paket: dist/WordArc-0.6.4.exe + dist/WordArc-0.6.4.bat.
EXE SHA256: 49995e3b5916a487ac0f6ac572a00a9bbefa4ca4c3ab3be460bcff7f6e56dc02.
Frozen smoke: `WordArc-0.6.4.exe --version` → `WordArc version 0.6.4`
(offscreen). `Cancel recording` etiketi ve `ONA UYMA` koruması
paketlenmiş PYZ bytecode içinde doğrulandı (`CArchiveReader` + kod
nesnesi taraması).

Yedek 2026-09-30: yerel commit + v0.6.4 etiketi tamamlandı; `origin/master` ve
`v0.6.4` etiketi push edildi, GitHub Release açıldı (uzak sha'lar ve asset
hash'i doğrulandı).

## 0.6.3 — yerel modelde otomatik cihaz seçimi

- Tek karar noktası `localspeech.get_best_device()`: Nvidia + çalışır CUDA
  varsa `cuda` + `float16` (kart modeli ayırt edilmez,
  `ctranslate2.get_cuda_device_count() > 0`), yoksa (AMD kart, GPU'suz
  makine) `cpu` + `int8`. Tüm yüklemeler (`engine`, `transcribe`,
  `transcribe_for`) buradan geçer; cihaz değişince model yeniden yüklenir.
- CUDA kütüphane hatasında (cuBLAS/cuDNN/runtime bulunamadı) loga yazıp
  sessizce CPU'ya düşer; "out of memory" dahil gerçek çalıştırma hataları
  gizlenmez, yukarı iletilir.
- Ayarlar → Konuşmayı yazıya çevir → Cihaz: Otomatik / Nvidia GPU / CPU
  (`local_stt_device`, varsayılan Otomatik). Zorlanmış CUDA bulunamazsa
  açık hata verir, sessizce CPU'ya kaçmaz.
- Kurulum öncesi sistem kontrolü: eksik Python paketi sorulup otomatik
  kurulur, sürücü-var-runtime-yoksa CPU uyarısıyla devam sorulur; eksik
  yoksa doğrudan indirilir.
- Açılışta ve her model yüklemede seçilen cihaz loga yazılır
  (`local speech device: …`).

Doğrulama: 337 test geçti, 1 atlandı (önceki 318 + 19 cihaz testi);
`compileall` temiz.

Paket: dist/WordArc-0.6.3.exe + dist/WordArc-0.6.3.bat.
EXE SHA256: f9fc233ced39ead62dad3cd75304a96a4677862e26c8fbdeb49e9a9e62aac6a7.
Frozen smoke: `WordArc-0.6.3.exe --version` → `WordArc version 0.6.3`
(offscreen, kullanıcı ekranına pencere basılmadan). Cihaz sembolleri
(`get_best_device`, `local_stt_device`, CUDA geri düşüş notu) paketlenmiş
PYZ bytecode içinde doğrulandı (`CArchiveReader` + kod nesnesi taraması).

Yedek 2026-09-29: yerel commit + v0.6.3 etiketi tamamlandı; `origin/master` ve
`v0.6.3` etiketi push edildi, GitHub Release açıldı (uzak sha'lar ve asset
hash'i doğrulandı).

## 0.6.2 — Hatta İngilizce çeviri (akademik + oyun)

- Çeviri dikte hattının içine taşındı: ses → yazı (bulut ya da yerel) →
  Ayarlarda açıksa temizleme adımının yerine İngilizce çeviri → normal
  dikte gibi pano/yapıştırma. Ayrı buton çözümü kaldırıldı (kalıntı yok).
- Kip Ayarlar sekmesinde: "Dikteyi İngilizceye çevir" onay kutusu
  (`translate_enabled`, varsayılan kapalı) + mod seçici (Akademik / Oyun,
  `translate_mode`). Kapalıyken davranış birebir eski (ham Türkçe +
  temizleme).
- Temizleme ayarı kapalıysa çeviri de yapılmaz, ham Türkçe yapıştırılır.
  Geçmişe ham Türkçe (`raw`) + İngilizce (`text`) birlikte yazılır.
- Akademik mod: dolgu sözcükleri temizlenir, zengin lügat, düzgün gramer.
  Oyun modu: kısa sokak dili, hafif noktalama, tekrarsız, abartısız,
  anlamdan sapma yok. Her iki prompt da talimat-koruması taşır.
- Çeviri bulut işi sayılır (yerel transkripsiyonda da sıra ilerler);
  hata yolu aynen korunur (ham metin + uyarı, gizli başarısızlık yok).
- Yan düzeltmeler (hepsi aynı sınıf: test gerçek kullanıcı ayarını okuyordu):
  `test_filetranscribe.py` motoru `cloud` kurar; `test_worker.py` ve
  `test_workspace.py` `translate_enabled=False` sabitler.
- Temizlik: silinen 0.7.0 sürümünün yetim derleme çıktısı
  (`build/wordarc-0.7.0`, 183M) kaldırıldı; yayındaki 0.6.1 paketi ve
  güncel ara çıktılar korundu. Buton artığı ve ölü çeviri anahtarı yok.

Doğrulama: 318 test geçti, 1 atlandı (önceki 304 + 14 hatta çeviri testi);
`compileall` temiz; `pip_audit` bilinen açık bulmadı.

Paket: dist/WordArc-0.6.2.exe + dist/WordArc-0.6.2.bat.
EXE SHA256: 8bf4be59bc2f7e5b50cf031278741a3e63991dbba7d862ba50eff145f6cbcf2b.
Frozen smoke: `WordArc-0.6.2.exe --version` → `WordArc version 0.6.2`
(offscreen, kullanıcı ekranına pencere basılmadan). Çeviri sembolleri
(`TRANSLATE_PROMPT_ACADEMIC/GAME`, `translate_enabled`, hatta `translate`
çağrısı, Türkçe karşılıklar) paketlenmiş PYZ bytecode içinde doğrulandı
(`CArchiveReader` + kod nesnesi taraması).

Yedek 2026-09-29: yerel commit + v0.6.2 etiketi tamamlandı; `origin/master` ve
`v0.6.2` etiketi push edildi, GitHub Release açıldı (uzak sha'lar ve asset
hash'i doğrulandı).

## 0.6.1 — damga tazeleme ve süre logları

- Ayarlar anahtar listesi açık kalan pencerede 5 saniyede bir tazelenir
  (gizlenince durur); işlem sonrası "henüz kullanılmadı" diye takılı kalması
  giderildi. Veride damga doğruydu, ekrana yansımıyordu.
- Dikte hattı transkripsiyon ve temizleme sürelerini loga yazar
  (`transcribe took …`, `cleanup took …`); yavaş temizleme tanısı için.
  0.6.0 sonrası tek başarılı işlem yedek anahtara geçmeden API 1'de
  bitmişti, gecikme API tarafındaydı.
- Rotasyon testleri gerçek kullanıcı ayarındaki sıra durumunu okuyup
  kırılgan hale gelmişti; testler artık sıra durumunu sıfırlayarak kurulur.

Doğrulama: 304 test geçti, 1 atlandı (önceki 302 + 2 yeni test);
`compileall` ve modül yükleme denetimi temiz; `pip_audit` bilinen açık
bulmadı; SBOM yeniden üretildi, değişmedi.

Paket: dist/WordArc-0.6.1.exe + dist/WordArc-0.6.1.bat.
EXE SHA256: 577c605682de6a861b46aaff012bc35f68e55200c48fa1a54e0e5c82d49a52cb.
Frozen smoke: `WordArc-0.6.1.exe --version` → `WordArc version 0.6.1`
(offscreen, kullanıcı ekranına pencere basılmadan). Düzeltme sembolleri
(`_on_usage_tick`, süre logları) paketlenmiş bytecode içinde doğrulandı.

Yedek 2026-09-27: yerel commit + v0.6.1 etiketi tamamlandı; `origin/master` ve
`v0.6.1` etiketi açık yetkiyle push edildi (uzak sha'lar doğrulandı).

## 0.6.0 — API sıralı kullanım (round-robin)

- Birden fazla Gemini API anahtarı varsa her yeni bulut işlemi (dikte,
  toplantı, ses dosyası) sıradaki API ile baştan sona tek slotta çalışır;
  transkripsiyon + temizleme ayrılmaz.
- Sıra `config.json` içinde (`gemini_next_slot` + `gemini_last_used`)
  tutulur; yeniden başlatmada kaldığı yerden devam eder. Başarısız işlem
  damga yazmadan sırayı ilerletir, iptal dokunmaz.
- Bulut kullanılmayan işlem (yerel transkripsiyon + temizleme kapalı) sırayı
  oynatmaz; yerel transkripsiyon + bulut temizlemede temizleme sıraya girer.
- Ayarlar anahtar listesi "API 1..N — son kullanım: gg.aa.yyyy ss:dd:ss /
  henüz kullanılmadı" gösterir; "Varsayılan/Yedek" dili kalktı. Pencere her
  açılışta damgaları tazeler.
- Yedek mesajı giden slotu adıyla söyler ("API 1 yanıt vermedi; API 2
  deneniyor..."); `on_fallback` artık `failed` slotunu da geçirir.

Doğrulama: 302 test geçti, 1 atlandı (önceki 280 + 22 yeni test);
`compileall` ve modül yükleme denetimi temiz; `pip_audit` bilinen açık
bulmadı; SBOM yeniden üretildi, değişmedi. Yeni testler sıra devri/sarma,
damga yazımı, başarısız denemede damgasız ilerleme, yerel kip davranışı,
başlangıç slotu, yedek mesajı ve ayar listesi damgalarını kapsar. Yeniden
başlatmada sıra devamlılığı izole ayarla ayrıca simüle edildi (0→1→2→başa
sarma, hatalı slot damgasız).

Paket: dist/WordArc-0.6.0.exe + dist/WordArc-0.6.0.bat.
EXE SHA256: f6093367c070d9611945478e9bea9a8d2e6968b7c8f46870c53b4d91fe1bcf76.
Frozen smoke: `WordArc-0.6.0.exe --version` → `WordArc version 0.6.0`
(offscreen, kullanıcı ekranına pencere basılmadan). Rotasyon sembolleri
(`claim_api_slot`, `start_slot`, `record_api_success`, damga dizgileri)
paketlenmiş bytecode içinde doğrulandı.

Yedek 2026-09-27: yerel commit + v0.6.0 etiketi tamamlandı; `origin/master` ve
`v0.6.0` etiketi açık yetkiyle push edildi (uzak sha'lar doğrulandı).

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
