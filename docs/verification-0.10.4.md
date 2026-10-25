# WordArc 0.10.4 — güvenilir kurulum geçişi, 25 Ekim 2026

Kullanıcı 0.10.4 bakım sürümünü yayımlamayı ve mevcut 0.10.2 kurulumunu
Program Files'a taşımayı açıkça onayladı. Kaynak private WordArc deposunda,
paket public WordArc-Releases deposunda tutulur.

## Değişiklik

Güncelleme artık yalnız setup başlatma sonucuyla uygulamayı kapatmaz.
Bağımsız denetleyici, Inno'nun yeni payload için çevrimdışı açılış kontrolünü
geçip hazır olduğunu bildirmesini bekler. Ardından eski süreç kapanır;
kurulumun çıkış kodu, kurulu uygulamanın sağlığı ve gerçek başlangıç onayı
izlenir. Hatalar günlük ve durum kaydında saklanır. İzin reddi veya hazırlık
hatası mevcut uygulamayı kapatmaz. Eski süreç kapandıktan sonraki başarısız
geçişte doğrulanmış kurtarma kopyası yeniden açılabilir.

Hedef 64 bit `C:\Program Files\WordArc` olarak sabittir. Önceki test yolu
devralınmaz. Eski dosyalar yeni uygulama doğrulanıp açıldıktan sonra, yalnız
kayıtlı yol ve SHA256 eşleşiyorsa temizlenir. Ayarlar, kayıtlar ve modeller
kurulum temizliğinin dışındadır. Ayrıntılı inceleme:
`docs/update-install-investigation-2026-10-25.md`.

## Paket ve doğrulama

- Setup: `dist/WordArc-0.10.4.exe`, 320531332 bayt.
- SHA256: `024bf0b262f635e7f91a77d02d3a85179027917073efda060658bae59f867b26`.
- İç EXE SHA256: `d1d22c05a87a58511f8f80d63f28579032a694458ca04778bcd0c755e0d4b869`.
- Vulkan onarım ZIP'i 1.9.2 aynı dosyadır; SHA256
  `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`.
- Resmî CPU paketi derlemesi: 744 test, 2 atlama, 12 subtest; bağımlılık
  denetimi temiz. Gömülü kaynak ve bağımsız denetleyici hash'leri doğrulandı.
- Teslim iç EXE'si `--version`, gerçek HTTPS/Qt güncelleme kontrolü ve
  çevrimdışı kurulum kontrolünden geçti.
- Teslim EXE'sinde tarama → seçim → ayar kaydı → çözümleme; GGML Turbo
  Vulkan/CPU ve HF Base CPU ile geçti. Fiziksel NVIDIA/CUDA cihazı yoktur.
- Gerçek Inno olumsuz payload denemesi eski dosyayı korudu. Ayrı AppId ile
  tam kurulum/başlangıç/eski dosya temizliği geçti; kullanıcı belgesi korundu.

Kanıtlar `.cache/build-0.10.4.log`, `.cache/installer-cycle/result.json`,
`.cache/release-0.10.4-offline-health.json` ve
`.cache/release-0.10.4-scan-acceptance.json` içindedir.

## Canlı geçiş ve yayın

Eski 0.10.2 işleminin asıl `C:\tmp\iss-e2e\app` klasörü taşınmış/silinmişti.
Çalışan görüntünün SHA256'sı arşivdeki 0.10.2 ile eşleştirildi. İşlemde pencere
ve komut kanalı bulunmadığından ilk geçiş güvenle iptal edildi. Tek seferlik
onarım aracı yalnız bu doğrulanmış PID'yi kapatma seçeneği içerir; bu davranış
normal güncelleyiciye eklenmedi. Geri dönüş kopyası özel güncelleme dizinindedir.

Gerçek yönetici izinli geçiş tamamlandı: yeni uygulama
`C:\Program Files\WordArc\WordArc.exe` yolundan 0.10.4 başlangıç onayı verdi.
Kurulu EXE hash'i teslim iç EXE'siyle aynıdır. 64 bit uninstall kaydı 0.10.4
ve doğru yolu gösterir; eski 32 bit kayıt kaldırıldı. Ayarlar karşılaştırması
başarılı, eski dosya temizliğinde uyarı yok. Yeni uygulamanın komut kanalından
Ayarlar açılması doğrulandı. Kullanıcının uygulaması açık bırakıldı.

Canlı kurulum sonucu `.cache/release-0.10.4-live-install.json`; kesin commit,
etiket, uzak asset boyut/hash'leri ve güncelleyicinin latest sonucu
`.cache/release-0.10.4-publication.json` kapanış kaydında tutulur. Bu kayıtlar
görülmeden canlı geçiş veya yayın tamamlandı kabul edilmez.

Yayın: https://github.com/zeitgeist-c/WordArc-Releases/releases/tag/v0.10.4

İlgisiz `installer/wordarc.iss` içindeki `AppPublisher=Geeker` çalışma
değişikliği korunur; kaynak kaydına ve teslim paketine dahil edilmez.
