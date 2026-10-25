# Motor ve model keşfi — 25 Ekim 2026

Başlangıç kaynağı: `5232f23` / `v0.10.2`, `master`.
Bu kayıt sürüm dışı kaynak çalışmasını anlatır. `brand.py` 0.10.2 kaldı;
mevcut dağıtım EXE'si yeniden üretilmedi. Commit/tag/push yapılmadı.
Başlangıçtaki `installer/wordarc.iss` kullanıcı değişikliği korundu.

## Kullanıcı akışı

Ayarlar → yerel ses çözümleme → **Motor ve model bul…**:

1. Ayrı pencere açılır; dosya araması sırasında hareketli ince çizgi, bulunan
   model sayısı, kontrol edilen öğe sayısı ve güncel konum gösterilir.
2. Önce WordArc, Hermes ve Hugging Face model depoları; ek seçilen klasörler;
   ardından kullanıcı klasörleri ve Windows'un yerel sabit diskleri aranır.
   Ağ sürücüleri otomatik eklenmez. Dizin bağlantıları izlenmez, sistem/test/
   bağımlılık/önbellek ağaçları atlanır. Bilinen model önbellekleri ayrıca
   başlangıç kökü oldukları için bu genel dışlamadan etkilenmez.
3. CPU ve CUDA, uygulamanın kendi Python ortamıyla ayrı alt süreçlerde
   kontrol edilir. Bu aşamanın çizgisi gerçek tamamlanan denetim sayısını
   gösterir. Vulkan/CPU native çalıştırıcıları ve hazır model dosyaları
   birlikte değerlendirilir.
4. Sonuçlarda model, kullanılabileceği aygıt, depolama kaynağı ve dosya yolu
   görünür. Aynı native motorun kopyaları seçenekleri çoğaltmaz. Kullanıcı
   satırı seçip **Bu modeli kullan** düğmesine basar.
5. Seçilen dosyalar yeniden kontrol edilir; modelin mevcut yoluna bağlantı
   kaydedilir. Aygıt/model seçimi ve yerel çözümleme tercihi ayarlara yazılır.
   Sonraki çözümleme mevcut dosyayı kullanır; başka uygulamanın modeli
   taşınmaz, dönüştürülmez veya yeniden indirilmez.

Model biçimleri birbirinin yerine geçmez: CTranslate2 modelleri CPU/CUDA,
GGML modelleri uyumlu whisper.cpp çalıştırıcısıyla CPU/AMD Vulkan için
sunulur. Desteklenen model adları mevcut ürünle aynı: Base, Small,
Large v3 Turbo. GGML için adları tanınan nicemlenmiş Turbo dosyaları da
keşfedilebilir. Motorun bulunması gerçek ses çözümlemesinin kanıtı değildir;
ekran bu aşamada **Dosyalar bulundu** der.

## Güvenilirlik ve dosya güvenliği

- Dosyanın varlık kontrolü dahil erişim hataları yakalanır; erişilemeyen
  aday diğerlerini durdurmaz. Bozuk/erişilemeyen çözümleyici önbelleği
  başka uyumlu adaya geçilmesini engellemez.
- Tarama indirme veya etkin seçim yapmaz. Taramada bulunan harici EXE'ler
  kendiliğinden çalıştırılmaz. Otomatik native doğrulama için uygulamanın
  gömülü manifestindeki dosya hash'leri ve native dosya envanteri eşleşmelidir.
  Harici çalıştırıcı yalnız kullanıcı onu seçtikten sonra doğrulanır.
- Ortak model için **Bağlantıyı kaldır** yalnız WordArc bağlantısını siler;
  dosyalar yerinde kalır. Yeniden indirme WordArc'ın kendi depolamasına yazar.
- Aynı adlı farklı model yolu seçilince CTranslate2 bellek önbelleği yeniden
  yüklenir. Native CPU motor seçimi uygulama/önbellek yenilemesinden sonra
  da korunur.
- Her tarama ve arayüz aygıt incelemesi nesil kimliği taşır. Eski yanıt yeni
  sonucu ezemez. Pencere kapanması ve iptal, bu taramanın işlemlerini
  sonlandırır; kullanıcıya ait başka süreçler kapatılmaz.
- Arama üst sınırı 65 saniye veya 1.000.000 dosya/dizin öğesidir. CPU/CUDA
  denetimleri ayrı ayrı en fazla 18 saniye, native CLI denetimi 8 saniyedir.
  Sınır nedeniyle bakılamayan yerler **kısmi tarama** olarak bildirilir;
  kullanıcı **Başka klasörde ara…** ile o konuma öncelik verebilir. İşletim
  sistemi dosya erişiminin kendisi gecikirse bunun kesin süre garantisi yoktur.
- Günlükteki WinError 5'in işletim sistemi/antivirüs/izin kök nedeni ayrıca
  belirlenmedi. Düzeltilen davranış, bu hatanın tüm keşfi kesmesidir.

## Doğrulama

Kullanılan ortam: `/Users/user/AppData/Local/Programs/Python/Python311/python.exe`
(Python 3.11.9, CTranslate2 4.8.2). Projedeki `.venv` çalıştırıcısı bu oturumda
mevcut değildi. Testler ayrı APPDATA/LOCALAPPDATA/TEMP altında çalıştırıldı.
Soket kullanan testler sandbox içinde beklediğinden tam set normal Windows
ortamında, aynı izole veri dizinleriyle yürütüldü.

- Son tam set: **731 passed, 2 skipped, 12 subtests passed**, 123,90 saniye.
  Kanıt: `.cache/engine-scan-full-tests.log`.
- Erişimi reddedilen ilk adaydan sonraki motora geçiş, harici EXE'nin taramada
  çalıştırılmaması, eksik model, nicemlenmiş Turbo adı, iptal/zaman aşımı,
  aynı modelin farklı kaynağı, bağlantı kaldırırken dosya koruması, native CPU
  seçiminin kalıcılığı ve eski UI yanıtı regresyonları eklendi.
- Tarama ekranı açık/koyu temada görüntülendi. Animasyonun 240 ms arayla
  alınan iki çizgi görüntüsünde farklı piksel üretmesi doğrulandı.
  Görseller: `.cache/engine-scan-dark.png`, `.cache/engine-scan-light.png`.
- Varsayılan gerçek tarama: 65,34 saniye, 1.000.236 öğe (son dizinin sayımı
  dahil), 6 model dosya kümesi, 7 kullanım seçeneği, 4 konum hatası. Sonuç
  kısmi olarak işaretlendi; bütün disklerin eksiksiz tarandığı iddia edilmez.
  Base/Small Hugging Face depoları ve WordArc altındaki CT2/GGML Turbo
  dosyaları bulundu. Hermes'in şu anda hangi modeli kullandığı ayrıca
  doğrulanmadı; bu dosyalar Hermes'e aitmiş gibi etiketlenmedi.
  Kanıt: `.cache/engine-scan-live-full.json`.
- İzole seçim kaydıyla, mevcut gerçek dosyalar kullanılarak JFK örnek sesi:

  | Seçilen model | Aygıt | Seçim + çözümleme |
  | --- | --- | --- |
  | GGML Large v3 Turbo | AMD RX 6650 XT / Vulkan | 5,30 s |
  | Aynı GGML Large v3 Turbo | CPU | 11,59 s |
  | Hugging Face CT2 Base | CPU | 1,95 s |

  Üç sonuç da boş değil; native CPU/Vulkan metinleri aynı. Gerçek kullanıcı
  model dosyaları ve ayarları değiştirilmedi. Kanıt:
  `.cache/engine-scan-acceptance/results.json`.
- Değişen Python modülleri derleme kontrolünden geçti; `git diff --check`
  temiz. Üç yeni modül `wordarc.spec` paket listesine eklendi.

Test yardımcıları, UI kayıt testlerinin gerçek Windows başlangıç kaydına
yazmaması ve OCR var/yok senaryolarının test makinesinin paketlerine bağlı
olmaması için izole edildi. Ürün OCR davranışı değiştirilmedi.

## Kalan kabul sınırı

Bu kanıt kaynak çalıştırmasına aittir. Yeni kurulum paketi, donmuş EXE'deki
yeni probe yolu, gerçek mikrofonla uzun kullanım ve fiziksel NVIDIA CUDA
çözümlemesi bu çalışmada doğrulanmadı. Kurulu uygulama eski EXE ile çalışıyorsa
bu ekran henüz o EXE'de yoktur. Sürüm/paket kapanışı ayrı yürütülmelidir.
