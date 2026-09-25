# WordArc — DURUM (ortak — Desktop + Telegram okur)

**Güncelleme:** 2026-09-25
**Versiyon:** 0.4.22 (`brand.py`)
**Branch:** master
**Son commit:** 994b4fc (v0.4.22 Yenile düğmesi cihaz listesi)
**Ağaç:** temiz
**Not:** Temiz ağaç; akış `wordarc-release` skill'i ile.

## Sırada
- Kullanıcı söyler.

## Yerel konuşma tanıma (2026-09-26, commitlenmedi)
Bulut (Gemini) varsayılan; ayarlarda **Nerede çalışsın** = bulut / yerel.
Yerel = faster-whisper, CPU, model exe'ye gömülmez, kullanıcı veri dizininde.

- `localspeech.py` — ortak STT katmanı: model yükleme, indirme, silme, WAV okuma.
- Üç model: `base` 141 MB / `small` 464 MB / `large-v3-turbo` 1,5 GB.
- Yerel ham metni verir; **temizleme hâlâ bulutta** (cloud cleanup).
- Toplantıda iki kanal ayrı çevrilir; konuşmacı ataması korunur.
- Yerel seçiliyse hata olsa bile ses buluta **gitmez** (bilinçli karar).

Ölçüm (30 sn, zor Türkçe kayıt, 50 kelime): base 43/50 · small 42/50 ·
large-v3-turbo 43/50; sırasıyla 18× / 9× / 4× gerçek zamanlı. turbo en zor
sesde en güvenli; "en doğru" değil, "en zor ses" deniyor.

Doğrulama: 215 test + `tools/verify_frozen_build.py` (konsol gölge spec'ten
gerçek transkripsiyon). Exe 88 MB → 174 MB.

Tuzaklar `wordarc-release` skill'ine yazıldı: spec'e hidden import yetmez,
build ortamında kurulu olmalı; `config.json` doğrulama betiğiyle ezilmemeli.
