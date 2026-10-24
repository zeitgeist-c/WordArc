# WordArc 0.10.1 — 24.10.2026 doğrulaması

Kullanıcı talebi: eksik Vulkan motorunu yeniden kurulum istemeden bulma/onarım,
etkin yeniden model indirme, uygulama ve Windows pencere simgelerini geri getirme.
Sürüm 0.10.0 → 0.10.1; kullanıcı açıkça istemedikçe tüm projelerde yalnız patch.

## Değişiklik

- `vulkan_runtime.py`: kayıtlı seçim, kullanıcı veri dizini, paket, PATH, yaygın
  kurulumlar ve sınırlı Hermes dizinleri taranır. CLI seçenekleri ve gerçek Vulkan
  cihaz çıktısı kontrol edilir; başka uygulamanın dosyaları değiştirilmez.
- Paketli motor hash manifesti doğrulanarak kalıcı kullanıcı dizinine kopyalanır.
  Eksik motor, SHA256 sabitli `WordArcVulkan-1.9.2.zip` ile onarılır. Ayrı motor
  ve model durumları; tarama/elle seçim; kurulu model için güvenli yeniden indirme.
- Model yenileme doğrulanmış `.part` dosyasını atomik değiştirir; indirme hatası
  mevcut doğrulanmış ağırlıkları silmez. Windows CR CR LF çıktısı normalize edilir.
- Simge pikselleri baştan yüklenir; varlık dosyası kayıpsa çizilen WordArc simgesi
  kullanılır. Başlık, uygulama penceresi ve QApplication bu simgeyi kullanır.

## Kanıt

- Son test grubu: **702 passed, 2 skipped, 12 subtests**, 81,11 s.
- `check.ps1 -Audit`: import/derleme/installer işaretleri ve OSV denetimi geçti;
  kilitli bağımlılıklarda bilinen açık bulunmadı. Test verisi ayrı APPDATA ve
  LOCALAPPDATA dizinlerinde tutuldu. Eksik proje venv'i yerine kilitli Python 3.12
  `.cache/release-venv` ortamı kullanıldı; geliştirme Pillow pini lock ile eşitlendi.
- Gerçek RX 6650 XT + large-v3-turbo + JFK örneği: kaynakta Vulkan 3,31 s;
  teslimin iç EXE'sinde Vulkan 5,01 s, CPU 8,38 s; aynı metin, GPU fallback yok.
- Paket motoru ve otomatik keşif yokmuş gibi izole test: tam hash sabitli motor
  ZIP'i yerel URL'den gerçek indirme/doğrulama/kurulum yoluyla açıldı; ardından
  aynı gerçek ses ve model Vulkan üzerinde çözümlendi.
- Pencerede logo ve etkin yeniden indirme/tarama/seçim görsel kontrolü; gerçek
  Windows penceresinde WM_GETICON küçük ve büyük simge tanıtıcıları dolu.
- `tools/verify_release_package.py --cuda`: gömülü sürüm ve kaynak bytecode'u,
  native dosya manifesti, ikonlar, onarım ZIP'i, TTS/CUDA pinleri ve izole
  `--version` açılışı doğrulandı. `verify_vulkan_package.py` setup yerine doğru
  iç EXE'yi kullanacak şekilde güncellendi; gerçek GPU+CPU kabulü geçti.

## Paket kimliği ve kaynak sınırı

- `WordArc-0.10.1.exe`: 312178298 bayt;
  SHA256 `066fe6b45db603cbf1fd4b8e8904a5ea4d19895e1960009a2b9b96a99ba93284`.
- `WordArcVulkan-1.9.2.zip`: 19741654 bayt;
  SHA256 `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`.
- Kullanıcıya ait `installer/wordarc.iss` içindeki AppPublisher=Geeker değişikliği
  korunur ve commit edilmez. Derleme kopyası bu dosyanın HEAD sürümünü kullanır;
  diğer paketlenen kaynakların ana ağaçla eşitliği ayrıca doğrulanmıştır.
- Inno Setup doğrudan doğrulanmış kullanıcı kurulum yolundan çalıştırıldı;
  izole LOCALAPPDATA yüzünden build.ps1'in otomatik Inno araması başarısız olmuştu.
  Standart paket CUDA DLL'lerini zaten isteğe bağlı indirir; bu derlemede gereksiz
  NVIDIA wheel kurulumunu atlamak için CpuOnly kullanıldı, CUDA pinleri paket
  denetiminde ayrıca doğrulandı. Fiziksel NVIDIA testi yapılmadı.
- Kurulum dosyası Inno ile derlendi; kullanıcıya ait çalışan eski uygulama
  kapatılmadı veya yerinde yükseltilmedi. Yeni mikrofon kaydı/Türkçe doğruluk testi
  ve eski hatanın tek kök nedeninin geçici dosya temizliği olduğunun kanıtı yoktur.
  Simge ve motor dosyası kaybına karşı kurtarma yolları doğrudan test edilmiştir.

Yayın hedefi: `zeitgeist-c/WordArc-Releases`, `v0.10.1`. Kaynak deposu
`zeitgeist-c/WordArc` private kalır. Kullanıcının bu oturumdaki açık `tmm` onayı
commit, etiket, kaynak push ve GitHub yayınını kapsar.
