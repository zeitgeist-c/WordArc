# WordArc — Windows için sesle yazma

WordArc konuşmayı düzenlenmiş metne dönüştürür, toplantı tutanağı için mikrofon ile sistem sesini kaydeder ve sesli komutları çalışma başına açık izinle Claude Code veya Codex'e iletebilir.

## Kurulum

1. `wordarc.exe` dosyasını indirin veya kaynaktan derleyin.
2. `wordarc.exe` ile `install.ps1` dosyasını aynı klasöre koyup `install.ps1` çalıştırın.
3. WordArc'ı başlatın. İlk çalıştırmada Ayarlar açılır.

Varsayılan kısayol `Ctrl+Space` tuşudur: kaydı başlatmak ve yazıya çevirmek için birer kez basın. Dikte, ajan, toplantı ve ayarlar işlemlerine tepsi menüsünden de erişilebilir.

## Geliştirme

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-lock.txt -r requirements-dev.txt
python wordarc.py
```

```powershell
.\check.ps1
.\build.ps1
```

Çıktı `dist\wordarc.exe` olur. Build; sabitlenmiş FFmpeg sürümünü ve özetini doğrular, testleri/import kontrolünü ve bağımlılık denetimini çalıştırır, `sbom.json` üretir, deterministik WordArc ikonunu oluşturur ve PyInstaller paketini hazırlar.

## Veri, gizlilik ve geçiş

Ayarlar `%APPDATA%\WordArc\config.json`; kayıtlar, toplantılar ve tanılama günlükleri `%LOCALAPPDATA%\WordArc\` altında tutulur. Gemini anahtarı Windows Credential Manager'da `WordArc/GeminiApiKey` adıyla saklanır.

İlk açılışta eski Verbatim dizinlerindeki eksik dosyalar atomik biçimde kopyalanır. Eski kimlik bilgisi yeni hedefe kopyalanıp doğrulandıktan sonra eski kayıt kaldırılır. WordArc'ta bulunan dosyaların üzerine yazılmaz ve eski dizinler silinmez; geri dönüş kopyası olarak kalır. `verbatim.py` bir sürüm boyunca uyumluluk giriş noktasıdır.

Geçmiş yeni kurulumlarda kapalıdır. Açılırsa geçmiş ve toplantı metinleri yerel diskte okunabilir metin olarak saklanır. Başarılı toplantı ses kaydı varsayılan olarak silinir.

Koyu tema varsayılandır; Açık ve Sistem temaları Ayarlar'dan anında değiştirilebilir. Marka SVG kaynakları `assets\brand` altındadır.

WordArc GPL-3.0 lisanslıdır. Özgün Linux projesi [yusufipk](https://github.com/yusufipk/dikte) tarafından geliştirilmiştir.
