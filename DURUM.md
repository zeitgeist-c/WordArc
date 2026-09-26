# WordArc — durum

Güncelleme: 2026-09-26
Hazırlanan paket: 0.5.2 (`brand.py`)
Dal: master
Git dönüş noktası: 4ae6c7d / v0.4.24

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
