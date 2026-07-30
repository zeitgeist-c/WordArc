# Dikte — Sesle yazı yazma (Windows)

Küresel bir kısayola basın, konuşun, tekrar basın — temizlenmiş transkripsiyon imlecinizin olduğu yere yapıştırılır.

## Hızlı başlangıç

1. `dikte.exe` dosyasını Sürümler sayfasından indirin (veya kaynaktan derleyin).
2. Aynı klasörde `install.ps1` çalıştırarak Başlat Menüsü kısayolu ve otomatik başlatma ekleyin.
3. Dikte'yi başlatın — ilk çalıştırmada ayarlar penceresi açılır.
4. **Ayarlar → API** bölümüne Gemini veya OpenRouter API anahtarı ekleyin.

## Kullanım

| Eylem | Sonuç |
|--------|--------|
| `Ctrl+Boşluk` | Dikteyi başlat / durdur |
| Konuşun, ardından `Ctrl+Boşluk` | Transkripsiyon imlece yapıştırılır |
| Tepsi → Kaydı iptal et | Geçerli kaydı sil |
| Tepsi → Asistan'a sor | Claude/Codex/OpenRouter'a soru sorun |
| Tepsi → Toplantı kaydet | Stereo toplantı kaydı (mikrofon + sistem sesi) |
| Tepsi → Ayarlar | API anahtarları, kısayollar, dil, dosya transkripsiyonu |

## Kaynaktan çalıştırma

```powershell
python -m pip install -r requirements.txt
python dikte.py
```

PyQt6, sounddevice, Python 3.10+ gereklidir.

## PyInstaller ile derleme

Proje köküne `ffmpeg.exe` koyun (gyan.dev adresinden), ardından:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed --add-data "ffmpeg.exe;." --collect-all sounddevice --name dikte dikte.py
```

Çıktı: `dist\dikte.exe` (~110 MB, tek dosya).

## Yapılandırma

`%APPDATA%\Dikte\config.json` konumunda saklanır. Ses çıktısı ve toplantı verileri `%LOCALAPPDATA%\Dikte\` klasöründedir.

## Orijinal proje

Dikte ilk olarak [yusufipk](https://github.com/yusufipk/dikte) tarafından Linux için geliştirilmiştir (GPL-3.0). Bu sürüm, aynı lisansla Windows'a taşınmış bir çataldır.
