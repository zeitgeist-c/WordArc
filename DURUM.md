# WordArc — durum

Güncelleme: 2026-10-16
Hazırlanan paket: 0.8.5 (`brand.py`)
Dal: master
Git dönüş noktası: be82cda / v0.8.4
Yedek 2026-10-16: kompakt gruplu araç çubuğu (B düzeni, Dolu şekillerin yanında),
sürüm 0.8.5; yerel commit + etiket, push/Release bu kapanışta.

## 2026-10-16 — 0.8.5: ekran alıntısı araç çubuğu yeniden düzenlendi

Kullanıcı onayıyla B düzeni uygulandı (alternatifler HTML maketle gösterildi,
"B'yi uygula" seçildi):

- Araçlar ince dikey ayraçlarla dört anlama grubuna ayrıldı: `seçim kalem çizgi
  ok │ dikdörtgen elips DOLU │ vurgu metin adım │ bulanık piksel`. Dolu, yalnız
  şekillerin içini boyadığı için alt satırdan alınıp dikdörtgen/elipsin hemen
  sağına taşındı.
- Alt satır: `renk kalınlık │ geri ileri │ panoya OCR kaydet iptal`; OCR düğmesi
  panoya yapıştır gibi mor zemine alındı.
- Kompakt ölçüler: düğme 30→26 px, ikon 19→17 px, satır aralığı 4→3, kalınlık
  kutusu 58×30→40×26. Araç çubuğu 366×80 → 363×69 (offscreen çekimle ölçüldü ve
  ekran görüntüsüyle gözle doğrulandı).
- 17 özelliğin tamamı korundu; kısayol tuşları ve ipuçları değişmedi. OCR
  yokluğunda gizlenme davranışı aynen duruyor.
- Kapılar: 599 passed, 1 skipped, 12 subtests; `check.ps1 -Audit` temiz.

## 2026-10-16 — 0.8.4 yeniden kesim: ekran alıntısında OCR (metni ayıkla)

Kullanıcı isteği: editör araç çubuğundaki "Dolu" düğmesinin ne olduğu
bilinmiyordu (adlandırma sorunu; ayrıca aşağıda açıklanan OCR eklendi). Ekran
alıntısı editörüne Windows'un kendi tanıma motorunu kullanan **Metni ayıkla
(OCR)** düğmesi geldi:

- Seçili bölgedeki metin tanınır, panoya kopyalanır, tepsi bildirimi gelir;
  okunabilir metin yoksa uyarı bildirimi gösterilir. Motor iş parçacığında
  çalışır; donmuş masaüstü beklerken kilitlenmez.
- Motor `Windows.Media.Ocr` (WinRT): model indirmesi yok, makinede kurulu
  dil paketleriyle tanır. Bu makinede `tr` ve `en-US` doğrulandı; arayüz dili
  Türkçe ise Türkçe tanıyıcı tercih edilir. Projeksiyonlar veya dil paketi
  yoksa düğme hiç görünmez; yakalama akışı etkilenmez.
- Altyapı: `ocr.py` yeni modül; `wordarc.spec` hiddenimports, `check.ps1`,
  `requirements.txt`/`requirements-lock.txt` (winrt 3.2.1) ve paket
  doğrulayıcıya eklendi.
- Build tuzağı: winrt tekerleği kendi `msvcp140.dll` kopyasını taşıyor;
  onnxruntime ile aynı processte çift CRT yüklemesi 0xC0000005 ile çökertiyor
  ve PyInstaller analizini öldürüyor. Spec, analizden önce o kopyayı siliyor
  (Windows System32 ve Qt paketi zaten yeterli kopyayı sağlıyor); matrix testi
  dokuz import sırasının hepsini doğruladı.
- Gerçek kanıt: render edilmiş Türkçe metin `ocr.extract_text` ile uçtan uca
  okundu ("Merhaba Dünya 12345" dahil, Türkçe karakterler korundu).
- Doğrulama: 599 test geçti, 1 atlandı, 12 alt test (yeni: `test_ocr.py`
  motor seçimi/satır birleştirme/uyumsuzluk sarmaları, OCR düğmesi olayı,
  düğmenin gizlenmesi, iplik köprüsü, başarısızlığın `failed` sinyalinden
  yürümesi, pano/uyarı bildirimleri).
- "Dolu" düğmesi dikdörtgen/elips seçiliyken içini yarı saydam renklerle
  doldurur; ipucu metni Türkçe çevirisiyle birlikte araç çubuğunda duruyor.
- Teslim (nihai 0.8.4 kesimi): `dist/WordArc-0.8.4.exe` ve `.bat`.
  EXE SHA256 `244666bd59a19d5bb3f6a4b70976bf2d57b63c57ab24481278edcd32e3a30d15`
  (önceki `d3885d5b…` kesiminin yerini aldı; paketteki `msvcp140` ikizi
  yalnız build ortamından silindi, paketin kendi çalışma zamanı Qt'nin
  taşıdığı kopyadır ve 9 import sırası matrix'i bu EXE ile doğrulandı).
  Canlı doğrulama: `background` açılışı çalıştı → `HKCU Run` girdisi EXE'nin
  kendisini gösteriyor, log v0.8.4 (frozen), UI 2,3 sn.

## 2026-10-16 — 0.8.4 yeniden kesim: tepsi tıklaması, otomatik başlatma varsayılanı, pencere düğmeleri

Kullanıcı isteğiyle üç davranış değişikliği; sürüm numarası değişmeden aynı
0.8.4 yeniden kesildi (kullanıcı açıkça sürüm yükseltmeden yedek istedi):

- Sistem tepsisindeki simgeye sol tık artık kaydı BAŞLATMIYOR; Ayarlar
  penceresini açıyor. Kayıt kısayol tuşuyla veya sağ tık menüsündeki
  "Kaydı başlat" ile yapılıyor.
- "Windows başladığında WordArc'ı başlat" yeni kurulumlarda varsayılan açık.
  Şema 4 → 5 göçü, daha önce hiç kapatmamış eski kurulumları bir kez dahil
  eder; sonra kapatan bir daha açılmaz. Ayar açıksa ve kayıt defteri girdisi
  yoksa açılışta girdi bir kez oluşturulur — kurulan sürümün kendisi bir
  sonraki oturum açılışta Windows'la gelir (`ensure_startup_registration`).
- Ayarlar penceresi `QDialog` varsayılanı olan yalnız-çarpı başlık çubuğu
  yerine küçült ve büyüt düğmeleriyle açılıyor
  (`WindowMinimizeButtonHint | WindowMaximizeButtonHint`).

- Doğrulama: 585 test geçti, 1 atlandı, 12 alt test (yeni: sol tık → pencere,
  diğer tepsi nedenleri hareketsiz, kayıt bir kez + ayar saygısı + hata
  açılışı engellemez, şema 5 göcü ve kapalı kalma, pencere bayrakları);
  `check.ps1` geçti. EXE paketi PYZ/`--version` ile kanıtlanır.
- Aynı `v0.8.4` etiketi ve Release assetleri yeni EXE/BAT ile değiştirildi;
  Release notundaki SHA256 güncel paketle birebir doğrulandı.

## 2026-10-16 — 0.8.4 çoklu monitör yakalama ve gösterge çizimleme kapanışı

Çalışma ağacında biriken iki kaynak düzeltme bu sürümde paketleniyor:
çoklu monitör bölge yakalama (tüm ekranların görüntüsü önce alınır, her
monitörde kendi geometri/DPI katmanı) ve düşük mikrofon seviyesinde
logaritmik -60..0 dBFS gösterge eşlemesi. Kayıt ayrıntıları aşağıdaki iki
kaynak notunda; bu kapanışa kadar `v0.8.3` EXE'si bu iki değişikliği
içermiyordu.

- Sürüm 0.8.3 → 0.8.4 (yalnız düzeltme, patch).
- Doğrulama: tam test kapısı 580 geçti, 1 atlandı, 12 alt test; `check.ps1`
  -Audit dahil geçti. `build.ps1` çıkış 0; `PACKAGE OK` +
  `verify_release_package.py` doğruladı. Pakette `overlay._display_level` ve
  çoklu monitör yolu (`screens`/`grabWindow`) bytecode düzeyinde kanıtlandı;
  gömülü sürüm 0.8.4. İzole teslim EXE'si `--version` ile exit 0
  ("WordArc version 0.8.4"), açılış dahil ~33 sn.
- Teslim: `dist/WordArc-0.8.4.exe` ve `dist/WordArc-0.8.4.bat`.
  EXE SHA256 `d3885d5b98819fc52f459009d666ba9505c54567a19912d91c539ae9671dad1c`.
  Eski 0.8.2/0.8.3 EXE/BAT korundu.
- `master` dalı, 0.8.3 kapanış zincirine (`c34b691`) yumuşak reset ile
  düzeltildi; 0.7.x revert hattının üzerinde lineer tarih yeniden kuruldu.
- GitHub: `origin/master` 0.8.0 öncesi durumdaydı; `master` + `v0.8.4`
  push'u ve EXE/BAT assetli Release bu kapanışla tamamlandı.

## 2026-10-16 — kaynakta düşük mikrofon seviyesinde gösterge görünürlüğü

Kullanıcı evde kutu boyutunun normal, konuşma dalgasının ise şirkettekine
göre küçük olduğunu doğruladı. Yerel ayarda Dalga ve Razer Seiren V3 Mini
seçili. Şirket bilgisayarının mikrofon kazancı/ses örneği ölçülmedi; iki
bilgisayar arasındaki kesin donanım farkı bağımsız doğrulanmış değildir.

Doğrulanan kod sorunu: ham doğrusal PCM tepe seviyesi doğrudan çizime
gidiyordu; Spectrum'ta %1 seviyede yarı yükseklik yaklaşık 2,48 piksel.
Gösterge girdisi artık sabit -60..0 dBFS aralığında logaritmik eşleniyor.
%1 ve %10 giriş, görünüm için sırasıyla 1/3 ve 2/3 seviyeye karşılık gelir.
Kaydedilen PCM, mikrofon kazancı, ses tanıma/VAD ve kutu boyutu değişmez;
sessizlik ve sonlu olmayan değerler sıfır gösterilir. Her dört biçim ile
toplantının iki kanalı aynı eğriyi kullanır; ayar önizlemeleri zaten görünüm
seviyesi ürettiği için yeniden eşlenmez.

- Doğrulama: 580 test geçti, 1 atlandı, 12 alt test geçti. Düşük girişte
  gerçek şerit çizimi, sessizlik, artan seviye sırası ve çift kanal kontrolü
  var. Sentetik önce/sonra görseli `.cache/ui-tests/meter-comparison.png`.
- Önceki çoklu monitör kaynak değişiklikleri korundu. Sürüm 0.8.3 kaldı;
  yeni EXE/BAT, commit veya etiket oluşturulmadı. Mevcut EXE bu düzeltmeyi
  henüz içermez. Gerçek şirket/ev mikrofonlarıyla karşılaştırmalı kabul yok.

## 2026-10-16 — kaynakta çoklu monitör yakalama düzeltmesi

Kullanıcı bildirimi: bölge yakalama yalnız kısayola basıldığı sıradaki ekranı
hazırlıyor, diğer monitörde seçim için iptal/yeniden başlatma gerekiyordu.
Artık bütün bağlı ekranların görüntüleri önce alınır; her monitörde kendi
geometrisine/DPI'ına bağlı bir seçim katmanı açılır. Başka ekranda seçim
yapmak aynı oturum içinde mümkündür; önceki seçim çubuğu gizlenir.
Kopyalama, kaydetme, Esc, hata veya monitör çıkarma bütün katmanları temizler.
Bu akış herhangi bir monitörde seçim yapmayı sağlar; monitör sınırlarını aşan
tek dikdörtgen seçimi bu düzeltmenin kapsamında değildir. Aktif ekran/pencere
yakalama modlarının kapsamı korunmuştur.

Gerçek ekran görüntülerinin DPR metadatası çizim sırasında ikinci ölçek
uyguluyordu; fiziksel piksel tuvalinin DPR'ı normalleştirildi. 100/125/150/200
yüzde ölçek, negatif ekran konumu ve yukarı yerleşim sentetik testlere alındı.
Yerel Qt envanteri iki monitör gördü: 2560×1440 / %125 ve solda 1920×1080 / %100.
Bu envanter gerçek yakalama/elle kabulün kanıtı değildir.

- Doğrulama: 568 test geçti, 1 atlandı, 12 alt test geçti; py_compile ve
  diff boşluk kontrolü başarılı. 2/3/4 monitör oturumu, ekran değiştirme,
  çözünürlük/renk korunması ve toplu kapanış otomatik doğrulandı.
- Durum: kaynak düzeltmesi; sürüm değişmedi, yeni EXE/BAT, commit veya etiket
  oluşturulmadı. Önceki `v0.8.3` ve teslim EXE'si bu yeni değişikliği içermez.

## 2026-10-16 — 0.8.3 kompakt yakalama ve kısayol kalitesi

Önceki turda hazırlanan simgeli araç çubuğu, yerinde düzenleme ve bas-ata
kısayol değişiklikleri bu sürüme dahil. LightShot/ScreenForge/ShareX/Flameshot
resmi belgeleriyle karşılaştırma ve kapsam: `docs/screenshot-quality-0.8.3.md`.

- Ctrl+A tam ekran seçimi; araç tuşları; oklarla hassas seçim taşıma;
  geri alınabilir Shift+Delete temizleme ve geçmiş durumuna uygun düğmeler.
- Bulanıklaştırmada özgün detay geri karıştırılmıyor; işlemler çizim sırasına
  uyuyor. Kaydet penceresi üstteki editöre bağlı; iptalde çizimler korunur.
  Saydam JPEG beyaz zemine aktarılır.
- Pause/medya/gezinme/numpad/F13–F24 ve tek tuş atama. Eşdeğer genel
  kısayolların çakışması ayarları değiştirmeden reddedilir. Atama sırasında
  genel kayıt iptal tuşu da askıya alınır.
- Tam test kapısı: 561 test geçti, 1 atlandı, 6 alt test geçti.
  Yerel Windows kayıt/WM_HOTKEY/temizleme yolu iki ardışık geçici kayıtta geçti.
- Sınırlar: gerçek çoklu monitör/karma DPI ve fiziksel tuşla masaüstü kabulü
  yapılmadı. Pause başka programda kayıtlıysa mevcut çakışma bildirimi geçerli.
- Resmi `build.ps1` test/compile/import/bağımlılık/paket kapıları geçti;
  bağımlılık denetiminde bilinen açık yok. EXE içinde güncel sürüm, kaynak
  bytecode'u (hotkey/paste dahil), CUDA ve native payload hash'leri doğrulandı.
  İzole teslim EXE'si `--version` ile exit 0 verdi; çıkarma dahil 25,787 saniye.
- Teslim: `dist/WordArc-0.8.3.exe` ve `dist/WordArc-0.8.3.bat`.
  EXE SHA256 `1aa837c88204d0b9b873b1b7548e313dad9c2c8dd96f105e220c9159e32d5aa8`.
  Önceki 0.8.2 EXE/BAT korundu.
- Yerel yedek 2026-10-16: kaynak ve sürüm otomasyonu commit `908fad7`;
  `v0.8.3` aynı commit'e bağlı. Önceki kaynak değişiklikleri dahil edildi.
- GitHub yedeği tamamlanmadı: otomatik onay denetimi
  `zeitgeist-c/WordArc` için `master` + `v0.8.3` push ve EXE/BAT Release
  aktarımını, bu hedefler için ayrıca açık kullanıcı onayı gerektiği
  gerekçesiyle reddetti. Dış aktarım/yayın yapılmadı; kullanıcı onayı bekliyor.

## 2026-10-16 — kaynakta kompakt yakalama çubuğu ve kısayol düzeltmesi

Yakalama çubuğu 366 × 80 mantıksal piksel boyutunda, iki sıralı simge
düğmeleriyle düzenlendi. Araç adları/işlem kısayolları ipuçlarında; seçili
araç ve renk görünür. Dört ekran köşesinde yerleşim kontrol edildi.
Ortak `HotkeyEdit` Pause, tek harf, gezinme/medya tuşları, F13–F24 ve
sayısal tuş takımını kabul ediyor. Atama yalnız KeyPress'te, bir kez yapılır;
dinleme biter. Esc, odak kaybı veya gizlenme tamamlanmamış atamayı geri alır.
Backspace/Delete temizler; değişiklik Ayarlar'daki Kaydet ile uygulanır.

- Doğrulama: 552 test geçti, 1 atlandı, 6 alt test geçti; py_compile ve
  diff boşluk kontrolü başarılı. Arayüz offscreen görüntüyle incelendi.
- Windows yerel kaydında Pause için hata 1409 (başka uygulamada kayıtlı),
  kontrol kombinasyonu Ctrl+Alt+Shift+F10 için başarılı kayıt/kaldırma görüldü.
  Fiziksel tuşla uçtan uca masaüstü denemesi yapılmadı.
- Bu kayıt kaynak düzeltmesidir; yeni sürüm/EXE, commit veya etiket üretilmedi.
  Başlangıçtaki kaydedilmemiş çalışma korundu; aşağıdaki 0.8.2 paket kanıtı
  bu yeni kaynak değişikliklerinin paketlendiği anlamına gelmez.

## 2026-10-16 — 0.8.2 ekran editörü ve bas-ata kısayollar

Ekran önizlemesinde düzenleme araçları eklendi: dikdörtgen/elips, ok, çizgi,
kalem, vurgulama, bulanıklaştırma/pikselleştirme, numaralı adım badge ve metin;
renk/kalınlık, geri al, çizimi sıfırla. Etkin pencere yakalama (`window` modu)
desteği ve Ayarlar sekmesine "Etkin pencereyi yakala" düğmesi eklendi.
Kısayol kutuları artık önceden tanımlı listeden değil, alana tıklayıp tuşlara basarak atanıyor
(`HotkeyEdit`); geçersiz kombinasyon reddediliyor, `×` temizliyor.

- Derin araştırma: vault'da `50 - Kaynaklar/Arastirma/2026-10-16-wordarc-ekran-alinti-onderme/report.md`.
- `screenshot_editor.py` yeni modül; wordarc.spec hiddenimports'a eklendi.
- `tools/verify_release_package.py` geçti; pakette `screenshot_capture` ve
  `screenshot_editor` mevcut.
- Son doğrulama: 518 test geçti, 1 atlandı; `check.ps1` ✅.
- Teslim: `dist/WordArc-0.8.2.exe` ve `dist/WordArc-0.8.2.bat`.
  EXE: SHA256 `d091fd3be51f618b97572f63e601184b91d0f56d17dc02bbf1c06bb324d050c4`.
  Paket `--version`: `WordArc version 0.8.2`.

Yedek 2026-10-16 tamamlandı: kaynak commit `3c2d9c7`, `v0.8.2` etiketi aynı
commit'e bağlı, `origin/master` ile eşit. GitHub Release:
https://github.com/zeitgeist-c/WordArc/releases/tag/v0.8.2 — EXE/BAT asset'leri
yüklendi, SHA256 değerleri yerel teslim dosyalarıyla eşleşti.

## 2026-10-16 — 0.8.1 seçimde ayarlama ve ekran üstü araç çubuğu

Ekran görüntüsü seçimi bırakınca direkt alınmıyor; seçim ekranda kalıyor.
8 tutamaçla boyutlandırma, içinden sürükleyerek taşıma, seçim altında
Kopyala/Kaydet/İptal çubuğu. Onay çift tıklama veya Enter (önizlemeye gider);
Esc/sağ tık iptal; Ctrl+C / Ctrl+S hızlı kopyalama/kaydetme. Kaydetme mantığı
önizlemeyle tek fonksiyonda birleşti; klasör/biçim tercihi iki yolda da
hatırlanıyor. Seçim ekran dışına taşmıyor.

- Son doğrulama: 512 test geçti, 1 atlandı; `check.ps1`, `compileall`, import
  kontrolü başarılı. Overlay offscreen görüntüyle gözle de doğrulandı
  (tutamaklar, ölçü etiketi, araç çubuğu).
- Teslim: `dist/WordArc-0.8.1.exe` ve `dist/WordArc-0.8.1.bat`.
  EXE: 1.581.470.559 bayt; SHA256
  `745fd31457a30b874db2da3b61c6891933d65a966098aa36d51b84d7cc0f2d3b`.
  Paket `--version`: `WordArc version 0.8.1`.
- Sınırlar: ok/dikdörtgen/metin çizimi ve bulanıklaştırma yok; gerçek
  masaüstünde elle deneme yapılmadı.

Yedek 2026-10-16 tamamlandı: kaynak commit `7efa3be`, `v0.8.1` etiketi aynı
commit'e bağlı ve `origin/master` ile eşit. GitHub Release:
https://github.com/zeitgeist-c/WordArc/releases/tag/v0.8.1 — EXE/BAT
asset'leri yüklendi, SHA256 değerleri yerel teslim dosyalarıyla eşleşti.

## 2026-10-15 — 0.8.0 ekran görüntüsü sekmesi

WordArc Ayarları'na ekran görüntüsü yakalama sekmesi eklendi. Bölge seçimi, aktif ekranın tamamını yakalama, önizleme, panoya kopyalama ve PNG/JPEG kaydetme; yapılandırılabilir global kısayol ve kayıt klasörü/biçim tercihleri mevcut.

- Kısayol: `Ctrl+Alt+S`.
- Varsayılan klasör: Windows `Pictures` (Resimler) bilinen klasörü altındaki `WordArc`.
- Lightshot sitesi ve ScreenForge 1.2.8 Windows portable paketi REA ve statik kaynak incelemesiyle incelendi. ScreenForge'un yakalama türü yayımlanan .NET DLL'indeki sanal ekran boyutları, GDI `BitBlt`, imleç çizimi ve kırpma üyelerinden gözlendi. Lightshot installer indirme sunucusu indirmeyi engelledi; Lightshot paket davranışı incelenemedi.
- Son doğrulama: 509 test geçti, 1 atlandı; `check.ps1`, `compileall`, import kontrolü ve PyInstaller frozen package gate başarılı. Paket `--version`: `WordArc version 0.8.0`; gate'in başlangıç süresi 11.523 sn.
- Teslim: `dist/WordArc-0.8.0.exe` ve `dist/WordArc-0.8.0.bat`. EXE: 1.581.464.377 bayt; SHA256 `ec9774647b681f685cea4e69767241f1260522fd44ed1a662dd6e2596a4a9db5`.
- Gerçek ekran seçimi ve global kısayol etkileşimi EXE içinde elle doğrulanmadı; otomatik testler alan kırpma, DPI ölçekleme, önizleme, panoya kopyalama, PNG/JPEG yazımı ve paket içindeki modülü doğruluyor.

EXE içindeki `screenshot_capture` kaynak kodu paket kapısında kaynakla karşılaştırıldı; modül frozen PYZ'de mevcut. Paket `--version` bağımsız çalıştırması da başarılı.

Yedek 2026-10-15 tamamlandı: commit `1030580160df3a388bd9f669d28cdec594551135`, `v0.8.0` etiketi aynı commit'e bağlı ve `origin/master` ile eşit. GitHub Release: https://github.com/zeitgeist-c/WordArc/releases/tag/v0.8.0 — EXE/BAT asset'leri yüklendi, SHA256 değerleri yerel teslim dosyalarıyla eşleşti.

## 2026-10-15 — 0.7.3 geri alındı, 0.7.2'ye dönüldü

Kullanıcı gömülü Hermes tetikleyiciyi beğenmedi; 0.7.3 (özellik + 3 düzeltme,
a3dacab ve 8ce2214) geri alındı, kaynak 0.7.2 durumuna döndü. 0.7.3 kayıtları
geçmiş bilgi olarak aşağıda duruyor; paket ve etiket 0.7.2'yi gösterir.

- `v0.7.3` etiketi (yerel + uzak) ve GitHub Release v0.7.3 silindi.
- dist içindeki 0.7.3 çıktıları silindi; 0.7.2 aynı kaynaktan yeniden
  paketlendi.
- AutoHotkey kaldırma geri alınmadı (ayrı onaylı temizlikti); genel
  Shift+Space tetikleyici yok. Hermes odaktayken kendi Shift+Space diktesi
  çalışır; genel kısayolu kullanıcı kendi eliyle halledecek.

---

Geri alınmış `0.7.3` ve eski sürüm kayıtları aşağıdadır.

Güncelleme: 2026-10-15
Hazırlanan paket: 0.7.2 (`brand.py`)
Dal: master
Git dönüş noktası: 6f1ca43 / v0.7.1

## 2026-10-15 — 0.7.3 geri alındı, 0.7.2'ye dönüldü

Kullanıcı gömülü Hermes tetikleyiciyi beğenmedi; 0.7.3 (özellik + 3 düzeltme,
a3dacab ve 8ce2214) geri alındı, kaynak 0.7.2 durumuna döndü. 0.7.3 kayıtları
geçmiş bilgi olarak aşağıda duruyor; paket ve etiket 0.7.2'yi gösterir.

- `v0.7.3` etiketi (yerel + uzak) ve GitHub Release v0.7.3 silindi.
- dist içindeki 0.7.3 çıktıları silindi; 0.7.2 aynı kaynaktan yeniden
  paketlendi.
- AutoHotkey kaldırma geri alınmadı (ayrı onaylı temizlikti); genel
  Shift+Space tetikleyici yok. Hermes odaktayken kendi Shift+Space diktesi
  çalışır; genel kısayolu kullanıcı kendi eliyle halledecek.

## 2026-10-15 — 0.7.3 Hermes tetikleyici gömüldü, AutoHotkey kalktı

Ayrı çalışan AutoHotkey yardımcısı (`hermes-dictate-hotkey.ahk`: Shift+Space
ile Hermes'i öne getirip dikteyi açıyordu) WordArc'ın içine taşındı; ayrı
program ve kısayol çakışması bitti.

- Yeni `hermes_trigger.py`: Hermes penceresini bulur (başlık + Hermes.exe
  denetimi), öne getirir, Hermes'in dikte tuşuna basar. Başarısızlık WordArc
  kaydını etkilemez, yalnız bilgi verilir.
- Hermes'in kendi kısayolu da Alt+Space olur (Hermes Ayarları → Klavye →
  "Start / stop dictation"); WordArc artık Alt+Space gönderir. İkisi birlikte
  geçmeli, yoksa tetikleme çalışmaz.
- Ayarlar → Başlangıç kartında "Hermes diktesi" kısayolu: varsayılan
  Alt+Space, seçilebilir; boş bırakılırsa tetikleyici kapalı. WordArc'ın
  kendi Ctrl+Space diktesi aynı.
- Not: Alt+Space Windows'ta pencere menüsünü de açar; WordArc çalışırken bu
  menü gelmez. Kullanıcı bu tuşu kullanmıyor.
- `check.ps1` import kapısı yeni modülü de denetliyor.

Resmi kapılar: 508 test geçti, 1 atlandı; compile/import temiz.

Teslim: dist/WordArc-0.7.3.exe ve dist/WordArc-0.7.3.bat.
EXE: 1.581.456.101 bayt; SHA256:
af2845c691580c3eb087dbbe4b3f2dd1d0aff0470e64996baff612244726d6bf.
Paket kapısı --version duvar saati 23,674 saniye; `hermes_trigger` modülü
gömülü PYZ'de kanıtlı.

Yedek 2026-10-15: kaynak commit'i + DURUM kaydı `origin/master`'a push;
`v0.7.3` etiketi aynı commit'te; GitHub Release v0.7.3 assetleri (EXE+BAT).

## 2026-10-15 — 0.7.3 aynı sürüm üzerine yeniden yapı (3 hata düzeltmesi)

Kullanıcı 0.7.3'te üç arıza bildirdi; üçü de doğrulandı, kök nedenler kapatıldı.
Sürüm numarası değişmedi, aynı adla yeniden paketlendi.

- Kaydet çöküyordu, kayıt başlamıyordu: Ayarlar penceresi sekmeleri
  çalışma alanına yeniden dizerken Hermes satırı yeni karta alınmamıştı;
  silinen kutuya dokunan `_save` `RuntimeError` veriyor, kayda basmak önce
  sessiz kaydetmeyi denediği için kayıt da açılmıyordu. Satır yeni Dikte
  kartına taşındı (`shortcut_pair` ile birlikte).
- Ayarlar'da Hermes satırı görünmüyordu: aynı kök neden; satır silinen
  kartta kalmıştı. Artık Başlangıç kartında "Kısayol | Hermes diktesi" yan
  yana, ikisi de seçilebilir; yükseklik tek kısayolla aynı, 920x700 dahil
  kayma yok (yerleşim kapısı yeşil).
- Alt+Space Hermes'i küçültüyordu: iki üst üste sorun. Hermes'in kendi
  kısayolu hâlâ Shift+Space idi, giden Alt+Space sistem menüsünü açtı. Ayrıca
  WordArc Hermes'i öne getiremeyince bile tuşu gönderiyordu. Artık öne
  getirme `AttachThreadInput` ile güçlendirildi; getirilemezse tuş
  GÖNDERİLMİYOR, bilgi veriliyor ("Hermes öne getirilemedi").
- Başlangıç klasöründe ölü `HermesDikteHotkey.vbs` ve kurulum betiği de
  silindi; yeniden başlatmada hata vermeyecek.

Resmi kapılar: 511 test geçti, 1 atlandı; compile/import temiz. Yeni
regresyon testleri: çalışma-alanı yıkımında Hermes kısayolunun sağ kalması,
öne getirme başarısızken tuş gönderilmemesi, gönderilen tuşun Alt+Space
olması.

Teslim: dist/WordArc-0.7.3.exe ve dist/WordArc-0.7.3.bat (aynı adla üzerine
yazıldı). EXE: 1.581.457.754 bayt; SHA256:
05f1dc89f49158805ec4e60b7377e0cdbd0a9e30fd49903ebbdd6a7a19aca925.
`hermes_trigger` (NOT_FORWARD + Alt gönderimi) gömülü PYZ'de kanıtlı.

Yedek 2026-10-15 (aynı sürüm): kaynak commit'i + DURUM kaydı
`origin/master`'a push; `v0.7.3` etiketi yeni yapı commit'ine taşındı;
GitHub Release v0.7.3 assetleri (EXE+BAT) yenileriyle değiştirildi. Önceki
yapı (af2845c6… artefaktı) artık geçerli değil.

## 2026-10-15 — 0.7.2 yeniden yapı: her biçim kendi çizimini yapıyor, canlı seviye pakette

Kullanıcı dört biçimin şeritte aynı göründüğünü bildirdi. İki ayrı sorun
vardı: (1) Spectrum ile Capsules çizimi %88 aynıydı — seçim gerçekten bir şey
değiştirmiyordu; (2) karşılaştırma görüntüsü yanıltıcıydı, çünkü `set_meter`
modül geneli: dört şerit aynı anda yakalanırken hepsi son stille çiziliyordu.
Ayrıca canlı seviye düzeltmesi (`86521de`) önceki teslim EXE'sine girmemişti
(EXE 11:11, düzeltme 12:00), bu yüzden gösterge konuşurken hareket etmiyordu.

- `overlay._draw_meter_into` dört biçimin tek çizim kaynağı oldu; kayıt
  şeridi, toplantının iki yarısı ve Ayarlar önizlemeleri aynı fonksiyondan
  geçiyor. Toplantı görünümü artık dalga seçiliyken gerçekten dalga çiziyor.
- Ayarlar > Arayüz: her biçimin canlı önizlemesi seçeneğin yanında; seçili
  olan çerçeveli. Ad tek başına anlatmadığı için önizleme şarttı. Çerçeve
  açılışta da çizilir: kayıtlı biçim listenin ilk maddesi (Çubuklar) olsa
  bile `_load()` bir kez boyar. Önizleme animasyonu yalnız görünürken çalışır.
- Ölü çizim kodu kaldırıldı (`_bars`, `_bar_colour`, `_draw_waveform`,
  `_draw_dual_waveform`, `_draw_dual_rounded`, `_meter_geometry`).
- Testler çizimi sabit tuvale doğrudan verip yapısal imza ölçüyor; dar
  şeritte (170 px) ve toplantıda da dört imza ayrışıyor. `tests/test_settings_meter.py`
  seçim turunu, açılıştaki çerçeveyi ve önizlemelerin ayrı çizildiğini korur.
- `tools/verify_release_package.py` artık `overlay` modülünü de kaynakla
  karşılaştırıyor; paketin bu çizimleri taşıdığı kanıtlı.

Resmi kapılar: 500 test geçti, 1 atlandı; compile/import ve pip-audit temiz.

Teslim: dist/WordArc-0.7.2.exe ve dist/WordArc-0.7.2.bat (aynı sürümün üzerine
yazıldı; sürüm numarası değişmedi). EXE: 1.581.341.166 bayt; SHA256:
785db446711f5261956b8c9bddad36e61d422d228d010edc315529900165d56c.
Paket kapısı --version duvar saati 12,693 saniye; gömülü kaynak denetlenen
modüllerle birebir eşleşiyor.

Yedek 2026-10-15: aynı sürümün üzerine yazıldı — kaynak commit'i + DURUM
kaydı `origin/master`'a push; `v0.7.2` etiketi yeni yapı commit'ine taşındı;
GitHub Release v0.7.2 assetleri (EXE+BAT) yenileriyle değiştirildi.
Önceki yapılar (672d9dfd… ve 531fe4c4… artefaktları) artık geçerli değil.

## 2026-10-15 — 0.7.2 seçilebilir ses dalgası, canlı metin şeritten kalktı

Kullanıcı canlı diktede şeritte akan metni istemedi: diğer kayıtlar gibi ses
göstergesi görünsün dedi. Ayrıca göstergenin daha modern olmasını ve biçimin
Ayarlar'dan seçilebilmesini istedi.

- Akan ara metin şeritten kaldırıldı. Kayıt sürerken yalnızca ses göstergesi
  ve süre çizilir; metin kayıt bitince temizlenip yapıştırılır.
  `show_live_text()` çağrısı korunur ama artık metni çizmez.
- Dört dalga biçimi eklendi; Ayarlar → Uygulama → "Ses dalgası biçimi":
  Çubuklar (eski), Frekans (yeni varsayılan; yuvarlak, yükseklikle parlayan
  çubuklar), Dalga (tek akıcı dolgu + parlak tepe çizgisi), Kapsüller (kalın
  yuvarlak, dikey renk geçişi). Seçim kaydedilince anında uygulanır.
- Toplantı görünümü de seçilen biçimle çizilir (sen üstte kırmızı, karşı
  taraf altta mavi). Şerit boyutu değişmedi; kompakt kalır.
- Biçim sözleşmesi piksel testiyle bağlandı: dört biçimin çizimi birbirinden
  farklı olmak zorunda (tests/test_overlay_meter.py).

Resmi kapılar: 485 test geçti, 1 atlandı; compile/import ve pip-audit temiz.

Teslim: dist/WordArc-0.7.2.exe ve dist/WordArc-0.7.2.bat.
EXE: 1.581.448.337 bayt; SHA256:
672d9dfd333e813467a25cda53fac9b4b9972a41877eb8b66c5db3b9b8cfebf8.

Paket kapısı ilk koşuda geçti. Teslim EXE --version duvar saati 11,868
saniye (çıkarma dahil); soğuk/ilk açılış için garanti değildir. Gömülü ana
kod ve denetlenen modüller kaynakla birebir eşleşiyor. Önceki 0.7.1, 0.7.0
ve 0.6.12 teslim dosyaları korundu.

Yedek 2026-10-15: kaynak/sürüm/build kaydı yerel sürüm commit'i + v0.7.2;
origin/master ve v0.7.2 push ile uzak kaynak yedeği.

## 2026-10-15 — 0.7.1 canlı dikte düzeltmeleri

Kullanıcı 0.7.0'ı gerçek kullanımda denedi ve üç sorun bildirdi; üçü de
kaynakta doğrulanıp düzeltildi.

- **Canlı ara metin hiç çizilmiyordu.** Overlay kayıt sürerken yalnızca
  seviye çubuklarını boyuyordu; `show_live_text()` ile gelen metin yalnızca
  "busy" durumunda görünen alana yazılıyordu. Piksel ölçümü kanıtladı
  (metin bölgesinde 0 parlak piksel). Artık şeridin üst satırı konuşulanı
  akıtıyor, seviye çubukları altında kalıyor, şerit uzun cümlede genişliyor.
- **Motor seçim listesi alttan taşıyordu.** Popup yüksekliği sabit 34 px
  satır varsayımıyla hesaplanıyordu; satırlar gerçekte daha yüksek çiziliyor
  ve son satır kırpılıyordu. Artık satırlar `sizeHintForRow()` ile ölçülüyor,
  liste çerçevesi/arama kutusu payı ayrı ekleniyor.
- **Ölü C++ nesnesi çökmesi (access violation).** Seçici popup kapanırken
  `destroyed` sinyali silinmiş nesneye dokunuyordu; tam süit bunu yakaladı.
  Yaşam döngüsü tek noktaya (`_close_picker` / `_live_picker`, `sip.isdeleted`)
  alındı; seçim ve Escape yollarında referans temizleniyor.
- Canlı motorun modeli seçilemez olduğu artık ayarlarda yazıyor:
  "Canlı, gemini-3.5-transcribe-live kullanır; değiştirilemez. Ardından
  metni, 'Transkripti temizleme' altındaki model düzenler." Motor kutusunun
  ipucu üç seçeneğin farkını anlatıyor. (Kullanıcının gördüğü "46 model"
  temizleme listesidir, transkripsiyonla ilgisi yok.)

Resmi kapılar: 480 test geçti, 1 atlandı; compile/import ve pip-audit temiz.

Teslim: dist/WordArc-0.7.1.exe ve dist/WordArc-0.7.1.bat.
EXE: 1.581.446.380 bayt; SHA256:
15fa65a6a9ac5651758e7f2b9e7f415d370aa0fc6cb4199f4c56583b200ae0ce.

Paket kapısı ilk koşuda geçti. Teslim EXE --version duvar saati 17,832
saniye (çıkarma dahil); soğuk/ilk açılış için garanti değildir. Gömülü ana
kod ve denetlenen modüller kaynakla birebir eşleşiyor. Önceki 0.7.0 ve
0.6.12 teslim dosyaları korundu.

Yedek 2026-10-15: kaynak/sürüm/build kaydı yerel sürüm commit'i + v0.7.1;
origin/master ve v0.7.1 push ile uzak kaynak yedeği.

## 2026-10-15 — 0.7.0 Gemini Live üçüncü motor

Ayarlardaki "Nerede çalışsın" seçimine üçüncü motor eklendi: Canlı (Gemini).
Konuşurken ara metin kayıt şeridinde akar; durunca metin temizlenip yapışır.
Bulut (REST) ve yerel (Whisper) aynen durur. Dosya ve toplantı yazımı live
seçiliyken bile REST buluttan yapılır (canlı oturum mikrofona aittir).

- Yeni `livespeech.py`: stdlib websocket ile `BidiGenerateContent`
  (`gemini-3.5-transcribe-live`), Smart/Birebir modu, 8 dk yumuşak sınır,
  iptal, API sıra failover'ı, hata metninde anahtar sızdırmazlığı.
- `audio.py` yanına `LiveStreamer` (100 ms PCM, WAV yok); overlay'e
  `show_live_text`; worker'a kayıtsız `run_transcript` girişi.
- Başlat/durdur/iptal live'a dallanır; API sıra damgası (başarı/deneme)
  korunur. Kapanışta oturum ve yakalama kapatılır.
- Paket kapısı `livespeech` modülünü de denetler (TOC + kaynak eşleşmesi);
  `check.ps1` import listesine eklendi.
- Resmi kapılar: 471 test geçti, 1 atlandı; compile/import, pip-audit temiz.
  Gerçek ağ turu sahte anahtarla doğrulandı (sunucu reddetti, sızıntı yok).
  Gerçek mikrofonla canlı sesli prova yapılmadı.

Teslim: dist/WordArc-0.7.0.exe ve dist/WordArc-0.7.0.bat.
EXE: 1.581.444.238 bayt; SHA256:
578f0ff40aee1ddde9618394b7192ada5cdbe769c82c05d48f9d9cdeeda14dac.

Paket kapısı ilk koşuda geçti. Teslim EXE --version duvar saati 15,823
saniye (çıkarma dahil); soğuk/ilk açılış için garanti değildir. Gömülü ana
kod ve denetlenen modüller kaynakla birebir eşleşiyor. Önceki 0.6.12 teslim
dosyaları korundu.

Yedek 2026-10-15: kaynak/sürüm/build kaydı yerel sürüm commit'i + v0.7.0;
origin/master ve v0.7.0 push ile uzak kaynak yedeği.

## 2026-10-12 — 0.6.12 açılış kartı ve arayüz beklemesi

Kullanıcı açılış kartının kenarlarının kırpıldığını ve açılışın yavaş olduğunu
bildirdi; ardından 0.6.12 EXE/BAT, commit, push ve yedek kapanışını yetkilendirdi.

- HiDPI çizimde ikinci ölçek kaldırıldı; ışık efekti yuvarlak karta kırpıldı,
  saydam pencere arka planı etkinleştirildi. Logo/yazı tasarımı korundu.
- Ana akışın eşzamanlı aygıt yoklaması kaldırıldı; ayarlardaki GPU/model
  incelemesi arka planda çalışır, Qt sinyaliyle sonuçları gösterir. Kontrol
  sürerken pencere ve motor seçimi kullanılabilir. İndirme/silme ve CPU
  kurtarma sonrasında model durumları yenilenir.
- UI hazırlık süresi loglanır; EXE çıkarma ve import aşamaları ayrı tutulur.
- Paket kapısı artık ana wordarc.py kodunun da kaynakla eşleşmesini ve QtSvg
  modülünü denetler. Büyük paketin ilk çalıştırılması için sınır 120 saniye;
  --version duvar saati ölçümü raporlanır.
- Resmi kaynak kapısı: 427 test geçti, 1 ağ testi atlandı; compile/import ve
  bağımlılık güvenlik denetimi geçti. Önceki sandbox pano erişim engeli bu
  sürümün yetkili test koşusunda tekrarlanmadı.

Yavaş sürücü taklidinde görünür pencere hazırlığı 0,739 / 0,025 saniye (önce /
sonra). Bu toplam EXE açılış ölçümü değildir; tek dosyalı büyük paketin geçici
klasöre çıkarma maliyeti devam eder. İnceleme: docs/startup-2026-10-12.md.

Teslim: dist/WordArc-0.6.12.exe ve dist/WordArc-0.6.12.bat.
EXE: 1.582.662.700 bayt; SHA256:
c952cbb957df9d7ce632b2ce8a9702c8ad1a05ebd34b5d724effce8a1e52bd02.

İlk build akışının son paket kapısı başarısız döndü; kaynak değiştirilmeden
bağımsız kapı tekrarlandı ve exit 0 ile geçti. Tekrar koşusunda gerçek EXE
--version duvar saati 13,144 saniye (çıkarma dahil); soğuk/ilk açılış için
garanti değildir. Gömülü ana kod ve modüller kaynakla birebir eşleşiyor.
Aynı teslim EXE'si resmi JFK örneğini gerçek AMD Vulkan ve GGML CPU yolunda
çözdü; metinler aynı, GPU koşusunda fallback yok. Başka Windows makinesi,
gerçek NVIDIA CUDA ve bu sürümün canlı mikrofon kabulü ayrıca doğrulanmadı.

Yedek 2026-10-12: kaynak/sürüm/build kaydı yerel sürüm commit'i + v0.6.12;
origin/master ve v0.6.12 push ile uzak kaynak yedeği. GitHub Release
yayımlanmadı. Önceki 0.6.11 teslim dosyaları korundu.
Kanıtlar: build/release-0.6.12-package.log,
build/release-0.6.12-verification.log ve build/release-0.6.12-gpu-cpu.json.

## 2026-10-07 — 0.6.11 Vulkan yoklama dayanıklılığı + açılış WIP'i

Kullanıcı oyun oynarken kart çalışmasına karşın program "Vulkan
bulunamadı" dedi. Logda 18:06'da paketlenmiş yoklamanın 15 sn'de zaman
aşımına uğradığı, boş sonucun `lru_cache`'te oturum boyu yapışıp kaldığı
görüldü; 19:12'de CPU'ya düşüldü (10,9 sn ses 43,8 sn'de yazıldı).
Kart/sürücü sağlamdı (`vulkaninfo` + elle yoklama RX 6650 XT'yi ~8 GB
ile buldu). Tetikleyici: Steam + RTSS implicit Vulkan katmanları ve oyun
yükü altında cihaz açılışının kilitlenmesi.

- `vulkan_speech.devices()`: `lru_cache` kalktı; yalnız başarılı sonuç
  5 dk önbellekte, boş sonuç bir sonraki çağrıda yeniden deneniyor
  (çağrı başına 2 deneme).
- `process_options()`: native alt süreçlerde
  `VK_LOADER_LAYERS_DISABLE=~implicit~`; overlay kancaları yoklama ve
  yazı-döküm çocuklarına girmiyor.
- WIP (kullanıcı onayıyla dahil): açılış splash'i ("WordArc
  açılıyor…"), kayda basışta sessiz ayar kaydı (banner+ses yalnız
  Kaydet düğmesinde), launcher tek-açılış guard'ı.
- Testler: 421 geçti, 1 atlandı; pip audit temiz; SBOM üretildi.

Teslim EXE kabulü (izole scratch, resmi JFK örneği, large-v3-turbo):
Vulkan RX 6650 XT fallbacksuz çalıştı, CPU çıktısıyla birebir aynı
metin. Kanıt: build/release-0.6.11-gpu-cpu.json.
Not: build içindeki ilk paket kapısında `--version` 30 sn'yi aştı
(1,5 GB link sonrası ilk açılış + tarama yükü); pakette sorun yok —
elle koşu ve bağımsız kapı yeşil.

Teslim: dist/WordArc-0.6.11.exe ve dist/WordArc-0.6.11.bat.
EXE: 1.581.292.593 bayt; SHA256:
aa30b1a6aa68262137a0a24f12f330aad4df14c48f3a303e4c31269e93627c9c.
Kaynak/sürüm/test değişiklikleri yerel sürüm commit'i ve v0.6.11 ile
kaydedilir; push/release yedek yetkisiyle yapılır. Önceki teslimler korunur.
Kapanış talimatı: tepsiden Çık, bat ile aç, sürümü Ayarlar'dan veya
`--version` ile doğrula.

## 2026-10-03 — 0.6.10 kaydet yavaşlığı düzeltmeleri

Kullanıcı Kaydet'in çok uzun sürdüğünü bildirdi. Darboğaz + performans
akışıyla `_save()` hot path'i profillendi: 3 tur 64ms ölçümde %76
`credential_store.write_all` çıktı; anahtarlık değişmemişken bile her
kaydetmede ~20 Credential Manager çağrısı yapılıyordu.

- `write_all` kayıtlı değer aynıysa yazmıyor (0 yazı/silme; x5 0,11ms).
- `trim_history` satır düşünce True dönüyor; `_save` yalnız o zaman
  dosyaya ve listeye dokunuyor.
- `ThemeManager.apply` aynı modda stil yenilemiyor (aynı mod x5 0,12ms;
  pencere açıkken ölçülen 37,6ms maliyet kalktı, mod değişimi aynı).
- Testler: credential erken-çıkış/değişim, trim bool, tema no-op.
- Resmi kapılar (pytest + compileall + import + audit + SBOM) ve paket
  arşiv kapısı build içinde geçti.

Teslim: dist/WordArc-0.6.10.exe ve dist/WordArc-0.6.10.bat.
EXE: 1.581.288.475 bayt; SHA256:
a58974fe1a5f544f3fc96684be637fbb66047134604c95d4c6b8ed06fa370fbf.
Kaynak/sürüm/test değişiklikleri yerel sürüm commit'i ve v0.6.10 ile
kaydedilir; push/release yedek yetkisiyle yapılır. Önceki teslimler korunur.

## 2026-10-01 — 0.6.9 AMD/Vulkan ve bağımsız CPU kurtarması

Kullanıcı RX 6650 XT ve Ryzen 7 7700 ile AMD GPU hızlandırması istedi.
Resmi Vulkan/Whisper/AMD kaynakları incelendi; gerçek ggml backend bu
bilgisayarda RX 6650 XT'yi yaklaşık 8 GB bellekle gördü. CUDA için mevcut
faster-whisper/CTranslate2 akışı korunur; AMD için whisper.cpp 1.9.2/Vulkan
ayrı süreçte eklenir. Motor, ggml DLL'leri ve Visual C++ runtime pakettedir.
CPU kurtarması, Vulkan'a bağlanmayan ayrı native payload kullanır.

Otomatik öncelik NVIDIA CUDA / AMD Vulkan / CPU. GGML modelleri ayrı ve
checksum/revision doğrulamasıyla indirilir; önceki CT2 modelleri korunur.
Vulkan modeli yokken eski CPU modeli çalışır. GPU sürücüsü yokken yalnız
GGML modeli kuruluysa da CPU çalışır. Elle AMD seçiminde bir kez CPU onayı,
ayar kaydı ve aynı kaydı tekrar işleme vardır; otomatik mod GPU hatasında
CPU'ya döner. Ses buluta düşürülmez. İptalde yalnız başlatılan child kapatılır.

Resmi 11 saniyelik JFK örneği / large-v3-turbo / üç tekrar ortancası:
RX 6650 XT 3,52 sn; Ryzen 7 7700 mevcut CPU motoru 5,63 sn. Bu örnekte yaklaşık
1,60 kat hızlanma; bütün metinler aynı. Model açılışı dahil, dosya önbelleği
sıcak; CPU'nun oturum model cache'iyle kısa ardışık dikte oranı farklı olabilir.
Türkçe mikrofon/uzun toplantı kalitesi ve başka temiz Windows kurulumu açık.
RTX 5060 üzerinde gerçek CUDA kabulü bu makinede yapılmış değildir.

410 test geçti, 1 ağ testi atlandı; import, pip check ve runtime güvenlik
denetimi temiz. Paket arşiv kapısı güncel kaynak bytecode'u, native manifest
hashlerini, Vulkan'dan bağımsız CPU importlarını ve CUDA DLL'lerini denetler.
Teslim EXE'si büyük-v3-turbo resmi örnek sesini hem RX 6650 XT/Vulkan hem
Vulkan'dan bağımsız GGML CPU yolunda gerçek olarak tamamladı; metinler aynı.
Kanıt: build/release-0.6.9-gpu-cpu.json. GPU'nun CPU'ya düşmediği ve GPU
ağırlık tamponu/backendinin kullanıldığı doğrulandı. Kaynak bytecode'u, 33
native dosyanın hashleri, CPU importları ve CUDA DLL arşiv denetimi geçti.
İlk paket kabul çalıştırmasında GPU keşfi/çözümleme toplamı 12,95 sn, CPU
9,69 sn oldu; bu değerler iç motorun üç tekrarlı ölçümüyle aynı sınırı ölçmez.
Bu kontrollerde LOCALAPPDATA ve sürücü önbelleği yeni temp dizinindeydi.
Normal mevcut sürücü önbelleğini kullanan aynı teslim EXE'si GPU çözümlemesini
4,04 sn'de tamamladı; kanıt build/release-0.6.9-gpu-normal-cache.json.
İlk sürücü/shader hazırlığı ek süre alabilir; GPU her kayıtta daha hızlıdır
iddiası yoktur.

AMD modeli doğrulanmış test kopyasından kullanıcı model klasörüne eklendi:
%LOCALAPPDATA%/WordArc/whisper/whisper.cpp/ggml-large-v3-turbo.bin.
1.624.555.275 bayt; SHA256:
1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69.
Eski modeller, config ve çalışan kullanıcı oturumu korunur. Vulkan SDK/ROCm
ve runtime DLL'lerini kullanıcı ayrıca indirmez; AMD sürücüsü kurulu olmalıdır.

Teslim: dist/WordArc-0.6.9.exe ve dist/WordArc-0.6.9.bat.
EXE: 1.582.635.897 bayt; SHA256:
cd9e6c068d668dfa475794f458e77b5dbc43f5147b94ef40a575bf1e23b2f6d4.
Kaynak/derleme/test değişiklikleri yerel sürüm commit'i ve v0.6.9 ile kaydedilir;
harici push/release yapılmaz. Önceki teslim sürümleri korunur.
Araştırma/ölçüm: docs/amd-vulkan-0.6.9.md; build/amd-benchmark-0.6.9.json.

## 2026-10-01 — 0.6.8 ortak seçim penceresi ve model listesi

Kullanıcı 44 model yüklenmesine karşın liste açılmadığını ve kısa motor
listesinde yalnız bir seçenek göründüğünü bildirdi. Model listesi veri
kaybından değil açılan pencerenin hemen kapanmasından görünmüyordu.
Gerçek Windows/Qt tıklamasıyla 44 satır mevcutken popup visible=False
yeniden üretildi. Pencereye henüz bağlanmamış görünür custom düğmesi ayrı
top-level Windows penceresi oluşturup odağı çalıyordu. Arama alanı/liste/custom
düğmesi oluşturulduğu anda popup parent'ına bağlandı; tıklama tamamlandıktan
sonra açılış yapıldı. Aynı gerçek fare denemesinde visible=True elde edildi.

Kısa/uzun tüm seçimler ortak, ekran içine yerleşen Qt.Popup kullanıyor; kısa
listede arama gizli, uzun/model listesinde arama açık. Native QComboBox
açılışı kullanılmıyor. Fareyle alan/ok ve klavye aynı yola girer; alanlarda
görünür açılış oku eklendi. Veri kimlikleri ve özel model metinleri korunuyor.
35 ilgili test geçti; native Windows/Qt kaynak denemesinde iki temada 8 liste
(2/4/7/44 seçenek), model araması ve son modeli seçme başarılı oldu.

Kaynakta 0.6.8, önceki CUDA/runtime/AI/arayüz düzeltmeleri korunuyor.
Canlı API model çekme ve gerçek GPU kabulü bu ortamda doğrulanmış sayılmaz.

Resmi sürüm kontrolü: 397 test geçti, 1 ağ testi atlandı; import/güvenlik ve
teslim EXE açılış/isim/sürüm/CUDA DLL arşiv kapıları geçti. Frozen 0.6.8 probe
iki temada 8 listeyi gerçek fareyle açtı; 44 modellik listede arama ve son
modeli seçme geçti. 11 CUDA DLL'si yine sadece bundle içinden yüklendi.
Teslimin 10 runtime modülü kaynakla, 9 ortak modülü frozen probe ile eşleşti.
Açılış oku SVG'si arşivde mevcut. Kanıtlar build/release-0.6.8*.log,
build/release-0.6.8-verification.json ve build/release-0.6.8-shots içindedir.

Teslim: dist/WordArc-0.6.8.exe + dist/WordArc-0.6.8.bat.
EXE: 1.545.650.069 bayt; SHA256:
36b7a3a27b8c2d2acc041015e5845cde18d6884ab444ac4d06c6460c659cb5fa.
Kapsam içi kaynak/derleme değişiklikleri yerel commit ve v0.6.8 etiketiyle
kaydedilir; harici push/release yapılmaz. Önceki teslimler korunmuştur.
İlk commit/tag girişimi otomatik incelemede tmm eksikliğiyle reddedildi;
kullanıcı daha sonra doğrudan "tmm — yerel commit ve etiketi oluştur" onayı
verdi. Yerel sürüm kaydı bu onayla tamamlanır; harici yayın kapsam dışıdır.

## 2026-10-01 — 0.6.7 gömülü CUDA runtime ve onaylı CPU geçişi

Kullanıcı RTX 5060 / sürücü 596.36 / nvidia-smi CUDA 13.2 bildirimiyle,
önceki EXE'nin cublas64_12.dll hatasını iletti. Bu makine farklıdır:
/Users/usert log yolu ve nvidia-smi burada yok; hedef GPU testi yapılamaz.

Standart build.ps1 teslimi artık requirements-cuda.txt NVIDIA wheel setini
kurup doğrular; cublas, CUDA runtime, NVRTC ve cuDNN DLL'leri iki spec'te
bin/lib düzeni korunarak eklenir. cuda_runtime sys._MEIPASS ve EXE yanını
arar; mevcut DLL'yi tam yoluyla yükler. Paket denetiminin --cuda kapısı
gerekli DLL'lerin gerçekten teslim EXE arşivinde bulunduğunu doğrular.

Açık CUDA seçiminde eksik DLL, CTranslate2 yüklenme nedeni ve GPU/sürücü
yokluğu ayrı raporlanır. Başlatma/çözümleme hatası sessiz CPU geçişi yapmaz.
Ortak GUI onay hizmeti dikte/toplantı/dosyada bir kez CPU geçişini teklif eder;
onayda ayarı kaydeder ve aynı kaydı CPU ile yeniden işler. Redde aynı oturumda
GPU başlatma ve uyarı döngüsü tekrarlanmaz. Kaydetme başarısızsa ayar geri alınır.
Otomatik modun CUDA hatasında sessiz CPU geri dönüşü korunmuştur.

Hedef GPU kabulü açık: temiz RTX 5060 ortamında large-v3-turbo gerçek kayıt
cuda/float16 ile tamamlanmalı ve nvidia-smi süreç kanıtı alınmalıdır.

Standart derlemenin ilk DLL adı kapısında cublasLt büyük/küçük harf karşılaştırma
hatası saptanıp düzeltildi; mevcut aynı EXE üzerinde --cuda kapısı tekrar geçti.
Paket adı/gömülü sürüm/modüller ve teslim EXE izole açılışı doğrulandı.
Frozen probe 11 CUDA DLL'sini sys._MEIPASS içinden yükledi; harici Python
DLL'si kullanılmadığı tam dosya yollarıyla doğrulandı. Aynı probe CPU/base
sessiz WAV çözümlemesini ve arayüz/seçim testlerini geçti.
Teslimin 10 runtime modülü kaynakla, 9 ortak modülü frozen probe ile eşleşti.
CUDA wheel setinin ayrı güvenlik denetiminde bilinen açık bulunmadı.

Teslim: dist/WordArc-0.6.7.exe + dist/WordArc-0.6.7.bat.
EXE: 1.545.649.495 bayt; SHA256:
4ec3135524037939ad48991490e3c6b5445596492cbe83af358f49b5713b7802.
Kanıtlar: build/release-0.6.7-{package,cuda,workspace,runtime,cuda-audit}.log
ve build/release-0.6.7-verification.json. İlk derleme 390 test/1 atlama;
ardından GUI thread/cancel için 2 test daha eklendi, ilgili 9 onay testi geçti.
Hedef kabul adımları docs/cuda-acceptance-0.6.7.md içindedir.
Son resmi kontrol: 392 test geçti, 1 ağ testi atlandı; import ve güvenlik
kapıları geçti. Teslimin wordarc giriş betiği de mevcut kaynakla bytecode
olarak eşleşti. Kapsam içi kaynak/derleme kayıtları yerel commit ve v0.6.7
etiketinde tutulur; harici push/release yapılmaz. GPU kabulü hâlâ açıktır.

## 2026-10-01 — 0.6.6 seçim listesi düzeltmesi

Kullanıcı kısa açılır listelerin boş görünmesini ve seçilememesini bildirdi.
Kök neden: Qt stylesheet içindeki desteklenmeyen max-height: 70vh kuralı.
Gerçek Qt ölçümünde liste yüksekliği 2 px, viewport 0 px oldu. Kural kaldırıldı;
aynı dört seçenekli liste 102 px, viewport 100 px olarak açıldı. Ekran sınırına
yerleşim mevcut FitsOnScreenCombo tarafından korunuyor.

Yeni test iki temada 2/4/7 seçenekli gerçek açılır listelerin bütün satırlarının
görünürlüğünü ve fareyle seçimi doğruluyor. Eski kural yeniden enjekte edilince
6/6 test başarısız; düzeltmeyle 6/6 başarılı. Kaynak ve EXE/BAT 0.6.6 olarak
hazırlandı; önceki sürüm paketleri korunuyor.

383 test geçti, 1 ağ testi atlandı; resmi import/güvenlik/paket kapıları geçti.
0.6.6 frozen probe içinde iki temada altı gerçek liste açıldı; bütün seçenekler
göründü ve fareyle seçim başarılı oldu. Ekran görüntüleri:
build/release-0.6.6-shots/choices-*.png. Teslimin 9 runtime modülü kaynakla,
8 ortak modülü frozen probe ile eşleşti; teslim EXE'sinin izole açılışı geçti.
Kanıt: build/release-0.6.6*.log ve build/release-0.6.6-verification.json.
Teslim: dist/WordArc-0.6.6.exe + dist/WordArc-0.6.6.bat.
SHA256: 598ee987311c40c5f445db24fd59bac0124277ba31b7acb596ca4cf01eba259a.
Kapsam içi değişiklikler yerel commit ve v0.6.6 etiketiyle kaydedilir; push yok.

## 2026-10-01 — 0.6.5 sürüm kapanışı

Kullanıcının bütün değişiklikleri yeni sürümde toplama talebiyle 0.6.5 hazırlandı.
Dört ana sekme korundu; kontroller ve ayrıntılar ayrılmış panellere taşındı.
Gelişmiş ayarlar yerel sekmelere bölündü, API/model seçimleri aramalı açılır
panellerle düzenlendi. Dar pencerelerde panel seçimi kullanılıyor.

AI temizleme, İngilizce, altyazı ve tutanak yönergeleri anlamı ve verileri
koruyacak biçimde yenilendi; eski varsayılanların göçü kullanıcıya özel
yönergeleri koruyor. Eksik/engellenmiş yanıtlar ve boş temizleme çıktısı
ayrıştırıldı. CUDA DLL araması, otomatik CPU geri dönüşü ve unicodedata paket
bağımlılığı düzeltildi. İsteğe bağlı CUDA derlemesi build.ps1 -Cuda ile yapılır.

Bu teslim CPU/otomatik geri dönüş paketidir; NVIDIA runtime wheel seti ortamda
kurulu değildir. Gerçek GPU, canlı AI kalite karşılaştırması ve gerçek mikrofon
kaydı bu sürüm kapanışında doğrulanmış sayılmıyor. Önceki paketler korunmuştur.
377 test geçti, 1 ağ testi atlandı; resmi derleme/import ve bağımlılık güvenlik
kapıları geçti. Teslim EXE/BAT adları, gömülü sürüm, bağımlılıklar ve izole
açılış paket denetiminden geçti. Teslimin 9 runtime modülü mevcut kaynakla,
8 ortak modülü console probe ile bytecode olarak eşleşti. 0.6.5 console probe
izole çalışma alanını açtı; base model ve sentetik sessiz WAV ile CPU
çözümlemesi/unicodedata denetimi geçti. Kanıtlar: build/release-0.6.5*.log ve
build/release-0.6.5-verification.json.

Teslim: dist/WordArc-0.6.5.exe + dist/WordArc-0.6.5.bat.
EXE SHA256: 43d016a8620227db65892e80cdf5171985792249da1f51ff04e71a65eef63fcf.
Sürüm kapanışı: kapsam içi kaynak/derleme değişiklikleri yerel commit ve aynı
commit'e v0.6.5 etiketiyle kaydedilir; harici push/release yapılmaz.

## 2026-10-01 — 0.6.4 yerel yeniden derlemesi

Kullanıcının gördüğü eski arayüzün nedeni: önceki düzeltmeler yalnız kaynak/test
derlemesindeydi; dist içindeki 30 Eylül EXE'si yenilenmemişti. build.ps1 ile
güncel kaynak dist/WordArc-0.6.4.exe ve aynı adlı BAT'a aktarıldı. Eski paket
build/previous-delivery-2026-10-01 altında saklandı. Başlatıcı artık diğer
WordArc süreçlerini topluca zorla kapatmıyor.

377 test geçti, 1 ağ testi atlandı; derleme/import ve bağımlılık güvenlik
kontrolleri geçti. Teslim paketinin 9 runtime modülü güncel kaynakla, bunlardan
8'i doğrulanmış console probe ile bytecode olarak eşleşti. Yeni PanelTabs
düzeni arşivde doğrulandı; teslim EXE'sinin izole açılışı geçti. Güncel dist
EXE'sinden gerçek ayarlar penceresi açıldı ve çalışan süreç yolu doğrulandı.

Paket SHA256: 4bab8a874a97986b28c39d5bdd9930ed85a56559ab9f2e6ec4697eb19d74595f.
Önceki EXE SHA256: 49995e3b5916a487ac0f6ac572a00a9bbefa4ca4c3ab3be460bcff7f6e56dc02.
Build kimliği: 2026-10-01-4bab8a874a97. Ayrıntı: build/delivery-rebuild-2026-10-01.json.
Kaynak: HEAD 02f2a0e + çalışma ağacındaki düzeltmeler. Mevcut v0.6.4 etiketi
önceki paketin kaydıdır; bu yeniden derlemeyi tanımlamaz. Yeni sürüm/commit/tag
ve harici push/release yok; proje kuralındaki tmm bekleniyor.

Bu paket CPU/otomatik geri dönüş yolunu içerir. CUDA runtime wheel seti bu
ortamda kurulmadı; gerçek NVIDIA GPU ve canlı AI kalite değerlendirmesi hâlâ
doğrulanmadı. Gerçek kayıt/GPU başarı iddiası değildir.

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
