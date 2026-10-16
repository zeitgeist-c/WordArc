# WordArc 0.8.3 ekran görüntüsü kalite incelemesi

Tarih: 2026-10-16. Kapsam: mevcut yakalama/editör akışı, kısayollar ve
0.8.3 dağıtımı. Önceki çalışma ağacındaki aynı kapsamlı değişiklikler dahil.

## Karşılaştırma ve kararlar

- [LightShot](https://app.prntscr.com/en/hotkeys.html): Ctrl ile seçimden
  anında kopyalama, Ctrl+C/S, Esc ve Ctrl+A davranışları incelendi. WordArc'ta
  Ctrl+A ile ekranı seçme eklendi; kaydetme dosya adı/klasör seçimini koruyor.
- [ShareX](https://getsharex.com/docs/region-capture): araç kısayolları, oklarla
  hassas taşıma, Shift+Delete ile tüm işaretleri silme ve geri alma örnek alındı.
- [Flameshot](https://flameshot.org/docs/guide/key-bindings/): yakalama sırasında
  araçlara hızlı erişim ve kompakt düzen yaklaşımı karşılaştırıldı.
- [ScreenForge](https://github.com/ruwiss/screen_forge): mevcut referans raporunda
  adı geçen proje bulundu; düzenleme/yakalama kapsamı resmi README ile kontrol
  edildi. Kullanıcı 2026-10-16 tarihinde kastettiği referansın bu GitHub projesi
  olduğunu doğruladı. Önceki rapor:
  `50 - Kaynaklar/Arastirma/2026-10-16-wordarc-ekran-alinti-onderme/report.md`
  (Obsidian). Bu eski rapor öneridir; tamamlanmış özellik kanıtı değildir.

## Bu sürümde düzeltmeler

- İki sıralı simge çubuğu; araç adları ve tuşları ipuçlarında.
- Pause ve diğer tek tuşlarla bas-ata; tek atama sonrası dinleme kapanır.
  Genel kısayollar ve kayıt iptal tuşu dinleme boyunca askıya alınır.
- Aynı Windows kombinasyonu iki genel işleme atanırsa ayarlar değiştirilmeden
  kayıt reddedilir; Ctrl/Control ve Print/PrintScreen eşdeğerleri de kontrol edilir.
- Kaydet penceresinin sahibi yakalama katmanı; iptal edilirse editör korunur.
- Bulanıklaştırmada özgün detay artık geri karıştırılmaz. Etkiler çizim sırasına
  uyar: daha sonra uygulanan bulanıklık önceki metin/şekilleri de etkiler.
  Bulanıklık/mozaik kesin veri silme garantisi değildir; hassas içerik için
  opak dolgulu dikdörtgen kullanılabilir.
- Saydam JPEG beyaz zemine dönüştürülür.
- Geri al/ileri al düğmeleri geçmişin durumunu gösterir; Shift+Delete ile temizleme
  geri alınabilir. Ctrl+A tam ekranı seçer; oklar seçimi 1, Shift+ok 10 piksel taşır.
- V seçme, P kalem, L çizgi, A ok, R dikdörtgen, E elips, H vurgu, T metin,
  N numaralı adım, B bulanıklık, M mozaik. Ctrl+C/S/Z/Y ve Enter/Esc korunur.
- Win32 kayıt imzaları tanımlandı, uygulama kısayol kimlikleri uygun aralıkta
  yeniden kullanılıyor. Başka uygulamaya ait Pause kaydı zorla alınmaz.

## Sonraki işler ve sınırlar

Yerel OCR, son bölgeyi yeniden yakalama, çoklu monitörün tamamını birleştirme,
kayan sayfa ve ekran sabitleme değerlendirilebilir. OCR ek bağımlılık/paket
doğrulaması; karma DPI ve monitörler arası yakalama gerçek donanım denemesi
gerektirir. Bu sürüm aktif ekran yakalamasını korur. Bu incelemede başka
uygulamaların tüm ikilileri çalıştırılmadı; belgeler ve mevcut kaynak incelendi.
Fiziksel klavye/gerçek çoklu monitör denemesi otomatik testlerin yerine geçmez.

Güncel test, paket hash'i ve Git/yayın kanıtları `DURUM.md` içindedir.
