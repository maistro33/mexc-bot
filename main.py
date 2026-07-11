#!/usr/bin/env python3
"""
TELEGRAM SİNYAL KOPYALAMA BOTU — GERÇEK PARA
🔖 VERSİYON: v16.27 (SADECE MANUEL + TEYITLI + 4 TP + TP1 TABAN + 1H-VOLATILITE SL + ACIK-POZ DUZELTME + 3 sabit TP - VUR KAÇ %35/%35/%30 tam kapanış + hizli ac/kapat + teyit bekleme + kademeli SL yukseltme + 3-bilesenli trend teyidi + scalp oz tarama[VARSAYILAN KAPALI] + coklu kanal + manuel komutlar teyitsiz direkt acilir)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Belirtilen Telegram kanalını (https://t.me/Kripto_Botu) dinler, gelen
sinyalleri ayrıştırır, Bitget'te GERÇEK PARA ile birebir açar.

⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: Bu kanalın geçmiş performansı hakkında HİÇBİR
VERİMİZ YOK — backtest edilmedi, doğrulanmadı. Konuşmamızda daha önce
gördüğümüz benzer bir kanal (net düşüş trendinin ortasında LONG önermiş,
SL'e çarpmıştı) bu tür kaynakların güvenilirliği konusunda bir uyarıydı.
Kanalın kendi mesajı bile "Kesinlikle yüksek kaldıraç kullanmayın" diyor
— bu bot 10x ile çalışacak şekilde ayarlandı (kullanıcı talebiyle,
kanalın kendi tavsiyesinin TERSİNE).

v16 DEĞİŞİKLİKLERİ (gerçek işlem örnekleri üzerinden yapıldı — CHIP kısa
vadeli sinyalde erken TP kümelenmesi, M/USDT güçlü trendinde %10.9
hareketin sadece %6.16'sının yakalanması gözlemlendi):
  1. TP dilimleri artık EŞİT DEĞİL — ilk ve son TP'lerde küçük pay,
     orta TP'lerde normal pay, kalan BÜYÜK pay (%25) trailing'e ayrılıyor.
     Amaç: güçlü trend'lerde daha fazla kâr yakalamak, zayıf/kısa
     hareketlerde yine de erken güvenlik kâr almak.
  2. TP_OLCEK_CARPANI 1.5 → 2.0: TP'ler biraz daha uzağa yayılıyor,
     TP1 artık normal piyasa gürültüsüyle değil, gerçek bir hareketle
     tetiklenme ihtimali daha yüksek.
  3. TRAILING_GERI_CEKILME_PCT 1.5% → 2.5%: trend'e nefes alma payı
     verildi — büyük hareketlerde (M/USDT örneğindeki gibi) trailing
     çok erken kapanmasın diye.
  4. YENİ: SL girişe (breakeven) çekildiğinde ayrı bir bildirim geliyor
     — o ana kadar kilitlenen kârı gösteriyor.
  5. YENİ: Komutsuz hızlı komutlar genişletildi — "edge long", "edge
     short", "edge kapat" gibi kısa mesajlarla hem açma hem KAPATMA
     yapılabiliyor (öncesinde kapatma için mutlaka /kapat gerekiyordu).
  6. YENİ (v16.1): Trend teyidi sağlanmayan sinyaller artık ANINDA
     çöpe atılmıyor — TEYIT_BEKLEME_DAKIKA (varsayılan 180 dk, env
     değişkeniyle ayarlanabilir) boyunca arka planda tekrar tekrar
     kontrol ediliyor. Teyit bu süre içinde gelirse sinyal o ANDAKİ
     güncel fiyattan açılıyor; süre dolarsa tamamen düşürülüyor.
  7. YENİ (v16.2): KADEMELİ SL YÜKSELTME (ratchet) — eskiden SL sadece
     TP1'de girişe (breakeven) çekiliyordu, sonraki TP'lerde sabit
     kalıyordu. Şimdi HER TP'de SL bir önceki TP seviyesine çekiliyor
     (TP2 vurulunca SL→TP1 fiyatı, TP3 vurulunca SL→TP2 fiyatı, vb.)
     — SL asla geriye alınmıyor, sadece iyileşiyor. Bu kural, kod
     deploy edildiği anda HALİHAZIRDA AÇIK olan işlemlere de hemen
     uygulanıyor (acik_pozisyonlara_kademeli_sl_uygula fonksiyonu).
  8. YENİ (v16.3): TELEGRAM ÜZERİNDEN KALICI YEDEK — Railway gibi
     platformlarda /data klasörü Volume eklenmediyse KALICI DEĞİLDİR,
     her redeploy'da sıfırlanır (AGLD işleminde yaşandığı gibi: TP
     listesi kayboldu, sadece %3 güvenlik SL'i kaldı). Artık trade_state
     ve bekleyen_sinyaller, Telegram'da SABİTLENMİŞ bir mesaja JSON
     olarak yazılıyor — bot her yeniden başladığında oradan geri
     yükleniyor. Railway ayarlarına dokunmaya gerek YOK, tamamen kod içi
     bir çözüm.
  9. YENİ (v16.4) — İKİ AYRI DÜZELTME:
     a) GERÇEK DOLUŞ FİYATI: PnL hesapları artık piyasa emri gönderilmeden
        ÖNCE çekilen tahmini (ticker) fiyat yerine, emrin borsadaki GERÇEK
        ortalama doluş fiyatını ve komisyonunu kullanıyor. Önceki haliyle
        bot "-0.01$" derken gerçek borsa sonucu "-0.25$" çıkabiliyordu
        (UAI örneği) — bu fark artık ölçülüyor, günlük zarar limiti de
        buna göre daha doğru işliyor (gercek_dolus_bilgisi_al fonksiyonu).
     b) TP1 SONRASI NEFES PAYI: SL, TP1'den sonra artık TAM girişe değil,
        girişin %0.4 kadar altına (long) çekiliyor — anlık bir gürültüyle
        (komisyon/slippage kadar bir dokunuşla) işlem hemen kapanmasın,
        TP2'ye doğru devam edebilsin diye (TP1_BREAKEVEN_TAMPON_PCT).
        Bedeli: SL bu bölgede vurulursa artık tam sıfır değil, ufak ve
        kontrollü bir risk (~%0.4) üstlenilmiş oluyor.
  10. YENİ (v16.5): TP'LER GERÇEK LİMİT EMRİ — Eskiden bot her 5 saniyede
      bir anlık fiyatı TP hedefiyle karşılaştırıyordu; fiyat iki kontrol
      arasında hızlıca TP'ye değip geri çekilirse (kısa fitil) bot o anı
      KAÇIRABİLİYORDU (VELVET örneği). Şimdi her TP seviyesi için gerçek
      reduceOnly LİMİT emri açılış anında borsaya gönderiliyor — borsanın
      kendi eşleştirme motoru fiyata değen her anı yakalar. Emir
      konulamazsa o seviye eski (fiyat karşılaştırma) yönteme döner.
  11. YENİ (v16.8) — İKİ KRİTİK DÜZELTME (gerçek para kaybına yol açmış
      hatalar, LAB işleminde tespit edildi):
      a) YARIŞ DURUMU: trade_state artık pozisyon açılır açılmaz HEMEN
         yazılıyor — eskiden TP limit emirleri (6 borsa API çağrısı, 1-3+
         saniye) ÖNCE koyuluyor, state SONRA yazılıyordu. Bu aradaki
         pencerede manage() döngüsü pozisyonu "sahipsiz" sanıp genel %3
         güvenlik SL'i koyabiliyordu — TP takibi, kademeli SL, tampon
         payı hiçbiri devrede olmadan (LAB'daki -2.72$ zararın sebebi).
      b) ÇİFTE KAPANMA: Bir TP için gerçek limit emri borsada "açık"
         olarak doğrulanabiliyorsa, artık fiyat karşılaştırmasına HİÇ
         düşülmüyor. Eskiden emrin durumu "dolmuş" görünmese bile (API
         gecikmesi) fiyat hedefi geçtiyse bot KENDİ EK bir kapatma emri
         gönderiyordu — borsadaki gerçek emir de sonradan dolunca AYNI
         dilim İKİ KEZ kapanabiliyordu (TP1'den hemen sonra pozisyonun
         beklenenden hızlı tükenmesinin olası sebebi).
  12. YENİ (v16.9) — 3-BİLEŞENLİ TREND TEYİDİ: Eski teyit kuralı sadece
      son 2 tane 4h/1h mumun tepe/dip kıyaslamasına bakıyordu — bu kısa
      vadeli gürültüye çok açıktı. İki gerçek örnekte bu netleşti: TRIA
      (genel trend sert düşüşteydi, filtre doğru reddetti) ve BEAT (genel
      trend yine düşüşteydi ama filtre 2 mumluk kıpırdanmayla yanlışlıkla
      onay verdi, SL'e gitti). Yeni kural üç bileşene bakıyor — LONG için
      üçü de sağlanmalı: (1) fiyat 4h MA20'nin üstünde, (2) son 5 tane 4h
      mumun en az 3'ü yükselişte kapanmış, (3) 1h RSI > 40. SHORT için
      tersi uygulanır. Amaç: kısa vadeli gürültüye karşı daha dayanıklı,
      büyük resme bakan bir teyit (trend_teyidi_yeterli_mi fonksiyonu).
  13. YENİ (v16.10) — 3 SABİT TP + ERKEN GENİŞ TRAİLİNG: TP6'ya nadiren
      ulaşıldığı (kullanıcı gözlemi) için trailing pratikte neredeyse hiç
      devreye girmiyordu — MORPHO gibi TP4'te dönen işlemlerde kalan
      pozisyon hep sabit TP4-6 hedeflerini beklerken SL'e geri dönüyordu.
      Şimdi sadece TP1-TP2-TP3 sabit hedef (garanti kâr, kademeli SL
      yükseltmesiyle); TP3 vurulunca kalan BÜYÜK pay (%55) hemen trailing
      moduna geçiyor. Trailing'in erken başlaması nedeniyle geri çekilme
      payı da %2.5'ten %3.5'e genişletildi (henüz olgunlaşmamış bir
      hareketten erken çıkılmasın diye). Ayrıca trailing sırasında stop
      her belirgin şekilde (≥%1) yukarı çekildiğinde artık ayrı bir
      bildirim gönderiliyor (eskiden sessizce güncelleniyordu, sadece
      kapanışta haber veriliyordu).
  14. YENİ (v16.11) — ÖZ TARAMA: Kanal sinyalleri ve manuel emirlerin
      YANINDA, bot artık en likit ~25 coini periyodik (varsayılan 20 dk)
      tarayıp KENDİ LONG/SHORT adayını üretebiliyor — aynı MA20+5mum+RSI
      teyit mantığını (trend_teyidi_yeterli_mi ile aynı felsefe) kullanıyor,
      üstüne RSI'da bir ÜST sınır da ekliyor (tepe/dip kovalamasın diye).
      Sadece "teyitsizden teyitliye" GEÇİŞ anında tetiklenir (aynı coin
      sürekli teyitli kalsa bile tekrar tekrar açılmaya çalışılmaz).
      Kullanıcı talebiyle: kanal ve manuel emirlerle AYNI havuzu (MAX_POS,
      günlük zarar limiti) paylaşır, ayrı bir bütçesi yoktur — sinyali_isle()
      üzerinden akar. OZ_TARAMA_AKTIF=false env değişkeniyle kapatılabilir.
  15. YENİ (v16.12) — ÖZ TARAMA SCALP'E ÇEVRİLDİ + ÇOKLU KANAL:
      a) Öz tarama artık 4h/1h yerine KISA VADELİ (3m ana trend + 1m
         momentum) çalışıyor — "scalp yapıyoruz, geç kalmasın" isteğiyle.
         Watchlist seçimi de değişti: önce likit havuzdan (hacme göre) ilk
         60 alınıyor, sonra bunlar arasından KISA VADELİ VOLATİLİTESİ
         (3m mumların ortalama high-low/close oranı) en yüksek 20'si
         seçiliyor — durgun coinlerde scalp aramanın anlamı yok. Tarama
         periyodu 20 dk'dan 2 dk'ya indirildi. Öz tarama kaynaklı sinyaller
         artık kanalın 4h/1h kuyruğuna (180 dk bekleme) HİÇ takılmıyor —
         kendi 3m/1m teyidi (hâlâ MA20+5mum+RSI, hem alt hem üst sınırla)
         yeterli sayılıp direkt açılıyor (sinyali_isle içindeki "oz_tarama"
         istisnası).
      b) İKİNCİ BİR TELEGRAM KANALI da dinlenebiliyor artık
         (KANAL_USERNAME_2 env değişkeni) — kullanıcı talebiyle "diğer bir
         kanaldan gelenler de açılsın, teyitli". İkinci kanaldan gelen
         sinyaller BİRİNCİ kanalla AYNI teyit akışından (4h/1h
         trend_teyidi_yeterli_mi) geçiyor, hiçbir ayrıcalığı yok.
  16. YENİ (v16.13) — SCALP SL/TP ARTIK VOLATİLİTE BAZLI (kullanıcı
      gözlemi: "TP1 çok erken geliyor"): Öz tarama sinyalleri eskiden
      entry/sl=None ile gönderilip botun SABİT %2 SL varsayımına
      (basit format) düşüyordu — TP1 de bunun üzerinden ~%0.6 gibi ÇOK
      DAR bir mesafeye kuruluyordu, scalp'in kısa vadeli gürültüsünde
      saniyeler içinde tetikleniyordu. Şimdi SL, coin'in GERÇEK ÖLÇÜLEN
      3m volatilitesine göre hesaplanıyor (volatilite×1.5, min %0.4, maks
      MAX_SL_PCT); TP'ler de R-katları olarak (0.6R/1.2R/2.0R) NİHAİ
      şekilde hesaplanıp asil_islemi_ac'e gönderiliyor — kanalın
      tp_olcekle mantığından (2x + TP1 ekstra 1.5x) BİLEREK muaf
      tutuluyor, yoksa TP1 bu sefer ~1.8R gibi TERSİNE aşırı geniş
      olurdu.
  17. YENİ (v16.14) — TP SAYISI 3'TEN 4'E ÇIKARILDI: Kullanıcı talebiyle
      TP1-TP2-TP3-TP4 artık sabit hedef (her biri pozisyonun %15'i,
      toplam %60 — kalan %40 trailing'e), TP4 vurulunca trailing devreye
      giriyor (TP3'ten sonra değil). Scalp (öz tarama) tarafındaki R-katı
      listesi de buna uyacak şekilde 4 elemana çıkarıldı: 0.5R/1.0R/1.6R/
      2.4R.

GÜVENLİK (önceki botlardan taşınan, kanıtlanmış mekanizmalar):
  - API şifresi ortam değişkeninden okunur, koda yazılmaz
  - Restart + çalışma-zamanı sahipsiz pozisyon koruması
  - Çıkış emirleri gerçekten uygulandığı doğrulanmadan takipten çıkarılmaz
  - Günlük zarar limiti + otomatik gece yarısı sıfırlama
  - Risk bazlı pozisyon boyutlandırma

SİNYAL FORMATI (şu ana kadar gördüğümüz TEK örneğe göre yazıldı — bu
kanalın gerçek formatı FARKLIYSA, örnek bir mesaj paylaşman gerekecek,
ayrıştırıcıyı ona göre güncelleriz):

  📊 #BASUSDT.P
  🏁 LONG - Giriş Fiyatı: 0.030974
  🚫 Stop: 0.0294253 ya da sonraki sinyal
  TP1: 0.03112887 ──
  TP2: 0.031283740000000004 ──
  ...

ÇALIŞTIRMA: Bu bot Telethon (Telegram kullanıcı kütüphanesi) kullanır.
İlk çalıştırmadan önce session_olustur.py'yi BİR KERE, kendi bilgisayarında
çalıştırıp bir "session string" üretmen gerekiyor (ayrı dosya olarak
veriyorum). Onu STRING_SESSION ortam değişkenine koyduktan sonra bu bot
Railway'de sorunsuz çalışır.
"""

import os
import re
import time
import json
import threading
import logging
import asyncio
import ccxt
import telebot
from telethon import TelegramClient, events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SIGNAL_COPY")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN   = os.getenv("TELE_TOKEN", "")       # kendi bildirim botun (Telegram Bot API)
CHAT_ID      = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY      = os.getenv("BITGET_API", "")
API_SEC      = os.getenv("BITGET_SEC", "")
PASSPHRASE   = os.getenv("BITGET_PASS", "")

TG_API_ID    = int(os.getenv("TG_API_ID", "0"))   # my.telegram.org'dan
TG_API_HASH  = os.getenv("TG_API_HASH", "")       # my.telegram.org'dan
TG_STRING_SESSION = os.getenv("STRING_SESSION", "") or os.getenv("TG_SESSION", "")
KANAL_KULLANICI_ADI = os.getenv("KANAL_USERNAME", "FuturesKripto")
# ── v16.12: İKİNCİ BİR KANAL da dinlenebilsin diye (kullanıcı talebi:
# "diğer bir telegram kanalından gelenlerde de açabilsin, teyitli").
# Boşsa sadece ilk kanal dinlenir, mevcut davranış hiç değişmez. İkinci
# kanaldan gelen sinyaller de AYNI teyit akışından (trend_teyidi_yeterli_mi,
# 4h/1h MA20+mum+RSI) geçer — hiçbir ayrıcalığı yok, kanal_kopya gibi işlem
# görür (kaynak etiketi mesajdan otomatik ayırt edilir, Telethon event'i
# hangi kanaldan geldiğini zaten bilir).
KANAL_KULLANICI_ADI_2 = os.getenv("KANAL_USERNAME_2", "").strip()
KANAL_LISTESI = [KANAL_KULLANICI_ADI] + ([KANAL_KULLANICI_ADI_2] if KANAL_KULLANICI_ADI_2 else [])

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni ayarlanmamış.")
if not TG_API_ID or not TG_API_HASH or not TG_STRING_SESSION:
    raise RuntimeError("TG_API_ID / TG_API_HASH / STRING_SESSION ortam değişkenleri "
                        "eksik — önce session_olustur.py'yi çalıştırıp session string üretmen gerekiyor.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

TOPLAM_SERMAYE   = 35.0
MARGIN_SABIT     = 10.0    # ── kullanıcı talebiyle: sabit marj, risk bazlı değil ──
LEV              = 10
MAX_POS          = 2       # kanal genelde tek sinyal veriyor, aynı anda 1 işlem
MIN_POS_NOTIONAL = 30.0

MAX_GUNLUK_ZARAR = -10.0

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/signal_copy_state.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/signal_copy_log.json")
PORT = int(os.getenv("PORT", "8080"))

# ════════════════════════════════════════════
# TELEGRAM BİLDİRİM (kendi bot token'ın — sinyal kanalıyla KARIŞTIRMA)
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


if bot:
    @bot.message_handler(commands=["manuel"])
    def manuel_sinyal_komutu(msg):
        """
        Kanaldan gelmeyi beklemeden test/manuel giriş için:
        /manuel yazıp ardından (yeni satırda) sinyal metnini yapıştır
        (tam kanal formatı) YA DA sadece 'MAGMA LONG' gibi basit yaz.
        """
        metin = msg.text.replace("/manuel", "", 1).strip()
        if not metin:
            bot.send_message(msg.chat.id, "Kullanım: /manuel MAGMA LONG  (ya da tam sinyal metnini yapıştır)")
            return

        sinyal = sinyal_ayristir(metin)
        if not sinyal:
            sinyal = hizli_sinyal_ayristir(metin)
        if not sinyal:
            bot.send_message(msg.chat.id, "⚠️ Metin hiçbir formatta ayrıştırılamadı.")
            return

        bot.send_message(msg.chat.id, f"✅ Ayrıştırıldı: {sinyal}\nİşleniyor...")
        sinyal["kaynak_etiket"] = "manuel"
        sinyali_isle(sinyal)

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        with state_lock:
            if not trade_state:
                bot.send_message(msg.chat.id, "Açık pozisyon yok.")
                return
            satirlar = ["📋 AÇIK POZİSYONLAR\n"]
            for sym, d in trade_state.items():
                satirlar.append(f"{sym} [{d['direction'].upper()}] giriş:{d['entry']:.8f} "
                                 f"SL:{d['sl']:.8f} TP_index:{d.get('tp_index',0)}/{len(d.get('tp_liste',[]))}")
            bot.send_message(msg.chat.id, "\n".join(satirlar))

    @bot.message_handler(commands=["ac"])
    def ac_komutu(msg):
        """
        Net bir açma komutu. Kullanım: /ac MAGMA LONG  (ya da SHORT)
        (Not: '/manuel' ve komutsuz kısa mesaj — örn. 'Magma long' — hâlâ
        çalışmaya devam ediyor, bu sadece daha net bir alternatif.)
        """
        metin = msg.text.replace("/ac", "", 1).strip()
        if not metin:
            bot.send_message(msg.chat.id, "Kullanım: /ac MAGMA LONG")
            return
        sinyal = sinyal_ayristir(metin) or hizli_sinyal_ayristir(metin)
        if not sinyal:
            bot.send_message(msg.chat.id, "⚠️ Anlaşılamadı. Örnek: /ac MAGMA LONG")
            return
        bot.send_message(msg.chat.id, f"⚡ Açılıyor: {sinyal['symbol']} {sinyal['direction'].upper()}")
        sinyal["kaynak_etiket"] = "manuel"
        sinyali_isle(sinyal)

    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        """
        Manuel kapatma komutu. Kullanım:
          /kapat          -> açık TEK pozisyon varsa onu kapatır
          /kapat EDGE     -> EDGE (ya da başka coin) pozisyonunu kapatır
        (Not: komutsuz "edge kapat" gibi kısa mesajlar da aynı işi yapar —
        aşağıdaki komutsuz_hizli_giris fonksiyonuna bakın.)
        """
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        basari, mesaj = _pozisyon_kapat_yardimci(msg.chat.id, parca)
        bot.send_message(msg.chat.id, mesaj)


    KISA_MESAJ_UST_SINIR = 30  # bu karakterden uzun mesajlar sohbet sayilir, islem denenmez

    def _pozisyon_kapat_yardimci(chat_id, parca):
        """
        /kapat ve komutsuz "coin kapat" tarafından ORTAK kullanılan kapatma
        mantığı. parca boşsa ve tek açık pozisyon varsa onu kapatır; coin
        adı verilmişse o pozisyonu arar.
        """
        with state_lock:
            acik_semboller = list(trade_state.keys())

        if not acik_semboller:
            return False, "Açık pozisyon yok, kapatılacak bir şey bulunamadı."

        hedef_sym = None
        if parca:
            for sym in acik_semboller:
                if parca in sym.upper():
                    hedef_sym = sym
                    break
            if not hedef_sym:
                return False, (f"'{parca}' ile eşleşen açık pozisyon bulunamadı. "
                                f"Açık olanlar: {acik_semboller}")
        else:
            if len(acik_semboller) > 1:
                return False, (f"Birden fazla açık pozisyon var, hangisini kastettiğini belirt: "
                                f"{acik_semboller}\nÖrn: /kapat {acik_semboller[0].split('/')[0]}")
            hedef_sym = acik_semboller[0]

        bot.send_message(chat_id, f"⏳ {hedef_sym} kapatılıyor...")
        return manuel_pozisyon_kapat(hedef_sym)

    def komut_metni_ayikla(metin):
        """
        YENİ (v16): Komutsuz kısa mesajları ayıklar — üç türü tanır:
          - "edge kapat" / "edge kapat et" gibi -> ('kapat', 'EDGE')
          - "edge long" / "edge long ac" / "long edge" gibi -> ('ac', sinyal_dict)
          - hiçbiri değilse -> (None, None)
        "ac" kelimesi artık ZORUNLU DEĞİL — sadece coin + yön yeterli.
        """
        temiz = metin.strip()
        if not temiz or len(temiz) > KISA_MESAJ_UST_SINIR:
            return None, None

        # ── KAPATMA: "kapat" kelimesi geçiyorsa, geri kalanını sembol adı say ──
        if re.search(r"\bkapat\b", temiz, re.IGNORECASE):
            sembol_parca = re.sub(r"\bkapat\b", "", temiz, flags=re.IGNORECASE)
            sembol_parca = re.sub(r"\bet\b", "", sembol_parca, flags=re.IGNORECASE).strip().upper()
            return "kapat", sembol_parca

        # ── AÇMA: coin + long/short (ac kelimesi opsiyonel) ──
        sinyal = hizli_sinyal_ayristir(temiz)
        if sinyal:
            return "ac", sinyal

        return None, None

    @bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
    def komutsuz_hizli_giris(msg):
        """
        v16: "/manuel" veya "/ac" yazmadan, doğrudan KISA bir mesajla hem
        AÇMA hem KAPATMA yapılabilir:
          "edge long"   -> EDGE LONG açar (ac kelimesi gerekmez)
          "edge short"  -> EDGE SHORT açar
          "edge kapat"  -> EDGE pozisyonunu kapatır
          "kapat"       -> tek açık pozisyon varsa onu kapatır
        Güvenlik payı: mesaj KISA_MESAJ_UST_SINIR karakterden uzunsa
        (muhtemelen sıradan sohbet), hiçbir şey denenmez.
        """
        tur, veri = komut_metni_ayikla(msg.text)

        if tur == "kapat":
            basari, mesaj = _pozisyon_kapat_yardimci(msg.chat.id, veri)
            bot.send_message(msg.chat.id, mesaj)
            return

        if tur == "ac":
            sinyal = veri
            bot.send_message(msg.chat.id, f"⚡ Hızlı giriş algılandı: {sinyal['symbol']} {sinyal['direction'].upper()}")
            sinyal["kaynak_etiket"] = "manuel"
            sinyali_isle(sinyal)
            return
        # tur None ise: sıradan sohbet, dokunma


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)

def tg(msg):
    if not bot:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def gercek_dolus_bilgisi_al(emir, sym, tahmini_fiyat):
    """
    v16.8 DÜZELTME: PnL hesapları eskiden `exchange.fetch_ticker()` ile
    ÖNCEDEN çekilen tahmini fiyatı kullanıyordu — ama piyasa emrinin
    GERÇEK doluş fiyatı (özellikle STOP/hızlı hareket eden coinlerde)
    bundan belirgin farklı olabiliyor (UAI örneğinde botun -0.01$ dediği
    işlem gerçekte -0.25$ ile kapanmıştı — ~%2.5 slippage + komisyon hiç
    hesaba katılmamıştı). Bu fonksiyon, emrin borsadaki GERÇEK ortalama
    doluş fiyatını ve komisyonunu almaya çalışır; alamazsa tahmini fiyata
    geri döner (hesap yine çalışır, sadece daha az kesin olur).
    """
    fiyat = safe(emir.get("average")) or safe(emir.get("price"))
    komisyon = 0.0
    try:
        fee = emir.get("fee")
        if fee:
            komisyon = safe(fee.get("cost"))
    except Exception:
        pass

    if not fiyat:
        try:
            time.sleep(0.5)
            detay = exchange.fetch_order(emir.get("id"), sym)
            fiyat = safe(detay.get("average")) or safe(detay.get("price"))
            fee = detay.get("fee")
            if fee:
                komisyon = safe(fee.get("cost"))
        except Exception as e:
            log.warning(f"[DOLUS] {sym} emir detayı alınamadı, tahmini fiyata dönülüyor: {e}")

    if not fiyat:
        fiyat = tahmini_fiyat  # son çare: ticker tahmini

    return fiyat, komisyon


def get_candles(sym, tf, limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except Exception as e:
        log.warning(f"[VERI] {sym} {tf}: {e}")
        return None


# ════════════════════════════════════════════
# KALICI DURUM
# ════════════════════════════════════════════
trade_state = {}
state_lock = threading.Lock()

def durumu_diske_yaz():
    try:
        os.makedirs(os.path.dirname(TRADE_STATE_PATH), exist_ok=True)
        with state_lock:
            veri = dict(trade_state)
        with open(TRADE_STATE_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[KALICI] Diske yazma başarısız: {e}")
    durumu_telegrama_yedekle()  # v16.8: diskin yanında Telegram'a da yedekle


def durumu_diskten_yukle():
    global trade_state
    try:
        if os.path.exists(TRADE_STATE_PATH):
            with open(TRADE_STATE_PATH) as f:
                yuklenen = json.load(f)
            with state_lock:
                trade_state = yuklenen
            log.info(f"[KALICI] {len(yuklenen)} kayıtlı işlem durumu yüklendi")
    except Exception as e:
        log.warning(f"[KALICI] Yükleme başarısız: {e}")


# ════════════════════════════════════════════
# TELEGRAM ÜZERİNDEN KALICI YEDEK (v16.8)
# ════════════════════════════════════════════
# Railway gibi platformlarda /data klasörü KALICI DEĞİLDİR — Volume
# eklenmediyse her redeploy'da (kod güncellemesi, yeniden başlatma) diskteki
# her şey sıfırlanır. Bu, açık bir işlemin TP listesini/tp_index'ini/kademeli
# SL seviyesini kaybetmesine yol açar (AGLD'de yaşadığımız gibi).
#
# Bu fonksiyonlar, Railway ayarlarına HİÇ dokunmadan, tamamen kod içi bir
# çözüm sunuyor: kritik durumu (trade_state + bekleyen_sinyaller) Telegram'da
# SABİTLENMİŞ (pinned) bir mesaja JSON olarak yazıyoruz. Telegram'ın kendisi
# kalıcı depolama görevi görüyor — bot her yeniden başladığında o mesajdan
# okuyup geri yüklüyor.
STATE_PIN_ETIKETI = "🗄️ BOT_DURUM_YEDEK (dokunma — otomatik güncellenir)"
_pin_message_id = None
_pin_lock = threading.Lock()


def durumu_telegrama_yedekle():
    global _pin_message_id
    if not bot or not CHAT_ID:
        return
    try:
        with state_lock:
            veri_state = dict(trade_state)
        try:
            with bekleyen_lock:
                veri_bekleyen = {
                    sym: {"sinyal": k["sinyal"], "gozlem_str": k["gozlem_str"],
                          "eklenme_zamani": k["eklenme_zamani"]}
                    for sym, k in bekleyen_sinyaller.items()
                }
        except NameError:
            veri_bekleyen = {}  # bekleyen_sinyaller henüz tanımlanmadıysa (ilk yükleme anı)

        icerik = json.dumps({"trade_state": veri_state, "bekleyen_sinyaller": veri_bekleyen})
        metin = f"{STATE_PIN_ETIKETI}\n{icerik}"
        if len(metin) > 4000:
            log.warning("[TG_YEDEK] Durum verisi çok büyük (>4000 karakter), Telegram'a yazılamadı")
            return

        with _pin_lock:
            if _pin_message_id:
                try:
                    bot.edit_message_text(metin, CHAT_ID, _pin_message_id)
                    return
                except Exception:
                    pass  # mesaj silinmiş olabilir — aşağıda yeniden oluşturulacak

            gonderilen = bot.send_message(CHAT_ID, metin)
            _pin_message_id = gonderilen.message_id
            try:
                bot.pin_chat_message(CHAT_ID, _pin_message_id, disable_notification=True)
            except Exception as e:
                log.warning(f"[TG_YEDEK] Sabitleme başarısız (yine de çalışmaya devam eder): {e}")
    except Exception as e:
        log.warning(f"[TG_YEDEK] Telegram'a yazma başarısız: {e}")


def durumu_telegramdan_yukle():
    """
    Başlangıçta, sabitlenmiş mesajdan trade_state ve bekleyen_sinyaller'i
    geri yükler. acilista_pozisyonlari_dogrula() ÇAĞRILMADAN ÖNCE çalışmalı
    — böylece o fonksiyon açık bir pozisyonu "kayıtsız" sanıp üzerine genel
    %3 güvenlik SL'i koymaz, gerçek TP/SL/tp_index bilgisi korunur.
    """
    global trade_state, _pin_message_id
    if not bot or not CHAT_ID:
        return
    try:
        chat = bot.get_chat(CHAT_ID)
        pinned = getattr(chat, "pinned_message", None)
        if not pinned or not pinned.text or STATE_PIN_ETIKETI not in pinned.text:
            log.info("[TG_YEDEK] Sabitlenmiş durum mesajı bulunamadı, boş başlanıyor")
            return
        _pin_message_id = pinned.message_id
        json_kismi = pinned.text.split("\n", 1)[1]
        veri = json.loads(json_kismi)

        yuklenen_state = veri.get("trade_state", {})
        with state_lock:
            trade_state.update(yuklenen_state)

        yuklenen_bekleyen = veri.get("bekleyen_sinyaller", {})
        with bekleyen_lock:
            for sym, kayit in yuklenen_bekleyen.items():
                bekleyen_sinyaller[sym] = kayit

        if yuklenen_state or yuklenen_bekleyen:
            tg(f"♻️ Telegram yedeğinden geri yüklendi: {len(yuklenen_state)} açık işlem, "
               f"{len(yuklenen_bekleyen)} bekleyen sinyal")
    except Exception as e:
        log.warning(f"[TG_YEDEK] Telegram'dan yükleme başarısız: {e}")


# ════════════════════════════════════════════
# TRADE LOG (kapanan işlemlerin kalıcı kaydı — panel için)
# ════════════════════════════════════════════
trade_log = []
log_lock = threading.Lock()

def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    try:
        os.makedirs(os.path.dirname(TRADE_LOG_PATH), exist_ok=True)
        with open(TRADE_LOG_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[LOG] Diske yazma başarısız: {e}")


def trade_log_yukle():
    global trade_log
    try:
        if os.path.exists(TRADE_LOG_PATH):
            with open(TRADE_LOG_PATH) as f:
                yuklenen = json.load(f)
            with log_lock:
                trade_log = yuklenen
            log.info(f"[LOG] {len(yuklenen)} geçmiş işlem yüklendi")
    except Exception as e:
        log.warning(f"[LOG] Yükleme başarısız: {e}")


def acilista_pozisyonlari_dogrula():
    try:
        pozisyonlar = exchange.fetch_positions()
    except Exception as e:
        tg(f"⚠️ Açılışta pozisyon kontrolü başarısız: {e}")
        return

    for p in pozisyonlar:
        qty = safe(p.get("contracts"))
        if qty <= 0:
            continue
        sym = p["symbol"]
        entry = safe(p.get("entryPrice"))
        side = p.get("side")

        with state_lock:
            kayitli = trade_state.get(sym)
        if kayitli:
            tg(f"♻️ {sym} pozisyonu kayıtlı durumla eşleşti.")
            continue

        direction = "long" if side == "long" else "short"
        guvenlik_sl_pct = 0.03
        sl = entry * (1 - guvenlik_sl_pct) if direction == "long" else entry * (1 + guvenlik_sl_pct)
        with state_lock:
            trade_state[sym] = {"sl": sl, "tp_liste": [], "tp_index": 0,
                                 "direction": direction, "entry": entry, "kaynak": "kurtarilan"}
        durumu_diske_yaz()
        tg(f"🚨 UYARI: {sym} için kayıtlı durum yoktu — geçici %3 güvenlik SL'i kondu: {sl:.8f}")


def acik_pozisyonlara_kademeli_sl_uygula():
    """
    v16.8: Bot yeniden başlatıldığında (yeni kod deploy edildiğinde), o an
    ZATEN AÇIK olan işlemler de yeni kademeli SL (ratchet) mantığından
    faydalansın diye — eski sürümde açılmış ve bazı TP'leri çoktan vurmuş
    bir işlem, yeni kurala göre SL'in NEREDE OLMASI GEREKTİĞİNİ hesaplar
    ve mevcut SL'den daha iyiyse HEMEN uygular (bir sonraki TP'yi beklemeden).
    Böylece "koddaki iyileştirme sadece yeni işlemlerde değil, açık
    işlemlerde de devreye girsin" isteği karşılanmış olur.
    """
    with state_lock:
        semboller = list(trade_state.keys())

    for sym in semboller:
        with state_lock:
            durum = trade_state.get(sym)
        if not durum:
            continue

        tp_index = durum.get("tp_index", 0)
        tp_liste = durum.get("tp_liste", [])
        entry = durum.get("entry")
        direction = durum.get("direction")
        mevcut_sl = durum.get("sl")

        if tp_index == 0 or not tp_liste or entry is None or mevcut_sl is None or direction is None:
            continue  # henüz hiç TP vurulmamış — yeni kuralın etkileyeceği bir şey yok

        # ── tp_index burada "şimdiye kadar KAÇ TP VURULDU" sayısıdır (T).
        # T==1 (sadece TP1 vuruldu) → SL, girişin biraz altına/üstüne (v16.8
        # tampon payı) çekilmeli — TAM breakeven değil. T>=2 (TP2, TP3, ...
        # vuruldu) → SL, BİR ÖNCEKİ TP'nin fiyatına çekilmeli: tp_liste[T-2]
        # (0-index). Bu, manage() içindeki canlı mantıkla BİREBİR aynı
        # formül — sadece burada "sonradan yakalama" yapılıyor. ──
        if tp_index == 1:
            onerilen_sl = entry * (1 - TP1_BREAKEVEN_TAMPON_PCT) if direction == "long" \
                          else entry * (1 + TP1_BREAKEVEN_TAMPON_PCT)
        else:
            hedef_index = tp_index - 2
            if hedef_index < 0 or hedef_index >= len(tp_liste):
                continue
            onerilen_sl = tp_liste[hedef_index]

        sl_iyilesir_mi = (direction == "long" and onerilen_sl > mevcut_sl) or \
                          (direction == "short" and onerilen_sl < mevcut_sl)
        if sl_iyilesir_mi:
            with state_lock:
                trade_state[sym]["sl"] = onerilen_sl
            durumu_diske_yaz()
            tg(f"🔄 {sym} — bot güncellendi, yeni kademeli SL kuralı UYGULANDI: "
               f"{mevcut_sl:.8f} → {onerilen_sl:.8f} (TP{tp_index} zaten vurulmuş durumdaydı)")


def acik_pozisyonlarin_dar_sl_duzelt():
    """
    v16.27: acik_pozisyonlara_kademeli_sl_uygula() sadece EN AZ 1 TP
    vurulmuş pozisyonları düzeltiyor (tp_index>0 şartı var) — henüz HİÇ
    TP vurmamış (tp_index==0) pozisyonlara dokunmuyordu. Ama tam bu
    kategoride gerçek bir hata vardı: v16.25-v16.26 arası açılan "basit
    format" manuel işlemler, YANLIŞLIKLA 3dk'lık ultra-kısa scalp
    volatilite ölçümüyle SL hesaplıyordu (WLDUSDT örneği: SL sadece
    %0.40 — neredeyse anında gürültüyle vurulacak kadar dar).
    Bu fonksiyon, henüz TP'si vurulmamış açık pozisyonlar için SL'i
    GÜNCEL 1H volatiliteyle YENİDEN hesaplar; yeni hesap MEVCUTTAN DAHA
    GENİŞ (daha güvenli, gürültüye dayanıklı) çıkarsa SL'i ona GENİŞLETİR.
    Daraltma YAPMAZ (mevcut SL zaten yeterince genişse dokunulmaz) —
    tek yönlü, sadece "tehlikeli derecede dar" durumu düzeltir.
    """
    with state_lock:
        semboller = list(trade_state.keys())

    for sym in semboller:
        with state_lock:
            durum = trade_state.get(sym)
        if not durum:
            continue

        tp_index = durum.get("tp_index", 0)
        entry = durum.get("entry")
        direction = durum.get("direction")
        mevcut_sl = durum.get("sl")

        if tp_index != 0 or entry is None or direction is None or mevcut_sl is None:
            continue  # zaten TP vurulmuşsa yukarıdaki kademeli fonksiyon ilgileniyor

        mevcut_sl_pct = abs(entry - mevcut_sl) / entry
        if mevcut_sl_pct >= 0.012:
            continue  # zaten makul genişlikte (yeni tabanımızla aynı/üstü), dokunma

        volatilite_pct = manuel_volatilite_hesapla(sym, tf="1h", mum_sayisi=20)
        if volatilite_pct is None:
            continue
        yeni_sl_pct = max(0.012, min(volatilite_pct / 100 * 2.0, MAX_SL_PCT))
        if yeni_sl_pct <= mevcut_sl_pct:
            continue  # yeni hesap da darsa (olmamalı ama) eski SL'i koru

        yeni_sl = entry * (1 - yeni_sl_pct) if direction == "long" else entry * (1 + yeni_sl_pct)
        with state_lock:
            trade_state[sym]["sl"] = yeni_sl
        durumu_diske_yaz()
        tg(f"🛠️ {sym} — eski hatalı DAR SL düzeltildi: {mevcut_sl:.8f} (%{mevcut_sl_pct*100:.2f}) "
           f"→ {yeni_sl:.8f} (%{yeni_sl_pct*100:.2f}, 1H volatilite bazlı)")


# ════════════════════════════════════════════
# GÜNLÜK ZARAR TAKİBİ
# ════════════════════════════════════════════
gunluk_pnl = 0.0
gunluk_lock = threading.Lock()

def gunluk_limit_asildi():
    with gunluk_lock:
        return gunluk_pnl <= MAX_GUNLUK_ZARAR

def gunluk_pnl_ekle(miktar):
    global gunluk_pnl
    with gunluk_lock:
        gunluk_pnl += miktar
        return gunluk_pnl

def gunluk_reset_loop():
    global gunluk_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now(datetime.timezone.utc)
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with gunluk_lock:
                eski = gunluk_pnl
                gunluk_pnl = 0.0
            tg(f"🔄 Yeni gün! Dünkü gerçekleşen: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}")
            time.sleep(3600)


# ════════════════════════════════════════════
# SİNYAL AYRIŞTIRMA (BU KANALIN GERÇEK FORMATI FARKLIYSA GÜNCELLENMESİ GEREKİR)
# ════════════════════════════════════════════
HIZLI_SL_PCT = 0.02  # basit "coin yön" formatında, kanal SL vermediği için sabit %2 kullanılır
MAX_SL_PCT = 0.03    # kanalın verdiği SL bile bu yüzdeyi aşarsa, kendi SL'imize sıkıştırılır —
                     # sabit $100 notional ile geniş SL = marjın büyük kısmını riske atmak demek

def hizli_sinyal_ayristir(metin):
    """
    Basit format: 'MAGMA LONG', 'Magma long ac', 'edge short', 'btc short'
    gibi — sadece coin adı + yön. "ac" kelimesi opsiyoneldir, olsa da
    olmasa da çalışır. Giriş/SL kanal vermediği için, giriş anlık piyasa
    fiyatından alınır, SL sabit %2 ile hesaplanır.
    """
    m = re.search(r"\b([A-Za-z][A-Za-z0-9]{1,10})\b.*?\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    if not m:
        return None
    sembol = m.group(1).upper()
    if sembol in ("LONG", "SHORT", "AC", "KAPAT"):
        return None
    yon = "long" if m.group(2).upper() == "LONG" else "short"
    return {"symbol": f"{sembol}/USDT:USDT", "direction": yon, "entry": None, "sl": None, "tp_liste": []}


def sinyal_ayristir(metin):
    """
    Şu ana kadar gördüğümüz TEK örnek formata göre yazıldı:
      📊 #BASUSDT.P
      🏁 LONG - Giriş Fiyatı: 0.030974
      🚫 Stop: 0.0294253 ...
      TP1: 0.03112887
      TP2: 0.031283740000000004
      ...
    Döner: {"symbol":..., "direction":..., "entry":..., "sl":..., "tp_liste":[...]} veya None
    """
    sembol_m = re.search(r"#(\w+?)USDT", metin, re.IGNORECASE)
    yon_m = re.search(r"\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    giris_m = re.search(r"Giri[şs].*?Fiyat[ıi]?\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    stop_m = re.search(r"Stop\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    tp_liste = re.findall(r"TP\d+\s*:?\s*([\d.]+)", metin, re.IGNORECASE)

    if not (sembol_m and yon_m and giris_m and stop_m):
        return None

    return {
        "symbol": f"{sembol_m.group(1).upper()}/USDT:USDT",
        "direction": "long" if yon_m.group(1).upper() == "LONG" else "short",
        "entry": float(giris_m.group(1)),
        "sl": float(stop_m.group(1)),
        "tp_liste": [float(x) for x in tp_liste],
    }


# ════════════════════════════════════════════
# POZİSYON BOYUTU
# ════════════════════════════════════════════
def pozisyon_boyutu_hesapla(entry, sl):
    """
    SABİT MARJ modeli (kullanıcı talebiyle): notional = MARGIN_SABIT × LEV.
    SL mesafesi artık boyutlandırmayı etkilemiyor — sadece SL fiyatının
    kendisi (nereye konacağı) için kullanılıyor, miktar için değil.
    """
    if entry <= 0:
        return None, None
    notional = MARGIN_SABIT * LEV
    amount = notional / entry
    return amount, notional


def gercek_bakiye_yeterli_mi(gereken_marj):
    """
    İşlem açmadan önce GERÇEK borsa bakiyesini kontrol eder — sabit
    TOPLAM_SERMAYE varsayımı (35$) gerçek bakiyeyle uyuşmayabilir (örn.
    önceki kayıplardan sonra daha düşük olabilir). "Bakiye yetersiz" hatasını
    borsadan almak yerine, ÖNCEDEN kontrol edip net bir mesaj veririz.
    """
    try:
        bakiye = exchange.fetch_balance()
        serbest_usdt = safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] Kontrol edilemedi: {e}")
        return True  # kontrol edilemiyorsa engel olma, borsanın kendi kontrolüne güven
    return serbest_usdt >= gereken_marj


TP_OLCEK_CARPANI = 1.0  # v16.22: 0.5 çok sıkıydı (TP1 neredeyse hiç kâr bırakmıyordu),
                        # 1.0'a çıkarıldı — kanalın/otomatiğin verdiği orijinal mesafeyi
                        # koruyor. Asıl güvence aşağıdaki MIN_TP1_HAREKET_PCT tabanı.

# ── TP DİLİM AĞIRLIKLARI (v16.24 — 4 TP'DE TAM KAPANIŞ) ──
# Kullanıcı talebiyle TP4 eklendi. TP1/TP2/TP3/TP4 vuruldukça pozisyon
# kademeli kapanır, TP4'te pozisyonun TAMAMI kapanmış olur
# (0.30+0.25+0.25+0.20 = 1.00) — trailing'e bırakılan pay YOK. Her TP'de
# kâr kilitlenir, SL bir sonraki TP seviyesine çekilir.
TP_DILIM_ORANLARI = [0.30, 0.25, 0.25, 0.20]
TP_SAYISI_KULLANILAN = 4  # kanaldan/otomatikten gelen TP listesi bu uzunluğa kırpılır

# ── TP1 SONRASI BREAKEVEN NEFES PAYI (v16.8 İNCE AYAR) ──
# Eskiden TP1 vurulunca SL TAM girişe çekiliyordu — fiyat en ufak bir
# gürültüyle (komisyon/slippage dahil neredeyse anlık) girişe dokunsa
# işlem hemen kapanıyordu (EPIC, UAI örneklerinde 23 saniyede kapanan
# işlemler gibi). Şimdi TP1 sonrası SL, girişin biraz ALTINA (long için)
# konuyor — küçük bir geri çekilmede işlem kapanmıyor, TP2'ye doğru nefes
# alma şansı buluyor. Bedeli: SL bu bölgede vurulursa artık tam sıfır
# değil, ufak ve KONTROLLÜ bir risk (aşağıdaki yüzde kadar) üstleniliyor.
TP1_BREAKEVEN_TAMPON_PCT = 0.0015  # v16.8: %0.4'ten %0.15'e küçültüldü — 09 Temmuz
                        # verisinde 6 işlemde TP1-tampon kaynaklı küçük zarar oluştu
                        # (~-2.93$ toplam). Nefes payı korunuyor (EPIC/UAI'deki anlık
                        # kapanma sorunu geri gelmesin diye) ama zarar riski küçültüldü.

# ── TRAILING STOP (v16.18: TP1 sonrası hemen başlıyor) ──
TRAILING_GERI_CEKILME_PCT = 0.025  # v16.18: %3.5'ten %2.5'e sıkılaştırıldı — kullanıcı
                                    # talebiyle ("kârı geri vermeyelim"). %3.5 çok gevşekti,
                                    # zirveden büyük bir kâr payını geri veriyordu. %2.5,
                                    # normal 1H piyasa gürültüsüne (~%1.5-2) hâlâ dayanıklı
                                    # ama kârın daha büyük kısmını kilitliyor.

# ── TRAILING SIRASINDA STOP YÜKSELME BİLDİRİMİ (v16.10 YENİ) ──
# Trailing aktifken, fiyat her yeni zirve yaptığında efektif stop seviyesi
# de yükseliyor (zirve × (1-pay)) — ama bunu HER 5 saniyelik kontrolde
# bildirmek spam olur. Bu yüzden sadece zirve, bir önceki BİLDİRİLEN
# zirveden en az bu yüzde kadar ilerlediğinde yeni bir mesaj gönderiliyor.
TRAILING_BILDIRIM_ESIK_PCT = 0.01  # zirve en az %1 ilerlemeden yeni bildirim yok

# ── TP1'İ AYRICA GENİŞLETME (v16.8) ──
# VANRY/THE gibi örneklerde TP1 çok yakın olduğu için ya çok küçük kâr
# bırakıp geçiyor ya da tampon bölgesinde küçük zararla geri dönüyordu.
# Bu, SADECE TP1'in hedef mesafesini (diğer TP'lere dokunmadan) ekstra
# büyütüyor — TP1 biraz daha geç gelir ama geldiğinde daha anlamlı bir
# kâr bırakır, gürültüyle tetiklenme ihtimali azalır.
TP1_EK_GENISLETME_CARPANI = 1.0  # v16.21: SCALP MODU — 1.5'ten 1.0'a indirildi (yani
                        # artık TP1'e ekstra genişletme YOK). Scalp'te TP1'in HIZLI
                        # gelmesi isteniyor, geç gelip daha büyük kâr bırakması değil.

MIN_TP1_HAREKET_PCT = 0.0157  # v16.22: TP1 EN AZ bu yüzde kadar fiyat hareketinde
                        # olacak (kanal/otomatik ne kadar dar verirse versin taban
                        # buraya çekilir). $100 notional, %35 TP1 dilimiyle ≈ $0.55
                        # kâr hedefler — "hemen al-çık ama boşuna değil, birikir büyür".

def tp_olcekle(entry, sl, tp_liste, direction, carpan=TP_OLCEK_CARPANI):
    """
    Kanaldan gelen (ya da otomatik hesaplanan) TP'lerin oranını KORUYUP,
    hepsini aynı çarpanla büyütür. Kanalın 0.1/0.2/.../0.8R yapısı çok
    zayıf bir risk/ödül sağlıyordu (başabaş için %72 kazanma gerekiyordu);
    bu fonksiyon aynı şekli koruyarak matematiği sağlıklı hale getirir.
    v16.8: TP1 (ilk seviye) ayrıca TP1_EK_GENISLETME_CARPANI ile büyütülüyor
    — diğer TP'ler etkilenmiyor, sadece TP1 biraz daha uzağa taşınıyor.
    v16.22: MIN_TP1_HAREKET_PCT TABANI eklendi — bazı kanal sinyalleri
    (örn. PARTIUSDT: risk %5 iken TP1 sadece 0.10R = %0.5 hareket) o kadar
    dar TP1 veriyor ki $100 notional'da %35 dilimle bile kâr $0.10-0.20
    civarında kalıp "birikmiyor". Artık TP1, oran×çarpan ne çıkarsa çıksın,
    EN AZ bu yüzdelik fiyat hareketinde olacak şekilde tabana çekiliyor —
    hedef: TP1 dilim (%35) kabaca $0.50-0.60 civarı kâr bıraksın.
    """
    risk_mesafe = abs(entry - sl)
    if risk_mesafe <= 0 or not tp_liste:
        return tp_liste
    yeni_oranlar = []
    for i, tp in enumerate(tp_liste):
        oran = abs(tp - entry) / risk_mesafe
        yeni_oran = oran * carpan
        if i == 0:
            yeni_oran *= TP1_EK_GENISLETME_CARPANI
            min_oran = (MIN_TP1_HAREKET_PCT * entry) / risk_mesafe
            yeni_oran = max(yeni_oran, min_oran)
        yeni_oranlar.append(yeni_oran)

    # v16.23: TP1'e taban uygulanınca TP2/TP3 geride kalıp sıralamayı
    # bozabiliyordu (örn. TP1=0.31R'a çekildi ama TP2 ham hâliyle 0.20R'da
    # kaldı — TP2, TP1'İN ÖNÜNDE/ALTINDA kalırdı). Her TP, kendinden
    # ÖNCEKİNDEN en az %20 daha uzakta olacak şekilde zorlanıyor —
    # sıralama (TP1<TP2<TP3) HER ZAMAN korunuyor.
    for i in range(1, len(yeni_oranlar)):
        min_gerekli = yeni_oranlar[i-1] * 1.2
        if yeni_oranlar[i] < min_gerekli:
            yeni_oranlar[i] = min_gerekli

    yeni_liste = []
    for yeni_oran in yeni_oranlar:
        yeni_tp = entry + yeni_oran * risk_mesafe if direction == "long" else entry - yeni_oran * risk_mesafe
        yeni_liste.append(yeni_tp)
    return yeni_liste


# ════════════════════════════════════════════
# GERÇEK İŞLEM AÇMA (sinyal geldiğinde çağrılır)
# ════════════════════════════════════════════
def calc_macd_hist(kapaniş_listesi, hizli=12, yavas=26, sinyal=9):
    """Basit liste tabanlı MACD histogram (pandas'a bağımlı olmadan)."""
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    ema_h = s.ewm(span=hizli, adjust=False).mean()
    ema_y = s.ewm(span=yavas, adjust=False).mean()
    macd = ema_h - ema_y
    sinyal_hatti = macd.ewm(span=sinyal, adjust=False).mean()
    return float((macd - sinyal_hatti).iloc[-1])


def calc_bollinger_yuzdeB(kapaniş_listesi, period=20, std_mult=2.0):
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    orta = s.rolling(period).mean()
    std = s.rolling(period).std()
    ust = orta + std_mult * std
    alt = orta - std_mult * std
    genislik = (ust - alt).replace(0, 0.0001)
    yuzdeB = (s - alt) / genislik
    return float(yuzdeB.iloc[-1]) if not pd.isna(yuzdeB.iloc[-1]) else None


def calc_sma(kapaniş_listesi, period=20):
    """Basit hareketli ortalama (v16.9 — MA20 teyit kuralı için)."""
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    orta = s.rolling(period).mean()
    son = orta.iloc[-1]
    return float(son) if not pd.isna(son) else None


def calc_rsi(kapaniş_listesi, period=14):
    """Standart RSI (v16.9 — MA20 teyit kuralı için, 3. bileşen)."""
    import pandas as pd
    s = pd.Series(kapaniş_listesi)
    fark = s.diff()
    kazanc = fark.clip(lower=0)
    kayip = -fark.clip(upper=0)
    ort_kazanc = kazanc.rolling(period).mean()
    ort_kayip = kayip.rolling(period).mean()
    rs = ort_kazanc / ort_kayip.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))
    son = rsi.iloc[-1]
    return float(son) if not pd.isna(son) else None


def deneysel_gozlem_hesapla(sym):
    """
    DENEYSEL (henüz filtre DEĞİL, sadece gözlem): karar ağacı analizinde
    4h Bollinger %B ve 1h MACD histogramının en etkili göstergeler çıkması
    üzerine, her sinyalde bunları da hesaplayıp Telegram'a not düşüyoruz.
    Küçük örneklemden (49 sinyal) çıktığı için HENÜZ GÜVENİLİR DEĞİL —
    sadece zamanla veri biriktirmek için.
    """
    try:
        h4 = get_candles(sym, "4h", 30)
        h1 = get_candles(sym, "1h", 40)
        if not h4 or not h1 or len(h4) < 21 or len(h1) < 35:
            return None
        h4_kapanis = [c[4] for c in h4]
        h1_kapanis = [c[4] for c in h1]
        boll_4h = calc_bollinger_yuzdeB(h4_kapanis)
        macd_1h = calc_macd_hist(h1_kapanis)
        return {"4h_bollB": round(boll_4h, 2) if boll_4h is not None else None,
                "1h_macd_hist": round(macd_1h, 6)}
    except Exception:
        return None


def trend_teyidi_yeterli_mi(sym, direction):
    """
    v16.9 — ÜÇ BİLEŞENLİ TEYİT (eski 2-mum kıyaslamasının yerine geçti).

    ESKİ KURAL (v16-v16.8) sadece son 2 tane 4h/1h mumun tepe/dip
    kıyaslamasına bakıyordu (h4_high[-1] > h4_high[-2] gibi). Bu, ÇOK KISA
    vadeli gürültüye açıktı — iki somut gerçek örnekte yanlış karar verdi:
      - TRIA/USDT: genel trend SERT DÜŞÜŞTEYDİ (sonunda öyle de çıktı,
        sıçrama geri çöktü) ama filtre "4h yükseliş teyitli değil" deyip
        DOĞRU ret vermişti — bu örnekte filtre aslında haklıydı.
      - BEAT/USDT: genel trend yine SERT DÜŞÜŞTEYDİ (art arda alçalan
        4h tepeler) ama son 2 mumdaki ufak bir kıpırdanma yüzünden filtre
        "teyit sağlandı" deyip LONG açtı — SL'e doğru gitti. Burada filtre
        YANLIŞ onay vermişti, çünkü sadece 2 muma bakıp büyük resmi (haftalık
        düşüş) kaçırdı.

    YENİ KURAL — büyük resme bakan, kısa vadeli gürültüye karşı daha
    dayanıklı 3 bileşen; LONG için ÜÇÜ DE sağlanmalı:
      1) FİYAT 4h MA20'NİN ÜSTÜNDE (genel trend konumu — tek mum değil,
         20 mumluk ortalamaya göre nerede olduğumuz)
      2) SON 5 TANE 4h MUMUN EN AZ 3'Ü YÜKSELİŞTE KAPANMIŞ (kapanış >
         açılış) — kısa vadeli eğilim, tek mumun gürültüsüne takılmasın
      3) 1h RSI > 40 — momentum zayıf değil (49 sinyal analizinde TP
         grubunda ort. 47.6, SL grubunda ort. 38.1 çıkmıştı)
    SHORT için üçü de ters çevrilmiş hâliyle uygulanır (MA20 altında,
    5 mumun en az 3'ü düşüşte kapanmış, 1h RSI < 60).

    NOT: Bu hâlâ kanalın gerçek stratejisini çözdüğümüz anlamına gelmiyor,
    sadece göreceli zayıf görünen durumları eleyen bir koruma filtresi.
    Temel dayandığı örneklem (49 sinyal) küçük, kesin bir garanti değil.
    """
    try:
        h4 = get_candles(sym, "4h", 30)
        h1 = get_candles(sym, "1h", 30)
        if not h4 or not h1 or len(h4) < 21 or len(h1) < 15:
            return True, "veri yetersiz, filtre uygulanamadı — geçildi"

        h4_kapanis = [c[4] for c in h4]
        h4_acilis = [c[1] for c in h4]
        h1_kapanis = [c[4] for c in h1]

        fiyat = h4_kapanis[-1]
        ma20 = calc_sma(h4_kapanis, period=20)
        rsi_1h = calc_rsi(h1_kapanis, period=14)
        if ma20 is None or rsi_1h is None:
            return True, "gösterge hesaplanamadı, filtre uygulanamadı — geçildi"

        # ── son 5 mumun kaçı yükselişte/düşüşte kapanmış ──
        son_5_acilis = h4_acilis[-5:]
        son_5_kapanis = h4_kapanis[-5:]
        yukselis_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k > a)
        dusus_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k < a)

        if direction == "long":
            ma20_ustunde = fiyat > ma20
            mum_egilimi_yeterli = yukselis_sayisi >= 3
            rsi_yeterli = rsi_1h > 40

            if not ma20_ustunde:
                return False, f"4h fiyat MA20'nin altında ({fiyat:.8f} < {ma20:.8f})"
            if not mum_egilimi_yeterli:
                return False, f"son 5 mumun sadece {yukselis_sayisi}'i yükselişte kapandı (min 3 gerekli)"
            if not rsi_yeterli:
                return False, f"1h RSI zayıf ({rsi_1h:.1f} <= 40)"
        else:
            ma20_altinda = fiyat < ma20
            mum_egilimi_yeterli = dusus_sayisi >= 3
            rsi_yeterli = rsi_1h < 60

            if not ma20_altinda:
                return False, f"4h fiyat MA20'nin üstünde ({fiyat:.8f} > {ma20:.8f})"
            if not mum_egilimi_yeterli:
                return False, f"son 5 mumun sadece {dusus_sayisi}'i düşüşte kapandı (min 3 gerekli)"
            if not rsi_yeterli:
                return False, f"1h RSI zayıf ({rsi_1h:.1f} >= 60)"

        return True, (f"teyit sağlandı (MA20:{ma20:.8f}, mum:{yukselis_sayisi if direction=='long' else dusus_sayisi}/5, "
                       f"1h_RSI:{rsi_1h:.1f})")
    except Exception as e:
        return True, f"kontrol hatası ({e}), geçildi"


# ════════════════════════════════════════════
# ÖZ TARAMA — BOT KENDİ COİN BULUP AÇAR (v16.11, v16.12'de SCALP'e çevrildi)
# ════════════════════════════════════════════
# Kullanıcı talebiyle: kanal sinyalleri + manuel emirlerin YANINDA, bot
# artık likit VE YÜKSEK VOLATİLİTELİ coinleri periyodik olarak kendi
# tarayıp, KISA VADELİ (3m ana trend + 1m momentum) teyit mantığıyla
# kendi sinyalini üretip AÇABİLİYOR — scalp tarzı, hızlı giriş/çıkış.
#
# ÖNEMLİ SINIRLAR (kasıtlı, güvenlik için):
#  - Sadece YETERİNCE LİKİT coinler taranıyor (OZ_TARAMA_MIN_HACIM_USDT
#    altındakiler elenir) — düşük hacimli coinler manipülasyona daha açık.
#  - Likit coinler arasından, en YÜKSEK VOLATİLİTELİ olanlar öne alınıyor
#    (son birkaç 3m mumun ortalama range'i / fiyat) — scalp için hareket
#    olmayan durgun coinlerde işlem aramanın anlamı yok.
#  - RSI'da hem ALT hem ÜST sınır var (long için 40-75, short için 25-60)
#    — aşırı uzamış (tepeyi/dibi kovalayan) bir girişten kaçınmak için.
#  - "TAZELİK" kontrolü var — bir coin sürekli teyitli kalsa bile HER
#    taramada tekrar tekrar açılmaya çalışılmıyor; sadece "teyitsizden
#    teyitliye" geçiş anında tetikleniyor.
#  - TEYİTLİ: kendi 3m/1m göstergeleri (MA20+5mum+RSI) sağlanmadan asla
#    açılmıyor — "otomatik ama gelişigüzel değil" isteği bu şekilde
#    karşılanıyor.
#  - Kanal sinyalleri ve manuel emirlerle AYNI havuzu (trade_state,
#    MAX_POS, günlük zarar limiti) paylaşıyor — ayrı bir bütçesi yok.
#  - Tarama periyodu ÇOK KISA (varsayılan 2 dk) — scalp fırsatları 3m'lik
#    mumlarla oluşup kayboluyor, 20 dk'da bir bakmak "geç kalmasın"
#    isteğine aykırı olurdu.
OZ_TARAMA_AKTIF = os.getenv("OZ_TARAMA_AKTIF", "false").lower() == "true"  # v16.15: kullanıcı
                # talebiyle VARSAYILAN KAPALI — son birkaç günde (özellikle scalp modunun
                # devreye girdiği 09-10 Temmuz'da) sermaye 67$'dan 38.89$'a düşmüştü, kesin
                # tek sebep olduğu kanıtlanmadı ama zamanlama örtüşüyordu. Kanal sinyalleri
                # ve manuel emirler ETKİLENMİYOR, normal çalışmaya devam ediyor. Tekrar açmak
                # için Railway'de OZ_TARAMA_AKTIF=true ortam değişkenini eklemen yeterli.
OZ_TARAMA_ARALIK_DK = float(os.getenv("OZ_TARAMA_ARALIK_DK", "2"))  # scalp: sık tarama
OZ_TARAMA_MIN_HACIM_USDT = float(os.getenv("OZ_TARAMA_MIN_HACIM_USDT", "5000000"))  # 24h min hacim (likidite güvenliği)
OZ_TARAMA_WATCHLIST_BOYUTU = int(os.getenv("OZ_TARAMA_WATCHLIST_BOYUTU", "20"))  # en volatil N coin (likit havuzdan)
OZ_TARAMA_LIKIT_HAVUZ_BOYUTU = int(os.getenv("OZ_TARAMA_LIKIT_HAVUZ_BOYUTU", "60"))  # önce hacme göre bu kadarı alınır, sonra volatiliteye göre elenir
OZ_TARAMA_ANA_TF = "3m"   # trend/MA20 için ana zaman dilimi (scalp)
OZ_TARAMA_MOMENTUM_TF = "1m"  # RSI için momentum zaman dilimi (scalp)

oz_tarama_gecmis = {}  # {symbol: "long"|"short"|None} — son teyit durumu, tazelik kontrolü için
oz_tarama_lock = threading.Lock()


def oz_tarama_volatilite_hesapla(sym, mum_sayisi=20):
    """
    Son N adet OZ_TARAMA_ANA_TF (3m) mumunun ortalama (high-low)/close
    oranını yüzde olarak döner — "bu coin şu an ne kadar hareketli"
    ölçüsü. Yüksek değer = yüksek volatilite = scalp için daha çok fırsat.
    SADECE oz_tarama_loop() (1-5dk'lık ultra-kısa scalp) içinde kullanılır.
    """
    try:
        mumlar = get_candles(sym, OZ_TARAMA_ANA_TF, mum_sayisi)
        if not mumlar or len(mumlar) < 5:
            return None
        oranlar = []
        for c in mumlar:
            _, o, h, l, kapanis, _ = c
            if kapanis > 0:
                oranlar.append((h - l) / kapanis)
        if not oranlar:
            return None
        return (sum(oranlar) / len(oranlar)) * 100  # yüzde
    except Exception:
        return None


def manuel_volatilite_hesapla(sym, tf="1h", mum_sayisi=20):
    """
    v16.27: Manuel ("basit format") komutlar İÇİN AYRI volatilite ölçümü.
    Eskiden manuel komutlar da oz_tarama_volatilite_hesapla() (3dk bazlı)
    kullanıyordu — bu, 1-5dk'lık ultra-kısa scalp için tasarlanmıştı ve
    manuel işlemlerde (WLDUSDT örneği: ham volatilite=%0.27) gerçekçi
    olmayan, aşırı dar SL'lere (%0.40 tabana takılan) yol açıyordu.
    Şimdi manuel komutlar 1 SAATLİK mumların ortalama (high-low)/close
    oranını kullanıyor — daha büyük zaman dilimi, daha gerçekçi/geniş bir
    SL mesafesi üretir, gürültüyle anında vurulma riski büyük ölçüde azalır.
    """
    try:
        mumlar = get_candles(sym, tf, mum_sayisi)
        if not mumlar or len(mumlar) < 5:
            return None
        oranlar = []
        for c in mumlar:
            _, o, h, l, kapanis, _ = c
            if kapanis > 0:
                oranlar.append((h - l) / kapanis)
        if not oranlar:
            return None
        return (sum(oranlar) / len(oranlar)) * 100  # yüzde
    except Exception:
        return None


def oz_tarama_watchlist_getir():
    """
    1) Bitget'teki USDT perpetual'lar arasından, 24h hacme göre yeterince
       likit olan ilk OZ_TARAMA_LIKIT_HAVUZ_BOYUTU kadarını alır (düşük
       hacimli coinler baştan elenir — manipülasyon riski).
    2) Bu likit havuz içinden, KISA VADELİ (3m) VOLATİLİTESİ en yüksek
       olan OZ_TARAMA_WATCHLIST_BOYUTU kadarını seçer — scalp için hareket
       olmayan durgun coinlere bakmanın anlamı yok.
    """
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[OZ_TARAMA] Ticker listesi alınamadı: {e}")
        return []

    hacim_adaylari = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        hacim = safe(t.get("quoteVolume"))
        if hacim >= OZ_TARAMA_MIN_HACIM_USDT:
            hacim_adaylari.append((sym, hacim))

    hacim_adaylari.sort(key=lambda x: x[1], reverse=True)
    likit_havuz = [sym for sym, _ in hacim_adaylari[:OZ_TARAMA_LIKIT_HAVUZ_BOYUTU]]

    volatilite_listesi = []
    for sym in likit_havuz:
        vol = oz_tarama_volatilite_hesapla(sym)
        if vol is not None:
            volatilite_listesi.append((sym, vol))

    volatilite_listesi.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in volatilite_listesi[:OZ_TARAMA_WATCHLIST_BOYUTU]]


def oz_tarama_aday_degerlendir(sym):
    """
    SCALP TEYİDİ (v16.12): trend_teyidi_yeterli_mi ile AYNI FELSEFE (MA20 +
    5-mum eğilimi + RSI, hem alt hem üst sınırla) ama KISA VADELİ zaman
    dilimlerinde — 3m mumlarla trend/MA20, 1m mumlarla RSI/momentum.
    "Otomatik ama gelişigüzel değil" isteği bu üç şartın HEPSİNİN
    sağlanmasıyla karşılanıyor; hiçbiri eksikse aday reddedilir.
    Döner: "long", "short", ya da None (aday yok).
    """
    try:
        ana = get_candles(sym, OZ_TARAMA_ANA_TF, 30)
        mom = get_candles(sym, OZ_TARAMA_MOMENTUM_TF, 30)
        if not ana or not mom or len(ana) < 21 or len(mom) < 15:
            return None

        ana_kapanis = [c[4] for c in ana]
        ana_acilis = [c[1] for c in ana]
        mom_kapanis = [c[4] for c in mom]

        fiyat = ana_kapanis[-1]
        ma20 = calc_sma(ana_kapanis, period=20)
        rsi_mom = calc_rsi(mom_kapanis, period=14)
        if ma20 is None or rsi_mom is None:
            return None

        son_5_acilis = ana_acilis[-5:]
        son_5_kapanis = ana_kapanis[-5:]
        yukselis_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k > a)
        dusus_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k < a)

        if fiyat > ma20 and yukselis_sayisi >= 3 and 40 < rsi_mom < 75:
            return "long"
        if fiyat < ma20 and dusus_sayisi >= 3 and 25 < rsi_mom < 60:
            return "short"
        return None
    except Exception as e:
        log.warning(f"[OZ_TARAMA] {sym} değerlendirilemedi: {e}")
        return None


def oz_tarama_loop():
    """
    Her OZ_TARAMA_ARALIK_DK dakikada bir (scalp: varsayılan 2 dk) likit VE
    volatil coinleri tarar, TAZE bir LONG/SHORT teyidi bulursa sinyali_isle()
    üzerinden AYNI havuza (MAX_POS, günlük zarar limiti) sokar — ama kendi
    3m/1m teyidi zaten yeterli sayıldığı için (bkz. sinyali_isle içindeki
    "oz_tarama" istisnası) kanalın 4h/1h kuyruğuna TAKILMADAN, GECİKMEDEN
    direkt açılır.
    """
    if not OZ_TARAMA_AKTIF:
        log.info("[OZ_TARAMA] Devre dışı (OZ_TARAMA_AKTIF=false)")
        return

    tg(f"🔍 Öz tarama (SCALP) AKTİF — her {OZ_TARAMA_ARALIK_DK} dk'da bir "
       f"likit havuzdan ({OZ_TARAMA_LIKIT_HAVUZ_BOYUTU} coin, min 24h hacim "
       f"${OZ_TARAMA_MIN_HACIM_USDT:,.0f}) en volatil {OZ_TARAMA_WATCHLIST_BOYUTU} "
       f"coin taranacak ({OZ_TARAMA_ANA_TF} trend + {OZ_TARAMA_MOMENTUM_TF} momentum, teyitli)")

    while True:
        try:
            time.sleep(OZ_TARAMA_ARALIK_DK * 60)

            if gunluk_limit_asildi():
                continue
            with state_lock:
                pozisyon_dolu = len(trade_state) >= MAX_POS
            if pozisyon_dolu:
                continue  # slot yoksa taramaya bile gerek yok

            watchlist = oz_tarama_watchlist_getir()
            for sym in watchlist:
                with state_lock:
                    zaten_acik = sym in trade_state
                with bekleyen_lock:
                    zaten_bekliyor = sym in bekleyen_sinyaller
                if zaten_acik or zaten_bekliyor:
                    continue

                yon = oz_tarama_aday_degerlendir(sym)

                with oz_tarama_lock:
                    onceki_yon = oz_tarama_gecmis.get(sym)
                    oz_tarama_gecmis[sym] = yon

                # ── TAZELİK KONTROLÜ: sadece teyitsizden teyitliye GEÇİŞ
                # anında tetiklenir — coin birkaç tarama boyunca teyitli
                # kalsa bile tekrar tekrar açılmaya çalışılmaz. ──
                if yon is None or yon == onceki_yon:
                    continue

                # ── v16.13 DÜZELTME: "TP1 çok erken geliyor" — eskiden öz
                # tarama sinyalleri entry/sl=None ile gönderilip botun
                # SABİT %2 SL varsayımına (HIZLI_SL_PCT) düşüyordu, TP1 de
                # bunun üzerinden ~%0.6 gibi ÇOK DAR bir mesafeye kuruluyordu
                # — bu kanal sinyalleri (4h/1h) için makul olsa da, scalp'in
                # kısa vadeli gürültüsünde saniyeler/dakikalar içinde
                # tetikleniyordu (asıl hareket gelişmeden erken çıkılıyordu).
                # Şimdi SL, coin'in GERÇEK ÖLÇÜLEN 3m volatilitesine göre
                # hesaplanıyor — durgun bir coin dar SL alır, hareketli bir
                # coin daha geniş SL alır, TP'ler de buna ORANTILI kalır
                # (R-katları şeklinde, sabit yüzde değil).
                try:
                    ticker = exchange.fetch_ticker(sym)
                    entry_fiyat = safe(ticker.get("last"))
                except Exception as e:
                    log.warning(f"[OZ_TARAMA] {sym} fiyat alınamadı: {e}")
                    continue
                if entry_fiyat <= 0:
                    continue

                volatilite_pct = oz_tarama_volatilite_hesapla(sym)
                if volatilite_pct is None:
                    continue
                # SL mesafesi = ölçülen volatilitenin ~1.5 katı, ama en az
                # %0.4 ve en çok MAX_SL_PCT (%3) ile sınırlı — hem çok dar
                # (gürültüyle anında vurulan) hem çok geniş (aşırı risk) SL
                # engellenmiş oluyor.
                sl_pct = max(0.004, min(volatilite_pct / 100 * 1.5, MAX_SL_PCT))
                sl_fiyat = entry_fiyat * (1 - sl_pct) if yon == "long" else entry_fiyat * (1 + sl_pct)
                risk = abs(entry_fiyat - sl_fiyat)
                # TP'ler R-katları: 0.5R / 1.0R / 1.6R / 2.4R (v16.14: TP4
                # eklendi, kanal tarafındaki TP1-4 yapısıyla tutarlı olsun
                # diye) — kanal sinyallerindeki tp_olcekle'nin TEKRAR
                # ölçeklemesini istemiyoruz (bkz. asil_islemi_ac'teki
                # "oz_tarama zaten final" kontrolü), bu yüzden burada NİHAİ
                # fiyatları doğrudan veriyoruz.
                oranlar = [0.5, 1.0, 1.6, 2.4]
                if yon == "long":
                    tp_liste = [entry_fiyat + o * risk for o in oranlar]
                else:
                    tp_liste = [entry_fiyat - o * risk for o in oranlar]

                sinyal = {"symbol": sym, "direction": yon, "entry": entry_fiyat, "sl": sl_fiyat,
                          "tp_liste": tp_liste, "kaynak_etiket": "oz_tarama"}
                tg(f"🤖 [ÖZ TARAMA/SCALP] {sym} {yon.upper()} adayı bulundu (taze teyit, "
                   f"{OZ_TARAMA_ANA_TF}/{OZ_TARAMA_MOMENTUM_TF}, volatilite:%{volatilite_pct:.2f}, "
                   f"SL mesafesi:%{sl_pct*100:.2f}) — açılıyor...")
                sinyali_isle(sinyal)

                with state_lock:
                    if len(trade_state) >= MAX_POS:
                        break  # slot dolduysa bu turu bitir
        except Exception as e:
            log.error(f"[OZ_TARAMA] {e}")
            time.sleep(30)


def manuel_pozisyon_kapat(sym):
    """
    Gerçekten borsadan pozisyonu kapatır (reduceOnly market emri), STOP/TP'de
    kullandığımız AYNI doğrulama mantığıyla — emrin gerçekten uygulandığını
    kontrol etmeden trade_state'ten silmiyoruz.
    """
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            return True, f"ℹ️ {sym} zaten borsada açık değilmiş, kayıt temizlendi."

        qty = safe(gercek_pos.get("contracts"))
        direction = "long" if gercek_pos.get("side") == "long" else "short"
        entry = safe(gercek_pos.get("entryPrice"))

        with state_lock:
            kayitli_durum = trade_state.get(sym, {})
        tp_emirlerini_iptal_et(sym, kayitli_durum.get("tp_emirleri", []), kayitli_durum.get("tp_index", 0))

        kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                       qty, params={"reduceOnly": True})
        time.sleep(1)
        guncel = exchange.fetch_positions([sym])
        kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)

        if not kapandi_mi:
            return False, f"⚠️ {sym} kapatma emri gönderildi ama doğrulanamadı — tekrar dene."

        t = exchange.fetch_ticker(sym)
        tahmini_fiyat = safe(t["last"])
        price, komisyon = gercek_dolus_bilgisi_al(kapatma_emri, sym, tahmini_fiyat)
        gross = (price - entry) * qty if direction == "long" else (entry - price) * qty
        gross -= komisyon
        gunluk_pnl_ekle(gross)

        with state_lock:
            onceki_gerceklesen = trade_state.get(sym, {}).get("gerceklesen_pnl", 0)
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        trade_log_kaydet({
            "symbol": sym, "direction": direction, "entry": entry,
            "exit": price, "pnl": gross + onceki_gerceklesen, "sonuc": "MANUEL_KAPATMA",
            "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        })
        return True, f"✅ {sym} manuel olarak kapatıldı | PnL≈{gross:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma sırasında hata: {e}"


TEYIT_BEKLEME_DAKIKA = int(os.getenv("TEYIT_BEKLEME_DAKIKA", "180"))  # v16.1: teyitsiz sinyal
                        # hemen düşürülmüyor, bu süre boyunca (dk) arka planda tekrar tekrar
                        # kontrol ediliyor — süre dolmadan teyit sağlanırsa GÜNCEL fiyattan açılıyor.
                        # Kanaldan gördüğün davranışa göre bu süreyi env değişkeniyle ayarlayabilirsin
                        # (örn. Railway'de TEYIT_BEKLEME_DAKIKA=240 dersen 4 saat bekler).
TEYIT_KONTROL_ARALIGI_SN = 60  # bekleyen sinyaller kaç saniyede bir yeniden kontrol edilsin

bekleyen_sinyaller = {}  # {symbol: {"sinyal":..., "gozlem_str":..., "eklenme_zamani": epoch}}
bekleyen_lock = threading.Lock()


def sinyali_isle(sinyal):
    if gunluk_limit_asildi():
        tg("⛔ Günlük zarar limiti aşıldı, bu sinyal atlandı.")
        return

    with state_lock:
        if len(trade_state) >= MAX_POS:
            tg(f"⏭️ Zaten açık pozisyon var (MAX_POS={MAX_POS}), sinyal atlandı: {sinyal['symbol']}")
            return

    sym = sinyal["symbol"]
    direction = sinyal["direction"]

    # ── v16.12: ÖZ TARAMA (scalp) kaynaklı sinyaller kendi 3m/1m teyidini
    # zaten oz_tarama_aday_degerlendir() içinde geçmiş oluyor — bu yüzden
    # burada AYRICA kanalın 4h/1h teyidinden (trend_teyidi_yeterli_mi) VE
    # 180 dk'lık kuyruktan geçirilmiyor.
    # v16.26: MANUEL komutlar ARTIK TEKRAR teyitten geçiyor — kullanıcı
    # talebi değişti ("yaz teyitli olsun"): SKLUSDT örneğinde bot, kısa
    # vadeli bir tepe noktasına denk gelen anda piyasa fiyatından körlemesine
    # girmişti (giriş = tam yerel tepe, hemen ardından geri çekildi). v16.16'da
    # "manuel komut anında açsın" diye BİLEREK muaf tutulmuştu, o karar artık
    # geçersiz — manuel komutlar da kanal sinyalleriyle AYNI teyit sürecinden
    # (trend_teyidi_yeterli_mi + bekleyen_sinyaller kuyruğu) geçiyor. ──
    if sinyal.get("kaynak_etiket") == "oz_tarama":
        gozlem = deneysel_gozlem_hesapla(sym)
        gozlem_str = f" | 📊 Deneysel: {gozlem}" if gozlem else ""
        asil_islemi_ac(sinyal, gozlem_str)
        return

    # ── DENEYSEL GÖZLEM (henüz filtre değil, sadece veri biriktirme) ──
    gozlem = deneysel_gozlem_hesapla(sym)
    gozlem_str = f" | 📊 Deneysel: {gozlem}" if gozlem else ""

    teyit_ok, teyit_mesaj = trend_teyidi_yeterli_mi(sym, direction)
    if not teyit_ok:
        with bekleyen_lock:
            zaten_bekliyor = sym in bekleyen_sinyaller
            bekleyen_sinyaller[sym] = {
                "sinyal": sinyal, "gozlem_str": gozlem_str, "eklenme_zamani": time.time(),
            }
        durumu_telegrama_yedekle()  # v16.8: kuyruk da kaybolmasın diye yedekle
        if zaten_bekliyor:
            tg(f"⏭️ {sym} {direction.upper()} hâlâ teyitsiz ({teyit_mesaj}) — bekleme süresi yenilendi"
               f"{gozlem_str}")
        else:
            tg(f"⏳ {sym} {direction.upper()} şimdilik atlandı — trend teyidi zayıf ({teyit_mesaj}).\n"
               f"Arka planda en fazla {TEYIT_BEKLEME_DAKIKA} dk boyunca izlenecek, teyit gelirse "
               f"GÜNCEL fiyattan otomatik açılacak{gozlem_str}")
        return

    asil_islemi_ac(sinyal, gozlem_str)


def _sinyali_guncel_fiyata_yenile(sinyal):
    """
    v16.1 DÜZELTME: Kuyrukta saatlerce bekleyen bir sinyal onaylandığında,
    kanalın SAATLER ÖNCE verdiği (artık bayat olabilecek) mutlak giriş/SL/TP
    fiyatlarını KULLANMIYORUZ. Bunun yerine kanalın orijinal RİSK YÜZDESİ
    (SL mesafesi) ve TP oranları (R katları) KORUNUR, sadece referans
    fiyat GÜNCEL piyasa fiyatına yeniden ankorlanır. Böylece "güncel
    fiyattan açılıyor" mesajı gerçeği yansıtır — sadece giriş fiyatı değil,
    SL/TP seviyeleri de güncelliğini korur.
    Basit format (entry=None) sinyallerde zaten dokunmaya gerek yok —
    asil_islemi_ac bunları otomatik olarak anlık fiyattan hesaplıyor.
    """
    sym = sinyal["symbol"]
    direction = sinyal["direction"]
    orig_entry = sinyal.get("entry")
    orig_sl = sinyal.get("sl")
    orig_tp = sinyal.get("tp_liste") or []

    if orig_entry is None or orig_sl is None:
        return dict(sinyal)  # basit format — değişiklik gerekmiyor

    try:
        t = exchange.fetch_ticker(sym)
        guncel_fiyat = safe(t["last"])
    except Exception as e:
        tg(f"⚠️ {sym} güncel fiyat alınamadı, kuyruktan açılamadı: {e}")
        return None
    if guncel_fiyat <= 0:
        tg(f"⚠️ {sym} geçersiz fiyat alındı, kuyruktan açılamadı")
        return None

    risk_pct = abs(orig_entry - orig_sl) / orig_entry
    yeni = dict(sinyal)
    yeni["entry"] = guncel_fiyat
    yeni["sl"] = guncel_fiyat * (1 - risk_pct) if direction == "long" else guncel_fiyat * (1 + risk_pct)

    if orig_tp:
        risk_mesafe_orig = abs(orig_entry - orig_sl)
        if risk_mesafe_orig > 0:
            oranlar = [abs(tp - orig_entry) / risk_mesafe_orig for tp in orig_tp]
            yeni_risk_mesafe = abs(guncel_fiyat - yeni["sl"])
            if direction == "long":
                yeni["tp_liste"] = [guncel_fiyat + o * yeni_risk_mesafe for o in oranlar]
            else:
                yeni["tp_liste"] = [guncel_fiyat - o * yeni_risk_mesafe for o in oranlar]

    return yeni


def teyit_bekleme_loop():
    """
    v16.1: Teyit edilemediği için hemen açılmayan sinyalleri arka planda
    TEYIT_BEKLEME_DAKIKA süresince tekrar tekrar kontrol eder. Bazı
    trendlerin teyit vermesi (4h'de yeni zirve/dip oluşması) kanaldan
    hemen sonra değil, saatler sonra gerçekleşebiliyor — bu döngü o
    durumları yakalar. Süre dolarsa sinyal tamamen düşürülür.
    """
    while True:
        try:
            time.sleep(TEYIT_KONTROL_ARALIGI_SN)
            with bekleyen_lock:
                semboller = list(bekleyen_sinyaller.keys())

            for sym in semboller:
                with bekleyen_lock:
                    kayit = bekleyen_sinyaller.get(sym)
                if not kayit:
                    continue

                gecen_dk = (time.time() - kayit["eklenme_zamani"]) / 60
                if gecen_dk > TEYIT_BEKLEME_DAKIKA:
                    with bekleyen_lock:
                        bekleyen_sinyaller.pop(sym, None)
                    durumu_telegrama_yedekle()
                    tg(f"🗑️ {sym} {kayit['sinyal']['direction'].upper()} — {TEYIT_BEKLEME_DAKIKA} dk "
                       f"içinde teyit gelmedi, sinyal tamamen düşürüldü")
                    continue

                if gunluk_limit_asildi():
                    continue  # günlük limit aşılmışsa bekleyen sinyalleri açmaya çalışma

                with state_lock:
                    pozisyon_dolu = len(trade_state) >= MAX_POS
                if pozisyon_dolu:
                    continue  # zaten açık pozisyon varsa sırasını beklesin, listede kalsın

                direction = kayit["sinyal"]["direction"]
                teyit_ok, teyit_mesaj = trend_teyidi_yeterli_mi(sym, direction)
                if teyit_ok:
                    with bekleyen_lock:
                        bekleyen_sinyaller.pop(sym, None)
                    durumu_telegrama_yedekle()
                    guncel_sinyal = _sinyali_guncel_fiyata_yenile(kayit["sinyal"])
                    if guncel_sinyal is None:
                        continue  # fiyat alınamadı, hata mesajı zaten gönderildi
                    tg(f"✅ {sym} {direction.upper()} — teyit {gecen_dk:.0f} dk sonra sağlandı "
                       f"({teyit_mesaj}), GÜNCEL fiyattan (SL/TP de yeniden ankorlandı) açılıyor")
                    asil_islemi_ac(guncel_sinyal, kayit["gozlem_str"])
        except Exception as e:
            log.error(f"[TEYIT_BEKLEME] {e}")
            time.sleep(10)


def asil_islemi_ac(sinyal, gozlem_str=""):
    """
    Gerçek borsa emrini gönderen kısım — hem anında teyit edilen sinyaller
    hem de teyit_bekleme_loop() tarafından sonradan onaylanan sinyaller
    buraya gelir. Fiyat/SL/TP hesapları HER ZAMAN çağrıldığı ANDAKİ piyasa
    verisiyle yapılır (bekleyen sinyalde saatler önceki fiyat kullanılmaz).
    """
    sym = sinyal["symbol"]
    direction = sinyal["direction"]
    entry_hedef = sinyal["entry"]
    sl = sinyal["sl"]

    if entry_hedef is None or sl is None:
        # ── Basit format: giriş = anlık fiyat, SL = GERÇEK VOLATİLİTEYE
        # GÖRE hesaplanır (v16.27) ──
        # v16.25'te SL sabit %2'den volatilite bazlıya geçirilmişti ama
        # YANLIŞLIKLA oz_tarama'nın 3dk'lık ultra-kısa scalp ölçümünü
        # (oz_tarama_volatilite_hesapla) kullanıyordu. WLDUSDT örneğinde
        # bu, ham volatilite=%0.27 gibi çok küçük bir değer verip SL'i
        # tabana (%0.40) sıkıştırdı — gürültüyle anında vurulacak kadar
        # dar. Şimdi manuel_volatilite_hesapla() (1 SAATLİK mumlar, 20
        # periyot) kullanılıyor — daha büyük zaman dilimi, daha gerçekçi
        # ve daha geniş bir SL mesafesi üretir. Taban da %0.4'ten %1.2'ye,
        # çarpan da 1.5'ten 2.0'a yükseltildi (1H ölçüm zaten 3dk'dan
        # doğal olarak daha büyük çıkar ama yine de fazladan güvenlik payı
        # eklendi — MAX_SL_PCT (%3) hâlâ üst sınır olarak duruyor).
        try:
            t = exchange.fetch_ticker(sym)
            entry_hedef = safe(t["last"])
        except Exception as e:
            tg(f"⚠️ {sym} anlık fiyat alınamadı: {e}")
            return

        volatilite_pct = manuel_volatilite_hesapla(sym, tf="1h", mum_sayisi=20)
        if volatilite_pct is not None:
            sl_pct_hesap = max(0.012, min(volatilite_pct / 100 * 2.0, MAX_SL_PCT))
            sl_kaynagi = f"1H volatilite bazlı, ham volatilite=%{volatilite_pct:.2f}"
        else:
            sl_pct_hesap = HIZLI_SL_PCT
            sl_kaynagi = "1H volatilite alınamadı, sabit yedek değer kullanıldı"
        sl = entry_hedef * (1 - sl_pct_hesap) if direction == "long" else entry_hedef * (1 + sl_pct_hesap)

        # ── Kanalın GERÇEK TP oranlarına göre 6 kademeli TP (ham hâli) ──
        risk_mesafe = abs(entry_hedef - sl)
        KANAL_TP_ORANLARI = [0.1, 0.2, 0.3, 0.4, 0.5, 0.8]
        if direction == "long":
            tp_liste_otomatik = [entry_hedef + oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        else:
            tp_liste_otomatik = [entry_hedef - oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        sinyal["tp_liste"] = tp_liste_otomatik

        tg(f"ℹ️ {sym} basit format — giriş≈{entry_hedef:.8f}\n"
           f"SL (%{sl_pct_hesap*100:.2f}, {sl_kaynagi}): {sl:.8f}\n"
           f"Otomatik TP (kanal oranlarıyla, ham): {[round(x,8) for x in tp_liste_otomatik]}")

    # ── kanalın SL'i çok genişse ATLAMIYORUZ — kendi SL'imizi
    # (MAX_SL_PCT mesafesinde) koyup işleme devam ediyoruz ──
    sl_pct = abs(entry_hedef - sl) / entry_hedef
    if sl_pct > MAX_SL_PCT:
        sl_eski = sl
        sl = entry_hedef * (1 - MAX_SL_PCT) if direction == "long" else entry_hedef * (1 + MAX_SL_PCT)
        tg(f"ℹ️ {sym} kanalın SL'i çok genişti (%{sl_pct*100:.2f}) — kendi SL'imize "
           f"sıkıştırıldı: {sl_eski:.8f} → {sl:.8f} (%{MAX_SL_PCT*100:.1f})")

    # ── ORTAK NOKTA: hem gerçek kanal sinyali hem basit format buraya gelir.
    # Kanalın ham TP oranları (0.1-0.8R) matematiksel olarak zayıftı
    # (başabaş için %72 kazanma gerekiyordu) — aynı şekli koruyarak
    # ölçekliyoruz (v16: 2.0x, TP6 ~0.8R'den ~1.6R'ye çıkıyor).
    # v16.13: ÖZ TARAMA (scalp) sinyalleri BURAYA GİRMİYOR — onlar zaten
    # oz_tarama_loop() içinde NİHAİ R-katlarıyla (0.6R/1.2R/2.0R) hesaplanmış
    # geliyor. Bunları da kanal mantığıyla TEKRAR ölçeklersek (2.0x + TP1
    # ekstra 1.5x) TP1 hedefi ~1.8R gibi aşırı GENİŞ bir mesafeye çıkardı —
    # tam ters yönde bir hataya (TP1 hiç gelmeyen bir pozisyon) yol açardı. ──
    if sinyal.get("tp_liste") and sinyal.get("kaynak_etiket") != "oz_tarama":
        tp_ham = sinyal["tp_liste"]
        tp_olcekli_tam = tp_olcekle(entry_hedef, sl, tp_ham, direction)
        # ── v16.10: sadece İLK 3 TP sabit hedef olarak kullanılıyor —
        # TP3'ten sonra kalan pozisyon TP4-6'yı beklemeden trailing'e
        # geçiyor (bkz. TP_DILIM_ORANLARI notu). Ham/ölçekli TP4-6 hâlâ
        # Telegram mesajında bilgi amaçlı gösteriliyor ama pozisyon
        # yönetiminde (limit emirleri, tp_index takibi) kullanılmıyor.
        sinyal["tp_liste"] = tp_olcekli_tam[:TP_SAYISI_KULLANILAN]
        tg(f"📐 TP'ler {TP_OLCEK_CARPANI}x ölçeklendi (ilk {TP_SAYISI_KULLANILAN}'ü sabit hedef, "
           f"sonrası trailing'e bırakıldı):\n"
           f"Ham: {[round(x,8) for x in tp_ham]}\n"
           f"Ölçekli (tam): {[round(x,8) for x in tp_olcekli_tam]}\n"
           f"Kullanılan (TP1-{TP_SAYISI_KULLANILAN}): {[round(x,8) for x in sinyal['tp_liste']]}")
    elif sinyal.get("tp_liste") and sinyal.get("kaynak_etiket") == "oz_tarama":
        sinyal["tp_liste"] = sinyal["tp_liste"][:TP_SAYISI_KULLANILAN]
        tg(f"📐 Scalp TP'leri (R-katları, ölçeklenmeden kullanılıyor): "
           f"{[round(x,8) for x in sinyal['tp_liste']]}")

    amount, notional = pozisyon_boyutu_hesapla(entry_hedef, sl)
    if not amount:
        tg(f"⚠️ {sym} pozisyon boyutu hesaplanamadı, atlandı")
        return

    gereken_marj = notional / LEV
    if not gercek_bakiye_yeterli_mi(gereken_marj):
        tg(f"⚠️ {sym} atlandı — gerçek bakiye yetersiz (gereken marj≈${gereken_marj:.2f}). "
           f"Bakiyeni kontrol et.")
        return

    try:
        exchange.set_leverage(LEV, sym)
    except Exception as e:
        tg(f"⚠️ {sym} kaldıraç ayarlanamadı: {e} — işlem atlandı")
        return

    try:
        t = exchange.fetch_ticker(sym)
        price = safe(t["last"])
    except Exception as e:
        tg(f"⚠️ {sym} fiyat alınamadı: {e}")
        return

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        tg(f"⚠️ {sym} miktar hassasiyeti alınamadı: {e}")
        return
    if qty <= 0:
        return

    side = "buy" if direction == "long" else "sell"
    try:
        acilis_emri = exchange.create_market_order(sym, side, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giriş emri başarısız: {e}")
        return

    # v16.21: açılış komisyonu da yakalanıp trade_state'e kaydediliyor —
    # eskiden sadece KAPANIŞ komisyonları toplam PnL'den düşülüyordu,
    # açılış komisyonu hiç sayılmıyordu (bu yüzden bot'un attığı "TOPLAM
    # işlem PnL" mesajı gerçek borsa sonucundan sistematik olarak daha
    # iyimser çıkıyordu — kullanıcı örneği: bot -0.09$ dedi, borsa -0.1457$
    # gösterdi, fark tam da bu kayıp açılış komisyonuydu).
    try:
        _, acilis_komisyon = gercek_dolus_bilgisi_al(acilis_emri or {}, sym, price)
    except Exception:
        acilis_komisyon = 0.0

    # ── v16.8 KRİTİK DÜZELTME: trade_state artık TP limit emirlerini
    # KOYMADAN ÖNCE yazılıyor. Eskiden (v16.8) TP emirleri önce koyuluyordu
    # (6 ayrı borsa API çağrısı, 1-3+ saniye sürebiliyor) — bu süre boyunca
    # pozisyon borsada AÇIKTI ama trade_state'te HENÜZ YOKTU. Eğer manage()
    # döngüsü arka planda tam bu pencerede pozisyonu tarasaydı, "kayıtlı
    # durum yok" sanıp üzerine genel %3 güvenlik SL'i koyuyordu — TP
    # takibi, kademeli SL, tampon payı hiçbiri devrede olmadan (LAB
    # işleminde gerçekleşen -2.72$ zararın sebebi muhtemelen buydu).
    # Şimdi state HEMEN yazılıyor, TP emirleri sonradan ekleniyor —
    # pozisyonun "sahipsiz" göründüğü pencere ortadan kalkıyor. ──
    with state_lock:
        trade_state[sym] = {
            "sl": sl, "tp_liste": sinyal["tp_liste"], "tp_index": 0,
            "direction": direction, "entry": price, "qty": qty,
            "kaynak": sinyal.get("kaynak_etiket", "kanal_kopya"),
            "orijinal_qty": qty, "tp_emirleri": [],
            "acilis_komisyon": acilis_komisyon,
        }
    durumu_diske_yaz()

    # ── v16.8: TP'LER ARTIK GERÇEK LİMİT EMRİ OLARAK BORSAYA KONUYOR ──
    # Eskiden bot her 5 saniyede bir anlık fiyatı TP hedefiyle karşılaştırıyordu
    # — fiyat iki kontrol arasında hızlıca TP'ye değip geri çekilirse (kısa bir
    # fitil), bot o anı KAÇIRABİLİYORDU (VELVET örneğinde olduğu gibi). Şimdi
    # her TP seviyesi için gerçek bir reduceOnly LİMİT emri açılış anında
    # borsaya gönderiliyor — borsanın kendi eşleştirme motoru fiyata değen
    # her anı yakalar, bizim döngümüzün o saniyede bakıp bakmadığından
    # bağımsız. Bir emir konulamazsa (hata), o TP için eski (fiyat karşılaştırma)
    # yönteme otomatik geri dönülüyor — hibrit ve güvenli.
    tp_emirleri = tp_limit_emirlerini_koy(sym, direction, sinyal["tp_liste"], qty)
    with state_lock:
        if sym in trade_state:  # işlem bu sırada zaten kapanmadıysa güncelle
            trade_state[sym]["tp_emirleri"] = tp_emirleri
    durumu_diske_yaz()

    kacan_emir_sayisi = sum(1 for e in tp_emirleri if e.get("id") is None)
    ek_uyari = (f"\n⚠️ {kacan_emir_sayisi} TP seviyesi için limit emri konulamadı — "
                f"o seviyeler eski (fiyat kontrol) yöntemiyle takip edilecek") if kacan_emir_sayisi else ""

    tg(
        f"📈 [KANAL KOPYA] {sym} {direction.upper()} AÇILDI\n"
        f"Giriş≈{price:.8f} | SL:{sl:.8f}\n"
        f"TP listesi: {sinyal['tp_liste']}\n"
        f"Notional≈${notional:.2f}{gozlem_str}{ek_uyari}"
    )


def tp_limit_emirlerini_koy(sym, direction, tp_liste, orijinal_qty):
    """
    v16.8: Her TP seviyesi için borsaya gerçek reduceOnly LİMİT emri koyar.
    Döner: [{"id": emir_id_veya_None, "fiyat":..., "miktar":...}, ...] —
    tp_liste ile aynı sırada, aynı uzunlukta.
    """
    emirler = []
    kapama_yon = "sell" if direction == "long" else "buy"
    toplam_tp = len(tp_liste)
    for i, tp_fiyat in enumerate(tp_liste):
        oran = _tp_dilim_orani(i, toplam_tp)
        miktar_ham = orijinal_qty * oran
        try:
            miktar = float(exchange.amount_to_precision(sym, miktar_ham))
            fiyat_hassas = float(exchange.price_to_precision(sym, tp_fiyat)) \
                if hasattr(exchange, "price_to_precision") else tp_fiyat
            if miktar <= 0:
                emirler.append({"id": None, "fiyat": tp_fiyat, "miktar": miktar_ham})
                continue
            emir = exchange.create_limit_order(sym, kapama_yon, miktar, fiyat_hassas,
                                                params={"reduceOnly": True})
            emirler.append({"id": emir.get("id"), "fiyat": tp_fiyat, "miktar": miktar})
        except Exception as e:
            log.warning(f"[TP_EMIR] {sym} TP{i+1} limit emri konulamadı: {e}")
            emirler.append({"id": None, "fiyat": tp_fiyat, "miktar": miktar_ham})
    return emirler


def tp_emirlerini_iptal_et(sym, tp_emirleri, tp_index):
    """
    v16.8: SL/trailing/manuel kapatmadan ÖNCE, henüz vurulmamış TP limit
    emirlerini iptal eder — böylece pozisyon kapandıktan sonra borsada
    "yetim" reduceOnly emirler kalıp kafa karıştırmaz veya hataya yol açmaz.
    """
    for i in range(tp_index, len(tp_emirleri)):
        emir_id = tp_emirleri[i].get("id")
        if emir_id:
            try:
                exchange.cancel_order(emir_id, sym)
            except Exception as e:
                log.warning(f"[TP_IPTAL] {sym} TP{i+1} emri iptal edilemedi (muhtemelen zaten dolmuş/iptal): {e}")


# ════════════════════════════════════════════
# POZİSYON YÖNETİMİ (SL / TP kademeleri — emir doğrulamalı)
# ════════════════════════════════════════════
def _tp_dilim_orani(tp_index, toplam_tp_sayisi):
    """
    v16: TP_DILIM_ORANLARI listesi toplam_tp_sayisi ile TAM eşleşmiyorsa
    (örn. kanal farklı sayıda TP verdiyse) orantılı şekilde yeniden ölçekler.
    Liste 6 eleman için tasarlandı (standart durum); farklı sayıda TP'de
    aynı "şekli" (uçlarda küçük, ortada büyük) orantılı uygular.
    """
    if toplam_tp_sayisi == len(TP_DILIM_ORANLARI):
        return TP_DILIM_ORANLARI[tp_index]
    # farklı sayıda TP varsa: aynı toplam payı (0.80) eşit dağıt
    toplam_pay = sum(TP_DILIM_ORANLARI)
    return toplam_pay / toplam_tp_sayisi


def manage():
    while True:
        try:
            positions = exchange.fetch_positions()
            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue
                sym = p["symbol"]
                entry = safe(p["entryPrice"])
                direction = "long" if p["side"] == "long" else "short"

                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    entry_guvenlik = entry
                    guvenlik_sl_pct = 0.03
                    sl_guvenlik = entry_guvenlik * (1 - guvenlik_sl_pct) if direction == "long" else entry_guvenlik * (1 + guvenlik_sl_pct)
                    with state_lock:
                        trade_state[sym] = {"sl": sl_guvenlik, "tp_liste": [], "tp_index": 0,
                                             "direction": direction, "entry": entry_guvenlik, "kaynak": "kurtarilan_calisma_zamani"}
                    durumu_diske_yaz()
                    tg(f"🚨 UYARI: {sym} için kayıtlı durum yoktu — geçici %3 güvenlik SL'i kondu")
                    continue

                t = exchange.fetch_ticker(sym)
                price = safe(t["last"])
                sl = durum["sl"]

                sl_vuruldu = (price <= sl) if direction == "long" else (price >= sl)
                if sl_vuruldu:
                    kapandi_mi = False
                    kapatma_emri = None
                    # ── v16.8: pozisyonu kapatmadan ÖNCE, henüz vurulmamış TP limit
                    # emirlerini iptal et — yoksa pozisyon kapandıktan sonra borsada
                    # "yetim" reduceOnly emirler kalır. ──
                    tp_emirlerini_iptal_et(sym, durum.get("tp_emirleri", []), durum.get("tp_index", 0))
                    try:
                        kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       qty, params={"reduceOnly": True})
                        time.sleep(1)
                        guncel = exchange.fetch_positions([sym])
                        kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
                    except Exception as e:
                        log.error(f"[STOP] {sym}: {e}")

                    if not kapandi_mi:
                        tg(f"⚠️ {sym} STOP emri doğrulanamadı, tekrar denenecek")
                        continue

                    gercek_fiyat, komisyon = gercek_dolus_bilgisi_al(kapatma_emri or {}, sym, price)
                    gross = (gercek_fiyat - entry) * qty if direction == "long" else (entry - gercek_fiyat) * qty
                    gross -= komisyon
                    with state_lock:
                        onceki_gerceklesen = trade_state[sym].get("gerceklesen_pnl", 0)
                        acilis_komisyon = trade_state[sym].get("acilis_komisyon", 0)
                    # v16.21: açılış komisyonu SADECE burada, işlemin son kapanışında
                    # bir kere düşülüyor (TP dilimlerinde değil) — yoksa birden fazla
                    # dilimde tekrar tekrar düşülüp toplam PnL yanlış olurdu.
                    toplam_pnl_stop = gross + onceki_gerceklesen - acilis_komisyon
                    gunluk_pnl_ekle(gross - acilis_komisyon)
                    # ── v16.8: STOP'un GERÇEK ZARAR mı, TP1 TAMPON BÖLGESİNDE mi (küçük
                    # kontrollü risk), yoksa KADEMELİ SL YÜKSELTMESİ (kâr kilitleme)
                    # sonucu mu olduğunu ayırt et. "Riskli taraf" fark yüzdesi: SL,
                    # girişin ne kadar aleyhte tarafında (pozitifse aleyhte). ──
                    fark_pct = (entry - sl) / entry if direction == "long" else (sl - entry) / entry
                    tampon_sinir = TP1_BREAKEVEN_TAMPON_PCT + 0.0015  # tampon payı + küçük tolerans
                    if fark_pct <= 0:
                        kategori = "kar_kilitli"
                    elif fark_pct <= tampon_sinir:
                        kategori = "tampon"
                    else:
                        kategori = "zarar"

                    if kategori == "tampon" and onceki_gerceklesen > 0:
                        tg(f"🟡 STOP (TP1 tampon bölgesinde) {sym} | bu dilim≈{gross:+.2f}$ | "
                           f"TOPLAM işlem PnL≈{toplam_pnl_stop:+.2f}$ (önceki TP'lerden kilitlenen kâr "
                           f"büyük ölçüde korundu, sadece küçük kontrollü risk payı kullanıldı)")
                    elif kategori == "kar_kilitli":
                        tg(f"🟢 STOP (kâr kilitleme seviyesinde) {sym} | bu dilim≈{gross:+.2f}$ | "
                           f"TOPLAM işlem PnL≈{toplam_pnl_stop:+.2f}$ (kademeli SL yükseltmesi sayesinde "
                           f"ek kâr korunmuş oldu)")
                    else:
                        tg(f"❌ STOP {sym} | TOPLAM işlem PnL≈{toplam_pnl_stop:+.2f}$")
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    trade_log_kaydet({
                        "symbol": sym, "direction": direction, "entry": entry,
                        "exit": gercek_fiyat, "pnl": toplam_pnl_stop, "sonuc": "STOP",
                        "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    })
                    continue

                tp_liste = durum.get("tp_liste", [])
                tp_index = durum.get("tp_index", 0)
                tp_emirleri = durum.get("tp_emirleri", [])

                # ── TP KADEMELERI (v16.8: önce GERÇEK limit emrinin durumuna bakılır —
                # borsanın kendi eşleştirme motoru fiyata değen her anı yakalar, bizim
                # 5 saniyelik döngümüzün o an bakıp bakmadığından bağımsız. Emir yoksa
                # veya kontrol edilemezse, eski fiyat-karşılaştırma yöntemine (fallback)
                # otomatik geri dönülür — hiçbir şey kırılmaz. ──
                if tp_index < len(tp_liste):
                    kayitli_emir = tp_emirleri[tp_index] if tp_index < len(tp_emirleri) else {}
                    emir_id = kayitli_emir.get("id")

                    tp_vuruldu = False
                    emirle_dolmus = False
                    gercek_fiyat = price
                    komisyon = 0.0
                    kapatilacak = kayitli_emir.get("miktar")
                    emir_dogrulanabildi = False

                    if emir_id:
                        try:
                            emir_durum = exchange.fetch_order(emir_id, sym)
                            emir_dogrulanabildi = True
                            durum_str = (emir_durum.get("status") or "").lower()
                            if durum_str in ("closed", "filled"):
                                tp_vuruldu = True
                                emirle_dolmus = True
                                gercek_fiyat = safe(emir_durum.get("average")) or safe(emir_durum.get("price")) or price
                                doldurulan = safe(emir_durum.get("filled"))
                                if doldurulan > 0:
                                    kapatilacak = doldurulan
                                fee = emir_durum.get("fee")
                                if fee:
                                    komisyon = safe(fee.get("cost"))
                        except Exception as e:
                            log.warning(f"[TP_KONTROL] {sym} TP{tp_index+1} emri kontrol edilemedi, "
                                        f"fiyat karşılaştırmasına dönülüyor: {e}")

                    # ── v16.8 KRİTİK DÜZELTME: ÇİFTE KAPANMA ÖNLEME ──
                    # Eskiden: emir_id varsa ama "dolmuş" görünmüyorsa (durum='open'),
                    # kod yine de fiyat karşılaştırmasına DÜŞÜYORDU — fiyat hedefe
                    # ulaşmış ama emrin durumu henüz güncellenmemişse, biz KENDİ
                    # market emrimizi gönderiyorduk, ama borsadaki GERÇEK limit emri
                    # hâlâ AÇIK duruyordu (iptal edilmemiş) — o da sonradan dolabilirdi.
                    # Sonuç: AYNI DİLİM İKİ KEZ kapanabiliyordu (TP1'den hemen sonra
                    # pozisyonun beklenenden çok kapanması/hızla tükenmesi bunun
                    # belirtisi olabilir). Şimdi: emrin durumu BAŞARIYLA doğrulandıysa
                    # (açık olduğu kesin biliniyorsa) fiyat karşılaştırmasına HİÇ
                    # düşülmüyor — borsanın kendi emrine güveniliyor, bir sonraki
                    # kontrolde tekrar bakılıyor. Fallback SADECE emir hiç
                    # konulamadıysa (emir_id yok) ya da durumu hiç ÖĞRENİLEMEDİYSE
                    # (API hatası) devreye giriyor. ──
                    if not tp_vuruldu and not (emir_id and emir_dogrulanabildi):
                        hedef = tp_liste[tp_index]
                        tp_vuruldu = (price >= hedef) if direction == "long" else (price <= hedef)

                    if tp_vuruldu:
                        son_tp = (tp_index == len(tp_liste) - 1)
                        # ── v16: eşit bölme yerine ağırlıklı oran kullanılıyor.
                        # Oran, İLK ORİJİNAL miktara göre; kapatılacak miktar o
                        # yüzden "kalan qty"den değil sabit orandan hesaplanıyor. ──
                        orijinal_qty = durum.get("orijinal_qty", qty)
                        if "orijinal_qty" not in durum:
                            with state_lock:
                                trade_state[sym]["orijinal_qty"] = qty
                            orijinal_qty = qty
                        if kapatilacak is None:
                            oran = _tp_dilim_orani(tp_index, len(tp_liste))
                            kapatilacak = min(orijinal_qty * oran, qty)  # elde olandan fazlasını isteme

                        basarili = True
                        if not emirle_dolmus:
                            # ── Gerçek limit emri yoktu / tespit edilemedi — eskisi gibi
                            # bizim kendi MARKET emrimizle kapatmamız gerekiyor. ──
                            basarili = False
                            kapatma_emri = None
                            try:
                                kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                               kapatilacak, params={"reduceOnly": True})
                                time.sleep(1)
                                basarili = True
                            except Exception as e:
                                log.error(f"[TP{tp_index+1}] {sym}: {e}")
                            if basarili:
                                gercek_fiyat, komisyon = gercek_dolus_bilgisi_al(kapatma_emri or {}, sym, price)

                        if basarili:
                            gross_dilim = (gercek_fiyat - entry) * kapatilacak if direction == "long" \
                                          else (entry - gercek_fiyat) * kapatilacak
                            gross_dilim -= komisyon
                            gunluk_pnl_ekle(gross_dilim)

                            # ── v16.8: KADEMELİ SL YÜKSELTME (ratchet) ──
                            # Eskiden SL sadece TP1'de girişe (breakeven) çekiliyordu, sonraki
                            # TP'lerde sabit kalıyordu. Şimdi HER TP'de SL bir önceki TP
                            # seviyesine çekiliyor — TP2 vurulunca SL, TP1 fiyatına; TP3
                            # vurulunca SL, TP2 fiyatına... Böylece fiyat geri dönerse bile
                            # önceki TP'lerin kârı da korunmuş oluyor, sadece "başa baş" değil.
                            # SL asla GERİYE (daha riskli yöne) alınmaz — sadece iyileşirse uygulanır.
                            # v16.8: TP1 sonrası artık TAM girişe değil, küçük bir tampon payı
                            # kadar altına (long) / üstüne (short) çekiliyor — anlık gürültüyle
                            # hemen kapanmasın diye.
                            if tp_index == 0:
                                yeni_sl = entry * (1 - TP1_BREAKEVEN_TAMPON_PCT) if direction == "long" \
                                          else entry * (1 + TP1_BREAKEVEN_TAMPON_PCT)
                            else:
                                yeni_sl = tp_liste[tp_index - 1]
                            mevcut_sl = trade_state[sym]["sl"]
                            sl_iyilesti = (direction == "long" and yeni_sl > mevcut_sl) or \
                                          (direction == "short" and yeni_sl < mevcut_sl)

                            with state_lock:
                                trade_state[sym]["tp_index"] = tp_index + 1
                                trade_state[sym]["gerceklesen_pnl"] = trade_state[sym].get("gerceklesen_pnl", 0) + gross_dilim
                                if sl_iyilesti:
                                    trade_state[sym]["sl"] = yeni_sl
                                if son_tp:
                                    trade_state[sym]["trailing_aktif"] = True
                                    trade_state[sym]["trailing_zirve"] = price
                                    trade_state[sym]["trailing_son_bildirim_zirve"] = price
                                kilitlenen_kar = trade_state[sym]["gerceklesen_pnl"]
                            durumu_diske_yaz()

                            mesaj = (f"💰 TP{tp_index+1} {sym} vuruldu | dilim PnL≈{gross_dilim:+.2f}$ | "
                                     f"o ana kadar kilitlenen toplam≈{kilitlenen_kar:+.2f}$")
                            if son_tp:
                                mesaj += " | 📈 Kalan büyük dilim TRAILING moduna geçti"
                            tg(mesaj)

                            # ── SL güncelleme bildirimi (breakeven+tampon ilk TP'de, sonrakilerde kâr kilitleme) ──
                            if sl_iyilesti:
                                kalan_qty_sonrasi = max(qty - kapatilacak, 0)
                                if tp_index == 0:
                                    maks_ek_risk = abs(entry - yeni_sl) * kalan_qty_sonrasi
                                    tg(f"🔒 {sym} STOP artık giriş civarında (%{TP1_BREAKEVEN_TAMPON_PCT*100:.2f} "
                                       f"tampon payıyla, {yeni_sl:.8f}) — şu ana kadar kilitlenen kâr≈"
                                       f"{kilitlenen_kar:+.2f}$. Küçük bir geri çekilmede işlem hemen "
                                       f"kapanmaz, TP2'ye doğru devam edebilir; en kötü ihtimalle bu "
                                       f"STOP'ta ek≈-{maks_ek_risk:.2f}$ kontrollü risk oluşur")
                                else:
                                    ek_kar = (yeni_sl - entry) * kalan_qty_sonrasi if direction == "long" \
                                              else (entry - yeni_sl) * kalan_qty_sonrasi
                                    tg(f"🔐 {sym} STOP TP{tp_index} seviyesine ({yeni_sl:.8f}) yükseltildi — "
                                       f"kalan pozisyon artık en kötü ihtimalle bu STOP'ta kapanırsa "
                                       f"ek≈{ek_kar:+.2f}$ daha kilitlenmiş olacak (zaten kesinleşen "
                                       f"{kilitlenen_kar:+.2f}$'ın üstüne)")

                # ── TRAILING STOP (TP3 sonrası kalan büyük dilim için — v16.10) ──
                elif durum.get("trailing_aktif"):
                    zirve = durum.get("trailing_zirve", entry)
                    if direction == "long":
                        yeni_zirve = max(zirve, price)
                        geri_cekilme_tetiklendi = price <= yeni_zirve * (1 - TRAILING_GERI_CEKILME_PCT)
                    else:
                        yeni_zirve = min(zirve, price)
                        geri_cekilme_tetiklendi = price >= yeni_zirve * (1 + TRAILING_GERI_CEKILME_PCT)

                    if yeni_zirve != zirve:
                        with state_lock:
                            trade_state[sym]["trailing_zirve"] = yeni_zirve
                        durumu_diske_yaz()

                        # ── v16.10 YENİ: Stop her belirgin şekilde yukarı çekildiğinde
                        # (zirve son bildirilen seviyeden en az TRAILING_BILDIRIM_ESIK_PCT
                        # kadar ilerlediyse) bildirim gönder — her 5sn'lik ufak kıpırdanmada
                        # değil, sadece anlamlı bir ilerlemede (spam olmasın diye). ──
                        son_bildirim_zirve = durum.get("trailing_son_bildirim_zirve", entry)
                        if direction == "long":
                            ilerleme_pct = (yeni_zirve - son_bildirim_zirve) / son_bildirim_zirve if son_bildirim_zirve else 0
                            efektif_stop = yeni_zirve * (1 - TRAILING_GERI_CEKILME_PCT)
                        else:
                            ilerleme_pct = (son_bildirim_zirve - yeni_zirve) / son_bildirim_zirve if son_bildirim_zirve else 0
                            efektif_stop = yeni_zirve * (1 + TRAILING_GERI_CEKILME_PCT)

                        if ilerleme_pct >= TRAILING_BILDIRIM_ESIK_PCT:
                            with state_lock:
                                trade_state[sym]["trailing_son_bildirim_zirve"] = yeni_zirve
                            durumu_diske_yaz()
                            tg(f"📈 {sym} TRAILING STOP yükseldi — yeni zirve:{yeni_zirve:.8f}, "
                               f"efektif stop≈{efektif_stop:.8f} (%{TRAILING_GERI_CEKILME_PCT*100:.1f} pay ile)")

                    if geri_cekilme_tetiklendi:
                        kapandi_mi = False
                        kapatma_emri = None
                        tp_emirlerini_iptal_et(sym, durum.get("tp_emirleri", []), durum.get("tp_index", 0))
                        try:
                            kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                           qty, params={"reduceOnly": True})
                            time.sleep(1)
                            guncel = exchange.fetch_positions([sym])
                            kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
                        except Exception as e:
                            log.error(f"[TRAILING] {sym}: {e}")

                        if not kapandi_mi:
                            tg(f"⚠️ {sym} trailing kapanışı doğrulanamadı, tekrar denenecek")
                            continue

                        gercek_fiyat, komisyon = gercek_dolus_bilgisi_al(kapatma_emri or {}, sym, price)
                        gross_dilim = (gercek_fiyat - entry) * qty if direction == "long" else (entry - gercek_fiyat) * qty
                        gross_dilim -= komisyon
                        gunluk_pnl_ekle(gross_dilim)

                        with state_lock:
                            toplam_pnl = trade_state[sym].get("gerceklesen_pnl", 0) + gross_dilim
                            trade_state.pop(sym, None)
                        durumu_diske_yaz()
                        tg(f"📉 TRAILING kapandı {sym} | son dilim PnL≈{gross_dilim:+.2f}$ | "
                           f"TOPLAM işlem PnL≈{toplam_pnl:+.2f}$")
                        trade_log_kaydet({
                            "symbol": sym, "direction": direction, "entry": entry,
                            "exit": gercek_fiyat, "pnl": toplam_pnl, "sonuc": "TRAILING_KAPANDI",
                            "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        })

            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


# ════════════════════════════════════════════
# TELEGRAM KANAL DİNLEME (Telethon)
# ════════════════════════════════════════════
from telethon.sessions import StringSession
telethon_client = TelegramClient(StringSession(TG_STRING_SESSION), TG_API_ID, TG_API_HASH)


SADECE_MANUEL = os.getenv("SADECE_MANUEL", "true").lower() == "true"  # v16.20: kullanıcı
# talebiyle ("sadece manuel kalsın") — TRUE iken kanal(lar)dan gelen hiçbir
# sinyal işleme alınmaz, pozisyonlar SADECE 'edge long'/'edge short' manuel
# komutlarıyla açılır. Telethon event filtresine dokunulmadı (chats=[] gibi
# belirsiz/riskli bir davranışa yol açmasın diye) — bunun yerine mesaj
# geldiğinde en başta bu bayrağa bakılıp direkt çıkılıyor.


@telethon_client.on(events.NewMessage(chats=KANAL_LISTESI))
async def yeni_mesaj_geldi(event):
    if SADECE_MANUEL:
        log.info("[KANAL] SADECE_MANUEL aktif — kanal mesajı görmezden gelindi")
        return
    metin = event.raw_text
    kanal_kaynagi = getattr(event.chat, "username", None) or "bilinmeyen"
    log.info(f"[KANAL:{kanal_kaynagi}] Yeni mesaj alındı: {metin[:80]}...")
    sinyal = sinyal_ayristir(metin)
    if not sinyal:
        log.info("[KANAL] Mesaj sinyal olarak ayrıştırılamadı, atlandı")
        return
    tg(f"📡 Kanal sinyali algılandı (@{kanal_kaynagi}): {sinyal['symbol']} {sinyal['direction'].upper()}")
    sinyali_isle(sinyal)


# ════════════════════════════════════════════
# WEB PANEL (tarayıcıdan performans görüntüleme)
# ════════════════════════════════════════════
def panel_html_olustur():
    with log_lock:
        gecmis = list(trade_log)

    toplam = len(gecmis)
    if toplam == 0:
        icerik_ozet = "<p style='color:#888'>Henüz kapanan işlem yok.</p>"
        grafik_svg = ""
        liste_html = ""
    else:
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        kaybeden = [t for t in gecmis if t["pnl"] <= 0]
        net_toplam = sum(t["pnl"] for t in gecmis)
        kazanma_orani = len(kazanan) / toplam * 100
        ort_kazanan = sum(t["pnl"] for t in kazanan) / len(kazanan) if kazanan else 0
        ort_kaybeden = sum(t["pnl"] for t in kaybeden) / len(kaybeden) if kaybeden else 0
        basabas_oran = abs(ort_kaybeden) / (abs(ort_kaybeden) + ort_kazanan) * 100 if (ort_kazanan + abs(ort_kaybeden)) > 0 else 0

        renk_net = "#00e08a" if net_toplam >= 0 else "#ff4d6d"

        icerik_ozet = f"""
        <div class="grid">
          <div class="kart"><div class="etiket">NET TOPLAM</div>
            <div class="deger" style="color:{renk_net}">{net_toplam:+.2f}$</div></div>
          <div class="kart"><div class="etiket">KAZANMA ORANI</div>
            <div class="deger">%{kazanma_orani:.1f}</div></div>
          <div class="kart"><div class="etiket">KAZANAN ({len(kazanan)})</div>
            <div class="deger" style="color:#00e08a">ort {ort_kazanan:+.2f}$</div></div>
          <div class="kart"><div class="etiket">KAYBEDEN ({len(kaybeden)})</div>
            <div class="deger" style="color:#ff4d6d">ort {ort_kaybeden:+.2f}$</div></div>
        </div>
        <div class="kart" style="margin-top:12px">
          <span class="etiket">Başa baş için gereken kazanma oranı</span>
          <span class="deger" style="float:right;color:#ff4d6d">%{basabas_oran:.1f}</span>
        </div>
        """

        # ── Basit SVG kümülatif PnL çizgisi (dış kütüphane yok) ──
        kumulatif = []
        toplam_su_an = 0
        for t in gecmis:
            toplam_su_an += t["pnl"]
            kumulatif.append(toplam_su_an)
        genislik, yukseklik = 700, 200
        if len(kumulatif) > 1:
            min_v, max_v = min(kumulatif), max(kumulatif)
            aralik = (max_v - min_v) or 1
            noktalar = []
            for i, v in enumerate(kumulatif):
                x = i / (len(kumulatif) - 1) * genislik
                y = yukseklik - ((v - min_v) / aralik * yukseklik)
                noktalar.append(f"{x:.1f},{y:.1f}")
            svg_puan = " ".join(noktalar)
            grafik_svg = f"""
            <div class="kart" style="margin-top:12px">
              <div class="etiket">KÜMÜLATİF NET PNL</div>
              <svg viewBox="0 0 {genislik} {yukseklik}" style="width:100%;height:180px">
                <polyline fill="none" stroke="#4da3ff" stroke-width="2" points="{svg_puan}" />
              </svg>
            </div>
            """
        else:
            grafik_svg = ""

        satirlar = []
        for t in reversed(gecmis[-100:]):
            renk = "#00e08a" if t["pnl"] > 0 else "#ff4d6d"
            satirlar.append(f"""
            <div class="islem-satir">
              <div><b>{t['symbol'].split('/')[0]}</b>
                <span class="rozet">{t['direction'].upper()}</span>
                <span class="rozet" style="background:#333">{t.get('sonuc','?')}</span></div>
              <div style="color:{renk}">{t['pnl']:+.2f}$</div>
            </div>
            <div style="color:#888;font-size:12px">{t.get('zaman','')}</div>
            """)
        liste_html = "".join(satirlar)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sinyal Kopya Botu — Panel</title>
<style>
body {{ background:#0d0d12; color:#eee; font-family:-apple-system,sans-serif; padding:16px; margin:0; }}
.baslik {{ color:#888; font-size:13px; letter-spacing:2px; text-transform:uppercase; }}
h1 {{ margin:4px 0 16px 0; font-size:28px; }}
.rozet-mod {{ background:#3a2a00; color:#ffb300; padding:8px 14px; border-radius:8px; display:inline-block; margin-bottom:16px; font-weight:600; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.kart {{ background:#16161f; border-radius:12px; padding:16px; }}
.etiket {{ color:#888; font-size:12px; letter-spacing:1px; text-transform:uppercase; }}
.deger {{ font-size:28px; font-weight:700; margin-top:6px; }}
.islem-satir {{ display:flex; justify-content:space-between; padding:10px 0 2px 0; border-top:1px solid #222; font-size:15px; }}
.rozet {{ background:#222; padding:2px 8px; border-radius:6px; font-size:11px; margin-left:6px; }}
</style></head>
<body>
  <div class="baslik">SİNYAL KOPYA BOTU</div>
  <h1>Performans Paneli</h1>
  <div class="rozet-mod">🔴 GERÇEK PARA — @{KANAL_KULLANICI_ADI} kanalından kopyalanıyor</div>
  <p style="color:#888">{len(trade_log)} kapanan işlem · sayfa her yenilendiğinde güncellenir</p>
  {icerik_ozet}
  {grafik_svg}
  <h3 style="margin-top:24px;color:#888">İŞLEM GEÇMİŞİ (yeniden eskiye, son 100)</h3>
  {liste_html}
</body></html>"""


def panel_sunucu_baslat():
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/panel", "/panel/"):
                icerik = panel_html_olustur().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(icerik)
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

        def log_message(self, *args):
            pass  # http.server'in kendi loglarini bastiriyoruz, gurultu olmasin

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


def telethon_baslat():
    telethon_client.start()
    log.info("[TELETHON] Kanal dinleme başladı")
    telethon_client.run_until_disconnected()


# ════════════════════════════════════════════
# BAŞLANGIÇ
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("TELEGRAM SİNYAL KOPYALAMA BOTU (v16.27) BAŞLIYOR...")
    durumu_diskten_yukle()
    trade_log_yukle()
    durumu_telegramdan_yukle()  # v16.8: disk kaybolmuş olsa bile Telegram yedeğinden geri yükle
    acilista_pozisyonlari_dogrula()
    acik_pozisyonlara_kademeli_sl_uygula()
    acik_pozisyonlarin_dar_sl_duzelt()

    threading.Thread(target=manage, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    threading.Thread(target=panel_sunucu_baslat, daemon=True).start()
    threading.Thread(target=teyit_bekleme_loop, daemon=True).start()
    threading.Thread(target=oz_tarama_loop, daemon=True).start()  # v16.11: bot kendi coin de bulur

    tg(
        "🚀 TELEGRAM SİNYAL KOPYALAMA BOTU\n"
        "🔖 VERSİYON: v16.27 (SADECE MANUEL + TEYITLI + 4 TP + TP1 TABAN + 1H-VOLATILITE SL + ACIK-POZ DUZELTME + 3 sabit TP - VUR KAÇ %35/%35/%30 tam kapanış + hizli ac/kapat + teyit bekleme + "
        "kademeli SL yukseltme + 3-bilesenli trend teyidi + scalp oz tarama[VARSAYILAN KAPALI] + "
        "coklu kanal + manuel direkt acilir)\n\n"
        f"💰 Sermaye: ${TOPLAM_SERMAYE} | Kaldıraç: {LEV}x\n"
        f"🎯 Marj/işlem: ${MARGIN_SABIT} (sabit) × {LEV}x = ${MARGIN_SABIT*LEV} notional\n"
        f"📡 Dinlenen kanal(lar): {', '.join('@'+k for k in KANAL_LISTESI)} "
        f"{'⛔ (SADECE_MANUEL aktif — kanal sinyalleri İŞLENMİYOR)' if SADECE_MANUEL else ''}\n"
        f"🤖 Öz tarama: {'AKTİF' if OZ_TARAMA_AKTIF else 'KAPALI'} "
        f"(her {OZ_TARAMA_ARALIK_DK} dk, en likit {OZ_TARAMA_WATCHLIST_BOYUTU} coin, "
        f"aynı MAX_POS={MAX_POS} havuzunu paylaşır)\n"
        f"⛔ Günlük zarar limiti: ${MAX_GUNLUK_ZARAR}\n"
        f"⏳ Teyit bekleme süresi: {TEYIT_BEKLEME_DAKIKA} dk\n\n"
        "⚠️ Bu kanalın geçmiş performansı doğrulanmadı.\n"
        "💬 Hızlı komutlar: 'edge long', 'edge short', 'edge kapat' (ac kelimesi gerekmez)"
    )

    telethon_baslat()
