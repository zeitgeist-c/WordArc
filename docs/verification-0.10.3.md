# WordArc 0.10.3 — motor ve model keşfi, 25 Ekim 2026

Kullanıcı önce tarama/keşif düzeltmesini, ardından yedek kapanışını onayladı.
Bakım sürümü 0.10.2 → 0.10.3. Kaynak deposu private WordArc; kurulum paketleri
public WordArc-Releases deposunda tutulur.

## Değişiklik ve paket

Motor/model taraması CPU, CUDA ve AMD Vulkan kullanım seçeneklerini seçili
aygıttan bağımsız toplar. Hareketli ilerleme çizgisi, bulunan model/dosya
sayıları, ayrıntı bölümü ve açık model seçimi vardır. Bilinen depoların ardından
kullanıcı klasörleri ve yerel sabit diskler taranır. Limit nedeniyle tamamı
gezilemezse sonuç kısmi olarak bildirilir. Erişim hatası sonraki adayı engellemez.
Ortak dosyalar taşınmaz veya silinmez; WordArc mevcut dosyaya bağlantı saklar.

Harici EXE'ler taramada kendiliğinden çalıştırılmaz. Otomatik denetim yalnız
uygulamanın native manifestiyle eşleşen motorlarda yapılır; harici motor açık
seçimden sonra doğrulanır. Eski işçi sonuçları yeni ekranı ezemez. Seçim alanları
birlikte güncellenerek geçici aygıt tercihiyle fazladan denetim başlatılması
önlenir.

- Kurulum: `dist/WordArc-0.10.3.exe`, **312251266 bayt**.
- Kurulum SHA256: `b08be38282ffa812a9a960ff77ece933ee3de10e69f91adba57ab7e834846556`.
- İç uygulama SHA256: `1e90b86b4e7a988f5435148c6bb85bdb69672de33c5cffc357b530ae59808fc9`.
- Motor onarım paketi: `WordArcVulkan-1.9.2.zip`, 19741654 bayt,
  SHA256 `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`.
- Onarım paketinin hash'i değişmedi; indirme tanımı v0.10.3 yayınına bağlandı.

## Doğrulama

Derleme ayrı kaynak kopyasında, Python 3.12.10 / PyInstaller 6.22.3 ve
kilitli bağımlılıklarla yapıldı. Kullanıcının `installer/wordarc.iss` içindeki
AppPublisher=Geeker değişikliği korundu, commit ve pakete alınmadı; derleme bu
dosyanın önceki Git kaydını kullandı. Üretilen paketlenebilir kaynaklar ana
çalışma ağacıyla eşleştirildi.

- `build.ps1` kapıları: **731 test, 2 atlama, 12 subtest**, 122,69 s;
  Python derleme/import/installer denetimleri geçti.
- Bağımlılık güvenlik denetimi: bilinen açık bulunmadı; SBOM üretildi.
- Native Vulkan payload, CPU kurtarma dosyaları, TTS modelleri, simgeler ve
  gömülü Python kaynakları/sürümü doğrulandı. Yeni keşif, UI, kaynak bağlantısı
  ve tanılama modüllerinin kodları kaynakla karşılaştırıldı.
- CUDA indirme tanımları ve hash manifesti paket içinde; CUDA kitaplıkları
  eskisi gibi isteğe bağlı indirilir. Derleme ortamında bunları tekrar
  kurmayan `-CpuOnly` seçeneği kullanıldı; ürünün CUDA indirme/kullanım kodu
  çıkarılmadı. Ek `verify_release_package.py --cuda` kapısı geçti.
- Teslim iç EXE'sinde `--version` açılışı 5,38 s (çıkarma dahil), gerçek HTTPS
  + Qt güncelleme kontrolü 0,36 s. Sertifika ve hostname doğrulaması açık.
- Teslim EXE'sinin gerçek tarama penceresinde, kullanıcı verisinden ayrı
  kayıtla **arama → satır seçimi → Bu modeli kullan → ayar kaydı → mevcut
  dosyayla çözümleme** zinciri geçti:

  | Model | Aygıt | Tanılama içi süre |
  | --- | --- | --- |
  | GGML Large v3 Turbo | AMD RX 6650 XT / Vulkan | 6,11 s |
  | Aynı GGML Large v3 Turbo | CPU | 13,33 s |
  | Hugging Face CT2 Base | CPU | 2,44 s |

  Bu süreler EXE'nin ilk çıkarma/açılış maliyetini kapsamaz. Üç akış da
  frozen=true, version=0.10.3, selection_saved=true, linked_without_copy=true
  olarak tamamlandı. Vulkan CPU'ya düşmedi; GGML CPU/Vulkan metinleri aynı.

Kanıtlar `.cache/build-0.10.3.log`, `.cache/release-0.10.3-scan-acceptance.json`
ve `.cache/release-source-0.10.3/` altındadır. Kabul gerçek kullanıcı ayarlarını
ve modellerini değiştirmeden yürütüldü; yalnız testin başlattığı süreçler
kullanıldı.

## Sürüm kaydı ve yayın

Kaynak ve sürüm/derleme otomasyonu yerel sürüm commit'inde, `v0.10.3` aynı
kaynakta tutulur. Yayın hedefi:
https://github.com/zeitgeist-c/WordArc-Releases/releases/tag/v0.10.3 .
Yayın kapanışında uzak asset adı, boyutu ve SHA256 ile güncelleyicinin latest
seçimi ayrıca doğrulanır; kesin commit ve uzak kapanış kanıtı
`.cache/release-0.10.3-publication.json` dosyasında kaydedilir.

## Kabul sınırları

Bu makinede fiziksel NVIDIA/CUDA cihazı yoktur; CUDA kullanılabilir değil
sonucu doğru gösterildi, gerçek CUDA çözümlemesi denenmedi. Mikrofonla uzun
süreli kullanım ve her bilgisayardaki her klasör bu testlerin kapsamı değildir.
İşletim sistemi kaynaklı erişim engelinin nedeni kaldırılmış sayılmaz; uygulama
o adayı güvenle atlayıp diğerleriyle devam eder. Kullanıcının kurulu açık
uygulaması bu yedek çalışmasında yerinde yükseltilmez.
