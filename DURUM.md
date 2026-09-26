# WordArc — DURUM (ortak — Desktop + Telegram okur)

**Güncelleme:** 2026-09-26
**Versiyon:** 0.4.24 (`brand.py`)
**Branch:** master
**Son commit:** 32890b3 (v0.4.23 Yerel Whisper + cihaz kart listesi)
**Ağaç:** temiz (yedek akışı çalışıyor)
**Not:** Akış `wordarc-release` skill'i ile.

## Sırada
- Kullanıcı söyler.

## Liste yerleşimi düzeltmesi (2026-09-26, commitlenmedi)
Şikayet: listeler hiç görünmüyor. Kök neden: popup iki yana da sığmadığında
eski kod tam boyu koruyup ekran dışına itiyordu (`_open_where_it_fits`).
Ayrıca Qt seçili satırı kutuyla hizalar; geç seçimde popup üstten taşar,
altta yer olsa bile.
Düzeltme: `_choose_placement` (saf fonksiyon) — Qt'nin yeri görünürse
dokunma; alta tam sığarsa kutunun altına; üste tam sığarsa yukarı; hiçbiri
olmazsa geniş tarafı alıp o odaya kısalt (en az 3 satır), liste kayar.
Doğrulama: 234 test (6 yeni `TestPlacementMath`, ekransız deterministik) +
`tools/check_dropdowns.py` 0 kesik. `tmm` gelmeden commit yok.

## Yerel konuşma tanıma (v0.4.23'te yayında)
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
