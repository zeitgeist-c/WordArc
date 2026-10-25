# Güncelleme/kurulum geçişi — 25 Ekim 2026

Başlangıç: `1660c0e` / v0.10.3 kaynak; kullanıcının çalışan kurulumu 0.10.2.
Kullanıcı, düzeltmenin 0.10.4 olarak yayımlanmasını ve Program Files'a kurulmasını
açıkça onayladı. Önceden var olan AppPublisher=Geeker değişikliği ayrı tutulur.

## Kanıt

- Çalışan EXE: `C:/tmp/iss-e2e/app/WordArc.exe`. Windows'un 32 bit uninstall
  kaydı DisplayVersion=0.10.2, InstallLocation aynı test klasörü. Bu yolun
  önceki kabulde kalıcı kurulum olarak korunması yanlıştı.
- Günlükte 25 Ekim 13:53 ve 13:57'de yalnız `setup launched` var; ardından
  yeni sürümün kurulduğuna veya açıldığına dair kanıt yok. Eski sürüm kaldı.
- İndirilen `WordArc-0.10.3-setup.exe` 312251266 bayt ve SHA256
  `b08be38282ffa812a9a960ff77ece933ee3de10e69f91adba57ab7e834846556`:
  yayınla aynı. Bu olay bozuk/eksik indirme olarak açıklanamaz.
- Eski kod ShellExecuteW isteğinin kabul edilmesini kurulum başarısı gibi
  ele alıp uygulamayı kapatıyordu. Hazırlık bildirimi, sonuç kodu, kalıcı
  kurulum günlüğü ve yeni uygulama açılış onayı yoktu. O eski girişimlerin
  hangi işletim sistemi hatasıyla durduğu geriye dönük kanıtlanamadı.
- Inno varsayılan UsePreviousAppDir=yes olduğundan test yolu devralınıyordu.
  ArchitecturesAllowed tek başına 64 bit kurulum modunu etkinleştirmiyordu.

## Düzeltme

Kurulum hedefi 64 bit `Program Files/WordArc` olarak sabitlendi; önceki test
yolu ve `/DIR` bu ürün hedefini değiştiremez. Kurulum günlükleri açık.

Dosya kurma/geri alma işini yine Inno yapar. Küçük, bağımsız bir Windows
denetleyicisi yalnız geçişi izler. İmzalanmamış özel bir dosya değiştirme
motoru yazılmadı:

1. İndirme, geçici Windows klasörü yerine kullanıcıya ait kalıcı güncelleme
   dizininde tutulur; SHA256 yeniden denetlenir.
2. Denetleyici doğrulanmış kendi kopyasıyla ayrı süreçte başlar. Donmuş
   uygulamanın DLL arama yolu ve PyInstaller süreç ortamı dış kurulumdan
   ayrılır. Windows yönetici izin isteği sırasında eski uygulama açık kalır.
3. Inno, yeni payload'u geçici olarak açıp internet/kullanıcı ayarı gerektirmeyen
   açılış kontrolünü çalıştırır. Bu kontrol başarısızsa mevcut kurulum değişmez.
4. Inno hazır bildirimi verir; uygulama bunu alınca kapanır. Kurulum eski PID'nin
   çıkmasını bekler. Denetleyici gerçek kurulum çıkış kodunu izler.
5. Kurulu yeni EXE yine çevrimdışı kontrol edilir, temiz ortamla kullanıcı
   olarak açılır ve gerçek UI başlangıcını sürüm/yol içeren onayla bildirir.
6. Eski konumdaki yalnız önceden hash'i kaydedilmiş uygulama/uninstall dosyaları
   bundan sonra silinir. Başarılı geçişte indirme ve önceki EXE kurtarma kopyası
   temizlenir; günlük ve durum kaydı kalır. Kullanıcı dosyası değişmişse silinmez.
7. Hata, iptal ve zaman aşımı eski uygulamayı sessizce kaybettirmez. Eski süreç
   kapandıysa ve kurulum artık çalışmıyorsa, değişmemiş eski EXE veya özel
   kurtarma kopyası yeniden açılır. Kurtarma geçici özel kopyadan yapılabilir;
   bu başarısız durum normal Program Files kurulumu olarak sunulmaz.

Yeni kurulum 64 bit kaydı kullanır. Eski 32 bit uninstall/başlangıç kaydı ancak
yeni payload doğrulanıp kurulduktan sonra ve eski kurulum yoluyla eşleşiyorsa
kaldırılır. Mevcut masaüstü kısayolu yeni hedefe güncellenir. Ayarlar, ses
kayıtları, toplantılar ve modeller bu temizliğin kapsamına girmez.

## Kaynak ve ayrı kurulum denemeleri

- Kaynak test turu: 744 test, 2 atlama, 12 subtest; son paket kapıları ayrıca
  yürütülür. Hata/izin reddi/kurulum erken çıkışı/yanlış yeni sürüm/başlangıç
  onayı yokluğu/eski dosyaların korunması testleri eklendi.
- Gerçek Inno, desteklenmeyen payload'u çıkış kodu 7 ile reddetti; eski dosya
  değişmedi. Kanıt `.cache/installer-preflight-test/reject.log`.
- Ayrı AppId, ayrı klasör ve sentetik payload ile gerçek Inno hazırlık
  bildirimi → yalnız testin eski sürecinin kapanması → kurulum → yeni süreç
  başlangıç onayı → eski dosyanın silinmesi geçti. Aynı klasördeki kullanıcı
  belgesi korundu. Kanıt `.cache/installer-cycle/result.json`.
- Bu ayrı test yönetici izin ekranını simüle etmez; özel test kurulumunda
  UAC gerektirmeyen mod kullanılır. Gerçek Program Files/UAC kabulü ve teslim
  paketinin doğrulamaları sürüm kapanış kaydında ayrıca belirtilir.

## Resmî davranış kaynakları

- Inno önceki yol varsayılanı: https://jrsoftware.org/ishelp/topic_setup_usepreviousappdir.htm
- Inno hazırlık aşaması: https://jrsoftware.org/ishelp/topic_scriptevents.htm
- 64 bit kurulum modu: https://jrsoftware.org/ishelp/topic_setup_architecturesinstallin64bitmode.htm
- Donmuş süreç dış program/yeniden başlatma ortamı:
  https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
