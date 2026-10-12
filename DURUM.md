# WordArc — durum

Güncelleme: 2026-10-12
Hazırlanan paket: 0.6.12 (`brand.py`)
Dal: master
Git dönüş noktası: aad6592 / v0.6.11

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
