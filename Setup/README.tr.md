# WordArc Windows kurulumu

`WordArc-Setup-v0.4.2.exe` başka bir Windows 10/11 x64 bilgisayara
kopyalanıp doğrudan çalıştırılabilir. Python veya FFmpeg kurulumu gerekmez.

Kurulum kullanıcı profiline yapılır; yönetici yetkisi istemez. Başlat menüsü
kısayolu oluşturulur. Masaüstü kısayolu ve Windows ile otomatik başlatma
seçenekleri kurulum ekranından değiştirilebilir.

Kurulum paketi üretmek için proje kökünden:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" ".\Setup\wordarc.iss"
```

Eski Verbatim veri klasörleri silinmez. WordArc ilk çalışmada eksik ayar ve
verileri güvenli biçimde kendi dizinlerine taşır.
