# 0.6.7 CUDA kabulü

Kaynakların gerektirdiği CUDA 12/cuDNN 9 kitaplıkları tek dosyalık EXE'ye
eklenir. NVIDIA ekran sürücüsü ayrı kurulu kalır. Sistem Python'una wheel
kurmak dağıtımın gömülü ortamını değiştirmez.

Resmi kaynaklar:
- https://opennmt.net/CTranslate2/installation.html
- https://pypi.org/project/nvidia-cuda-runtime-cu12/12.9.79/

## Bu ortamda doğrulanabilenler

DLL paketi yükleme, EXE arşivindeki DLL adları, gömülü DLL'lerin bundle içinden
yüklenmesi, hata sınıflandırması, CPU onayı/ret/kaydetme geri alması, aynı
sesin CPU'da yeniden işlenmesi ve otomatik geri dönüş test edilir.
Bu makinede NVIDIA GPU/sürücü yoktur. Hedef bilgisayarın kullanıcı adı ve
log yolu farklıdır. Gerçek RTX 5060 sonucu bu kontrollerden çıkarılamaz.

## Hedef RTX 5060 bilgisayarında

1. Eski WordArc oturumunu tepsi menüsünden kapat. Yeni EXE'yi boş bir
   klasörden çalıştır; yanına CUDA DLL'si kopyalama.
2. Yerel motor, large-v3-turbo ve cihaz=Nvidia GPU seç. Dikte için temizleme
   ve çeviriyi kapat; böylece GPU transkripsiyon kanıtı bulut işlemiyle karışmaz.
3. PowerShell'de `nvidia-smi -l 1` çalıştır. En az 20 saniyelik gerçek konuşma
   kaydet ve çözümlemeyi başlat. Büyük dosya transkripsiyonu da işlem süresini
   gözlemlemeyi kolaylaştırır.
4. Logdaki `local speech device: cuda (float16) for model large-v3-turbo`
   satırını, tamamlanmış gerçek metni ve nvidia-smi işlem çıktısını birlikte
   kaydet.
5. GPU olmayan bilgisayarda açık CUDA seçimini dene: neden bildirilmeli ve
   CPU'ya geçiş sorulmalı. Evet cevabıyla config.json local_stt_device=cpu
   olmalı ve aynı kayıt yeniden işlenmeli. Hayır cevabında ayar cuda kalmalı,
   aynı oturumda soru/GPU başlatması tekrar etmemeli.
6. Otomatik cihaz seçiminde GPU olmadan aynı ses CPU/int8 ile tamamlanmalı;
   CPU geçişi için soru açılmamalı.

