# WordArc — Windows için sesle yazma

> English: [README.md](./README.md)

WordArc konuşmayı düzenlenmiş metne dönüştürür. `Ctrl+Space` bas, konuş, tekrar bas — metin yazıya çevrilir, temizlenir ve çalıştığın yere yapıştırılır. Mikrofon + sistem sesiyle güvenilir toplantı tutanağı da alır.

![Ayarlar - Dikte](./docs/screenshots/01-ayarlar-dikte.png)

## Özellikler

- **Bas-konuş dikte** — `Ctrl+Space` başlat/durdur, `Escape` yazıya çevirmeden siler.
- **Toplantı modu** — `wordarc.py meeting` mikrofon + sistem sesini (WASAPI loopback) kaydeder, tutanaklık metin üretir.
- **Ekran görüntüsü** — `Ctrl+Alt+S` ile etkin ekranda alan seç; Ayarlar sekmesinden etkin ekranı al, görüntüyü panoya kopyala veya PNG/JPEG kaydet.
- **Sistem sesi yakalama** — karşı taraf sesi mikser paylaşımı olmadan alınır.
- **Ses aktivite algısı (VAD)** — göndermeden önce sessizliği kırpar.
- **Çalıştığın yere yapıştır** — sonuç odaktaki uygulamaya yapıştırılır.
- **Tepsi servisi** — dikte, ajan, toplantı, ayarlar tepsi menüsünde; yerel IPC ile tek örnek.
- **Metin geçmişi (seçimlik)** — varsayılan kapalı; açılınca geçmiş yerel düz metindir.
- **Öncelik gizlilikte** — başarılı toplantı sesi varsayılan silinir; Gemini anahtarı Windows Credential Manager'da (`WordArc/GeminiApiKey`).
- **İki dil** — Türkçe ve İngilizce; koyu varsayılan, açık ve sistem temalı.
- **Eski kurulum geçişi** — ilk açılışta eksik dosyalar atomik kopyalanır, mevcut WordArc dosyaları ezilmez.

## Hızlı başlangıç (sıfır kurulum)

1. Güncel `WordArc-X.Y.Z.exe` indirilir ve çalıştırılır (Program Files'a admin kurulum, ~500MB — NVIDIA kullanılacaksa GPU desteği sonradan iner).
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

`check.ps1` pytest, compileall ve tüm modüllerin import kontrolünü yapar. `build.ps1` sabit FFmpeg sürümünü doğrular, testleri koşar, bağımlılık denetimi yapar, `sbom.json` üretir, deterministik ikonu çizer, TTS ağırlıklarını vendorlar ve kurulum dosyasını PyInstaller + Inno Setup ile üretir.

## Veri ve gizlilik

- Ayarlar: `%APPDATA%\WordArc\config.json`
- Kayıtlar, toplantılar, tanılama ve indirilen modeller: `%LOCALAPPDATA%\WordArc\` (konuşma modelleri `whisper`, GPU çalışması `cuda` altında — kurulum ve kaldırma bunlara dokunmaz)
- Gemini anahtarı: Windows Credential Manager, `WordArc/GeminiApiKey`
- Geçmiş varsayılan kapalı; başarılı toplantı sesi varsayılan silinir.
- `verbatim.py` bir sürüm boyunca uyumluluk giriş noktasıdır.

## Proje yapısı

```text
wordarc.py        tepsi uygulaması, CLI, tek örnek IPC
worker.py         dikte hattı
meeting.py        toplantı hattı
audio*.py         mikrofon + WASAPI loopback yakalama
settings_ui.py    ayarlar ve ekran görüntüsü sekmeleri
screenshot_capture.py  alan/tam ekran yakalama ve yerel önizleme
hotkey.py         genel kısayollar
assets/brand      özgün SVG kaynakları, ikon üretimi
tools/            marka ve yardımcı scriptler
tests/            pytest paketi
```

## SSS

- **`Ctrl+Space` işlemiyor?** Kısayol başka uygulamada olabilir — boşaltıp `wordarc.py restart` çalıştır.
- **Toplantıda karşı ses yok?** Sistem sesi yakalama loopback ister; Windows ses ayarlarına bak.
- **Anahtar reddedildi?** Ayarlar'dan yeniden gir; yalnızca Credential Manager'da durur.
- **Yerel model GPU'da mı?** Yerel motor GPU'yu ve CUDA 12/cuBLAS/cuDNN 9 DLL'lerini kontrol eder. Otomatik modda CUDA kullanılamazsa CPU (`int8`) seçilir; geç çözümleme hatasında kayıt baştan CPU'da işlenir. Cihaz=Nvidia GPU seçiliyken başlatma/çözümleme başarısızsa neden gösterilir ve CPU geçişi bir kez sorulur. Onayla ayar kaydedilir, aynı kayıt CPU'da yeniden işlenir. Redde ayar korunur. Cihaz Ayarlar → Ses ve modeller bölümünden seçilir.
- **CUDA bağımlılıkları ve paketleme:** Kaynaktan çalıştırırken `.venv\Scripts\python.exe -m pip install -r requirements-cuda.txt` kullanılır. Standart `./build.ps1 -Python .venv/Scripts/python.exe` derlemesi NVIDIA CUDA runtime/cuBLAS/NVRTC/cuDNN kitaplıklarını kurar, EXE'ye ekler ve arşivde doğrular. NVIDIA sürücüsü ayrıca kurulu olmalıdır. İlk indirme yaklaşık 1,4 GB'dır. DLL denetimi gerçek GPU çözümlemesinin yerine geçmez; [GPU kabul adımları](docs/cuda-acceptance-0.6.7.md) ayrı uygulanır.
- **AMD ekran kartı:** 0.6.9 ile Ayarlar → Ses ve modeller → Cihaz bölümünde **AMD ekran kartı (Vulkan)** bulunur. Otomatik seçim önce NVIDIA CUDA'yı, ardından kullanılabilir AMD Vulkan'ı, ardından CPU'yu seçer. Vulkan motoru ve DLL'leri EXE'dedir; kullanıcıya Vulkan SDK/ROCm kurulumu gerekmez. AMD'nin Vulkan destekli ekran kartı sürücüsü kurulu olmalıdır.
- **AMD model indirmesi:** AMD için whisper.cpp/GGML biçimindeki model ayrıca indirilir (`large-v3-turbo`: yaklaşık 1,5 GB). Cihazı AMD veya Otomatik seçip **İndir** düğmesini kullanın. Önceki CPU/CUDA modeliniz korunur; Vulkan modeli henüz yoksa Otomatik mod eski CPU modeliyle çalışır. Vulkan başarısızsa Otomatik mod aynı kaydı CPU'da tekrar işler; AMD elle seçiliyse CPU'ya geçip ayarı kaydetmeden önce bir kez onay ister. CPU kurtarması mevcut GGML modelini kullanabilir, ikinci model indirmesi şart değildir.
- **AMD doğrulama ve hız:** RX 6650 XT / Ryzen 7 7700 için araştırma, ölçüm yöntemi ve paket kabulü [AMD/Vulkan notunda](docs/amd-vulkan-0.6.9.md) bulunur. Tek bir örnek kaydın sonucu tüm Türkçe kayıtlar için kalite/hız garantisi değildir.

## Yol haritası

- `docs/screenshots/` temiz kurulum görüntüleri
- Temizlik için daha fazla dilbilgisi
- Uygulama bazlı yapıştırma profilleri

## Katkı

Akış: issue aç, küçük PR, push öncesi `.\check.ps1` çalıştır. Şablon: [PR şablonu](./.github/PULL_REQUEST_TEMPLATE.md).

## Lisans

GPL-3.0. Özgün Linux projesi [yusufipk](https://github.com/yusufipk/dikte) tarafından geliştirilmiştir.
