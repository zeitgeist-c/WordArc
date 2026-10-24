# WordArc 0.10.2 — 24.10.2026 güncelleme denetimi

Kullanıcı ekranında denetim `Denetleniyor…` durumunda kalıyor. Mevcut uygulama
logunda aynı yolun üç hatası görüldü (09:30, 12:34, 13:27): `_UpdateWorker.run`
→ `update.fetch_latest` → `urllib.request.urlopen` → varsayılan SSL context
oluşturulurken `ssl.SSLError: [X509] BIO lib`. Bu hata UpdateError olmadığı için
worker'dan kaçıyor; ne sonuç ne hata sinyali gönderiliyor. Önceki kabul yalnız
kaynak HTTP isteğini sınamıştı; donmuş uygulamanın arayüz denetimini kapsamıyordu.

## Düzeltme

- Güncelleme sorgusu ve indirmesi, paketlenen certifi CA verisinden açıkça HTTPS
  context oluşturur ve bellekte tutar. `CERT_REQUIRED` ve hostname doğrulaması
  açık kalır; doğrulama devre dışı bırakılmaz. Varsayılan Windows sertifika
  yükleyicisinin BIO hatasına sebep olan yol kullanılmaz.
- SSL/ağ/bozuk JSON hata yolları UpdateError olur. Worker beklenmeyen istisnaları
  da loglayıp arayüze terminal hata sinyali iletir.
- 30 saniyelik Qt zamanlayıcısı, uzun süren denetimi sonuçlandırır. Düğme yeniden
  kullanılabilir olur. Her denetimin kimliği vardır; süresi dolmuş isteğin geç
  cevabı sonraki denetimin durumunu değiştiremez.
- Yeniden deneme eski indirme teklifini temizler; güncel/hata sonucu butonları
  tutarlı biçimde geri getirir.
- `--update-check --output <json>` yalnız açık tanılama kipidir. Gerçek worker,
  Qt sinyalleri, durum metodu ve HTTPS yolunu kullanır; kullanıcı ayarı, kayıt,
  kimlik bilgisi ya da kurulu uygulama üzerinde değişiklik yapmaz.

## Doğrulama

- Düzeltme öncesi logdaki SSL hatasını temsil eden iki test başarısızdı;
  düzeltme sonrası güncelleme/arayüz grubu 95 test geçti.
- Tam grup: **710 passed, 2 skipped, 12 subtests**, 83,10 s.
- `check.ps1 -Audit` import/derleme/installer kontrolleri ve bağımlılık denetimi
  geçti; bilinen açık bulunmadı.
- Gerçek kaynak Ayarlar penceresinde düğmeye tıklanarak kontrol tamamlandı;
  güncel sürüm sonucu ve etkin düğme doğrulandı. Kaynak tanılama JSON'u: başarı,
  state=latest, check_enabled=true, tls_verified=true, yaklaşık 0,80 s.
- Donmuş uygulama kabulü artık `verify_release_package.py` kapısına dahildir:
  gerçek GitHub isteği + Qt callback sonucu + sertifika doğrulaması zorunludur.
- Teslimin iç EXE'sinde gerçek HTTPS + Qt denetimi **0,35 s** içinde latest
  sonucuyla tamamlandı. İzole `--version` 4,51 s (EXE açılımı dahil).
  Gömülü kaynak, sürüm, varlık, motor manifesti ve onarım ZIP'i doğrulandı.
- `WordArc-0.10.2.exe`: 312221827 bayt; SHA256
  `b5db20fa2c4fbcfb2ed7359a4231de82dff0a060d212153aab8a5c383252358e`.
  `WordArcVulkan-1.9.2.zip` değişmedi: 19741654 bayt; SHA256
  `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`.

## Sınırlar

SSL context'in eski pakette neden BIO hatası verdiği, belirli bir Windows
sertifikasının bozuk olduğu anlamına gelmez; tek bir sertifika/kayıt kök nedeni
kanıtlanmadı. Kanıtlanan neden SSL yükleme hatasının yakalanmaması ve arayüze
sonuç iletilmemesidir. Ağ işlemi yapan Python thread'i zorla öldürülmez; zaman
aşımından sonraki yanıtı yok sayılır. Kurulu eski uygulama otomatik değiştirilmez.

Önceden bulunan `installer/wordarc.iss` AppPublisher=Geeker değişikliği korunur
ve sürüm commit'ine alınmaz. Derleme ayrı kopyada bu dosyanın HEAD sürümüyle
yapılır. Kaynak deposu private kalır; dağıtım `WordArc-Releases` deposundadır.
