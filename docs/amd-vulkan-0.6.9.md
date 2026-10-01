# WordArc 0.6.9 — AMD/Vulkan

Tarih: 2026-10-01. Kullanıcı RX 6650 XT ve Ryzen 7 7700 bildirdi;
Vulkan backend aynı RX 6650 XT'yi yaklaşık 8 GB bellekle gerçekten gördü.

## Araştırma ve karar

Ryzen 7 7700, 8 çekirdek/16 iş parçacığı ve AVX2/AVX512 desteği sunar.
CPU tarafı güçlü olduğundan GPU/CPU oranı yalnız donanım özelliğinden
çıkarılmadı. Resmi whisper.cpp Vulkan desteği, Vulkan destekli sürücüyle
Windows'ta farklı üreticilerin GPU'larında kullanılabilir.

Kaynaklar:
- https://www.amd.com/en/products/processors/desktops/ryzen/7000-series/amd-ryzen-7-7700.html
- https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support
- https://opennmt.net/CTranslate2/hardware_support.html

NVIDIA için faster-whisper/CTranslate2 CUDA/float16 korunur. AMD için
whisper.cpp 1.9.2/Vulkan eklenmiştir. Mevcut CT2 ağırlıkları farklı biçimdedir;
GGML modeller ayrı klasörde indirilir, eski modeller silinmez. Model indirmesi
revision, boyut ve SHA256 ile doğrulanır; durdurma/devam ettirme korunur.

## Davranış

- Otomatik: kullanılabilir NVIDIA CUDA, sonra AMD Vulkan, sonra CPU.
- Vulkan modeli henüz yoksa kurulu CT2 modeli CPU'da çalışmaya devam eder.
- Otomatik Vulkan hatası: kaydı baştan CPU'da işler; oturumda GPU'yu tekrar
  tekrar başlatmaz. Ses buluta gönderilmez.
- Elle AMD seçimi: hata nedeni gösterilir; mevcut GUI onay hizmeti CPU'ya
  geçişi bir kez sorar, onayda ayarı kaydeder ve aynı kaydı yeniden işler.
- Yalnız GGML modeli varsa CPU kurtarması ikinci model indirmeden çalışır.
  Kurtarma CLI/DLL'leri ayrı klasörde, Vulkan'a bağlanmadan derlenir.
- Sürücü ve native çözümleme ayrı süreçtedir. İptalde yalnız başlatılan
  süreç sonlandırılır. Uzun çıktı dosyaya alınır; pipe kilitlenmesi önlenir.
- RX harici kart, işlemcinin dahili Radeon'undan önce seçilir.

Motor/DLL/lisanslar EXE içinde; kullanıcıya Vulkan SDK, ROCm veya C++ derleyici
kurulumu gerekmez. AMD Vulkan sürücüsü dışarıdan kurulu olmalıdır. Model
İndir düğmesiyle bir defa indirilir; turbo 1.624.555.275 bayttır.
Native motorların ihtiyaç duyduğu Visual C++ runtime DLL'leri de her motorun
yanına eklenir. CPU payload import tablosunda Vulkan bağımlılığı bulunmadığı
paket kapısında denetlenir.

## Gerçek ölçüm

Resmi whisper.cpp samples/jfk.wav, 11 saniye, İngilizce, large-v3-turbo,
8 CPU thread, 5 beam; model açılışı dahil üç tekrarın ortancası:

| Yol | Süre |
| --- | ---: |
| RX 6650 XT / Vulkan | 3,52 sn |
| Ryzen 7 7700 / mevcut CTranslate2 CPU int8 | 5,63 sn |
| GGML CPU kurtarma motoru | 8,25 sn |

Bu örnekte Vulkan mevcut CPU yolundan yaklaşık 1,60 kat hızlı; dokuz çıktının
metni aynıdır. İlk tek ölçüm 3,88/8,20 saniyeydi; yinelenen ölçüm esas alınır.
Dosya sistemi önbelleği sıcaktır; yeniden açılış/uzun ses/Türkçe gerçek mikrofon
kalitesi bu sonuçtan çıkarılamaz. Kanıt: build/amd-benchmark-0.6.9.json ve
build/amd-native-proof.log. Native log GPU ağırlık tamponunu ve Vulkan backend
kullanımını gösterir; CPU'da sessiz çalışma GPU başarısı sayılmaz.
Vulkan CLI her kayıtta model açar; mevcut CTranslate2 motoru modeli oturumda
tutar. Bu tablo iki tarafta model açılışını içerir; art arda kısa diktelerin
CPU önbelleğiyle hız karşılaştırması farklı olabilir. GPU her kayıtta daha
hızlıdır iddiası yoktur.

## Paket kabulü

build.ps1 önce tools/build_vulkan.py ile sabit kaynak/SDK hashlerini ve native
payload manifestini doğrular. SDK installer çalıştırılmaz; gereken başlık,
derleyici ve import library yalnız proje .cache dizinine çıkarılır.
requirements-native-build.txt yalnız geliştirme bilgisayarı içindir.
Paket kontrolü gömülü native dosyaların hashlerini ve Python bytecode'unun
güncel kaynakla eşleşmesini denetler.

Gerçek teslim EXE'si --local-stt-check ile izole çıktı/model/ses hedeflerinde
Vulkan ve GGML CPU yollarından test edilir; config ve kullanıcı oturumu
değişmez. Son paket sonuçları DURUM.md'ye kaydedilir.

Gerçek 0.6.9 tesliminde iki yol da örnek kaydı tamamladı ve metinler eşleşti.
İlk paket kontrolünde GPU keşfi ve çözümleme toplamı 12,95 sn, CPU 9,69 sn:
ilk native DLL/driver hazırlığı motor ölçümüne ek süre getirir. Motor
karşılaştırma tablosu bütün EXE başlangıç süresinin karşılaştırması değildir.
Kanıt: build/release-0.6.9-gpu-cpu.json. Paket hash'i ve Git kaydı DURUM.md'de.
Bu izole kontrol LOCALAPPDATA'yı da sıfırdan oluşturdu, dolayısıyla sürücü
önbelleği soğuktu. Normal mevcut sürücü önbelleğiyle aynı EXE GPU çözümlemesini
4,04 sn'de tamamladı; build/release-0.6.9-gpu-normal-cache.json.

Hedef RTX 5060 CUDA çözümlemesi, temiz başka Windows kurulumu ve kullanıcının
Türkçe/uzun toplantı kayıtları ayrıca kabul edilmelidir; hatasızlık garantisi
verilmez. Önceki 0.6.8 paketleri geri dönüş için korunur.
