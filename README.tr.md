# WordArc — Windows için sesle yazma

> English: [README.md](./README.md)

WordArc konuşmayı düzenlenmiş metne dönüştürür. `Ctrl+Space` bas, konuş, tekrar bas — metin yazıya çevrilir, temizlenir ve çalıştığın yere yapıştırılır. Mikrofon + sistem sesiyle güvenilir toplantı tutanağı da alır.

![Ayarlar - Dikte](./docs/screenshots/01-ayarlar-dikte.png)

## Özellikler

- **Bas-konuş dikte** — `Ctrl+Space` başlat/durdur, `Escape` yazıya çevirmeden siler.
- **Toplantı modu** — `wordarc.py meeting` mikrofon + sistem sesini (WASAPI loopback) kaydeder, tutanaklık metin üretir.
- **Sistem sesi yakalama** — karşı taraf sesi mikser paylaşımı olmadan alınır.
- **Ses aktivite algısı (VAD)** — göndermeden önce sessizliği kırpar.
- **Çalıştığın yere yapıştır** — sonuç odaktaki uygulamaya yapıştırılır.
- **Tepsi servisi** — dikte, ajan, toplantı, ayarlar tepsi menüsünde; yerel IPC ile tek örnek.
- **Metin geçmişi (seçimlik)** — varsayılan kapalı; açılınca geçmiş yerel düz metindir.
- **Öncelik gizlilikte** — başarılı toplantı sesi varsayılan silinir; Gemini anahtarı Windows Credential Manager'da (`WordArc/GeminiApiKey`).
- **İki dil** — Türkçe ve İngilizce; koyu varsayılan, açık ve sistem temalı.
- **Eski kurulum geçişi** — ilk açılışta eksik dosyalar atomik kopyalanır, mevcut WordArc dosyaları ezilmez.

## Hızlı başlangıç (sıfır kurulum)

1. Güncel `WordArc-X.Y.Z.exe` ile `install.ps1` aynı klasöre konur, `install.ps1` çalıştırılır.
2. WordArc başlatılır — ilk açılışta Ayarlar gelir. Gemini API anahtarı girilir.
3. `Ctrl+Space` bir kez basılır, konuşulur, tekrar basılır. Temiz metin yapıştırılır.

Komut satırı:

```powershell
python wordarc.py             # Ayarları aç, tepsi servisini çalıştır
python wordarc.py background  # arkaplanda çalış (Windows başlangıcı)
python wordarc.py toggle      # kaydı başlat / durdur
python wordarc.py cancel      # kaydı sil
python wordarc.py meeting     # toplantı kaydını başlat / bitir
python wordarc.py settings    # ayar penceresini aç
python wordarc.py quit        # uygulamayı kapat
```

## Geliştirme

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-lock.txt -r requirements-dev.txt
python wordarc.py
```

Kontrol ve derleme:

```powershell
.\check.ps1
.\build.ps1
```

`check.ps1` pytest, compileall ve tüm modüllerin import kontrolünü yapar. `build.ps1` sabit FFmpeg sürümünü doğrular, testleri koşar, bağımlılık denetimi yapar, `sbom.json` üretir, deterministik ikonu çizer ve PyInstaller ile `dist\WordArc-X.Y.Z.exe` + eşleşen `.bat` paketler.

## Veri ve gizlilik

- Ayarlar: `%APPDATA%\WordArc\config.json`
- Kayıtlar, toplantılar, tanılama: `%LOCALAPPDATA%\WordArc\`
- Gemini anahtarı: Windows Credential Manager, `WordArc/GeminiApiKey`
- Geçmiş varsayılan kapalı; başarılı toplantı sesi varsayılan silinir.
- `verbatim.py` bir sürüm boyunca uyumluluk giriş noktasıdır.

## Proje yapısı

```text
wordarc.py        tepsi uygulaması, CLI, tek örnek IPC
worker.py         dikte hattı
meeting.py        toplantı hattı
audio*.py         mikrofon + WASAPI loopback yakalama
settings_ui.py    ayar penceresi
hotkey.py         genel kısayol
assets/brand      özgün SVG kaynakları, ikon üretimi
tools/            marka ve yardımcı scriptler
tests/            pytest paketi
```

## SSS

- **`Ctrl+Space` işlemiyor?** Kısayol başka uygulamada olabilir — boşaltıp `wordarc.py restart` çalıştır.
- **Toplantıda karşı ses yok?** Sistem sesi yakalama loopback ister; Windows ses ayarlarına bak.
- **Anahtar reddedildi?** Ayarlar'dan yeniden gir; yalnızca Credential Manager'da durur.
- **Yerel model GPU'da mı?** Yerel motor, sürücü ve CUDA çalışması yanıt veriyorsa Nvidia GPU'yu kendi seçer (kart fark etmez, `cuda` + `float16`); yoksa CPU ile çalışır (`cpu` + `int8`). Nvidia GPU için güncel sürücü + CUDA runtime gerekir; Windows'ta AMD kartlarda yalnızca CPU desteklenir. Cihaz Ayarlar → Konuşmayı yazıya çevir → Cihaz adımından zorlanabilir.

## Yol haritası

- `docs/screenshots/` temiz kurulum görüntüleri
- Temizlik için daha fazla dilbilgisi
- Uygulama bazlı yapıştırma profilleri

## Katkı

Akış: issue aç, küçük PR, push öncesi `.\check.ps1` çalıştır. Şablon: [PR şablonu](./.github/PULL_REQUEST_TEMPLATE.md).

## Lisans

GPL-3.0. Özgün Linux projesi [yusufipk](https://github.com/yusufipk/dikte) tarafından geliştirilmiştir.
