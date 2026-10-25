# Motor taraması incelemesi — 25 Ekim 2026

İncelenen kaynak: `5232f23`, `v0.10.2`, `master`. Başlangıçta
`installer/wordarc.iss` içinde mevcut kullanıcı değişikliği vardı; korundu.
Bu çalışma inceleme ve tasarımdır; çalışma kodu, kullanıcı ayarları ve motor
dosyaları değiştirilmedi. Yeni sürüm veya paket üretilmedi.

## Doğrulanan sorunlar

1. `settings_ui.py:1892` içindeki “Motoru tara” işleyicisi Vulkan önbelleklerini
   sıfırlayıp `_refresh_local_controls()` çağırıyor. Bağımsız bir tüm-motorlar
   taraması başlatmıyor. Sonraki `_inspect_local()` yalnız seçili aygıt için
   `get_best_device(preference)` çağırıyor. CPU seçimi Vulkan keşfine girmiyor;
   CUDA kullanılabilirken CUDA ve Otomatik seçimleri de Vulkan'ı kontrol etmeden
   dönebiliyor. Tarama kapsamı kullanım tercihine bağlı.
2. `vulkan_runtime.py:49` içindeki `exe.is_file()` çağrısı `try` bloğundan önce.
   Buradaki `PermissionError` taramayı kesiyor. `resolve()` aday başına hata
   yalıtımı yapmadığı için sonraki motor adayına geçilemiyor.
3. `resolve()` ilk uyumlu adayı bulunca dönüyor. Bu, çalışma sırasında motor
   seçmek için uygun olabilir; tüm bulunan motorların envanterini oluşturmaz.
   Arama yalnız kayıtlı seçim, yönetilen/gömülü motor, PATH ve belirli yaygın
   kurulum/Hermes dizinlerini kapsıyor; bütün diski taramıyor.
4. `inspect()` bulunamayan dosyayı, uyumsuz CLI'yi, cihaz bulunamamasını ve
   yakalanan süreç hatalarını çoğunlukla aynı boş sonuçla ifade ediyor.
   Arayüzde adayların yolları ve elenme nedenleri birlikte görünmüyor.
5. `_on_local_inspected()` sonucunda istek kimliği yok. Tarama basıldığında
   aynı tercih için eski inceleme sürüyorsa `_local_pending` yeni işi
   engelleyebilir; eski sonuç yeni taramanın sonucu gibi kabul edilebilir.
   Bu son madde koddan çıkarılan yarış olasılığıdır; gerçek UI'da yeniden
   üretilmedi.

## Gerçek uygulama günlüğü

Kaynak: `/Users/user/AppData/Local/WordArc/logs/wordarc.log`.
Saatler günlükte yazıldığı şekildedir; saat dilimi ayrıca doğrulanmadı.

- 25 Ekim 04:29, 04:31 ve 05:13 kayıtları AMD Radeon RX 6650 XT ve
  large-v3-turbo ile başarılı Vulkan çözümlemeleri içeriyor.
- 12:36:52'de aygıt incelemesi `PermissionError` ile başarısız.
- 12:40:05'te çözümleme çağrısı `vulkan_runtime.inspect()` içindeki
  `exe.is_file()` üzerinden `WinError 5` ile kesiliyor. Hedef,
  `AppData/Local/WordArc/engines/whisper-vulkan/whisper-cli.exe`.
- 12:40–12:42 arasında ayar incelemesi aynı hata türüyle tekrar başarısız.

Bu inceleme sırasında PowerShell `Get-Item` aynı dosyanın 489984 baytlık
metadata'sını okuyabildi. Dolayısıyla kalıcı bir dosya izni arızası, antivirüs
müdahalesi veya dosyanın bozulduğu sonucu çıkarılamaz. Geçici erişim sorununun
asıl nedeni henüz bilinmiyor. Kesin olan, bu hatanın bütün keşfi durdurmasıdır.

## İzole yeniden üretim

Mevcut fonksiyon gövdeleri AST üzerinden yüklenip sürücü ve dosya işlemleri
taklit edilerek çalıştırıldı; kullanıcı uygulaması/ayarları değiştirilmedi.

- `inspect()` dosya kontrolüne `PermissionError` verildiğinde hata dışarı
  kaçtı; adayın güvenle elenmesi gerçekleşmedi.
- `get_best_device()` CPU, kullanılabilir CUDA ve kullanılabilir CUDA ile
  Otomatik senaryolarında Vulkan keşfini sıfır kez çağırdı.
- “Motoru tara” işleyicisinin önbellek sıfırlayıp seçili aygıt yenilemesini
  bir kez çağırdığı doğrulandı.

Bunlar kaynak davranışı kanıtıdır; dağıtılan EXE'nin etkileşimli kabul testi
değildir. Genel test seti çalıştırılmadı: bu oturumdaki `.venv` içinde Python
çalıştırıcısı yok, varsayılan Python'da pytest/PyQt6/CTranslate2 bulunmuyor.

## Önerilen sistem

Tarama ile kullanılacak motorun seçimi ayrı işlemler olmalı. “Motorları tara”
CPU, CUDA ve Vulkan yerel arka uçlarının tamamını seçili kullanım tercihinden
bağımsız denetlemeli. Gemini ve Live Gemini için yerel EXE aranmaz; bunların
yapılandırma/bağlantı kontrolü ayrı kalır. Bilinmeyen her EXE'yi çalıştırmak
yerine yalnız WordArc'ın desteklediği motor sözleşmeleri doğrulanır.

1. **Envanter:** CPU Python paketleri, CUDA sürücü/kitaplıkları ve bütün
   desteklenen Vulkan konumları için adayları topla, yolları tekilleştir.
   Kullanıcı ek klasör seçebilsin; varsayılan olarak bütün disk aranmasın.
2. **Aday başına denetim:** Her aday için motor türü, yol, cihazlar ve
   `hazır / eksik / uyumsuz / erişim engellendi / zaman aşımı / denetim hatası`
   sonucu üret. Bulunma, çalıştırılabilme ve model mevcudiyeti ayrı alanlar
   olsun. Erişilemeyen dosya diğer adayları durdurmasın.
3. **İzole yürütme:** Dosya erişimi, DLL yükleme ve sürücü sorguları aday
   sınırında yakalansın. Native sorgular süre sınırlı alt süreçlerde yürüsün;
   iş parçacığı tek başına takılan DLL/sürücü çağrısını durduramaz. Başlangıç
   hedefi aday başına 10 saniye ve tüm tarama için 45 saniye; bunlar gerçek
   donanım ölçümüyle ayarlanacak tasarım varsayımlarıdır.
4. **Güvenilir yaşam döngüsü:** Her taramanın kimliği olsun; eski sonuçlar
   yeni taramayı ezemesin. Kullanıcı ilerlemeyi, hangi motorun kontrol
   edildiğini, iptal ve yeniden dene seçeneklerini görsün. İptal yalnız bu
   taramanın başlattığı alt süreçleri durdursun.
5. **Sonuç ekranı:** CPU, CUDA ve Vulkan için ayrı satırlar; bulunan konum,
   çalışma durumu ve somut neden gösterilsin. “Dosya var” bilgisi “ses
   çözümlemesi doğrulandı” olarak sunulmasın. Kullanıcı isterse hazır
   motor/model için kısa, yerel örnek sesle çalışma denemesi başlatabilsin.
6. **Seçim ve onarım:** Tarama indirme, dosya kopyalama, model değiştirme veya
   etkin motor değiştirme yapmasın. Kullanıcı sonuçtan seçsin; eksik bağımlılık
   için mevcut indirme/onarım işlemi açık düğmeyle başlasın. Aynı keşif
   yardımcıları çalışma zamanı seçiminde de kullanılsın; ayrı doğruluk
   kaynakları oluşmasın.

## Uygulama sırası ve kabul koşulları

- Önce erişim hatası tüm dosya kontrolleri dahil aday sınırında yalıtılır.
  İlk aday erişilemez, ikinci aday hazır olduğunda ikincisi bulunmalı;
  raporda ilk adayın erişim hatası korunmalı.
- Ardından ortak tarama servisi ve sonuç modeli eklenir. CPU seçiliyken bile
  CPU/CUDA/Vulkan satırlarının tamamı sonuçlanmalı. Hazır ilk Vulkan adayı
  bulunduğunda diğer adaylar envanterden kaybolmamalı.
- Arayüz iş kimliği, ilerleme ve iptal ile bağlanır. İki taramanın ters
  sırayla tamamlanması, donanım sorgusunun takılması ve pencerenin kapanması
  anlamlı regresyon senaryoları olmalı.
- Dosya izinleri ve mevcut model/ayarlar korunarak gerçek makinede ve sonra
  paketli EXE'de doğrulanır. CUDA için fiziksel NVIDIA kabulü ayrıca raporlanır.

Tamamlanmış iş: mevcut davranışın incelenmesi, günlük kanıtı, izole yeniden
üretim ve uygulanabilir tasarım. Bekleyen iş: kaynak düzeltmesi, yeni servis,
arayüz, regresyon testleri ve paketli uygulama doğrulaması.
