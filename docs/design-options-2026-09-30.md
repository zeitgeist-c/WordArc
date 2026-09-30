# WordArc tasarım seçenekleri — 2026-09-30

Durum: kullanıcı “Dört sekme · Ayrılmış panel” seçeneğini seçti; kaynakta uygulandı.
Önceki CUDA düzeltmelerinin çalışma ağacı korunuyor. İlk aşamada dağıtım EXE'si
değişmemişti; 2026-10-01 tarihinde yeni arayüz dist paketine aktarıldı (DURUM.md).

## Kullanıcı isteği

- Dört ana sekme beğeniliyor; daha çok sekme de değerlendirmeye açık.
- Gelişmiş ayarları açınca aşağı kaydırma istenmiyor.
- Ayarlar ve seçim pencerelerinin düzeni beğenilmiyor.
- Uygulamadan önce somut seçenekler gösterilecek; kullanıcı seçim yapacak.

## Mevcut kaynakta görülen nedenler

`Disclosure._expand` sayfanın içine yeni dikey içerik açıyor. 1040×760
boyutunda izole Qt denemesinde gelişmiş alanlar açıkken dikte sayfasının
kaydırma aralığı 731 px, toplantının 938 px, dosyanın 83 px olarak ölçüldü;
görünür içerik alanı 504 px. Ölçüm bu ortamın font/ölçek koşullarıyla sınırlıdır.

Ayarlar zaten beş iç kategori kullanıyor. Yalnız daha çok kategori eklemek
sorunu çözmez: bölüm içi form boyu ve genişlik kullanımı da düzenlenmeli.
`FitsOnScreenCombo.showPopup` tüm seçimleri 560×420 bir QDialog'a gönderiyor;
kısa seçenekler de gereksiz büyük seçim akışına giriyor.

## Önerilen ortak ilkeler

- Gelişmiş ayar açılması sayfayı uzatmamalı; ayrılmış panelin içeriğini değiştirmeli.
- Sık kullanılan seçimler ana yüzeyde; seçilen ayrıntı grubunun bütün kontrolleri
  görünür olmalı. Programdaki tüm ayarların aynı anda tek ekrana sığdığı iddia edilmez.
- Az seçenekli tercihler normal küçük açılır liste veya iki/üç seçenekli düğme grubu.
- Uzun cihaz/model adları alana bağlı, aranabilir seçim listesinde; tüm pencereyi
  kaplayan modal seçim yerine yerinde seçim. Özel model adı girişi korunacak.
- Kayıt/durdur, kaydet ve çalışma durumu uzun formun sonunda kaybolmamalı.
- API anahtarları maskeli satırlar ve satır içi eylemlerle gösterilmeli.
- Geçmiş ve terimler uzunlaştığında sayfalama veya ayrı liste görünümü.
- Uzun metin/tutanak içeriği kendi editöründe kaydırılabilir; ayar sayfası
  kaydırmasıyla aynı sorun değildir. Dar pencere ve yüksek Windows ölçeğinde
  sığmayan içeriği kırpmak veya yazıyı küçültmek kabul edilmez.

## Seçenekler

### Dört sekme · Ayrılmış panel — önerilen başlangıç

Dikte / Toplantı / Dosya / Ayarlar korunur. Dikte sağ tarafı
Gelişmiş / Sonuç / Geçmiş arasında değişir; gelişmiş panelin
Kayıt / Çıktı / Metin grupları aşağı uzamaz. Ayarlar tam genişlikte
Ses ve modeller / Metin ve terimler / API / Uygulama gruplarına ayrılır.
Avantaj: alışılmış yapı korunur. Bedel: sonuç ve gelişmiş ayrıntı aynı paneli
paylaştığından ikisi aynı anda görünmez.

### Altı sekme · Açık kategoriler

Dikte / Toplantı / Dosya / Modeller / API / Ayarlar.
Model ve API işlemleri doğrudan ana gezinmede bulunur. Dikte ayarları solda
yerel alt sayfalara ayrılır, sonuç sağda kalır. Avantaj: sonuç ve kayıt
ayrıntısı birlikte görünür. Bedel: ana gezinme daha kalabalıktır.

### Sol menü · Çalışma masası

Solda Dikte / Toplantı / Dosya / Geçmiş / Ses ve modeller / API / Uygulama.
Ortada sonuç, sağda işlem ayrıntıları; görev geçişleri soldan yapılır.
Avantaj: bölümlere doğrudan erişim ve geniş ekran kullanımı.
Bedel: mevcut dört sekmeli alışkanlık değişir; sol menü yatay alan kullanır.

## Önizleme ve seçim sonrası kabul şartları

Üç seçenek aynı etkileşimli önizlemede yer alır. Ana gezinme, gelişmiş
kategori geçişi, alan yanında model arama/seçme ve örnek API ekleme
kontrol edildi. 1068 px genişlikte ve dar önizlemede yatay taşma kontrolü geçti.
Önizleme gerçek mikrofonu, API'yi veya uygulama ayarlarını kullanmaz.

Seçim sonrası Qt uygulamasında tüm kontrollerin envanteriyle taşınma kontrolü,
Windows %100/%125/%150 ölçeği, hedef minimum pencere, klavye odağı, uzun TR/EN
etiketler, popover konumları ve mevcut kayıt akışları sınanmalı. Gerçek ekran
çözünürlüğü/ölçeği henüz bildirilmedi; küçük pencere için seçilebilir panel ve
panel içinde sınırlı kaydırma yedeği bulunuyor.

## Uygulama ve doğrulama — 2026-10-01

Dört ana sekme korunuyor. Dikte sağ panelinde Gelişmiş / Son dikte / Geçmiş,
gelişmiş içinde Kayıt / Çıktı / Metin yer alıyor. Toplantı sağ paneli Tutanaklar /
Gelişmiş; ses kaynakları solda sabit. Dosya seçenekleri ve temizleme kuralları
yerel sayfalar, çıktı sağda. Ayarlar yatay Ses ve modeller / Metin ve terimler /
API anahtarları / Uygulama kategorilerine ayrıldı. İndirme ilerlemesi model
kontrollerini aşağı itmeden ayrı yerel sayfada açılıyor.

Uzun/aranabilir seçimler alan yanında, ekran sınırlarına yerleşen Qt.Popup
menüleridir. Kısa listeler yerel açılır seçim kullanır. Arama, tek tıklama,
Enter/Escape, klavyeyle listeye geçiş ve özel model adı test edildi. Dil
değiştirirken seçili ayrıntı sayfaları korunur; eski geçmiş/tutanak gezinme
kimlikleri ilgili paneli açar.

Windows Segoe UI fontlarıyla 1040×760 ve 920×700 boyutlarında bütün seçili
masaüstü formları için yatay/dikey QScrollArea aralığı sıfır. TR/EN ve açık/koyu
temalar otomatik kontrol edildi. 520×400 boyutunda ayrıntı editörüne erişim
kontrolü geçti; bu boyutta panel içi kaydırma yedeği kullanılabilir. Metin
editörleri ve uzun listeler kendi içlerinde kaydırılır. Gerçek kullanıcının
monitörü/DPI'si ve canlı kayıt akışı ayrıca doğrulanmış değildir.

Tüm kaynak testleri: 377 geçti, 1 ağ testi atlandı. Bağımlılık kontrolü temiz.
Son kaynakla console twin EXE yeni çalışma alanını açtı; gerçek base model ve
sentetik sessiz WAV ile CPU çözümlemesi/unicodedata denetimi geçti. Teslim spec'i
ayrı test dizininde derlendi: Unicode uzantısı, motor DLL'si, CUDA yardımcı modülü
ve yeni yönergeler arşivde doğrulandı; izole --version açılışı geçti. Bu test
EXE'leri dağıtım teslimi değildir; gerçek mikrofon/GPU testi yerine geçmez.
Yeni sürüm/commit/tag/push yok; çalışma ağacı bu görev kapsamındaki değişiklikleri
içeriyor. Başlangıç HEAD: 02f2a0e; sürüm: 0.6.4.
