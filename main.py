#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
SCALP BOT v5.22 — 08 Ağustos 2026 (SADE MOD - kullanıcı kararı)
5m çoklu zaman dilimi, SADECE LONG, o an fiyatı %3+ yükselen coinleri
DİNAMİK olarak bulur (sabit coin listesi YOK — her taramada borsanın
TAMAMI taranır, RWA/tokenize hisse ve durgun majörler hariç).
RSI/ADX/hacim-spike/üst-fitil/teyit-bekleme filtreleri YOK - sadece
fiyat trendi. Sinyal bulunur bulunmaz HEMEN girilir. Çıkış SL + geniş
iz süren TP ile yönetilir (0.50R'de aktifleşir, büyük hareketlere
nefes payı bırakmak için genişletildi).
════════════════════════════════════════════════════════
⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: HİÇBİR TP/SL AYARI KÂRI GARANTİ ETMEZ.
Aşağıdaki ayarlar geçmiş veride (60 likit coin, 15 gün, 5m mumlar,
gerçek Bitget verisi, komisyon dahil, bar-by-bar simülasyon) pozitif
edge gösterdi, ama örneklem küçük (131 işlem) ve gelecekte aynı
performansı vermesi garanti değildir:
  - SL = 2.0×ATR(5m,14)
  - TP kademeli: %30 pozisyon @1R, %30 @2R, %40 @3R
  - İlk TP (1R) vurunca kalan pozisyonun SL'i BAŞABAŞA (girişe) çekilir
    - bu "garanti kâr" değildir, ama o andan sonra en kötü ihtimalle
    sıfır zararla kapanmayı sağlar (borsa kayması/gap riski hariç)
  - Backtest: 131 işlem, %58.0 kazanma, +25.78R toplam, +0.197R/işlem
    ortalama, İKİ ZAMAN YARISINDA DA pozitif (11.1R / 14.7R)
  - Karşılaştırma: tek TP (RR=1.0) aynı veri setinde sadece +0.063R/işlem
    verdi - kademeli TP burada AÇIKÇA daha iyi (1h'deki ana pullback
    botunun aksine - orada kademeli TP kaybediyordu, stratejiye göre
    değişiyor, kör kör kopyalanmadı)

DİNAMİK COİN TARAMA MANTIĞI:
Sabit bir coin listesi YOK. Her tarama turunda:
  1) exchange.fetch_tickers() ile TÜM USDT-M perpetual coinlerin 24s
     hacim/değişim bilgisi TEK istekte alınır (hızlı, ~700+ coin)
  2) RWA (isRwa=YES, tokenize hisse/emtia) ve durgun majörler
     (BTC/ETH/XRP/ADA/DOGE/BNB/TRX/LINK/LTC/BCH) elenir
  3) Kalanlardan hacim/hareket bazlı ön eleme ile en "canlı" ~80 aday
     seçilir (700+ coinin hepsinin 5m mumuna bakmak çok yavaş/rate-limit
     riskli olurdu)
  4) Sadece bu adayların 5m mumlarına bakılıp GERÇEK pump sinyali
     (hacim spike + kısa vadeli fiyat sıçraması) doğrulanır

COOLDOWN: Bir coin kapandıktan sonra (kâr/zarar fark etmeksizin) 1 SAAT
boyunca tekrar açılmaz - kullanıcı talebiyle eklendi, "kârı aldı hemen
tekrar açma" sorununu önlemek için.

════════════════════════════════════════════════════════
v4.18 DEĞİŞİKLİK GÜNLÜĞÜ — 04 Ağustos 2026 (bugünkü canlı işlem
incelemesi sonrası, kullanıcı talebiyle):

1) 🐛 KRİTİK PnL BUG DÜZELTMESİ: gerçek dolum fiyatı (gercek_giris)
   hesaplanıp sl/r_risk buna göre düzeltiliyordu, ama trade_state'e
   yazılan "entry" alanı YANLIŞLIKLA eski (sinyal anındaki tahmini)
   fiyatta kalıyordu. Bu, iz süren kâr al hesaplamasını VE borsanın
   kendi SL'i tetiklenip pozisyon manage_loop'ta "kayboldu" şeklinde
   tespit edildiğinde günlük/haftalık PnL sayaçlarını (ve dolayısıyla
   günlük/haftalık zarar limiti güvenlik mekanizmasını) yanlış
   besliyordu. Düzeltme: update() çağrısına "entry" eklendi.

2) 🎯 SPIKE (ani patlama) SİNYALİNE RSI AŞIRI-ALIM FİLTRESİ EKLENDİ:
   CYS örneği (RSI 97.66'da +58% tek mumda, saniyeler içinde -%52.7
   ile SL'e çarptı) gösterdi ki bu filtre sadece "sürdürülebilir
   tırmanış" sinyaline vardı, "ani patlama" sinyaline hiç yoktu -
   oysa CYS tam olarak ani patlama paterni. Artık spike sinyalinde de
   RSI(14) >= SPIKE_RSI_TAVAN ise sinyal reddediliyor.

3) 🎯 SUSTAINED (sürdürülebilir tırmanış) SİNYALİNE DE TEYİT BEKLEME
   EKLENDİ: Eskiden sadece spike sinyali 3 dakika "tutuyor mu" diye
   bekletiliyordu, sustained HEMEN açılıyordu. CYS/AIO gibi örnekler
   sustained sinyalinin de bazen tam tepede tetiklendiğini gösterdi.
   Artık her iki LONG sinyal türü de aynı teyit kuyruğundan geçiyor -
   fiyat CONFIRM_BEKLEME_SN boyunca %CONFIRM_MAX_RETRACE_PCT'ten fazla
   geri çekilmezse açılıyor, çekilirse iptal ediliyor.

4) 📉 MAX_SL_PCT %6'dan %3'E DÜŞÜRÜLDÜ (kaldıraç 10x sabit kalıyor -
   kullanıcı talebi): Bugünkü kayıplar (BEAT -57.7%, HFT -71.0%,
   HOME -62.4%, AIO -54.6%, CYS -52.7% ROI) hep MAX_SL_PCT tavanına
   (eski %6) çarpmaktan kaynaklanıyordu - 10x kaldıraçta %6 fiyat
   hareketi = %60 ROI kaybı. Yeni tavan (%3) ile aynı senaryoda ROI
   kaybı ~%30'a iner - hâlâ acı verici ama önceki felaket boyutunun
   yarısı. ⚠️ Trade-off: SL artık daha dar, bu da normal volatilitede
   whipsaw (erken/gereksiz SL) riskini artırabilir - izlenmesi gerekir.

5) ⚡ TARAMA KAPSAMI GENİŞLETİLDİ + PARALEL HALE GETİRİLDİ: kullanıcı
   gözlemi - "Bitget'te sürekli hareketli bir sürü coin var ama bot
   bazen kaçırıyor". Sebep: aday havuzu sıralı (seri) taranıyordu,
   her coin için 5m+15m mum çekmek ~0.3-0.5sn sürüyor, 40 adaylık
   havuzun TAMAMI taranmadan bir sonraki tur başlıyordu (60sn aralık).
   Artık: (a) ADAY_HAVUZU_BUYUKLUGU 40'tan 60'a çıkarıldı, (b) sinyal
   kontrolleri ThreadPoolExecutor ile PARALEL çalıştırılıyor (8 workers)
   - aynı sürede çok daha fazla coin kontrol ediliyor, hızlı hareket
   eden coinlerin kaçırılma ihtimali azalıyor.

6) 🩹 Panel metin düzeltmeleri: /panel Ayarlar artık gerçek trailing TP
   mantığını (sabit $ hedef değil) doğru açıklıyor. /panel Analiz artık
   "düşüş devamı" (short) türünü de sinyal-tipi dökümünde gösteriyor.
════════════════════════════════════════════════════════
"""

import os
import time
import json
import logging
import threading
import ccxt
import telebot
import pandas as pd
import numpy as np
import websocket
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                     stream=sys.stdout, force=True)
log = logging.getLogger("SCALP_BOT")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni eksik.")
if not CHAT_ID:
    raise RuntimeError("MY_CHAT_ID ortam değişkeni eksik - yetki kontrolü için ZORUNLU.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def yetkili_mi(msg_or_call):
    try:
        chat_id = msg_or_call.message.chat.id if hasattr(msg_or_call, "message") else msg_or_call.chat.id
    except Exception:
        return False
    if chat_id != CHAT_ID:
        log.warning(f"[YETKISIZ ERISIM] chat_id={chat_id}")
        return False
    return True


# ── DURGUN/SLUGGISH MAJÖRLER — dinamik taramada bilerek elenir ──
SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

# ── SİNYAL PARAMETRELERİ (backtest doğrulamalı, bkz. üstteki not) ──
VOL_SPIKE_MULT = 5.0        # 5m hacim, 20-bar ortalamasının kaç katı olmalı
RET_WINDOW_BARS = 3         # kaç 5m bar'lık getiriye bakılıyor (3x5dk=15dk)
RET_THRESHOLD = 0.015       # v5.2 KULLANICI KARARI (06.08.2026): %3->%1.5.
# Gerekçe: kullanıcı girişlerin dibe daha yakın olmasını istedi. Gerçek
# veriyle (30 coin/5gün) test edildi: %1.5 eşik, %3'e göre HEM daha çok
# işlem (605 vs 261) HEM daha yüksek kazanma oranı (%42.1 vs %39.5) HEM
# daha yüksek toplam getiri (+43.27R vs +26.58R) verdi - "daha fazla
# yalancı sinyal gelir" beklentisi bu veri setinde doğrulanmadı.
ADX_ESIK_15M = 15
COOLDOWN_SAAT = float(os.getenv("COOLDOWN_SAAT", "0.25"))
# v5.5 KULLANICI DENEYİ (06.08.2026): 4 saat -> 15 dakika (0.25 saat).
# ⚠️ DÜRÜSTLÜK NOTU: backtest (30 coin/5 gün) aslında 4 saatin daha iyi
# sonuç verdiğini gösterdi (+30.01R, %47.5 kazanma) - 15 dakika daha düşük
# çıktı (+22.03R, %44.9 kazanma). Kullanıcı buna rağmen canlıda denemek
# istedi - bu bilinçli bir deney, veri kanıtlı bir iyileştirme DEĞİL.
# Birkaç saat sonra gerçek sonuçlarla 4 saate dönüp dönmeyeceğimize karar
# verilecek.
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "12"))
# v5.8 KULLANICI KARARI (06.08.2026): 3sa -> 12sa. Gerekçe: "en iyi kârı
# kaçırmamak, kasayı büyütmek" hedefiyle test edildi (35 coin/6 gün) - 3
# saatlik zorla kapatma iyi giden trendleri erken kesiyordu. 6/12/24sa/
# sınırsız hepsi 3sa'den belirgin daha iyi çıktı (+17-18.5R vs +13.18R) ve
# kendi aralarında tutarlıydı (bugünkü diğer testler gibi çelişmedi) - 12sa
# en iyisiydi ve zorla kapanan işlem sayısı da (5) makul seviyedeydi.

# v1.1: SÜRDÜRÜLEBİLİR TIRMANIŞ sinyali
SUSTAINED_RET_WINDOW_BARS = 6   # 15m x 6 = 1.5 saat
SUSTAINED_RET_THRESHOLD = 0.04  # %4 hareket
SUSTAINED_VOL_RATIO_THRESH = 1.2
SUSTAINED_ADX_ESIK = 15
SUSTAINED_ZIRVE_MESAFE_MIN = float(os.getenv("SUSTAINED_ZIRVE_MESAFE_MIN", "0.03"))
SUSTAINED_RSI_TAVAN = 75  # v4.17: sürdürülebilir tırmanış RSI aşırı-alım filtresi

# v4.18 YENİ: spike (ani patlama) sinyaline de RSI aşırı-alım filtresi.
# CYS örneği: RSI 97.66'da tek mumda +58%, saniyeler içinde SL'e çarptı.
# Spike doğası gereği sustained'den daha ani olduğu için eşik biraz daha
# sıkı tutuldu (70) - "az önce patladı, RSI zaten tavanda" durumunu eler.
SPIKE_RSI_TAVAN = float(os.getenv("SPIKE_RSI_TAVAN", "75"))
# v4.22 YENİ: spike sinyaline "üst fitil" (tepeden ret) filtresi. Sinyal
# mumunun İÇİNDE fiyat tepeye çıkıp geri düşmüşse (uzun üst fitil), bu o an
# tepeden satış baskısı geldiğinin işareti - "en tepeden girme" riskini
# doğrudan azaltır. Fitil, mumun toplam aralığının bu orandan fazlasıysa
# sinyal reddedilir.
SPIKE_UST_FITIL_MAX = float(os.getenv("SPIKE_UST_FITIL_MAX", "0.50"))

# v4.5: dusus-devam sinyali icin sabitler
DUSUS_DEVAM_DIP_MESAFE_MIN = 0.03
DUSUS_DEVAM_MUM_ESIK = 0.01
DUSUS_DEVAM_HACIM_ESIK = 1.5
DUSUS_DEVAM_RSI_TABAN = 25
# v4.25 TRADER KARARI (04 Ağustos 2026): 45 coin/4 gün gerçek veriyle yapılan
# backtest'te düşüş devamı (SHORT) sinyali %14 kazanma, ortalama -0.798R
# gösterdi (14 işlem) - LONG sinyallerinden (sustained -0.323R, ama büyük
# kazançlar mevcut) belirgin daha kötü ve tutarlı biçimde negatif. Kullanıcı
# tüm kararı bana bıraktı; trader mantığıyla zayıf kanıtlanmış, para kaybeden
# bir kolu açık tutmanın gerekçesi yok. SHORT sinyali geçici KAPATILDI.
# Kod silinmedi - DUSUS_DEVAM_AKTIF=true ile tekrar açılabilir, ör. daha
# uzun/geniş bir backtest ileride farklı sonuç verirse.
DUSUS_DEVAM_AKTIF = os.getenv("DUSUS_DEVAM_AKTIF", "false").lower() == "true"

# v4.26 TRADER KARARI (05 Ağustos 2026, gece): Gerçek Bitget geçmişi ile
# botun /panel Analiz çıktısı arasında ciddi bir tutarsızlık bulundu -
# panel "7 işlem %100 kazanma +$4.17" gösterirken gerçek borsa geçmişi
# 12 işlem, %41.7 kazanma, ~-$0.91 net gösteriyordu (BEAT -1.34, ACX -1.33,
# BIRB -0.26, HFT -1.18 gibi zararlar panelde HİÇ görünmüyordu). Kök sebep
# tam teşhis edilemedi (volume mount path doğru, /sifirla çalıştırılmamış).
# Bu, gunluk_pnl/haftalik_pnl sayaçlarının da gerçek zararları eksik
# sayıyor olabileceği, dolayısıyla HAFTALIK_ZARAR_LIMIT_PCT güvenlik
# frenini KÖRLEŞTİRMİŞ olabileceği anlamına geliyor - kritik risk.
# Kullanıcı tüm kararı bana bıraktı: sorumlu trader kararı olarak YENİ
# POZİSYON AÇILMASI DURDURULDU (açık pozisyonların yönetimi/kapatılması
# etkilenmedi). TRADING_AKTIF=true ile tekrar açılabilir - ama önce
# loglama tutarsızlığının kök sebebi bulunmalı.
TRADING_AKTIF = os.getenv("TRADING_AKTIF", "true").lower() == "true"

ATR_CARPANI_SL = 2.0

# v4.18 DEĞİŞTİ: %6 -> %3. Kaldıraç 10x sabit kalıyor (kullanıcı talebi),
# ama SL mesafesi tavanı daraltıldı ki ATR şiştiğinde ROI kaybı %60'a
# değil ~%30'a çıksın. Bkz. yukarıdaki v4.18 değişiklik notu (madde 4).
MAX_SL_PCT = float(os.getenv("MAX_SL_PCT", "0.05"))
# v5.17 KULLANICI KARARI (07.08.2026): %3->%5. Backtest (35 coin/6 gün,
# devam teyitli girişlerle): %3 SL çok sık "kısa dalgalanmayla" tetiklenip
# asıl trendin devam edeceği işlemleri erken kapatıyordu - %5'e
# genişletince kazanma oranı %43.6->%47.0'a çıktı, toplam -4.17R->+12.90R'a
# döndü. Kullanıcı $1 marjinle çalışacağı için ($10 notional, 10x) mutlak
# dolar riski hâlâ küçük (~$0.50/işlem) - genişletmenin bedeli düşük.
MIN_SL_PCT = float(os.getenv("MIN_SL_PCT", "0.02"))

KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
HEDEF_NET_KAR_USDT = float(os.getenv("HEDEF_NET_KAR_USDT", "0.30"))
IZ_SURME_R_ORANI = float(os.getenv("IZ_SURME_R_ORANI", "1.0"))
# v5.22 KULLANICI KARARI (08.08.2026): 0.70R->1.0R. Kullanıcı "büyük kârı
# takip etsin, erken kapanmasın" dedi - dün test ettiğimiz 4 seçenekten
# (0.50/0.30, 0.70/0.40, 1.0/0.5) orta yolu (0.70/0.40) seçmiştim ama
# kullanıcının asıl istediği en agresif/en geç kilitlenen seçenekmiş
# (1.0R/0.5R, backtest'te en yüksek toplam +13.58R ama düşük kazanma
# oranı %35.7 vermişti - bilerek kabul edildi).
# v5.17 KULLANICI KARARI: 0.50R->0.70R. Kullanıcı "iz sürme büyük kârı
# erken kapatmasın" dedi. %5 SL tabanıyla test edildi: 0.70R/0.40R
# kombinasyonu dengeli çıktı (+11.39R, %41.7 kazanma) - çok geç kilitleme
# (1.0R) daha yüksek toplam verse de kazanma oranını çok düşürüyordu
# (%35.7), o yüzden orta yol seçildi.
# v5.4 KULLANICI KARARI (06 Ağustos 2026): aktifleşme (0.50R) ile geri çekme
# payı ARTIK AYRI parametreler. Eskiden ikisi de aynı IZ_SURME_R_ORANI'yi
# kullanıyordu - bu da "aktifleşme geç olsun (nefes alsın)" ile "aktifleştikten
# sonra az geri versin" isteklerini AYNI ANDA karşılayamıyordu (tek kadran).
# Backtest (30 coin/5 gün): geri çekme payı 0.50R'den 0.30R'ye indirilince
# toplam getiri neredeyse aynı kaldı (+27.97R vs +28.09R) ama kazanma oranı
# arttı (%44.9 vs %41.7) - kullanıcının "kâr çok geri veriyor" hissini
# karşılayan, veri destekli bir orta yol.
IZ_SURME_GERI_COKME_ORANI = float(os.getenv("IZ_SURME_GERI_COKME_ORANI", "0.5"))
# v5.22 KULLANICI KARARI: 0.40R->0.5R, IZ_SURME_R_ORANI notundaki gerekçeyle
# birlikte seçildi (dün test edilen 1.0R/0.5R kombinasyonu).
# v5.17 KULLANICI KARARI: 0.30R->0.40R - aktifleşme eşiğiyle (0.70R) birlikte
# test edilip seçildi, bkz. IZ_SURME_R_ORANI notundaki gerekçe.
# v5.0 KULLANICI KARARI (06 Ağustos 2026): 0.30R -> 0.50R. Kullanıcı "iz süren
# olsun ama nefes alsın, büyük kârı yakalasın" dedi - eşik daha da
# genişletildi. Artık pozisyon riskin YARISI kadar kâra ulaşmadan başabaşa
# çekilmiyor - daha fazla dalgalanma payı var, ama küçük kârlarda erken
# kilitlenme de o kadar azalıyor (iki ucu keskin bıçak, bilinçli tercih).
# v4.30 KULLANICI KARARI (05 Ağustos 2026): 0.15R -> 0.30R. Gerekçe: CYS ve
# VANRY işlemlerinde iz sürme çok erken ($0.16-0.17 kârda) aktifleşiyor,
# bu da fiyatın girişten henüz az uzaklaştığı bir anda başabaş SL'in de
# girişe çok yakın konmasına yol açıyordu - normal fiyat gürültüsü bile
# "nefes almadan" kapanmaya sebep oluyordu. Eşik iki katına çıkarılınca
# aktifleşme anında fiyat girişten daha uzakta olacak, başabaş SL ile
# güncel fiyat arasında daha doğal bir boşluk kalacak. Bedeli: koruma biraz
# daha geç devreye giriyor, ilk aşamada teorik olarak biraz daha fazla
# geri verme riski var - ama kullanıcı bu takası bilerek seçti.
TIERED_TP = [(0.30, 1.0), (0.30, 2.0), (0.40, 3.0)]  # artık kullanılmıyor (trailing TP), tarihsel referans

# v4.18 DEĞİŞTİ: 40 -> 60. Paralel taramayla (aşağıda ThreadPoolExecutor)
# artık daha büyük bir havuzu aynı sürede kontrol edebiliyoruz - "bot
# hareketli coinleri kaçırıyor" şikayetine karşı kapsam genişletildi.
ADAY_HAVUZU_BUYUKLUGU = int(os.getenv("ADAY_HAVUZU_BUYUKLUGU", "100"))
# v4.18 YENİ: paralel tarama için thread sayısı. Bitget rate limit'e takılmamak
# için ölçülü tutuldu - ccxt zaten enableRateLimit=True ile kendi içinde
# throttle ediyor, bu sadece I/O bekleme süresini örtüştürüyor.
TARAMA_PARALEL_WORKER = int(os.getenv("TARAMA_PARALEL_WORKER", "5"))
# v4.18: temkinli başlangıç değeri 5 - ccxt tek exchange nesnesi çoklu
# thread'den paylaşıldığı için (enableRateLimit tek-thread varsayımıyla
# çalışır) ilk günlerde loglarda 429/beklenmedik hata sıklığı artmazsa
# TARAMA_PARALEL_WORKER env değişkeniyle kademeli olarak yükseltilebilir.

GOSTERGE_MUM_5M = 60
GOSTERGE_MUM_15M = 40

# ── RİSK/GÜVENLİK AYARLARI ──
LEV_HAM_DEGER = os.getenv("LEV")
LEV = int(LEV_HAM_DEGER) if LEV_HAM_DEGER else 10  # kullanıcı talebiyle 10x SABİT KALIYOR
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.10"))
# v5.17 KULLANICI KARARI: sabit dolar marjin modu - 0 ise kapalı (eski
# risk-yüzdesi bazlı boyutlandırma kullanılır), pozitif bir sayı verilirse
# (örn. "1") her işlem o kadar sabit marjinle açılır, bakiyeden bağımsız.
SABIT_MARJIN_USDT = float(os.getenv("SABIT_MARJIN_USDT", "1"))
MAX_POS = int(os.getenv("MAX_POS", "2"))
# v5.3 KULLANICI KARARI (06.08.2026): AJAN 0 (websocket) için AYRI bir slot
# havuzu - artık ana tarama (AJAN 1) ile aynı MAX_POS'u paylaşmıyor, kendi
# bağımsız MAX_POS_WEBSOCKET limitine sahip. Toplamda aynı anda en fazla
# MAX_POS + MAX_POS_WEBSOCKET pozisyon açık olabilir.
MAX_POS_WEBSOCKET = int(os.getenv("MAX_POS_WEBSOCKET", "2"))
GUNLUK_ZARAR_LIMIT_PCT = 0.15
# v4.21 KULLANICI TALEBİYLE: günlük zarar limiti artık taramayı DURDURMUYOR.
# GUNLUK_ZARAR_LIMIT_PCT değeri panelde bilgi amaçlı gösterilmeye devam ediyor,
# ama gunluk_limit_kontrolu() artık tarama_loop'ta kullanılmıyor - kullanıcı
# bilinçli olarak bu güvenlik frenini kaldırmayı istedi (04 Ağustos 2026).
# Haftalık limit (%25) hâlâ aktif - son çare fren olarak duruyor.
GUNLUK_LIMIT_AKTIF = False
HAFTALIK_ZARAR_LIMIT_PCT = float(os.getenv("HAFTALIK_ZARAR_LIMIT_PCT", "0.25"))
# v5.21 KULLANICI KARARI (08.08.2026): haftalık limit de kapatıldı - $1 sabit
# marjinle çalışıldığı için (bkz. SABIT_MARJIN_USDT) tek işlemdeki mutlak
# dolar riski zaten çok küçük, limitin sürekli taramayı durdurup manuel
# müdahale gerektirmesi (özellikle /sifirla kaldırıldıktan sonra) faydadan
# çok sürtünme yaratıyordu. HAFTALIK_ZARAR_LIMIT_PCT değeri panelde bilgi
# amaçlı gösterilmeye devam ediyor, ama artık taramayı DURDURMUYOR.
HAFTALIK_LIMIT_AKTIF = False
KONTROL_ARALIGI_SN = 60

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/scalp_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/scalp_cooldown.json")
# v5.16 KULLANICI KARARI (06.08.2026): kullanıcı kontrollü kalıcı coin
# engelleme listesi - "bir coin bana sürekli zarar ettiriyor, onu bloke
# edebilmem lazım" isteği üzerine. /blokla ve /blokkaldir komutlarıyla
# yönetiliyor, diske kalıcı yazılıyor (bot yeniden başlasa bile kaybolmaz).
BLOKE_PATH = os.getenv("BLOKE_PATH", "/data/scalp_bloke.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/scalp_log.json")
GUNLUK_PATH = os.getenv("GUNLUK_PATH", "/data/scalp_gunluk.json")

trade_state = {}
state_lock = threading.Lock()
# v5.1 KRİTİK DÜZELTME: MAX_POS sınırı eskiden SADECE tarama_loop'un kendi
# bos_slot sayacında kontrol ediliyordu. Ama websocket tetikleyicisi (AJAN 0)
# AYRI bir thread'de bağımsız çalışıyor - ana taramanın "2 slot doldu"
# hesabından habersiz, kendi başına islem_acici_pozisyon_ac() çağırabiliyordu.
# Sonuç: ana tarama tam MAX_POS kadar pozisyon açarken, TAM O SIRADA
# websocket üçüncü bir pozisyon daha açabiliyordu (gerçek örnek: kullanıcı
# "aynı anda 3 işlem açtı" bildirdi, 06.08.2026). Artık islem_acici_pozisyon_ac
# fonksiyonunun KENDİSİ, çağrıldığı yerden bağımsız olarak MAX_POS'u kontrol
# ediyor ve atomik olarak bir "rezervasyon" alıyor - iki thread aynı anda
# son slotu görüp ikisi de açamaz.
# v5.3: artık sym -> kaynak ("tarama" ya da "websocket") eşleşmesi tutuyor,
# ki her kaynağın kendi bağımsız slot limitini doğru sayabilelim.
acilis_rezervasyonlari = {}
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()

# v5.16: kullanıcı kontrollü kalıcı coin engelleme listesi (bkz. BLOKE_PATH notu)
bloke_coinler = set()
bloke_lock = threading.Lock()

gunluk_pnl = 0.0
gunluk_baslangic_bakiye = None
gunluk_gun_damgasi = None
haftalik_pnl = 0.0
haftalik_baslangic_bakiye = None
haftalik_hafta_damgasi = None
gunluk_lock = threading.Lock()

# v3.0: ANİ PATLAMA (ve v4.18'den itibaren SUSTAINED da) sinyali için
# GİRİŞ TEYİDİ - sinyalden sonra fiyat kısa süre "tutuyor mu" diye izlenir.
CONFIRM_BEKLEME_SN = 90
# v4.31 KULLANICI KARARI (05 Ağustos 2026): 180sn -> 90sn. Gerekçe: HOME
# örneğinde 3 dakika beklerken fiyat zaten iyice yükselmiş, giriş "kovalama"
# noktasından oldu. 90sn hâlâ CYS/AIO tipi "tepede yakalanma" riskine karşı
# anlamlı bir koruma sağlıyor (sıfırlamadık) ama gecikmeyi yarıya indiriyor.
CONFIRM_MAX_RETRACE_PCT = 0.01
bekleyen_sinyaller = {}  # sym -> {sinyal_fiyat, atr, skor, tur, zaman}
# v4.23 YENİ: artık hem ana tarama döngüsü hem de AJAN 0 (websocket gözcüsü)
# bekleyen_sinyaller'a yazıyor - thread-safety için kilit eklendi.
bekleyen_lock = threading.Lock()

# v4.33 KULLANICI TALEBİYLE: aynı coin için tekrar tekrar "⏳ sinyal bulundu"
# mesajı gönderilmesin diye susturma mekanizması. CYS/1000RATS gibi oynak
# coinler her 1-2 dakikada bir teyit kuyruğuna girip çıkabiliyor, her
# seferinde Telegram mesajı ve Railway logu üretiyordu - bu da hem Telegram'ı
# hem Railway'i gereksiz meşgul ediyordu. Artık aynı coin için bu mesaj en
# fazla MESAJ_SUSTURMA_SN saniyede bir gönderiliyor (teyit kuyruğu mantığı
# aynen çalışmaya devam ediyor, sadece Telegram bildirimi kısıtlanıyor).
MESAJ_SUSTURMA_SN = 600  # aynı coin için "sinyal bulundu" mesajı en fazla 10 dakikada bir
son_sinyal_mesaji = {}
son_sinyal_mesaji_lock = threading.Lock()
_nabiz_sayac = {"deger": 0}


def sinyal_mesaji_gonder_mi(sym):
    with son_sinyal_mesaji_lock:
        son = son_sinyal_mesaji.get(sym, 0)
        if time.time() - son < MESAJ_SUSTURMA_SN:
            return False
        son_sinyal_mesaji[sym] = time.time()
        return True

# ════════════════════════════════════════════
# AJAN 0: WEBSOCKET GÖZCÜSÜ (v4.23 YENİ)
# ════════════════════════════════════════════
# Kullanıcı talebi: 60sn'lik periyodik tarama arasında hızlı hareket eden
# coinler kaçırılıyordu. Bu ajan Bitget'in public websocket'inden (ticker
# kanalı) CANLI fiyat akışı dinler, kısa pencerede (WS_PENCERE_SN) sert
# hareket gördüğü coin için AJAN 1'in normal sinyal fonksiyonlarını HEMEN
# çağırır - yani hiçbir güvenlik filtresi (RSI, üst fitil, trend, teyit
# kuyruğu) ATLANMAZ, sadece "ne zaman deep-check yapılacağı" hızlanır.
# ⚠️ Bu websocket bağlantısı canlı ortamda test edilmedi (sadece bağlantı
# ve mesaj formatı doğrulandı) - izlenmesi gerekir, sorun çıkarsa
# WS_GOZCU_AKTIF=false ile kapatılabilir.
WS_GOZCU_AKTIF = os.getenv("WS_GOZCU_AKTIF", "true").lower() == "true"
WS_HIZLI_TETIK_YUZDE = float(os.getenv("WS_HIZLI_TETIK_YUZDE", "0.012"))  # pencerede %1.2 hareket
# v4.32 KULLANICI KARARI (05 Ağustos 2026): %2 -> %1.2. Gerekçe: durgun
# piyasa günlerinde AJAN 0 neredeyse hiç tetiklenmiyordu. Eşik düşürüldü
# ama bu SADECE tetikleme hassasiyetini artırıyor - RSI/üst fitil/trend
# filtreleri hâlâ aynen uygulanıyor, güvenlik gevşetilmedi.
WS_PENCERE_SN = int(os.getenv("WS_PENCERE_SN", "30"))  # 30 saniyelik hareket penceresi
WS_TETIK_COOLDOWN_SN = 900  # v5.12: 120sn->900sn (15dk) - kullanıcı talebiyle
# COOLDOWN_SAAT (15dk) ile tutarlı hale getirildi, aynı coin AJAN 0
# tarafından art arda tekrar tekrar denenmesin diye.
WS_CONFIRM_BEKLEME_SN = 20
WS_CONFIRM_MAX_RETRACE_PCT = 0.008

# v5.12 DENEYSEL (06.08.2026, kullanıcı talebi): "erken yakalama" - normal
# AJAN 0 eşiği (%1.2/30sn) zaten kısmen oluşmuş bir hareketi bekliyor. Bu,
# çok daha KÜÇÜK ve KISA bir sıçramayı (12sn'de %0.5) "bir şey başlıyor
# olabilir" sinyali sayıp, normal 20sn yerine sadece 5sn'lik kısa kontrolle
# giriyor. ⚠️ DÜRÜSTLÜK NOTU: bu mum-içi/saniye seviyesinde bir mekanizma,
# elimizdeki 5dk'lık mum verisiyle BACKTEST EDİLEMEZ - sadece canlıda
# izlenip birkaç gün sonra karar verilecek bir deney. Ayrı "tur" etiketiyle
# (erken_yakalama) kaydediliyor ki normal AJAN 0 işlemlerinden panel'de
# ayırt edilebilsin.
WS_ERKEN_AKTIF = os.getenv("WS_ERKEN_AKTIF", "true").lower() == "true"
WS_ERKEN_ESIK_YUZDE = float(os.getenv("WS_ERKEN_ESIK_YUZDE", "0.005"))  # %0.5
WS_ERKEN_PENCERE_SN = int(os.getenv("WS_ERKEN_PENCERE_SN", "12"))
WS_ERKEN_CONFIRM_BEKLEME_SN = int(os.getenv("WS_ERKEN_CONFIRM_BEKLEME_SN", "5"))
ws_erken_son_tetik = {}
ws_erken_son_tetik_lock = threading.Lock()
WS_URL = "wss://ws.bitget.com/v2/ws/public"

ws_fiyat_takip = {}   # bitget_instId -> [(ts, fiyat), ...] kısa rolling buffer
ws_fiyat_lock = threading.Lock()
ws_son_tetik = {}     # ccxt_sym -> son tetiklenme zamanı
ws_son_tetik_lock = threading.Lock()
ws_abone_semboller = set()  # şu an abone olunan bitget instId'leri
ws_abone_lock = threading.Lock()
ws_app_ref = {"ws": None}


def ccxt_to_bitget_inst(sym):
    """'BANK/USDT:USDT' -> 'BANKUSDT'"""
    return sym.split("/")[0] + "USDT"


def bitget_inst_to_ccxt(inst_id):
    """'BANKUSDT' -> 'BANK/USDT:USDT'"""
    if inst_id.endswith("USDT"):
        return inst_id[:-4] + "/USDT:USDT"
    return None


def ws_abonelik_guncelle(ccxt_semboller):
    """Ana tarama döngüsü her turda güncel aday havuzunu bu fonksiyona
    gönderir - henüz abone olunmamış coinler için websocket'e subscribe
    mesajı yollanır. Zaten abone olunanlar tekrar gönderilmez."""
    if not WS_GOZCU_AKTIF:
        return
    ws = ws_app_ref.get("ws")
    if ws is None:
        return
    yeni = []
    with ws_abone_lock:
        for sym in ccxt_semboller:
            inst = ccxt_to_bitget_inst(sym)
            if inst not in ws_abone_semboller:
                ws_abone_semboller.add(inst)
                yeni.append(inst)
    if not yeni:
        return
    try:
        # Bitget tek mesajda çok sayıda args kabul ediyor (test edildi, 8+ sorunsuz)
        args = [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": inst} for inst in yeni]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
        log.info(f"[WS_ABONE] {len(yeni)} yeni coin'e abone olundu (toplam {len(ws_abone_semboller)})")
    except Exception as e:
        log.warning(f"[WS_ABONE] gönderilemedi: {e}")


def ws_erken_tetik_isle(sym, tetik_fiyat):
    """v5.12 DENEYSEL: erken yakalama - normal sinyal kontrolünü (5dk mum,
    %1.5/15dk şartı) ATLAR, doğrudan güncel fiyat + taze ATR ile SL hesaplar.
    Amaç: dev bir mumun TAM ORTASINDA/TEPESİNDE değil, BAŞLANGICINDA
    yakalamak. Sadece kısa (5sn) bir 'tutuyor mu' kontrolü var.
    ⚠️ Bu, normal AJAN 0'dan daha az doğrulanmış bir sinyal - backtest
    edilemedi, sadece canlı veriyle değerlendirilecek (tur=erken_yakalama
    etiketiyle panel'de ayrı takip ediliyor)."""
    try:
        if not TRADING_AKTIF or not WS_ERKEN_AKTIF:
            return
        with state_lock:
            if sym in trade_state:
                return
        if cooldown_da_mi(sym):
            return
        with ws_erken_son_tetik_lock:
            son = ws_erken_son_tetik.get(sym, 0)
            if time.time() - son < WS_TETIK_COOLDOWN_SN:
                return
            ws_erken_son_tetik[sym] = time.time()
        # aynı coin normal AJAN 0 tarafından da işleniyor olabilir - onunla
        # da çakışmasın diye aynı tetik-cooldown haritasını da kontrol/set et
        with ws_son_tetik_lock:
            son2 = ws_son_tetik.get(sym, 0)
            if time.time() - son2 < WS_TETIK_COOLDOWN_SN:
                return
            ws_son_tetik[sym] = time.time()

        df = get_df(sym, "5m", 20)
        if df is None or len(df) < 15:
            return
        atr_val = atr(df, 14).iloc[-1]
        if pd.isna(atr_val) or atr_val <= 0:
            return

        if sinyal_mesaji_gonder_mi(sym):
            tg(f"🌱 AJAN 0 (erken yakalama - DENEYSEL): {sym} çok küçük/hızlı bir sıçrama tespit etti "
               f"(≈%{WS_ERKEN_ESIK_YUZDE*100:.1f}, {WS_ERKEN_PENCERE_SN}sn'de), {WS_ERKEN_CONFIRM_BEKLEME_SN}sn "
               f"kısa kontrol yapılıyor")
        time.sleep(WS_ERKEN_CONFIRM_BEKLEME_SN)
        with state_lock:
            if sym in trade_state:
                return
        if cooldown_da_mi(sym):
            return
        try:
            t = exchange.fetch_ticker(sym)
            guncel_fiyat = safe(t["last"])
        except Exception:
            return
        if guncel_fiyat <= 0:
            return
        ters_hareket = (tetik_fiyat - guncel_fiyat) / tetik_fiyat
        if ters_hareket > WS_CONFIRM_MAX_RETRACE_PCT:
            log.info(f"[WS_ERKEN_IPTAL] {sym} kısa teyitte tersine döndü, iptal edildi")
            return

        sinyal = {"symbol": sym, "entry": guncel_fiyat, "atr": float(atr_val),
                  "skor": 0.0, "tur": "erken_yakalama"}
        with state_lock:
            if sym in trade_state:
                return
        if sinyal_mesaji_gonder_mi(sym):
            tg(f"✅ AJAN 0 (erken yakalama): {sym} kısa teyit geçti — AJAN 2'ye 'şimdi aç' komutu veriliyor")
        try:
            islem_acici_pozisyon_ac(sinyal, kaynak="websocket")
        except Exception as e:
            log.error(f"[ISLEM_ACICI_BEKLENMEYEN_HATA] {sym}: {e}")
            tg(f"🚨 {sym} açılışında beklenmeyen hata oluştu, cooldown'a alındı: {e}")
            acilis_basarisiz_cooldown_uygula(sym)
    except Exception as e:
        log.warning(f"[WS_ERKEN_TETIK] {sym}: {e}")


def ws_hizli_tetik_isle(sym, btc_bullish, havuz):
    """AJAN 0'ın hızlı hareket tespit ettiği bir coin için AJAN 1'in trend
    kontrolünü çalıştırır. v5.15 KULLANICI KARARI (06.08.2026): kullanıcı
    "her şeye zıplıyor, teyitli yapsın, garanti giriş" dedi - artık AJAN 0
    da AJAN 1 ile AYNI 'devam teyidi' kuyruğuna giriyor (sinyal mumundan
    SONRAKİ mum da yükselirse gir, dönerse hiç girme). Eski 20sn kısa
    retrace-teyidi bununla değiştirildi - hız feda edildi, giriş kalitesi
    öncelikli hale getirildi (kullanıcının bilinçli tercihi)."""
    try:
        if not TRADING_AKTIF:
            return
        with state_lock:
            if sym in trade_state:
                return
        if cooldown_da_mi(sym):
            return
        with ws_son_tetik_lock:
            son = ws_son_tetik.get(sym, 0)
            if time.time() - son < WS_TETIK_COOLDOWN_SN:
                return
            ws_son_tetik[sym] = time.time()

        sinyal = sembol_sinyal_kontrol_tumu(sym, btc_bullish)
        if not sinyal:
            return

        with bekleyen_lock:
            if sym in bekleyen_sinyaller:
                return
            # v5.20 KULLANICI KARARI (07.08.2026): "AJAN 0 teyit kalitesini
            # düzelt" isteği - AJAN 0'ın kazanma oranı AJAN 1'den belirgin
            # düşük çıkıyordu (bkz. panel kaynak kırılımı). AJAN 0 artık TEK
            # değil, İKİ ardışık mumun da yükselmesini istiyor (gereken_teyit=2)
            # - AJAN 1 zaten iyi çalıştığı için tek mumda kalıyor (gereken_teyit=1).
            bekleyen_sinyaller[sym] = {"sinyal_fiyat": sinyal["entry"], "atr": sinyal["atr"],
                                        "skor": sinyal["skor"], "tur": sinyal["tur"],
                                        "tetik_ts": sinyal["tetik_ts"], "zaman": time.time(),
                                        "kaynak": "websocket", "gecen_teyit": 0, "gereken_teyit": 2}
        if sinyal_mesaji_gonder_mi(sym):
            tg(f"⚡ AJAN 0 (websocket): {sym} hızlı hareket tespit etti, 2 ardışık mumun da "
               f"yükselmesi bekleniyor (güçlendirilmiş devam teyidi)")
    except Exception as e:
        log.warning(f"[WS_TETIK] {sym}: {e}")


_ws_tetik_havuzu = ThreadPoolExecutor(max_workers=3)


def ws_on_message(ws, message):
    try:
        # v4.24 DÜZELTME: Bitget metin tabanlı "ping"/"pong" heartbeat kullanıyor
        # (standart websocket protokol ping'i yetmiyor, ~2-2.5dk'da bağlantı
        # kopuyordu - canlıda gözlemlendi ve doğrulandı). "pong" cevabı JSON
        # değil, düz metin - json.loads'a girmeden burada elenmeli.
        if message == "pong":
            return
        d = json.loads(message)
        if d.get("action") not in ("snapshot", "update"):
            return
        arg = d.get("arg", {})
        if arg.get("channel") != "ticker":
            return
        data = d.get("data")
        if not data:
            return
        inst_id = arg.get("instId")
        fiyat = safe(data[0].get("lastPr"))
        if not inst_id or fiyat <= 0:
            return
        simdi = time.time()
        with ws_fiyat_lock:
            buf = ws_fiyat_takip.setdefault(inst_id, [])
            buf.append((simdi, fiyat))
            # pencereden eskileri temizle
            kesim = simdi - WS_PENCERE_SN
            while buf and buf[0][0] < kesim:
                buf.pop(0)
            if len(buf) < 2:
                return
            eski_fiyat = buf[0][1]
            # v5.12 YENİ: erken yakalama için kısa pencereli (WS_ERKEN_PENCERE_SN)
            # alt kümeyi de burada, aynı kilit altında hesaplıyoruz.
            erken_kesim = simdi - WS_ERKEN_PENCERE_SN
            erken_buf = [p for p in buf if p[0] >= erken_kesim]
            erken_eski_fiyat = erken_buf[0][1] if len(erken_buf) >= 2 else None
        if eski_fiyat <= 0:
            return
        degisim = abs(fiyat - eski_fiyat) / eski_fiyat
        ccxt_sym = bitget_inst_to_ccxt(inst_id)
        if not ccxt_sym:
            return
        if degisim >= WS_HIZLI_TETIK_YUZDE:
            _ws_tetik_havuzu.submit(ws_hizli_tetik_isle, ccxt_sym, True, None)
            return
        # v5.12 DENEYSEL: normal eşik karşılanmadıysa, çok daha küçük/kısa
        # bir "erken yakalama" eşiğini dene - bkz. yukarıdaki WS_ERKEN_AKTIF
        # tanımındaki dürüstlük notu (backtest edilemez, sadece canlı deney).
        if WS_ERKEN_AKTIF and erken_eski_fiyat and erken_eski_fiyat > 0:
            erken_degisim = (fiyat - erken_eski_fiyat) / erken_eski_fiyat  # SADECE yukarı yön
            if erken_degisim >= WS_ERKEN_ESIK_YUZDE:
                _ws_tetik_havuzu.submit(ws_erken_tetik_isle, ccxt_sym, fiyat)
    except Exception as e:
        log.warning(f"[WS_MESAJ] {e}")


def ws_on_error(ws, error):
    log.warning(f"[WS_HATA] {error}")


def ws_on_close(ws, close_status_code, close_msg):
    log.warning(f"[WS_KAPANDI] code={close_status_code} msg={close_msg}")


def ws_on_open(ws):
    log.info("[WS_ACIK] websocket bağlantısı kuruldu")


def ws_ping_gonder(ws_beklenen):
    """v4.24 YENİ: Bitget'in beklediği metin tabanlı "ping" heartbeat'i
    20 saniyede bir gönderir. Canlıda doğrulandı: standart websocket
    protokol ping'i (ping_interval parametresi) Bitget için yetersizdi,
    bağlantı ~2-2.5 dakikada bir kopuyordu ("Connection to remote host
    was lost"). Metin "ping" gönderimi bunu tamamen çözdü (50sn test
    edildi, hiç kopma olmadı). ws_beklenen: bu ping thread'inin hangi
    websocket nesnesine ait olduğunu bilmesi için - yeniden bağlanma
    durumunda eski thread'in yeni bağlantıya ping atmaya devam edip
    çakışmaması için kontrol ediliyor."""
    while True:
        time.sleep(20)
        if ws_app_ref.get("ws") is not ws_beklenen:
            return  # bağlantı değişmiş (yeniden bağlanmış), bu eski thread sonlansın
        try:
            ws_beklenen.send("ping")
        except Exception:
            return


def ws_gozcu_baslat():
    """AJAN 0'ı ayrı bir daemon thread'de sürekli çalıştırır, bağlantı
    koparsa otomatik yeniden bağlanır."""
    if not WS_GOZCU_AKTIF:
        log.info("[WS_GOZCU] WS_GOZCU_AKTIF=false, websocket gözcüsü devre dışı")
        return
    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL, on_open=ws_on_open, on_message=ws_on_message,
                on_error=ws_on_error, on_close=ws_on_close)
            ws_app_ref["ws"] = ws
            with ws_abone_lock:
                ws_abone_semboller.clear()  # yeniden bağlanınca abonelikler sıfırlanır
            # v4.24: protokol ping KAPALI (ping_interval=None) - Bitget bunu
            # yeterli bulmuyordu. Bunun yerine metin "ping" heartbeat thread'i
            # ayrı başlatılıyor (bkz. ws_ping_gonder).
            threading.Thread(target=ws_ping_gonder, args=(ws,), daemon=True).start()
            ws.run_forever(ping_interval=None)
        except Exception as e:
            log.warning(f"[WS_GOZCU] bağlantı hatası, 10sn sonra tekrar denenecek: {e}")
        ws_app_ref["ws"] = None
        time.sleep(10)


# ════════════════════════════════════════════
# ATOMİK DOSYA YAZMA
# ════════════════════════════════════════════
def atomik_yaz(path, veri):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(veri, f)
        os.replace(tmp, path)
    except Exception as e:
        log.warning(f"[ATOMIK_YAZ] {path}: {e}")


def guvenli_oku(path, varsayilan):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"[OKU] {path}: {e}")
    return varsayilan


def durumu_diske_yaz():
    with state_lock:
        veri = dict(trade_state)
    atomik_yaz(TRADE_STATE_PATH, veri)


def durumu_diskten_yukle():
    global trade_state
    trade_state = guvenli_oku(TRADE_STATE_PATH, {})


def cooldown_diske_yaz():
    with cooldown_lock:
        veri = dict(son_kapanis_zamani)
    atomik_yaz(COOLDOWN_PATH, veri)


def cooldown_diskten_yukle():
    global son_kapanis_zamani
    son_kapanis_zamani = guvenli_oku(COOLDOWN_PATH, {})


def bloke_diske_yaz():
    with bloke_lock:
        veri = sorted(bloke_coinler)
    atomik_yaz(BLOKE_PATH, veri)


def bloke_diskten_yukle():
    global bloke_coinler
    bloke_coinler = set(guvenli_oku(BLOKE_PATH, []))


def coin_bloke_mi(sym):
    """sym: 'COTI/USDT:USDT' gibi tam sembol. Sadece taban ismine (COTI)
    göre kontrol eder - kullanıcının 'bu coin'i engelle' isteğiyle uyumlu."""
    baz = sym.split("/")[0].upper()
    with bloke_lock:
        return baz in bloke_coinler


def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    atomik_yaz(TRADE_LOG_PATH, veri)


def trade_log_yukle():
    global trade_log
    trade_log = guvenli_oku(TRADE_LOG_PATH, [])


def gunluk_haftalik_diske_yaz():
    with gunluk_lock:
        veri = {
            "gunluk_pnl": gunluk_pnl, "gunluk_baslangic_bakiye": gunluk_baslangic_bakiye,
            "gunluk_gun_damgasi": gunluk_gun_damgasi,
            "haftalik_pnl": haftalik_pnl, "haftalik_baslangic_bakiye": haftalik_baslangic_bakiye,
            "haftalik_hafta_damgasi": haftalik_hafta_damgasi,
        }
    atomik_yaz(GUNLUK_PATH, veri)


def gunluk_haftalik_diskten_yukle():
    global gunluk_pnl, gunluk_baslangic_bakiye, gunluk_gun_damgasi
    global haftalik_pnl, haftalik_baslangic_bakiye, haftalik_hafta_damgasi
    veri = guvenli_oku(GUNLUK_PATH, {})
    gunluk_pnl = veri.get("gunluk_pnl", 0.0)
    gunluk_baslangic_bakiye = veri.get("gunluk_baslangic_bakiye")
    gunluk_gun_damgasi = veri.get("gunluk_gun_damgasi")
    haftalik_pnl = veri.get("haftalik_pnl", 0.0)
    haftalik_baslangic_bakiye = veri.get("haftalik_baslangic_bakiye")
    haftalik_hafta_damgasi = veri.get("haftalik_hafta_damgasi")


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_ = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr_.replace(0, 1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr_.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.rolling(period).mean()


def rsi(df, period=14):
    close = df["close"]
    delta = close.diff()
    kazanc = delta.clip(lower=0)
    kayip = -delta.clip(upper=0)
    ort_kazanc = kazanc.rolling(period).mean()
    ort_kayip = kayip.rolling(period).mean()
    rs = ort_kazanc / ort_kayip.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def get_df(sym, tf, limit=60):
    """Son (kapanmamış) mumu atar - sadece kapanmış mumlarla çalışır."""
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit + 1)
            if not candles or len(candles) < 2:
                return None
            candles = candles[:-1]
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.08)
            return df
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(1.5 * (deneme + 1))
                continue
            log.warning(f"[VERI] {sym} {tf}: {e}")
            return None
    return None


# ════════════════════════════════════════════
# AJAN 1: PİYASA İZLEYİCİ — dinamik coin havuzu + sinyal tespiti
# ════════════════════════════════════════════
_market_cache = {"markets": None, "ts": 0}


def market_bilgisi_al():
    if _market_cache["markets"] is None or (time.time() - _market_cache["ts"]) > 3600:
        try:
            _market_cache["markets"] = exchange.load_markets()
            _market_cache["ts"] = time.time()
        except Exception as e:
            log.warning(f"[MARKET_BILGI] {e}")
    return _market_cache["markets"] or {}


def sembol_max_kaldirac(sym, istenen_lev):
    markets = market_bilgisi_al()
    m = markets.get(sym)
    if not m:
        return istenen_lev
    max_lev = (m.get("limits", {}) or {}).get("leverage", {}).get("max")
    if max_lev is None:
        return istenen_lev
    return min(istenen_lev, int(max_lev))


def piyasa_izleyici_aday_havuzu():
    """AJAN 1 - ADIM A: borsanın TAMAMINI tek istekte tarar, RWA/durgun majörleri
    eler, hacim+hareket bazlı en 'canlı' ADAY_HAVUZU_BUYUKLUGU coini döner."""
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
        return []

    markets = market_bilgisi_al()
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
            continue
        m = markets.get(sym)
        if m and m.get("info", {}).get("isRwa") == "YES":
            continue
        vol = t.get("quoteVolume") or 0
        if vol < 300000:
            continue
        chg = t.get("percentage")
        if chg is None:
            continue
        skor = abs(chg) * np.log10(max(vol, 10))
        adaylar.append((sym, skor))

    adaylar.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in adaylar[:ADAY_HAVUZU_BUYUKLUGU]]


def piyasa_izleyici_basit_trend_sinyal(sym, btc_bullish):
    """v5.0 KULLANICI KARARI (06 Ağustos 2026): kullanıcı talebiyle TÜM
    RSI/ADX/hacim-spike/üst-fitil/15dk-trend/teyit-bekleme filtreleri
    KALDIRILDI. Gerekçe: gerçek geçmiş veriyle (50 coin/5 gün) yapılan
    karşılaştırmalı backtest'te, bu sade "sadece trend" yaklaşımı
    +4.82R toplam verirken, RSI/ADX dahil "karmaşık" filtreli sistem
    aynı veri setinde -12.80R vermişti. Fark filtrelerin kalitesinden
    değil, KARMAŞIK sistemin SL'e kadar beklemesinden, basit sistemin
    ise trend kırılınca hızlı çıkmasından kaynaklanıyordu - ama
    kullanıcı özellikle "sadece trend, başka hiçbir şey ekleme" dedi,
    bu yüzden giriş tarafı tamamen sadeleştirildi.

    MANTIK: son 15 dakikada (3×5dk mum) fiyat RET_THRESHOLD kadar
    yükseldiyse HEMEN gir - başka hiçbir koşul yok. Teyit beklemesi de
    YOK (kullanıcı: "hemen gir"). Çıkış SL + iz süren TP ile yönetiliyor
    (manage_loop) - o kısma dokunulmadı, kullanıcı "iz süren olsun ama
    nefes alsın" dedi, zaten 0.30R'ye genişletilmişti."""
    df5 = get_df(sym, "5m", GOSTERGE_MUM_5M)
    if df5 is None or len(df5) < 20:
        return None

    df5["ret_win"] = df5["close"].pct_change(RET_WINDOW_BARS)
    df5["atr"] = atr(df5, 14)

    row = df5.iloc[-1]
    if pd.isna(row["ret_win"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
        return None

    if row["ret_win"] < RET_THRESHOLD:
        return None

    fiyat = row["close"]
    atr_val = row["atr"]
    skor = row["ret_win"]
    return {"symbol": sym, "entry": fiyat, "atr": atr_val, "skor": skor, "tur": "basit_trend",
            "tetik_ts": int(row["ts"])}


def btc_1h_bullish():
    df = get_df("BTC/USDT:USDT", "1h", 40)
    if df is None or len(df) < 25:
        return None
    ma20 = df["close"].rolling(20).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma20):
        return None
    return fiyat > ma20


def sembol_sinyal_kontrol_tumu(sym, btc_bullish):
    """v5.0: artık tek, sade bir sinyal kontrolü var - bkz.
    piyasa_izleyici_basit_trend_sinyal üstündeki not."""
    try:
        return piyasa_izleyici_basit_trend_sinyal(sym, btc_bullish)
    except Exception as e:
        log.warning(f"[PARALEL_TARAMA] {sym}: {e}")
    return None


# ════════════════════════════════════════════
# HESAP / RİSK YARDIMCI FONKSİYONLAR
# ════════════════════════════════════════════
def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        return safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


def gun_damgasi():
    return time.strftime("%Y-%m-%d", time.gmtime())


def hafta_damgasi():
    t = time.gmtime()
    return f"{t.tm_year}-W{time.strftime('%W', t)}"


def gunluk_haftalik_reset_kontrol():
    global gunluk_pnl, gunluk_baslangic_bakiye, gunluk_gun_damgasi
    global haftalik_pnl, haftalik_baslangic_bakiye, haftalik_hafta_damgasi
    bugun = gun_damgasi()
    bu_hafta = hafta_damgasi()
    degisti = False
    with gunluk_lock:
        if gunluk_gun_damgasi != bugun:
            bakiye = gercek_bakiye_al()
            if bakiye is not None:
                gunluk_pnl = 0.0; gunluk_baslangic_bakiye = bakiye; gunluk_gun_damgasi = bugun
                degisti = True
                tg(f"🔄 Yeni gün, günlük zarar limiti sıfırlandı (bakiye: {bakiye:.2f}$)")
        if haftalik_hafta_damgasi != bu_hafta:
            bakiye = gercek_bakiye_al()
            if bakiye is not None:
                haftalik_pnl = 0.0; haftalik_baslangic_bakiye = bakiye; haftalik_hafta_damgasi = bu_hafta
                degisti = True
                tg(f"🔄 Yeni hafta, haftalık zarar limiti sıfırlandı (bakiye: {bakiye:.2f}$)")
    if degisti:
        gunluk_haftalik_diske_yaz()


def gunluk_limit_kontrolu():
    if not GUNLUK_LIMIT_AKTIF:
        return False
    with gunluk_lock:
        if gunluk_baslangic_bakiye is None:
            return False
        return gunluk_pnl <= -(gunluk_baslangic_bakiye * GUNLUK_ZARAR_LIMIT_PCT)


def haftalik_limit_kontrolu():
    if not HAFTALIK_LIMIT_AKTIF:
        return False
    with gunluk_lock:
        if haftalik_baslangic_bakiye is None:
            return False
        return haftalik_pnl <= -(haftalik_baslangic_bakiye * HAFTALIK_ZARAR_LIMIT_PCT)


def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


# ════════════════════════════════════════════
# AJAN 2: İŞLEM AÇICI — pozisyon açma, kademeli TP, breakeven kilit
# ════════════════════════════════════════════
def acilis_basarisiz_cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def sinyal_yonu(tur):
    return "short" if tur == "dusus_devam" else "long"


def islem_acici_pozisyon_ac(sinyal, kaynak="tarama"):
    sym = sinyal["symbol"]
    entry = sinyal["entry"]
    atr_val = sinyal["atr"]
    tur = sinyal.get("tur", "bilinmiyor")
    yon = sinyal_yonu(tur)

    # v4.26 TRADER KARARI: PnL/log tutarsızlığı bulunduğu için yeni pozisyon
    # açılması geçici durduruldu (bkz. TRADING_AKTIF tanımındaki not). Bu
    # kontrol, TÜM açılış yollarının (ana tarama + websocket tetikleyici)
    # geçtiği TEK ortak fonksiyonda - tek noktadan güvenli kapatma.
    if not TRADING_AKTIF:
        log.info(f"[TRADING_DURAKLI] {sym} sinyali bulundu ama TRADING_AKTIF=false, açılış atlanıyor")
        return

    # v5.16 KULLANICI KARARI: kullanıcı kontrollü coin engelleme - burada,
    # TEK ortak açılış noktasında kontrol ediliyor ki hangi ajan (tarama/
    # websocket/erken yakalama) tetiklerse tetiklesin kesin işlesin.
    if coin_bloke_mi(sym):
        log.info(f"[COIN_BLOKE] {sym} kullanıcı tarafından engellenmiş, açılış atlanıyor")
        return

    # v5.9 KRİTİK DÜZELTME: gerçek örnek - kullanıcı BLESS'i elle kapattı,
    # bot neredeyse aynı anda BLESS'i tekrar açtı. Sebep: cooldown_da_mi()
    # kontrolü sinyal ilk tespit edildiğinde (dakikalar önce, veri çekme
    # başlamadan önce) yapılıyordu - eğer o anda pozisyon HÂLÂ açıksa
    # (henüz elle kapatılmamışsa) kontrol geçiyor, ama gerçek açılışa kadar
    # geçen sürede (ağ çağrıları vb.) pozisyon kapanıp cooldown'a girebiliyor.
    # Artık açılışın KESİNLEŞTİĞİ en son an burada, TEKRAR kontrol ediliyor.
    if cooldown_da_mi(sym):
        log.info(f"[COOLDOWN_SON_KONTROL] {sym} açılış anında cooldown'a girmiş, iptal ediliyor")
        return

    # v5.3 KULLANICI KARARI: AJAN 0 (websocket) artık AYRI bir slot havuzuna
    # sahip (MAX_POS_WEBSOCKET) - ana taramanın (MAX_POS) slotlarıyla
    # yarışmıyor. Her kaynağın kendi limiti, o kaynağın açtığı gerçek
    # pozisyonlar + o kaynağın bekleyen rezervasyonları toplamıyla kontrol
    # ediliyor (v5.1'deki race-condition düzeltmesiyle aynı mantık, sadece
    # artık kaynak bazlı ayrıştırılmış).
    limit = MAX_POS_WEBSOCKET if kaynak == "websocket" else MAX_POS
    with state_lock:
        ayni_kaynak_acik = sum(1 for d in trade_state.values() if d.get("acilis_kaynagi", "tarama") == kaynak)
        ayni_kaynak_rezerve = sum(1 for k in acilis_rezervasyonlari.values() if k == kaynak)
        toplam_dolu = ayni_kaynak_acik + ayni_kaynak_rezerve
        if sym not in trade_state and toplam_dolu >= limit:
            log.info(f"[MAX_POS_DOLU] {sym} sinyali bulundu ama [{kaynak}] {toplam_dolu}/{limit} slot dolu, açılış atlanıyor")
            return
        acilis_rezervasyonlari[sym] = kaynak

    try:
        _islem_acici_pozisyon_ac_ic(sym, entry, atr_val, tur, yon, kaynak)
    finally:
        with state_lock:
            acilis_rezervasyonlari.pop(sym, None)


def _islem_acici_pozisyon_ac_ic(sym, entry, atr_val, tur, yon, kaynak="tarama"):
    """v5.1: islem_acici_pozisyon_ac'ın MAX_POS rezervasyonu dışındaki asıl
    gövdesi - fonksiyon adı değişti ama mantık aynı, sadece MAX_POS
    kontrolünün her zaman (rezervasyon serbest bırakılsa bile) çalışmasını
    garanti etmek için ayrı fonksiyona taşındı (try/finally netliği için)."""

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    if yon == "long":
        sl = entry - ATR_CARPANI_SL * atr_val
        if (entry - sl) / entry > MAX_SL_PCT:
            sl = entry * (1 - MAX_SL_PCT)
        if (entry - sl) / entry < MIN_SL_PCT:
            sl = entry * (1 - MIN_SL_PCT)
        sl_mesafe_pct = (entry - sl) / entry
        if sl_mesafe_pct <= 0:
            acilis_basarisiz_cooldown_uygula(sym)
            return
    else:
        sl = entry + ATR_CARPANI_SL * atr_val
        if (sl - entry) / entry > MAX_SL_PCT:
            sl = entry * (1 + MAX_SL_PCT)
        if (sl - entry) / entry < MIN_SL_PCT:
            sl = entry * (1 + MIN_SL_PCT)
        sl_mesafe_pct = (sl - entry) / entry
        if sl_mesafe_pct <= 0:
            acilis_basarisiz_cooldown_uygula(sym)
            return

    risk_dolar = bakiye * RISK_PCT_BAKIYE
    notional = risk_dolar / sl_mesafe_pct

    LEV_KULLANILAN = sembol_max_kaldirac(sym, LEV)

    # v5.17 KULLANICI KARARI (07.08.2026): "$1 marjinle deneyelim" isteği -
    # SABIT_MARJIN_USDT ayarlanmışsa, risk-yüzdesi bazlı boyutlandırma
    # yerine SABİT bir marjin kullanılıyor (notional = marjin x kaldıraç).
    # Böylece bakiye ne olursa olsun her işlem aynı küçük, sabit dolar
    # riskini taşıyor - hem uzun süre gerçek veri toplamayı hem de düşük
    # stresle öğrenmeyi sağlıyor.
    if SABIT_MARJIN_USDT > 0:
        notional = SABIT_MARJIN_USDT * LEV_KULLANILAN
        risk_dolar = notional * sl_mesafe_pct

    qty = None
    for deneme in range(5):
        gereken_marj = notional / LEV_KULLANILAN
        MAX_MARJ_PCT = 0.25 if MAX_POS <= 1 else 0.15
        notional_bu_deneme = notional
        if SABIT_MARJIN_USDT <= 0 and gereken_marj > bakiye * MAX_MARJ_PCT:
            notional_bu_deneme = bakiye * MAX_MARJ_PCT * LEV_KULLANILAN
        amount = notional_bu_deneme / entry
        try:
            qty = float(exchange.amount_to_precision(sym, amount))
        except Exception as e:
            tg(f"⚠️ {sym} miktar hesaplanamadı: {e}")
            acilis_basarisiz_cooldown_uygula(sym)
            return
        if qty <= 0:
            acilis_basarisiz_cooldown_uygula(sym)
            return

        try:
            exchange.set_leverage(LEV_KULLANILAN, sym)
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"[KALDIRAC] {sym}: set_leverage {LEV_KULLANILAN}x hata: {e}")

        try:
            emir_yonu = "buy" if yon == "long" else "sell"
            exchange.create_market_order(sym, emir_yonu, qty)
            notional = notional_bu_deneme
            with state_lock:
                trade_state[sym] = {
                    "entry": entry, "sl_orijinal": None, "sl_guncel": None, "sl_emir_id": None,
                    "qty_orijinal": qty, "r_risk": None, "tp_emirleri": [],
                    "acilis_zamani": time.time(), "breakeven_cekildi": False, "tur": tur,
                    "kurulum_tamamlanmadi": True, "en_iyi_kar": None, "rsi_giris": None,
                    "acilis_kaynagi": kaynak,
                }
            durumu_diske_yaz()
            break
        except Exception as e:
            hata_metni = str(e)
            leverage_hatasi = "40797" in hata_metni or "maximum settable leverage" in hata_metni.lower() or "leverage" in hata_metni.lower()
            if leverage_hatasi and LEV_KULLANILAN > 1 and deneme < 4:
                LEV_KULLANILAN = max(1, LEV_KULLANILAN // 2)
                log.warning(f"[GIRIS] {sym}: kaldıraç kaynaklı hata, {LEV_KULLANILAN}x ile tekrar deneniyor: {e}")
                continue
            tg(f"⚠️ {sym} giriş emri başarısız (denenen kaldıraç: {LEV_KULLANILAN}x): {e}")
            acilis_basarisiz_cooldown_uygula(sym)
            return
    else:
        tg(f"⚠️ {sym} atlandı — 5 denemede de giriş emri açılamadı")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    time.sleep(0.8)
    try:
        pozisyon_bilgisi = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyon_bilgisi if safe(p.get("contracts")) > 0), None)
        if gercek_pos and gercek_pos.get("leverage"):
            LEV_KULLANILAN = int(float(gercek_pos["leverage"]))
    except Exception as e:
        gercek_pos = None
        log.warning(f"[KALDIRAC_DOGRULA] {sym}: {e}")

    if gercek_pos and safe(gercek_pos.get("entryPrice")) > 0:
        gercek_giris = safe(gercek_pos.get("entryPrice"))
        if abs(gercek_giris - entry) / entry > 0.001:
            log.info(f"[GIRIS_KAYMASI] {sym}: sinyal={entry:.6f} gercek={gercek_giris:.6f} "
                     f"(%{(gercek_giris-entry)/entry*100:+.2f})")
        entry = gercek_giris
        sl = entry * (1 - sl_mesafe_pct) if yon == "long" else entry * (1 + sl_mesafe_pct)

    notional = qty * entry
    r_risk = (entry - sl) if yon == "long" else (sl - entry)

    sl_emir_id = None
    sl_fiyat = float(exchange.price_to_precision(sym, sl))
    sl_kapatma_yonu = "sell" if yon == "long" else "buy"
    for sl_deneme in range(3):
        try:
            sl_emri = exchange.create_order(sym, "market", sl_kapatma_yonu, qty, None,
                                             {"reduceOnly": True, "stopLossPrice": sl_fiyat})
            sl_emir_id = sl_emri.get("id")
            if sl_emir_id:
                break
        except Exception as e:
            log.warning(f"[HARD_STOP] {sym} deneme {sl_deneme+1}/3: {e}")
        time.sleep(0.5)

    if not sl_emir_id:
        tg(f"🚨 ACİL: {sym} için SL emri 3 denemede de yerleştirilemedi! "
           f"Pozisyon KORUMASIZ kalmasın diye HEMEN piyasa fiyatından kapatılıyor.")
        try:
            exchange.create_market_order(sym, sl_kapatma_yonu, qty, params={"reduceOnly": True})
            tg(f"✅ {sym} güvenlik amaçlı kapatıldı (SL yerleştirilemediği için).")
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
        except Exception as e:
            tg(f"🚨🚨 KRİTİK: {sym} SL YERLEŞTİRİLEMEDİ VE GÜVENLİK KAPATMASI DA BAŞARISIZ OLDU: {e}\n"
               f"LÜTFEN HEMEN BORSAYA GİRİP MANUEL KONTROL ET. (Kayıt bilerek silinmedi - "
               f"pozisyon hâlâ açık olabilir, tekrar açılmasın diye.)")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    tp_emirleri = []

    # v4.34 YENİ: erken uyarı (momentum zayıflama) özelliği için giriş
    # anındaki RSI'yı kaydediyoruz - backtest ile doğrulandı (05.08.2026,
    # 50 coin/5 gün gerçek veri): pozisyon zararda VE RSI girişten en az 8
    # puan düşüp 45'in altına inmişse erken çıkmak, ortalama zarar
    # büyüklüğünü yarıya indiriyordu (SL'e giden işlem ort. -1.0R iken
    # erken uyarıyla çıkanlar ort. -0.49R). Bu SADECE zaten zararda olan
    # pozisyonlar için ek bir erken-çıkış tetikleyicisi - SL/trailing
    # mantığına dokunmuyor.
    rsi_giris = None
    try:
        df_giris = get_df(sym, "5m", 20)
        if df_giris is not None and len(df_giris) >= 15:
            df_giris["rsi"] = rsi(df_giris, 14)
            son_rsi = df_giris["rsi"].iloc[-1]
            if not pd.isna(son_rsi):
                rsi_giris = float(son_rsi)
    except Exception as e:
        log.warning(f"[RSI_GIRIS] {sym}: {e}")

    with state_lock:
        if sym in trade_state:
            # v4.18 KRİTİK DÜZELTME: "entry" burada EKSİKTİ - state'te eski
            # (sinyal anındaki tahmini) fiyat kalıyordu, borsadan gelen
            # GERÇEK dolum fiyatı (yukarıda hesaplanan `entry`) hiç
            # kaydedilmiyordu. Bu, iz süren kâr al hesaplamasını ve
            # borsa-taraflı SL tetiklendiğinde günlük/haftalık PnL
            # sayaçlarını (dolayısıyla zarar limiti güvenlik ağını)
            # yanlış besliyordu. Şimdi "entry" de güncelleniyor.
            trade_state[sym].update({
                "entry": entry,
                "sl_orijinal": sl, "sl_guncel": sl, "sl_emir_id": sl_emir_id,
                "r_risk": r_risk, "tp_emirleri": tp_emirleri,
                "kurulum_tamamlanmadi": False, "en_iyi_kar": None,
                "rsi_giris": rsi_giris,
            })
        else:
            trade_state[sym] = {
                "entry": entry, "sl_orijinal": sl, "sl_guncel": sl, "sl_emir_id": sl_emir_id,
                "qty_orijinal": qty, "r_risk": r_risk, "tp_emirleri": tp_emirleri,
                "acilis_zamani": time.time(), "breakeven_cekildi": False, "tur": tur,
                "rsi_giris": rsi_giris, "acilis_kaynagi": kaynak,
                "kurulum_tamamlanmadi": False, "en_iyi_kar": None,
            }
    durumu_diske_yaz()

    tur_etiket = "ani patlama" if tur == "spike" else ("sürdürülebilir tırmanış" if tur == "sustained" else ("düşüş devamı" if tur == "dusus_devam" else tur))
    _risk_dolar_giris = r_risk * qty
    _iz_esik_giris = _risk_dolar_giris * IZ_SURME_R_ORANI if _risk_dolar_giris > 0 else HEDEF_NET_KAR_USDT
    _gc_esik_giris = _risk_dolar_giris * IZ_SURME_GERI_COKME_ORANI if _risk_dolar_giris > 0 else HEDEF_NET_KAR_USDT
    tp_ozet = (f"TP: İZ SÜREN — ${_iz_esik_giris:.2f} kârda aktifleşir ({IZ_SURME_R_ORANI:.2f}R), "
               f"en iyi kârdan ${_gc_esik_giris:.2f} geri çekilirse kapanır ({IZ_SURME_GERI_COKME_ORANI:.2f}R)")
    yon_etiket = "LONG" if yon == "long" else "SHORT"
    yon_emoji = "📈" if yon == "long" else "📉"
    if SABIT_MARJIN_USDT > 0:
        risk_ozet = f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Marjin: sabit ${SABIT_MARJIN_USDT:.2f} | Risk≈${risk_dolar:.2f}"
    else:
        risk_ozet = f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Risk≈${risk_dolar:.2f} (bakiyenin ~%{RISK_PCT_BAKIYE*100:.0f}'i)"
    tg(f"{yon_emoji} SCALP POZİSYON: {sym} {yon_etiket} [{tur_etiket}]\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (2×ATR, tavan %{MAX_SL_PCT*100:.0f})\n"
       f"{tp_ozet}\n"
       f"{risk_ozet}")


def pozisyonu_tamamen_kapat(sym, sebep="manuel"):
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        with state_lock:
            durum = trade_state.get(sym)
        if not gercek_pos:
            # v4.27 KRİTİK DÜZELTME: Bu dal eskiden PnL'i HİÇ KAYDETMEDEN
            # sessizce çıkıyordu. Senaryo: yazılım SL güvenlik ağı devreye
            # girdiğinde, borsanın KENDİ hard-SL emri genelde bizden önce
            # tetikleniyordu (milisaniyeler farkla) - biz "kapatmaya" geldiğimizde
            # pozisyon ZATEN kapanmış oluyordu. Eski kod bunu "yapacak bir şey
            # yok" sanıp trade_state'i temizliyor ama trade_log'a HİÇ
            # yazmıyordu - gerçek kayıplar (BEAT, ACX, BIRB, HFT örnekleri)
            # borsada gerçekleşmiş ama botun kendi kayıtlarında hiç
            # görünmüyordu. Artık: elimizde trade_state kaydı (durum) varsa,
            # borsadan GERÇEK SL emrinin dolum fiyatını çekip PnL'i doğru
            # şekilde trade_log'a ve günlük/haftalık sayaçlara ekliyoruz.
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()

            if durum:
                cikis_fiyat = None
                if durum.get("sl_emir_id"):
                    try:
                        sl_detay = exchange.fetch_order(durum["sl_emir_id"], sym)
                        gercek_sl_dolum = safe(sl_detay.get("average")) or safe(sl_detay.get("price"))
                        if gercek_sl_dolum and gercek_sl_dolum > 0:
                            cikis_fiyat = gercek_sl_dolum
                    except Exception as e:
                        log.warning(f"[KAYIP_KAPANIS_FIYATI] {sym}: SL emri dolum fiyatı alınamadı: {e}")
                if not cikis_fiyat:
                    try:
                        t = exchange.fetch_ticker(sym)
                        cikis_fiyat = safe(t["last"])
                    except Exception:
                        cikis_fiyat = durum.get("sl_guncel") or durum["entry"]
                entry = durum["entry"]
                qty = durum.get("qty_orijinal", 0)
                kapanis_yonu = sinyal_yonu(durum.get("tur"))
                pnl_tahmini = (cikis_fiyat - entry) * qty if kapanis_yonu == "long" else (entry - cikis_fiyat) * qty
                global gunluk_pnl, haftalik_pnl
                with gunluk_lock:
                    gunluk_pnl += pnl_tahmini
                    haftalik_pnl += pnl_tahmini
                gunluk_haftalik_diske_yaz()
                trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": pnl_tahmini,
                                   "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                   "not": f"{sebep}_borsada_onceden_kapanmis", "tur": durum.get("tur", "bilinmiyor"),
                                   "kaynak": durum.get("acilis_kaynagi", "bilinmiyor")})
                tg(f"ℹ️ {sym} — kontrol ettiğimizde borsada zaten kapanmıştı (muhtemelen borsanın "
                   f"kendi SL emri önce tetiklendi). Tahmini PnL≈{pnl_tahmini:+.2f}$ kayda eklendi.")
                return True, f"ℹ️ {sym} zaten borsada açık değilmiş — PnL≈{pnl_tahmini:+.2f}$ kaydedildi."
            return True, f"ℹ️ {sym} zaten borsada açık değilmiş, kayıt temizlendi (cooldown uygulandı)."

        qty = safe(gercek_pos.get("contracts"))
        entry_fiyat = safe(gercek_pos.get("entryPrice"))
        pozisyon_yonu = gercek_pos.get("side", "short")
        kapama_yon = "buy" if pozisyon_yonu == "short" else "sell"
        kapama_emri = exchange.create_market_order(sym, kapama_yon, qty, params={"reduceOnly": True})

        if durum:
            for t in durum.get("tp_emirleri", []):
                if not t.get("dolu") and t.get("id"):
                    try:
                        exchange.cancel_order(t["id"], sym)
                    except Exception:
                        pass
            if durum.get("sl_emir_id"):
                try:
                    exchange.cancel_order(durum["sl_emir_id"], sym)
                except Exception:
                    pass

        time.sleep(1)
        cikis_fiyat = None
        try:
            emir_detay = exchange.fetch_order(kapama_emri.get("id"), sym)
            gercek_dolum = safe(emir_detay.get("average")) or safe(emir_detay.get("price"))
            if gercek_dolum and gercek_dolum > 0:
                cikis_fiyat = gercek_dolum
        except Exception as e:
            log.warning(f"[CIKIS_FIYATI] {sym}: gerçek dolum fiyatı alınamadı, ticker'a dönülüyor: {e}")
        if not cikis_fiyat:
            try:
                t = exchange.fetch_ticker(sym)
                cikis_fiyat = safe(t["last"])
            except Exception:
                cikis_fiyat = entry_fiyat
        pnl = (cikis_fiyat - entry_fiyat) * qty if pozisyon_yonu == "long" else (entry_fiyat - cikis_fiyat) * qty
        trade_log_kaydet({"symbol": sym, "entry": entry_fiyat, "exit": cikis_fiyat, "pnl": pnl,
                           "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "not": sebep,
                           "tur": (durum or {}).get("tur", "bilinmiyor"),
                           "kaynak": (durum or {}).get("acilis_kaynagi", "bilinmiyor")})
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        with cooldown_lock:
            son_kapanis_zamani[sym] = time.time()
        cooldown_diske_yaz()
        return True, f"✅ {sym} tamamen kapatıldı | PnL≈{pnl:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma sırasında hata: {e}"


def sembol_bul(acik_semboller, parca):
    parca = parca.upper()
    for sym in acik_semboller:
        if sym.split("/")[0] == parca:
            return sym
    eslesen = [sym for sym in acik_semboller if parca in sym.upper()]
    return eslesen[0] if len(eslesen) == 1 else None


# ════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════
if bot:
    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            acik_semboller = list(trade_state.keys())
        if not acik_semboller:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        if parca:
            hedef = sembol_bul(acik_semboller, parca)
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen tek pozisyon bulunamadı: {acik_semboller}")
                return
        else:
            if len(acik_semboller) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla açık pozisyon var: {acik_semboller}")
                return
            hedef = acik_semboller[0]
        bot.send_message(msg.chat.id, f"⏳ {hedef} kapatılıyor...")
        basari, mesaj = pozisyonu_tamamen_kapat(hedef)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            durumlar = dict(trade_state)
        if not durumlar:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        satirlar = ["📋 AÇIK POZİSYON(LAR)\n"]
        for sym, d in durumlar.items():
            try:
                t = exchange.fetch_ticker(sym)
                guncel = safe(t["last"])
                d_yonu = sinyal_yonu(d.get("tur"))
                pnl_pct = (guncel - d["entry"]) / d["entry"] * 100 if d_yonu == "long" else (d["entry"] - guncel) / d["entry"] * 100
                en_iyi = d.get("en_iyi_kar")
                iz_durum = f" | 🎯 en iyi kâr: ${en_iyi:.2f}" if en_iyi is not None else ""
                yon_etiket2 = "LONG" if d_yonu == "long" else "SHORT"
                yon_emoji2 = "🟢" if d_yonu == "long" else "🔴"
                satirlar.append(f"{yon_emoji2} {sym} {yon_etiket2}\n"
                                 f"   Giriş:{d['entry']:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                                 f"   SL:{d['sl_guncel']:.6f}{iz_durum}")
            except Exception:
                satirlar.append(f"{sym} (fiyat alınamadı)")
        bot.send_message(msg.chat.id, "\n".join(satirlar))

    def panel_ozet_metni():
        with log_lock:
            gecmis = list(trade_log)
        satirlar = ["📊 SCALP BOT ÖZET\n"]
        try:
            bakiye_bilgi = exchange.fetch_balance()
            usdt = bakiye_bilgi.get("USDT", {})
            toplam_bakiye = safe(usdt.get("total", 0)) or safe(usdt.get("free", 0))
            satirlar.append(f"💰 Bakiye: {toplam_bakiye:.2f}$")
        except Exception:
            pass
        if gecmis:
            toplam = len(gecmis)
            kazanan = [t for t in gecmis if t["pnl"] > 0]
            net = sum(t["pnl"] for t in gecmis)
            satirlar.append(f"Toplam kapanan işlem: {toplam} | Kazanma: %{len(kazanan)/toplam*100:.1f}")
            satirlar.append(f"Net PnL: {net:+.2f}$")
            satirlar.append("\n📋 Son 5 kapanan işlem:")
            for t in list(reversed(gecmis))[:5]:
                emoji = "🟢" if t["pnl"] >= 0 else "🔴"
                sebep = t.get("not", "")
                satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]} {t['pnl']:+.2f}$ ({sebep})")
        else:
            satirlar.append("Henüz kapanan işlem yok.")
        with gunluk_lock:
            satirlar.append(f"\n📅 Bugün: {gunluk_pnl:+.2f}$ | 📆 Bu hafta: {haftalik_pnl:+.2f}$")
        with state_lock:
            satirlar.append(f"\n📈 Açık pozisyon: {len(trade_state)}/{MAX_POS + MAX_POS_WEBSOCKET} (tarama:{MAX_POS}, websocket:{MAX_POS_WEBSOCKET})")
        return "\n".join(satirlar)

    def panel_ayarlar_metni():
        return ("⚙️ SCALP BOT AYARLARI\n\n"
                f"Sürüm: v5.22 (iz s\u00fcrme daha da ge\u00e7 kilitleniyor - 0.70R/0.40R yerine 1.0R/0.5R, b\u00fcy\u00fck "
                f"k\u00e2r\u0131 daha \u00e7ok takip ediyor; g\u00fcnl\u00fck+haftal\u0131k zarar limiti tamamen kapat\u0131ld\u0131 - art\u0131k "
                f"taramay\u0131 durdurmuyor; AJAN 0 art\u0131k 2 ard\u0131\u015f\u0131k mum teyidi istiyor - AJAN 1 tek mumda "
                f"kal\u0131yor; /sifirla komutu tamamen kald\u0131r\u0131ld\u0131; kal\u0131c\u0131 performans istatistikleri "
                f"birikiyor; SL tavan\u0131 %3->%5; $1 sabit marjin modu; 'Coin Engelle' b\u00f6l\u00fcm\u00fc; giri\u015f "
                f"e\u015fi\u011fi %1.5; SADE MOD, 08.08.2026) — "
                f"RSI/ADX/hacim-spike/üst-fitil/teyit-bekleme filtreleri KALDIRILDI. "
                f"Sadece fiyat trendi ile hemen giriş, SL + geniş iz süren TP ile çıkış.\n"
                f"Kaldıraç: {LEV}x (sabit) | MAX_POS: {MAX_POS} (tarama) + {MAX_POS_WEBSOCKET} (websocket, ayrı havuz)\n"
                f"İşlem başına risk: {'sabit $' + format(SABIT_MARJIN_USDT, '.2f') + ' marjin' if SABIT_MARJIN_USDT > 0 else 'bakiyenin %' + format(RISK_PCT_BAKIYE*100, '.0f')}\n"
                f"GİRİŞ: son {RET_WINDOW_BARS*5} dakikada fiyat %{RET_THRESHOLD*100:.0f}+ yükseldiyse "
                f"HEMEN girilir (bekleme/teyit yok, RSI/ADX/hacim kontrolü yok)\n"
                f"SL: {ATR_CARPANI_SL}x ATR(5m,14), tavan %{MAX_SL_PCT*100:.0f} / taban %{MIN_SL_PCT*100:.0f}\n"
                f"TP: İZ SÜREN (trailing) — pozisyon riskin %{IZ_SURME_R_ORANI*100:.0f}'i kadar kâra "
                f"ulaşınca aktifleşir, SL başabaşa çekilir; sonra en iyi kârdan riskin "
                f"%{IZ_SURME_GERI_COKME_ORANI*100:.0f}'i kadar geri çekilirse kapanır "
                f"(aktifleşme geniş - nefes payı; geri çekme dar - kâr daha sıkı korunur)\n"
                f"SHORT sinyali: KAPALI (sadece LONG)\n"
                f"⚠️ YENİ POZİSYON AÇILIŞI: {'AKTİF' if TRADING_AKTIF else 'DURAKLATILDI'}\n"
                f"Coin cooldown: {COOLDOWN_SAAT} saat\n"
                f"Aday havuzu: her turda en canlı {ADAY_HAVUZU_BUYUKLUGU} coin, "
                f"{TARAMA_PARALEL_WORKER} paralel worker ile taranır\n"
                f"Günlük zarar limiti: %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f} (KAPALI - taramayı durdurmuyor) | "
                f"Haftalık: %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f} (KAPALI - taramayı durdurmuyor)\n"
                f"Tarama aralığı: {KONTROL_ARALIGI_SN}sn")

    def panel_gecmis_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "📜 Henüz kapanan işlem yok."
        satirlar = ["📜 SON 15 İŞLEM\n"]
        for t in list(reversed(gecmis))[:15]:
            tur = t.get("tur", "?")
            tur_kisa = "patlama" if tur == "spike" else ("sürdürülebilir" if tur == "sustained" else ("düşüş devamı" if tur == "dusus_devam" else tur))
            sebep = t.get("not", "")
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {t['pnl']:+.2f}$ "
                             f"[{tur_kisa}] ({sebep}) — {t['zaman']}")
        return "\n".join(satirlar)

    def panel_analiz_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "🔬 SCALP ANALİZ\n\nHenüz kapanan işlem yok."
        satirlar = ["🔬 SCALP ANALİZ\n"]
        satirlar.append("📊 Sinyal tipi bazında:")
        # v5.0: artık tek tür var (basit_trend) - eski spike/sustained/
        # dusus_devam türleri de geçmiş kayıtlarda kalmış olabilir, hepsi
        # gösteriliyor.
        turler = sorted(set(t.get("tur", "bilinmiyor") for t in gecmis))
        for tur in turler:
            alt = [t for t in gecmis if t.get("tur") == tur]
            if not alt:
                continue
            kazanan = [t for t in alt if t["pnl"] > 0]
            net = sum(t["pnl"] for t in alt)
            tur_ad = {"spike": "Ani patlama (eski)", "sustained": "Sürdürülebilir tırmanış (eski)",
                      "dusus_devam": "Düşüş devamı (eski)", "basit_trend": "Sade trend"}.get(tur, tur)
            satirlar.append(f"  {tur_ad}: {len(alt)} işlem, %{len(kazanan)/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

        # v5.10 YENİ: kullanıcı "AJAN 0 (websocket) işlemleri daha mı iyi?"
        # diye sordu - eskiden bu soruyu cevaplayacak veri hiç tutulmuyordu.
        # Artık her işlem hangi ajan tarafından açıldığını (tarama/websocket)
        # kaydediyor, burada karşılaştırmalı gösteriliyor.
        satirlar.append("\n🤖 Açılış kaynağına göre (AJAN 1 tarama vs AJAN 0 websocket):")
        kaynaklar = sorted(set(t.get("kaynak", "bilinmiyor") for t in gecmis))
        for kaynak in kaynaklar:
            alt = [t for t in gecmis if t.get("kaynak") == kaynak]
            if not alt:
                continue
            kazanan = [t for t in alt if t["pnl"] > 0]
            net = sum(t["pnl"] for t in alt)
            kaynak_ad = {"tarama": "AJAN 1 (tarama)", "websocket": "AJAN 0 (websocket)"}.get(kaynak, kaynak)
            satirlar.append(f"  {kaynak_ad}: {len(alt)} işlem, %{len(kazanan)/len(alt)*100:.0f} kazanma, "
                             f"net {net:+.2f}$, ort {net/len(alt):+.3f}$/işlem")

        satirlar.append("\n🚪 Kapanış sebebi bazında:")
        # v5.6 DÜZELTME: eskiden sabit bir liste taranıyordu - v4.27'de eklenen
        # "_borsada_onceden_kapanmis" ekli sebep isimleri (borsa bizden önce
        # kapattığında) bu listede olmadığı için panelde hiç görünmüyordu
        # (gerçek örnek: COTI, 06.08.2026). Artık gerçek kayıtlarda bulunan
        # TÜM sebepler otomatik toplanıp gösteriliyor, hiçbiri kaçmıyor.
        tum_sebepler = sorted(set(t.get("not", "bilinmiyor") for t in gecmis),
                               key=lambda s: -sum(1 for t in gecmis if t.get("not") == s))
        for sebep in tum_sebepler:
            alt = [t for t in gecmis if t.get("not") == sebep]
            if not alt:
                continue
            net = sum(t["pnl"] for t in alt)
            satirlar.append(f"  {sebep}: {len(alt)} işlem, net {net:+.2f}$")
        coin_pnl = {}
        for t in gecmis:
            sym = t["symbol"].split("/")[0]
            coin_pnl[sym] = coin_pnl.get(sym, 0) + t["pnl"]
        siralanmis = sorted(coin_pnl.items(), key=lambda x: x[1], reverse=True)
        if siralanmis:
            kazandiranlar = [x for x in siralanmis if x[1] > 0][:3]
            kaybettirenler = [x for x in siralanmis if x[1] < 0][-3:][::-1]
            if kazandiranlar:
                satirlar.append("\n🏆 En kazandıran coinler:")
                for sym, pnl in kazandiranlar:
                    satirlar.append(f"  {sym}: {pnl:+.2f}$")
            # v4.26 DÜZELTME: eskiden "en düşük 3 coin" gösteriliyordu - hepsi
            # pozitifse bile "En kaybettiren" başlığı altında yanıltıcı şekilde
            # gösteriliyordu (kullanıcı geri bildirimi: "zararları göstermiyor,
            # ama yine de zarar varmış gibi gösteriyor"). Artık SADECE gerçekten
            # net negatif olan coinler bu listede yer alıyor.
            if kaybettirenler:
                satirlar.append("💀 En kaybettiren coinler:")
                for sym, pnl in kaybettirenler:
                    satirlar.append(f"  {sym}: {pnl:+.2f}$")
            elif kazandiranlar:
                satirlar.append("💀 Zarar eden coin yok (hepsi net pozitif)")
        return "\n".join(satirlar)

    def panel_risk_metni():
        satirlar = ["📉 RİSK DURUMU\n"]
        with gunluk_lock:
            gp = gunluk_pnl; hp = haftalik_pnl
            gb = gunluk_baslangic_bakiye; hb = haftalik_baslangic_bakiye
        if gb:
            limit_dolar = gb * GUNLUK_ZARAR_LIMIT_PCT
            kalan = limit_dolar + gp
            if GUNLUK_LIMIT_AKTIF:
                satirlar.append(f"Günlük zarar limiti: -{limit_dolar:.2f}$ (bakiyenin %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}'i)")
                satirlar.append(f"Bugünkü PnL: {gp:+.2f}$ | Limite kalan pay: {kalan:.2f}$")
                satirlar.append("⛔ GÜNLÜK LİMİT AŞILDI - tarama duruyor" if gunluk_limit_kontrolu() else "✅ Günlük limit aşılmadı")
            else:
                satirlar.append("Günlük zarar limiti: KAPALI (kullanıcı talebiyle, 04.08.2026) - tarama durmuyor")
                satirlar.append(f"Bugünkü PnL (bilgi amaçlı): {gp:+.2f}$ (referans limit olsaydı: -{limit_dolar:.2f}$)")
        else:
            satirlar.append("Günlük başlangıç bakiyesi henüz kaydedilmedi.")
        if hb:
            limit_dolar_h = hb * HAFTALIK_ZARAR_LIMIT_PCT
            kalan_h = limit_dolar_h + hp
            satirlar.append(f"\nHaftalık zarar limiti: -{limit_dolar_h:.2f}$ (bakiyenin %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f}'i)")
            satirlar.append(f"Bu haftaki PnL: {hp:+.2f}$ | Limite kalan pay: {kalan_h:.2f}$")
            satirlar.append("⛔ HAFTALIK LİMİT AŞILDI - tarama duruyor" if haftalik_limit_kontrolu() else "✅ Haftalık limit aşılmadı")
        else:
            satirlar.append("\nHaftalık başlangıç bakiyesi henüz kaydedilmedi.")

        try:
            btc_bull = btc_1h_bullish()
            if btc_bull is None:
                satirlar.append("\n₿ BTC 1h rejimi alınamadı")
            elif btc_bull:
                satirlar.append("\n₿ BTC 1h rejimi: 🟢 YÜKSELİŞTE (bilgi amaçlı - v4.1'de filtre kaldırıldı)")
            else:
                satirlar.append("\n₿ BTC 1h rejimi: 🔴 DÜŞÜŞTE/YATAY (bilgi amaçlı - v4.1'de filtre kaldırıldı, tarama her durumda aktif)")
        except Exception:
            pass

        with cooldown_lock:
            cd = dict(son_kapanis_zamani)
        aktif_cooldown = [(s, t) for s, t in cd.items() if (time.time()-t) < COOLDOWN_SAAT*3600]
        if aktif_cooldown:
            satirlar.append(f"\n🕐 Cooldown'da olan coinler ({COOLDOWN_SAAT}sa):")
            for s, t in sorted(aktif_cooldown, key=lambda x: x[1], reverse=True)[:10]:
                kalan_dk = (COOLDOWN_SAAT*3600 - (time.time()-t)) / 60
                satirlar.append(f"  {s.split('/')[0]}: {kalan_dk:.0f} dk kaldı")
        return "\n".join(satirlar)

    def ana_menu_klavye():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
            telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📜 Geçmiş İşlemler", callback_data="panel_gecmis"),
            telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
        )
        markup.row(telebot.types.InlineKeyboardButton("📉 Risk Durumu", callback_data="panel_risk"))
        markup.row(telebot.types.InlineKeyboardButton("🚫 Coin Engelle", callback_data="panel_bloke"))
        markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
        return markup

    def geri_butonu():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
        return markup

    def panel_bloke_metni():
        with bloke_lock:
            bloke_liste = sorted(bloke_coinler)
        satirlar = ["🚫 COIN ENGELLEME\n"]
        if bloke_liste:
            satirlar.append("Şu an engelli coinler (aşağıdan kaldırabilirsin):")
            satirlar.append(", ".join(bloke_liste))
        else:
            satirlar.append("Şu an engelli coin yok.")
        satirlar.append("\nAşağıdaki listeden (açık pozisyonlar + son işlem yapılan "
                         "coinler) birine dokunarak engelleyebilir ya da engeli kaldırabilirsin.")
        return "\n".join(satirlar)

    def panel_bloke_klavye():
        with bloke_lock:
            bloke_liste = sorted(bloke_coinler)
        with state_lock:
            acik_bazlar = sorted({s.split("/")[0].upper() for s in trade_state.keys()})
        with log_lock:
            son_islemler = list(trade_log)[-15:]
        gecmis_bazlar = sorted({t["symbol"].split("/")[0].upper() for t in son_islemler})
        adaylar = sorted(set(acik_bazlar) | set(gecmis_bazlar))

        markup = telebot.types.InlineKeyboardMarkup()
        if bloke_liste:
            for baz in bloke_liste:
                markup.row(telebot.types.InlineKeyboardButton(f"✅ {baz} - engeli kaldır", callback_data=f"blokkaldir_{baz}"))
        for baz in adaylar:
            if baz in bloke_liste:
                continue
            markup.row(telebot.types.InlineKeyboardButton(f"🚫 {baz} - engelle", callback_data=f"blokla_{baz}"))
        markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
        return markup

    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    # v5.19 KULLANICI KARARI (07.08.2026): /sifirla komutu tamamen kaldırıldı
    # - kullanıcı artık manuel limit sıfırlamayı kullanmak istemiyor. Otomatik
    # gün/hafta sıfırlaması (gunluk_haftalik_reset_kontrol) bağımsız çalışmaya
    # devam ediyor, bot süresiz kilitli kalmaz - sadece manuel erken sıfırlama
    # imkânı kaldırıldı.

    @bot.message_handler(commands=["sifirlagecmis"])
    def sifirlagecmis_komutu(msg):
        if not yetkili_mi(msg):
            return
        global trade_log
        with state_lock:
            trade_log = []
        atomik_yaz(TRADE_LOG_PATH, [])
        bot.send_message(msg.chat.id, "🗑️ Tüm işlem geçmişi silindi. Bu geri alınamaz - "
                                        "panel analizindeki kalıcı istatistikler sıfırdan başlıyor.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith(("panel_", "blokla_", "blokkaldir_")))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "panel_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "panel_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_risk":
                bot.edit_message_text(panel_risk_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_bloke":
                bot.edit_message_text(panel_bloke_metni(), call.message.chat.id, call.message.message_id, reply_markup=panel_bloke_klavye())
            elif veri.startswith("blokla_"):
                baz = veri[len("blokla_"):]
                with bloke_lock:
                    bloke_coinler.add(baz)
                bloke_diske_yaz()
                bot.answer_callback_query(call.id, f"{baz} engellendi")
                bot.edit_message_text(panel_bloke_metni(), call.message.chat.id, call.message.message_id, reply_markup=panel_bloke_klavye())
                return
            elif veri.startswith("blokkaldir_"):
                baz = veri[len("blokkaldir_"):]
                with bloke_lock:
                    bloke_coinler.discard(baz)
                bloke_diske_yaz()
                bot.answer_callback_query(call.id, f"{baz} engeli kaldırıldı")
                bot.edit_message_text(panel_bloke_metni(), call.message.chat.id, call.message.message_id, reply_markup=panel_bloke_klavye())
                return
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[PANEL_BUTON] {e}")
            try: bot.answer_callback_query(call.id, "Tamam")
            except Exception: pass


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)


def baslangic_uzlastirma():
    print("[CHECKPOINT] baslangic_uzlastirma() başladı", flush=True)
    global gunluk_pnl, haftalik_pnl
    try:
        gercek_pozlar = exchange.fetch_positions()
        print(f"[CHECKPOINT] fetch_positions() tamamlandı, {len(gercek_pozlar)} pozisyon", flush=True)
        gercek_semboller = {p["symbol"] for p in gercek_pozlar if safe(p.get("contracts")) > 0}
    except Exception as e:
        log.warning(f"[UZLASTIRMA] {e}")
        print(f"[CHECKPOINT] fetch_positions() HATA: {e}", flush=True)
        return
    with state_lock:
        state_semboller = set(trade_state.keys())
    sadece_diskte = state_semboller - gercek_semboller
    if sadece_diskte:
        for sym in sadece_diskte:
            with state_lock:
                durum = trade_state.pop(sym, None)
            if durum:
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel_fiyat = safe(t["last"])
                except Exception:
                    guncel_fiyat = durum.get("sl_guncel", durum["entry"])
                entry = durum["entry"]
                qty = durum.get("qty_orijinal", 0)
                uzlas_yonu = sinyal_yonu(durum.get("tur"))
                pnl_tahmini = (guncel_fiyat - entry) * qty if uzlas_yonu == "long" else (entry - guncel_fiyat) * qty
                with gunluk_lock:
                    gunluk_pnl += pnl_tahmini
                    haftalik_pnl += pnl_tahmini
                gunluk_haftalik_diske_yaz()
                trade_log_kaydet({"symbol": sym, "entry": entry, "exit": guncel_fiyat, "pnl": pnl_tahmini,
                                   "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                   "not": "uzlastirma_tahmini", "tur": durum.get("tur", "bilinmiyor"),
                                   "kaynak": durum.get("acilis_kaynagi", "bilinmiyor")})
                tg(f"ℹ️ Uzlaştırma: {sym} bot çalışmazken kapanmış - ÇOK KABA tahmini PnL≈{pnl_tahmini:+.2f}$ "
                   f"kaydedildi. KESİN TUTAR İÇİN BORSA POZİSYON GEÇMİŞİNİ KONTROL ET.")
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
        durumu_diske_yaz()
    sadece_borsada = gercek_semboller - state_semboller
    if sadece_borsada:
        tg(f"⚠️ UYARI: borsada açık ama state'te olmayan pozisyonlar var: {sorted(sadece_borsada)}")


def tarama_loop():
    tg(f"🚀 SCALP BOT v5.22 başladı (SADE MOD) (MAX_POS={MAX_POS}+{MAX_POS_WEBSOCKET} websocket)\n"
       f"Giriş: sadece fiyat trendi (%{RET_THRESHOLD*100:.0f}+/{RET_WINDOW_BARS*5}dk), hemen açılır\n"
       f"SL={ATR_CARPANI_SL}x ATR (tavan %{MAX_SL_PCT*100:.0f}) | TP: İZ SÜREN, {IZ_SURME_R_ORANI*100:.0f}R'de aktifleşir\n"
       f"Coin cooldown: {COOLDOWN_SAAT} saat\n"
       + ("⚠️⚠️ YENİ POZİSYON AÇILIŞI DURAKLATILDI — panel PnL takibinde gerçek "
          "borsa geçmişiyle tutarsızlık bulundu, kök sebep netleşene kadar sadece "
          "açık pozisyon yönetimi çalışıyor. TRADING_AKTIF=true ile açılabilir.\n"
          if not TRADING_AKTIF else "✅ Yeni pozisyon açılışı AKTİF.\n")
       + "⚠️ Küçük örneklemli backtest - gerçek performans garantisi yoktur.")

    print("[CHECKPOINT] baslangic_uzlastirma() başlıyor", flush=True)
    baslangic_uzlastirma()
    print("[CHECKPOINT] baslangic_uzlastirma() bitti, gunluk_haftalik_reset_kontrol() başlıyor", flush=True)
    gunluk_haftalik_reset_kontrol()
    print("[CHECKPOINT] gunluk_haftalik_reset_kontrol() bitti, ana döngü başlıyor", flush=True)

    while True:
        try:
            print("[CHECKPOINT] tur başladı", flush=True)
            gunluk_haftalik_reset_kontrol()
            print("[CHECKPOINT] limit kontrolü yapılıyor", flush=True)

            if gunluk_limit_kontrolu() or haftalik_limit_kontrolu():
                print("[CHECKPOINT] limit aşıldı, tur atlanıyor", flush=True)
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            # v4.29 YENİ: TRADING_AKTIF=false iken (duraklatma modu) tarama VE
            # teyit kuyruğu tamamen atlanıyor. Eskiden duraklatma sadece pozisyon
            # AÇMAYI engelliyordu ama sinyal arama/teyit kuyruğu mantığı çalışmaya
            # devam ediyordu - bu da TRADING_AKTIF=false olsa bile cooldown hiç
            # uygulanmadığı için aynı coin'in (ör. CYS) her turda yeniden
            # bulunup Telegram'a defalarca "⏳ teyit kuyruğunda" mesajı atmasına
            # yol açıyordu (gerçek örnek: CYS 5+ kez art arda, 04.08.2026 gecesi).
            # Artık duraklatma modunda tarama_loop sadece NABIZ basıp bekliyor -
            # gerçek sessizlik. Açık pozisyon yönetimi (manage_loop) etkilenmedi.
            if not TRADING_AKTIF:
                with bekleyen_lock:
                    kuyruk_uzunluk = len(bekleyen_sinyaller)
                with state_lock:
                    acik_poz = len(trade_state)
                log.info(f"[NABIZ] DURAKLATILDI - tarama atlanıyor | teyit_kuyrugu={kuyruk_uzunluk} | "
                         f"acik_pozisyon={acik_poz}/{MAX_POS + MAX_POS_WEBSOCKET}")
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            print("[CHECKPOINT] bos_slot hesaplanıyor", flush=True)
            with state_lock:
                # v5.3: sadece "tarama" kaynaklı açık pozisyonlar sayılıyor -
                # websocket'in kendi ayrı MAX_POS_WEBSOCKET havuzu var, ana
                # taramanın bos_slot hesabını etkilemiyor.
                tarama_acik = sum(1 for d in trade_state.values() if d.get("acilis_kaynagi", "tarama") == "tarama")
                bos_slot = MAX_POS - tarama_acik
            if bos_slot <= 0:
                print("[CHECKPOINT] bos_slot yok, tur atlanıyor", flush=True)
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            btc_bullish = True

            print("[CHECKPOINT] piyasa_izleyici_aday_havuzu() çağrılıyor (fetch_tickers)", flush=True)
            adaylar_havuzu = piyasa_izleyici_aday_havuzu()
            print(f"[CHECKPOINT] aday_havuzu tamamlandı: {len(adaylar_havuzu)} coin", flush=True)
            acilan_sayisi = 0

            # v4.23 YENİ: AJAN 0'ın (websocket gözcüsü) dinlediği coin listesini
            # güncel aday havuzuyla senkronlar - böylece websocket sadece zaten
            # ilgilendiğimiz coinleri dinler, gereksiz genişlemez.
            print("[CHECKPOINT] ws_abonelik_guncelle() çağrılıyor", flush=True)
            ws_abonelik_guncelle(adaylar_havuzu)
            print("[CHECKPOINT] ws_abonelik_guncelle() bitti", flush=True)

            # v5.14 KULLANICI KARARI (06.08.2026): "girişler yanlış tarafta
            # bırakıyor, gerçek pump yakalasa sorun olmaz" tespiti üzerine -
            # backtest ile doğrulandı (35 coin/6 gün): tetik mumundan SONRAKİ
            # mum da yükselmeye devam ediyorsa gir, dönmüşse HİÇ girme. Bu,
            # işlem sayısını %35 azalttı ama ortalama R'yi ikiye katladı
            # (+0.074R -> +0.147R) ve toplamı artırdı (+28.78R -> +37.22R) -
            # bugünkü tüm filtre denemeleri arasında İLK KEZ hem kaliteyi hem
            # toplamı birlikte iyileştiren tek değişiklik. SADECE AJAN 1
            # (tarama) için - AJAN 0 (websocket) kendi hızlı 20sn teyidini
            # koruyor, buna dokunulmadı.
            # v5.15: kuyruk artık HEM tarama HEM websocket kaynaklı sinyalleri
            # içeriyor - bu yüzden döngü artık sadece tarama'nın bos_slot'una
            # göre KESİLMİYOR (öyle olsaydı tarama slotları doluyken
            # websocket'in kendi boş slotu olsa bile işlenmezdi). Gerçek
            # slot/kaynak kontrolü zaten islem_acici_pozisyon_ac() içinde
            # kaynak bazlı atomik olarak yapılıyor (bkz. v5.3 notu).
            with bekleyen_lock:
                kuyruk_semboller = list(bekleyen_sinyaller.keys())
            for sym in kuyruk_semboller:
                with bekleyen_lock:
                    p = bekleyen_sinyaller.get(sym)
                if p is None:
                    continue
                # 10 dakikadan eski kalmış (nadiren olur) - bayat, at
                # v5.20: bayat sayma süresi 600sn->900sn - AJAN 0 artık 2 mum
                # (en fazla ~10dk) bekleyebiliyor, 600sn'lik eski sınır bunu
                # tam ortasında kesebilirdi.
                if (time.time() - p["zaman"]) > 900:
                    with bekleyen_lock:
                        bekleyen_sinyaller.pop(sym, None)
                    continue
                df5_confirm = get_df(sym, "5m", 5)
                if df5_confirm is None or len(df5_confirm) < 2:
                    continue
                son_mum = df5_confirm.iloc[-1]
                if int(son_mum["ts"]) <= p["tetik_ts"]:
                    continue  # henüz yeni mum kapanmamış, beklemeye devam

                gereken = p.get("gereken_teyit", 1)
                if son_mum["close"] < p["sinyal_fiyat"]:
                    with bekleyen_lock:
                        bekleyen_sinyaller.pop(sym, None)
                    log.info(f"[DEVAM_TEYIDI_IPTAL] {sym} mum döndü ({p.get('gecen_teyit',0)+1}. teyit mumunda), giriş iptal edildi")
                    continue

                gecen = p.get("gecen_teyit", 0) + 1
                if gecen < gereken:
                    # bu mum teyit etti ama yeterli sayıya ulaşmadı - kuyrukta
                    # kalıp bir SONRAKİ mumu bekleyecek (v5.20: AJAN 0 için 2
                    # ardışık mum şartı).
                    with bekleyen_lock:
                        if sym in bekleyen_sinyaller:
                            bekleyen_sinyaller[sym]["gecen_teyit"] = gecen
                            bekleyen_sinyaller[sym]["tetik_ts"] = int(son_mum["ts"])
                    continue

                with bekleyen_lock:
                    bekleyen_sinyaller.pop(sym, None)
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym):
                    continue
                kaynak = p.get("kaynak", "tarama")
                ajan_etiket = "AJAN 0 (websocket)" if kaynak == "websocket" else "AJAN 1"
                if sinyal_mesaji_gonder_mi(sym):
                    tg(f"✅ {ajan_etiket}: {sym} devam teyidi geçti ({gecen}/{gereken} mum) — AJAN 2'ye 'şimdi aç' komutu veriliyor")
                try:
                    islem_acici_pozisyon_ac({"symbol": sym, "entry": float(son_mum["close"]), "atr": p["atr"],
                                              "skor": p["skor"], "tur": p["tur"]}, kaynak=kaynak)
                except Exception as e:
                    log.error(f"[ISLEM_ACICI_BEKLENMEYEN_HATA] {sym}: {e}")
                    tg(f"🚨 {sym} açılışında beklenmeyen hata oluştu, cooldown'a alındı: {e}")
                    acilis_basarisiz_cooldown_uygula(sym)
                acilan_sayisi += 1

            # v4.18 YENİ: kalan adayları PARALEL kontrol et - tek tek sırayla
            # değil, ThreadPoolExecutor ile aynı anda birden çok sembol için
            # ağ isteği gönderilir. Bu sayede aynı 60sn'lik tarama aralığında
            # çok daha fazla coin kontrol edilebiliyor, hızlı hareket eden
            # coinlerin bir sonraki tura kalıp kaçırılma ihtimali azalıyor.
            taranacaklar = []
            for sym in adaylar_havuzu:
                with state_lock:
                    if sym in trade_state:
                        continue
                with bekleyen_lock:
                    zaten_bekliyor = sym in bekleyen_sinyaller
                if cooldown_da_mi(sym) or zaten_bekliyor:
                    continue
                taranacaklar.append(sym)

            bulunan_sinyaller = []  # (sym, sinyal) sırayla - havuz zaten skor sıralı
            if taranacaklar:
                with ThreadPoolExecutor(max_workers=TARAMA_PARALEL_WORKER) as havuz:
                    gelecekler = {havuz.submit(sembol_sinyal_kontrol_tumu, sym, btc_bullish): sym
                                  for sym in taranacaklar}
                    sonuclar = {}
                    for gelecek in as_completed(gelecekler):
                        sym = gelecekler[gelecek]
                        try:
                            sonuclar[sym] = gelecek.result()
                        except Exception as e:
                            log.warning(f"[PARALEL_SONUC] {sym}: {e}")
                            sonuclar[sym] = None
                # orijinal skor sırasını koru (en canlı coin önce işlensin)
                for sym in taranacaklar:
                    sinyal = sonuclar.get(sym)
                    if sinyal:
                        bulunan_sinyaller.append((sym, sinyal))

            for sym, sinyal in bulunan_sinyaller:
                # çift kontrol - paralel tarama sırasında state değişmiş olabilir
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym):
                    continue

                # v5.14: hemen açmak yerine "devam teyidi" kuyruğuna alınıyor
                # - bkz. yukarıdaki kuyruk işleme bloğundaki not.
                with bekleyen_lock:
                    if sym in bekleyen_sinyaller:
                        continue
                    bekleyen_sinyaller[sym] = {"sinyal_fiyat": sinyal["entry"], "atr": sinyal["atr"],
                                                "skor": sinyal["skor"], "tur": sinyal["tur"],
                                                "tetik_ts": sinyal["tetik_ts"], "zaman": time.time(),
                                                "kaynak": "tarama", "gecen_teyit": 0, "gereken_teyit": 1}
                if sinyal_mesaji_gonder_mi(sym):
                    tg(f"🔍 AJAN 1: {sym} trend sinyali bulundu, bir sonraki mumun da yükselmesi bekleniyor (devam teyidi)")

            print(f"[CHECKPOINT] tur tamamlandı, acilan_bu_tur={acilan_sayisi}", flush=True)

            # v4.19 YENİ: her turda NABIZ logu - "log'da hiçbir şey yok" ile
            # "bot çalışıyor ama sinyal bulamıyor" birbirinden ayırt edilemiyordu
            # (bu turdan önce sadece sinyal bulununca/hata olunca log basılıyordu).
            # v4.33 DÜZELTME: kullanıcı talebiyle her turda değil, her 5 turda
            # bir (yaklaşık 5-8 dakikada bir) basılıyor - Railway log hacmini
            # azaltmak için. Tarama/güvenlik mantığı HER turda aynen çalışmaya
            # devam ediyor, sadece bu bilgi logunun sıklığı azaldı.
            _nabiz_sayac["deger"] += 1
            if _nabiz_sayac["deger"] % 5 == 0:
                with bekleyen_lock:
                    kuyruk_uzunluk = len(bekleyen_sinyaller)
                log.info(f"[NABIZ] tur tamam | havuz={len(adaylar_havuzu)} | "
                         f"teyit_kuyrugu={kuyruk_uzunluk} | acik_pozisyon(tarama)={MAX_POS - bos_slot}/{MAX_POS} | "
                         f"acilan_bu_tur={acilan_sayisi}")

            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


def manage_loop():
    global gunluk_pnl, haftalik_pnl
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(3)
                continue

            for sym in semboller:
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    tg(f"⏱️ {sym} — max tutma süresi ({MAX_HOLD_SAAT}sa) aşıldı, piyasa fiyatından kapatılıyor")
                    pozisyonu_tamamen_kapat(sym, sebep="max_hold_timeout")
                    continue

                if durum.get("kurulum_tamamlanmadi"):
                    continue

                try:
                    t = exchange.fetch_ticker(sym)
                    guncel_fiyat = safe(t["last"])
                    durum_yonu = sinyal_yonu(durum.get("tur"))
                    sl_ihlali = (guncel_fiyat <= durum["sl_guncel"]) if durum_yonu == "long" else (guncel_fiyat >= durum["sl_guncel"])
                    if guncel_fiyat > 0 and sl_ihlali:
                        tg(f"🛡️ YAZILIM SL GÜVENLİK AĞI: {sym} fiyatı ({guncel_fiyat:.6f}) "
                           f"SL seviyesini ({durum['sl_guncel']:.6f}) geçti — borsadaki emir ne "
                           f"durumda olursa olsun bot kendisi HEMEN kapatıyor.")
                        pozisyonu_tamamen_kapat(sym, sebep="yazilim_sl_guvenlik_agi")
                        continue
                except Exception as e:
                    log.warning(f"[SL_GUVENLIK_AGI] {sym}: fiyat kontrol edilemedi: {e}")
                    guncel_fiyat = None

                # v5.0 KULLANICI KARARI: RSI tabanlı "erken uyarı" mekanizması
                # KALDIRILDI - kullanıcı "sadece trend, başka hiçbir şey
                # ekleme" dedi. Çıkış artık sadece SL + iz süren TP.

                if guncel_fiyat and guncel_fiyat > 0:
                    try:
                        iz_yonu = sinyal_yonu(durum.get("tur"))
                        entry_iz = durum["entry"]
                        qty_iz = durum.get("qty_orijinal", 0)
                        anlik_kar = (guncel_fiyat - entry_iz) * qty_iz if iz_yonu == "long" else (entry_iz - guncel_fiyat) * qty_iz
                        en_iyi_kar = durum.get("en_iyi_kar")
                        r_risk_fiyat = durum.get("r_risk") or 0
                        risk_dolar_iz = r_risk_fiyat * qty_iz
                        iz_esik = risk_dolar_iz * IZ_SURME_R_ORANI if risk_dolar_iz > 0 else HEDEF_NET_KAR_USDT
                        # v5.4: geri çekme payı artık AYRI ve daha dar (0.30R)
                        # - aktifleşme (iz_esik, 0.50R) hâlâ geniş, nefes payı
                        # koruyor, ama bir kez aktifleştikten sonra kâr daha
                        # sıkı korunuyor (bkz. IZ_SURME_GERI_COKME_ORANI notu).
                        gc_esik = risk_dolar_iz * IZ_SURME_GERI_COKME_ORANI if risk_dolar_iz > 0 else HEDEF_NET_KAR_USDT
                        # v4.28 KRİTİK DÜZELTME: eskiden bu blok SADECE
                        # anlik_kar >= iz_esik iken çalışıyordu. Yani iz sürme
                        # aktifleştikten SONRA fiyat sert düşüp anlik_kar eşiğin
                        # ALTINA inerse (ama hâlâ başabaşın üstündeyse), TÜM
                        # kontrol atlanıyordu - "en iyi kârdan $X geri çekilirse
                        # kapat" kuralı hiç değerlendirilmiyordu, pozisyon sadece
                        # başabaş SL'e kadar kâr geri verebiliyordu (istenenden
                        # daha fazla). Artık iz sürme bir kez aktifleşince
                        # (breakeven_cekildi=True), anlik_kar eşiğin altına
                        # düşse bile kapanma kontrolü çalışmaya devam ediyor.
                        if anlik_kar >= iz_esik or durum.get("breakeven_cekildi"):
                            if anlik_kar >= iz_esik and not durum.get("breakeven_cekildi"):
                                try:
                                    if durum.get("sl_emir_id"):
                                        exchange.cancel_order(durum["sl_emir_id"], sym)
                                except Exception as e_cancel:
                                    log.warning(f"[IZ_SURME_IPTAL] {sym}: eski SL iptal edilemedi (görmezden geliniyor): {e_cancel}")
                                try:
                                    taze_pos = exchange.fetch_positions([sym])
                                    taze_giris = next((safe(p.get("entryPrice")) for p in taze_pos
                                                        if safe(p.get("contracts")) > 0), None)
                                    be_referans = taze_giris if taze_giris and taze_giris > 0 else entry_iz
                                    guvenlik_payi = KOMISYON_PCT * 2
                                    if iz_yonu == "long":
                                        be_fiyat = float(exchange.price_to_precision(sym, be_referans * (1 + guvenlik_payi)))
                                    else:
                                        be_fiyat = float(exchange.price_to_precision(sym, be_referans * (1 - guvenlik_payi)))
                                    be_yon_iz = "sell" if iz_yonu == "long" else "buy"
                                    be_emir = exchange.create_order(sym, "market", be_yon_iz, qty_iz, None,
                                                                     {"reduceOnly": True, "stopLossPrice": be_fiyat})
                                    with state_lock:
                                        durum["sl_emir_id"] = be_emir.get("id")
                                        durum["sl_guncel"] = be_fiyat
                                        durum["breakeven_cekildi"] = True
                                    durumu_diske_yaz()
                                    tg(f"🔒 {sym} — iz sürme AKTİFLEŞTİ (${anlik_kar:.2f} kâr, eşik≈${iz_esik:.2f}), SL başabaşa çekildi. "
                                       f"Fiyat lehte gittikçe takip edecek, en iyi kârdan ${gc_esik:.2f} "
                                       f"geri çekilirse kapanacak.")
                                except Exception as e:
                                    log.warning(f"[IZ_SURME_BASABAS] {sym}: yeni SL yerleştirilemedi: {e}")
                                    tg(f"⚠️ {sym} — iz sürme ${anlik_kar:.2f} kârda aktifleşmeye çalıştı ama "
                                       f"başabaş SL emri yerleştirilemedi: {e}. Eski SL geçerliliğini koruyor, "
                                       f"iz sürme takibi yine de devam ediyor.")
                            if en_iyi_kar is None or anlik_kar > en_iyi_kar:
                                with state_lock:
                                    durum["en_iyi_kar"] = anlik_kar
                                durumu_diske_yaz()
                            elif anlik_kar <= en_iyi_kar - gc_esik:
                                tg(f"🎯 İZ SÜREN TP: {sym} en iyi kâr ${en_iyi_kar:.2f} idi, "
                                   f"${gc_esik:.2f} geri çekildi (${anlik_kar:.2f}) — kapatılıyor.")
                                pozisyonu_tamamen_kapat(sym, sebep="iz_suren_tp")
                                continue
                    except Exception as e:
                        log.warning(f"[IZ_SURME] {sym}: {e}")

                try:
                    pozlar = exchange.fetch_positions([sym])
                    gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
                except Exception as e:
                    log.warning(f"[MANAGE] {sym} pozisyon sorgu hatası: {e}")
                    continue

                if not gercek_pos:
                    with state_lock:
                        durum2 = trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    for t in (durum2 or {}).get("tp_emirleri", []):
                        if t.get("dolu") or not t.get("id"):
                            continue
                        try:
                            emir_durumu = exchange.fetch_order(t["id"], sym)
                            if emir_durumu.get("status") in ("closed", "filled"):
                                t["dolu"] = True
                                continue
                        except Exception:
                            pass
                        try:
                            exchange.cancel_order(t["id"], sym)
                        except Exception:
                            pass
                    if durum2 and durum2.get("sl_emir_id"):
                        try:
                            exchange.cancel_order(durum2["sl_emir_id"], sym)
                        except Exception:
                            pass
                    with cooldown_lock:
                        son_kapanis_zamani[sym] = time.time()
                    cooldown_diske_yaz()
                    if durum2:
                        cikis_fiyat = None
                        if durum2.get("sl_emir_id"):
                            try:
                                sl_detay = exchange.fetch_order(durum2["sl_emir_id"], sym)
                                gercek_sl_dolum = safe(sl_detay.get("average")) or safe(sl_detay.get("price"))
                                if gercek_sl_dolum and gercek_sl_dolum > 0:
                                    cikis_fiyat = gercek_sl_dolum
                            except Exception:
                                pass
                        if not cikis_fiyat:
                            try:
                                t = exchange.fetch_ticker(sym)
                                cikis_fiyat = safe(t["last"])
                            except Exception:
                                cikis_fiyat = durum2["sl_guncel"]
                        entry = durum2["entry"]
                        tp_emirleri = durum2.get("tp_emirleri", [])
                        kapanis_yonu = sinyal_yonu(durum2.get("tur"))
                        dolu_qty_toplam = sum(t.get("qty", 0) for t in tp_emirleri if t.get("dolu"))
                        if kapanis_yonu == "long":
                            pnl_kademeler = sum((t["fiyat"] - entry) * t.get("qty", 0) for t in tp_emirleri if t.get("dolu"))
                        else:
                            pnl_kademeler = sum((entry - t["fiyat"]) * t.get("qty", 0) for t in tp_emirleri if t.get("dolu"))
                        kalan_qty = max(durum2["qty_orijinal"] - dolu_qty_toplam, 0)
                        pnl_kalan = (cikis_fiyat - entry) * kalan_qty if kapanis_yonu == "long" else (entry - cikis_fiyat) * kalan_qty
                        pnl_tahmini = pnl_kademeler + pnl_kalan
                        with gunluk_lock:
                            gunluk_pnl += pnl_tahmini
                            haftalik_pnl += pnl_tahmini
                        gunluk_haftalik_diske_yaz()
                        tum_tp_dolu = all(t.get("dolu") for t in tp_emirleri) and len(tp_emirleri) > 0
                        if tum_tp_dolu:
                            sebep_etiket = "tum_tp_tamamlandi"
                        elif durum2.get("breakeven_cekildi"):
                            sebep_etiket = "SL_basabasta_TP1_sonrasi"
                        else:
                            sebep_etiket = "SL_ilk_TPden_once"
                        trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat,
                                           "pnl": pnl_tahmini, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                           "not": sebep_etiket, "tur": durum2.get("tur", "bilinmiyor"),
                                           "kaynak": durum2.get("acilis_kaynagi", "bilinmiyor")})
                        tg(f"✅ {sym} pozisyonu tamamen kapandı [{sebep_etiket}] (tahmini PnL≈{pnl_tahmini:+.2f}$ — "
                           f"komisyon dahil değil, kesin tutar borsa Pozisyon Geçmişi'nden teyit edilmeli)")
                    continue

                guncel_qty = safe(gercek_pos.get("contracts"))
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue

                degisti = False
                for t in durum["tp_emirleri"]:
                    if t.get("dolu"):
                        continue
                    try:
                        emir_durumu = exchange.fetch_order(t["id"], sym)
                        if emir_durumu.get("status") in ("closed", "filled"):
                            t["dolu"] = True
                            degisti = True
                    except Exception:
                        pass

                if degisti and not durum.get("breakeven_cekildi"):
                    try:
                        if durum.get("sl_emir_id"):
                            exchange.cancel_order(durum["sl_emir_id"], sym)
                    except Exception:
                        pass
                    try:
                        yeni_sl_fiyat = float(exchange.price_to_precision(sym, durum["entry"]))
                        be_yonu2 = "sell" if sinyal_yonu(durum.get("tur")) == "long" else "buy"
                        yeni_sl_emri = exchange.create_order(sym, "market", be_yonu2, guncel_qty, None,
                                                              {"reduceOnly": True, "stopLossPrice": yeni_sl_fiyat})
                        with state_lock:
                            durum["sl_emir_id"] = yeni_sl_emri.get("id")
                            durum["sl_guncel"] = yeni_sl_fiyat
                            durum["breakeven_cekildi"] = True
                        durumu_diske_yaz()
                        tg(f"🔒 {sym} — ilk TP vuruldu, SL başabaşa ({yeni_sl_fiyat:.6f}) çekildi. "
                           f"Bu andan sonra pozisyon en kötü ihtimalle sıfır zararla kapanır.")
                    except Exception as e:
                        log.warning(f"[BREAKEVEN] {sym}: {e}")
                elif degisti:
                    durumu_diske_yaz()

            # v5.7 KULLANICI KARARI (06.08.2026): 10sn -> 3sn. Gerekçe: BTW
            # örneğinde "en iyi kâr $0.32, gerçekleşen $0.1857" arasında
            # beklenenden (~$0.11 geri çekme payı) biraz fazla fark vardı -
            # 10sn'lik kontrol aralığında fiyatın karar anıyla gerçek market
            # emri dolumu arasında kayması (slippage) buna katkıda bulunuyor.
            # Kontrol sıklığını artırmak bu gecikmeyi azaltır - strateji
            # mantığına dokunmuyor, sadece tepki hızını artırıyor.
            time.sleep(3)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(3)


if __name__ == "__main__":
    print("SCALP BOT v5.22 BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bloke_diskten_yukle()
    trade_log_yukle()
    gunluk_haftalik_diskten_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    threading.Thread(target=ws_gozcu_baslat, daemon=True).start()
    tarama_loop()
