# WordArc CUDA ve açılış hatası incelemesi — 2026-09-30

Başlangıç: master, HEAD `02f2a0e`, kaynak sürümü 0.6.4, çalışma ağacı temiz.
Kaynak: kullanıcının iki hata ekranı, mevcut kaynak/paket incelemesi ve bu
çalışmadaki test çıktıları. Bu çalışma bir sürüm teslimi değildir.

## Bulgular

1. Ekrandaki `cublas64_12.dll is not found or cannot be loaded` hatasıyla uyumlu
   olarak mevcut `dist/WordArc-0.6.4.exe` arşivinde cuBLAS DLL'leri yok.
   `get_cuda_device_count()` yalnız cihaz tespit ediyor; CUDA kitaplıklarının
   hazır olduğunu kanıtlamıyor. Kurulum kontrolü de aynı eksik varsayımı taşıyordu.
2. CPU'ya dönüş yalnız `WhisperModel` kurulurken uygulanıyordu. faster-whisper
   kitaplıkları `transcribe()` veya segment üreteci yürütülürken de yükleyebiliyor.
   Bu aşamadaki DLL hatası doğrudan kullanıcıya hata olarak gidiyordu.
3. Otomatik seçim, CPU'ya döndükten sonra bir sonraki kayıtta yine CUDA'yı
   seçebiliyordu. Aynı bozuk yükleme ve model kurulumu tekrarlanıyordu.
4. `failed to load` gibi genel metinler CUDA hatası sayılıyordu. CUDA dışındaki
   model hataları da CPU'ya dönüş kapsamına yanlışlıkla girebilirdi.
5. `unicodedata` açılış hatası ayrı bir hata. Bu çalışma sırasında mevcut
   0.6.4 EXE arşivinde `unicodedata.pyd` bulundu. Ekranda hata veren EXE'nin
   kimliği/hash'i bilinmediğinden aynı dosyada yeniden üretildiği iddia edilmez.
6. Frozen doğrulama aracının argümanları güncel probe ile uyuşmuyordu:
   `stt` komutu atlandığı için model/ses yolu yanlış konumdan okunuyordu.
7. Geniş test turunda çeviri ayarları testi gerçek Windows başlangıç ayarını
   değiştirmeye çalıştı; erişim hatası sonrası modal uyarıda bekledi. Testte
   `startup.set_enabled` izole edildi. Bu bulgu uygulamanın CUDA çökmesi değildir.

## Uygulanan değişiklikler

- Windows DLL yolları kaynak ortamı, frozen paket ve CUDA/cuDNN kurulumları için
  bulunuyor; DLL dizin tanıtıcıları gecikmeli yükleme için canlı tutuluyor.
- Hazır GPU kontrolüne gerçek DLL yükleme denetimi eklendi. Erişilemeyen PATH
  dizinleri tespiti bozmuyor.
- Geç CUDA DLL hatasında aynı kayıt CPU'da baştan çözümleniyor. Otomatik seçim
  aynı oturumda tekrar bozuk CUDA'yı denemiyor; GPU'ya açık geçiş yeniden denenebilir.
- Bellek yetersizliği (`CUBLAS_STATUS_ALLOC_FAILED` dahil) ve CUDA dışındaki hatalar
  gizlenmiyor. İptal denetimi düz metin segmentleri yürütülürken de uygulanıyor.
- `requirements-cuda.txt` NVIDIA Windows wheel sürümlerini sabitliyor;
  `build.ps1 -Cuda` bunları kuruyor ve DLL kontrolünden geçiriyor. Spec'ler
  kurulu NVIDIA wheel DLL'lerini korunan dizin yapısıyla topluyor.
- faster-whisper 1.2.1 ve CTranslate2 4.8.2 PyPI'de güncel olduğundan korundu.
  PyInstaller hook paketi 2026.7 → 2026.8 yükseltildi ve proje ortamına kuruldu.
- `unicodedata` açık hidden import oldu; teslim kontrolü `.pyd`, CTranslate2 DLL,
  CUDA hazırlama modülü ve gerçek EXE açılışını zorunlu kontrol ediyor.

## Doğrulama sınırları

- Tam test turu: 351 geçti, 1 ağ testi atlandı; sonuç
  `build/cuda-fix-tests-final.log` içinde.
- `pip check`, Python derleme ve Git diff boşluk kontrolleri geçti.
- Teslim spec'inden ayrı çalışma dizinine üretilen pencere konsolsuz EXE'nin
  izole `--version` açılışı geçti; unicode ve motor bileşenleri arşivde doğrulandı.
- Console twin içinde gerçek kurulu base modeli ve üretilen bir saniyelik
  sessiz WAV ile CPU yükleme/çözümleme geçti (`FROZEN RUNTIME OK`). Bu kontrol
  konuşma doğruluğu veya gerçek mikrofon deneyimi ölçümü değildir.
- Bu makinede CTranslate2 sıfır CUDA cihazı bildiriyor, `nvidia-smi` bulunmuyor.
  NVIDIA wheel seti burada kurulmadı; `-Cuda` derlemesi, NVIDIA DLL yüklemesi ve
  gerçek GPU çözümlemesi henüz doğrulanmadı. GPU hazırdır denemez.
- `dist` içindeki teslim EXE/BAT değiştirilmedi. Sürüm artırılmadı; yeni release,
  commit/tag veya push yapılmadı. Düzeltmeler kaynak çalışma ağacındadır.

Resmî gereksinimler: https://github.com/SYSTRAN/faster-whisper#gpu
