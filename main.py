#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
LIVE BOT v3.9 — 1D+4H+1H Uyum + LONG-only (GERÇEK PARA, SHORT kod içinde ama kapalı)
14 Ağustos 2026 (v2.0) → 21 Ağustos 2026 (v2.1) → 22 Ağustos 2026 (v2.2) → 14 Eylül 2026 (v3.6 → v3.7 → v3.8 → v3.9)

v3.9 (14.09.2026, kullanıcı kararıyla — "BTC'den bağımsız pump yapan coinleri kaçırmayalım" isteğiyle bulundu):
  v3.8'deki "BTC düşerse yeni pozisyonu TAMAMEN durdur" kararı geri
  alındı - orijinal kodun kendi geçmişinde bu tam olarak denenip terk
  edilmişti ("coin'leri tamamen engellemek yanlış çıkmıştı"). Yeni
  yaklaşım: MAX_POS yine yarıya iner (v3.7 davranışı), AMA o dönemde
  girecek coin için trend gücü eşiği YÜKSELTİLİR (MIN_4H_TREND_GUCU_PCT_TEMKINLI=%4.0, normalde %2.0). Böylece BTC
  zayıfken sadece BTC'den GERÇEKTEN bağımsız, güçlü hareket eden
  coinler işleme girebilir - zayıf/sınırda sinyaller elenir. "Hiçbir
  şey yapma" (v3.7) ile "her şeyi durdur" (v3.8) arasında orta yol.

v3.8 (14.09.2026, kullanıcı kararıyla — "piyasa dönünce bot bocalıyor,
kârlar eriyor" gözlemiyle bulundu):
  TEMKİNLİ MOD artık BTC'nin 1D+4H trendi düşüşe döndüğünde YENİ pozisyon
  açmayı TAMAMEN durduruyor (önceden sadece MAX_POS yarıya iniyordu).
  Açık pozisyonlara DOKUNULMAZ - onlar kendi SL/TP/kısmi kâr alma
  mantığıyla yönetilmeye devam eder.

  DEĞERLENDİRİLİP REDDEDİLEN ALTERNATİF: "trend dönünce pozisyonu
  tersine çevir / SHORT'a geç". Bu, kodun kendi geçmişinde zaten
  denenmiş ve başarısız olmuş bir yaklaşımdı - SHORT özelliği
  10.09.2026'da eklenip ilk gerçek işlemde (SLX) "short squeeze" ile
  kayıp verip 11.09.2026'da kapatılmıştı. Trend dönüş sinyali (1D+4H+1H
  üçünün de dönmesi) doğası gereği GEÇ gelir - bu noktada pozisyonu
  tersine çevirmek, geçici bir sıçramaya (whipsaw) yakalanıp hem eski
  hem yeni yönde kayıp verme riskini artırır. Bu yüzden tek yönlü,
  daha temkinli bir önlem seçildi: yeni risk eklemeyi durdur, var olan
  pozisyonlara müdahale etme.

v3.7 (14.09.2026, kullanıcı kararıyla — "KASA BÜYÜMESİ" isteğiyle bulundu):
  1) KISMİ KÂR ALMA + BREAKEVEN: pozisyon %1.5'e ulaşınca miktarın
     yarısı kapatılır (o kâr garanti altına alınır), kalan kısmın SL'i
     girişe (breakeven + komisyon payı) çekilir. Amaç: "%5 hedefe
     ulaşmadan pozisyon geri dönüp o ana kadarki kâr buharlaşıyor"
     sorununu azaltmak.
  2) KÜÇÜK BAKİYEDE MARJİN TABANI DÜZELTMESİ: hesapla_marjin() artık
     min(MARJIN_TABAN_USDT, bakiye/MAX_POS) kullanıyor. Önceden küçük
     bakiyelerde (örn. 4.26$) sabit $2 taban, bakiyenin ~%47'sini tek
     işleme kilitleyip MAX_POS'un çeşitlendirme amacını fiilen boşa
     çıkarıyordu. Artık bakiye küçükken pozisyon boyutu da küçülüyor,
     bakiye büyüyünce (MARJIN_TABAN_USDT*MAX_POS'u geçince) normal
     tabana otomatik dönüyor.
  ⚠️ Her iki değişiklik de henüz canlıda test edilmedi.

v3.6 (14.09.2026, kullanıcı kararıyla — GERÇEK VERİ ANALİZİNE DAYALI):
  161 gerçek işlemlik canlı log analiz edildi. Sonuç:
    - hizli_tp (19 işlem): net +18.17$, %100 kazanma → giriş YÖNÜ doğru,
      ama bu YALNIZCA işlemlerin %12'sinde gerçekleşiyor.
    - max_hold_timeout (128 işlem, toplamın %80'i): net -7.11$, %44 kazanma
      → botun asıl kanaması burada. 1D+4H+1H uyumu tek başına yeterince
      ayrıştırıcı değil, çok sık oluşan düşük-bilgi-değerli bir durum.
    - sl + sl_borsada_onceden (14 işlem): net -13.84$, %0 kazanma → nadir
      ama sert kayıplar (genelde önceden aşırı pompalanmış coinlerde).
  Net: -2.78$ / 161 işlem.

  Bu bulguya dayanarak İKİ YENİ FİLTRE eklendi (giriş sinyalini daha
  seçici hale getirmek için, backtest'e değil canlı veriye dayalı):

  1) HACİM TEYİDİ: sinyal anındaki 15m mumun hacmi, önceki 20 mumun
     ortalamasının en az HACIM_TEYIT_KATSAYI katı olmalı. Amaç: "sessiz"
     (gerçek alım ilgisi olmayan) fiyat hareketlerini elemek - bunlar
     genelde ne hedefe ulaşıyor ne net ters dönüyor, sadece max_hold'a
     kadar sürünüp hafif eksi kapanıyor (log'daki 128 işlemin çoğu bu).

  2) PUMP FİLTRESİ (coin zaten aşırı pompalanmışsa LONG girişi reddet):
     24 saatlik değişim PUMP_FILTRE_ESIK_PCT üzerindeyse giriş yapılmaz.
     Log'daki en sert SL kayıplarının (CATI, PROS, ZEN, DOOD, BR, PIEVERSE)
     ortak paterni: coin zaten güçlü yükselmişken girilmiş, hemen ardından
     sert geri çekilme SL'i tetiklemiş - klasik "tepede giriş" riski.

  Her iki eşik de (HACIM_TEYIT_KATSAYI=1.5, PUMP_FILTRE_ESIK_PCT=15.0)
  ilk tahmin değerleridir - birkaç günlük canlı veriyle (panel_analiz)
  gözden geçirilmesi gerekir.

  API YÜKÜNÜ ARTIRMAMAK İÇİN: pump filtresi ayrı fetch_ticker çağrısı
  yapmıyor, aday_havuzu()'nun zaten çektiği fetch_tickers() sonucunu
  kısa süreliğine (TICKER_CACHE_SN) önbellekleyip oradan okuyor.

v2.1 (21.08.2026, kullanıcı kararıyla):
  1) TEMKİNLİ MOD — BTC'nin kendi 1D+4H trendi ikisi de düşüşe dönerse
     MAX_POS geçici olarak yarıya iner (açık pozisyonlar etkilenmez).
  2) İZLEME LİSTESİ AJANI — paper_bot_v2'de test edildi, genel taramanın
     (en hareketli 80 coin) kaçırabileceği "sessiz" (büyük hareket
     olmadan 1D+4H'ye uyan) coinleri ayrı bir listede (max 10) izler.

v2.2 (22.08.2026, kullanıcı kararıyla): "bazı coinler kâra geçiyor sonra
birden düşüyor, sürekli kâr alan hızlı çıkan bot olsun, saatlerce
beklenmesin" isteğiyle:
  - İz sürme aktifleşme eşiği 1.0R'den 0.4R'ye indirildi
  - Geri çekilme payı 0.3R'den 0.15R'ye indirildi
  - Max tutma süresi 24 saatten 8 saate indirildi
  Bedeli: büyük/yavaş gelişen trend hareketlerinde daha erken çıkıp
  potansiyel ek kârı kaçırma riski artar - kullanıcı bu takası bilerek
  kabul etti (kârı erken koru > büyük hareketi tam yakala).

KULLANICI KARARI: Eski live_bot (v1.7, 4H+1H+15m, LONG+SHORT) durduruldu.
Onun yerine, paper_bot_v2'de (sanal) test edilen ve daha güçlü çekirdek
performans gösteren strateji gerçek paraya alındı.

TREND DÖNÜŞ AJANI (hem eski live_bot'ta hem paper_bot_v2'de test edildi,
İKİSİNDE DE net zarar verdiği görüldü) - KULLANICI KARARIYLA VARSAYILAN
KAPALI. Kod silinmedi, TREND_AJANI_AKTIF=true ile tekrar açılabilir.

MANTIK:
  1) 1D trend YUKARI olmalı (20 periyot MA)
  2) 4H trend YUKARI olmalı
  3) 1H trend YUKARI olmalı
  4) Üçü uyumlu değilse sinyal YOK
  5) 15m'de swing dip + dönüş onayı → LONG (SADECE LONG)
  6) [v3.6 YENİ] Hacim teyidi: son mum hacmi ortalamanın üstünde olmalı
  7) [v3.6 YENİ] Pump filtresi: coin 24s'te aşırı pompalanmışsa reddet

Çıkış: SL (swing bazlı, taban %5) + SABİT %5 HEDEF (v3.0: iz sürme
KALDIRILDI, hedefe değer değmez hemen kapanır - "hızlı gir çık" modu).

⚠️ DÜRÜSTLÜK NOTU: v3.6'daki iki yeni filtre, 161 işlemlik GERÇEK canlı
veri analizine dayanıyor (backtest'e değil). Ama bu filtrelerin kendisi
henüz canlıda test edilmedi - etkilerini görmek için birkaç günlük yeni
veri toplanıp panel_analiz ile tekrar değerlendirilmesi gerekir.
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
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                     stream=sys.stdout, force=True)
log = logging.getLogger("LIVE_BOT_V2")

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
    raise RuntimeError("MY_CHAT_ID ortam değişkeni eksik.")

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
    return chat_id == CHAT_ID


SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

# ── GERÇEK işlem parametreleri ──
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.20"))
MARJIN_TABAN_USDT = float(os.getenv("MARJIN_TABAN_USDT", "2.0"))
MARJIN_TAVAN_USDT = float(os.getenv("MARJIN_TAVAN_USDT", "50.0"))
SABIT_MARJIN_USDT = float(os.getenv("SABIT_MARJIN_USDT", "2.0"))
LEV = 10
NOTIONAL = SABIT_MARJIN_USDT * LEV  # sadece eski koddaki referanslar için tutuluyor
MAX_POS = int(os.getenv("MAX_POS", "3"))

LOOKBACK_15M = 20
MA_PERIYOT = 20
SL_BUFFER_PCT = 0.015
MIN_SL_PCT = 0.05
TARGET_MAX_LOSS_USDT = float(os.getenv("TARGET_MAX_LOSS_USDT", "0.90"))
MAX_SL_PCT_TAVAN = TARGET_MAX_LOSS_USDT / NOTIONAL

# ════════════════════════════════════════════
# KULLANICI KARARI (01.09.2026): FIRSATÇI STRATEJİYE GEÇİŞ
# ════════════════════════════════════════════
GIRIS_MAX_DIP_MESAFE = float(os.getenv("GIRIS_MAX_DIP_MESAFE", "0.02"))
MIN_4H_TREND_GUCU_PCT = float(os.getenv("MIN_4H_TREND_GUCU_PCT", "2.0"))
HIZLI_HEDEF_PCT = float(os.getenv("HIZLI_HEDEF_PCT", "0.05"))
SHORT_AKTIF = os.getenv("SHORT_AKTIF", "false").lower() == "true"
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
COOLDOWN_SAAT = 1.0
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "8"))
KONTROL_ARALIGI_SN = 60
ADAY_HAVUZU_BUYUKLUGU = 80

# ════════════════════════════════════════════
# v3.6 YENİ: HACİM TEYİDİ + PUMP FİLTRESİ
# ════════════════════════════════════════════
# KULLANICI KARARI (14.09.2026, 161 işlemlik gerçek canlı veri analiziyle
# bulundu): işlemlerin %80'i (128/161) max_hold_timeout ile kapanıyor ve
# bu grup net zarar veriyor (-7.11$, %44 kazanma). 1D+4H+1H uyumu tek
# başına yeterince ayrıştırıcı değil. Hacim teyidi eklenerek "gerçek bir
# hareketin başında mıyız yoksa durgun/sessiz bir yükselişte mi
# sıkışacağız" ayrımı yapılmaya çalışılıyor.
# ⚠️ Bu eşik canlıda henüz test edilmedi - ilk tahmin değeri. Birkaç
# günlük veri sonrası panel_analiz ile gözden geçirilmeli.
HACIM_TEYIT_AKTIF = os.getenv("HACIM_TEYIT_AKTIF", "true").lower() == "true"
HACIM_TEYIT_KATSAYI = float(os.getenv("HACIM_TEYIT_KATSAYI", "1.5"))
HACIM_TEYIT_PERIYOT = int(os.getenv("HACIM_TEYIT_PERIYOT", "20"))

# KULLANICI KARARI (14.09.2026, aynı analiz): en sert SL kayıplarının
# (CATI, PROS, ZEN, DOOD, BR, PIEVERSE - toplam ~14 işlem, -13.84$) ortak
# paterni: coin girişten önce zaten güçlü pompalanmıştı, hemen ardından
# sert geri çekilme SL'i tetikledi. Pump filtresi bu "tepede giriş"
# riskini azaltmaya çalışıyor.
# ⚠️ Bu eşik de canlıda henüz test edilmedi - ilk tahmin değeri.
PUMP_FILTRE_AKTIF = os.getenv("PUMP_FILTRE_AKTIF", "true").lower() == "true"
PUMP_FILTRE_ESIK_PCT = float(os.getenv("PUMP_FILTRE_ESIK_PCT", "15.0"))

# API yükünü artırmamak için: aday_havuzu()'nun zaten çektiği
# fetch_tickers() sonucu kısa süreliğine önbelleklenir, pump_coin_mu()
# bu önbellekten okur (ekstra API çağrısı yapmaz).
TICKER_CACHE_SN = 30
_ticker_cache = {"veri": {}, "ts": 0}

# ════════════════════════════════════════════
# v3.7 YENİ: KISMİ KÂR ALMA + BREAKEVEN
# ════════════════════════════════════════════
# KULLANICI KARARI (14.09.2026): "%5 hedefe ulaşmadan pozisyon geri
# dönüyor, o zamana kadarki kâr buharlaşıyor" gözlemi üzerine eklendi.
# Mantık: pozisyon KISMI_KAR_ESIK_PCT'e ulaştığında miktarın
# KISMI_KAR_ORANI kadarı kapatılır (o kâr garanti altına alınır), kalan
# kısmın SL'i girişe (breakeven + komisyon payı) çekilir - kalan kısım
# en kötü ihtimalle nötr kapanır, ayrıca tam %5 hedefe ulaşma şansı da
# korunur.
# Eşik %1.5 (hedefin ~%30'u) seçildi: küçük hesap + 10x kaldıraçta tek
# bir SL kaybı bakiyenin önemli bir kısmını götürüyor (geçmiş veride
# görülen -1$ civarı kayıplar, ~4$'lık bakiyenin %20-25'i), bu yüzden
# erken bir eşikle "en azından bir şey garanti et" önceliklendirildi.
# Oran %50 seçildi: ne çok erken tüm pozisyonu feda edip hızlı_tp
# grubunun büyük kazançlarını (backtest/canlıda görülen +1$'ı aşan
# işlemler) kaçırmamak, ne de whipsaw riskini tam taşımak arasında denge.
# ⚠️ Bu, ortalama kazancı hafifçe düşürebilir (erken kısmi kapanışlar
# tam hedeften daha az kazandırır) ama tutarlılığı artırması beklenir -
# henüz canlıda test edilmedi, birkaç günlük veriyle değerlendirilmeli.
KISMI_KAR_AKTIF = os.getenv("KISMI_KAR_AKTIF", "true").lower() == "true"
KISMI_KAR_ESIK_PCT = float(os.getenv("KISMI_KAR_ESIK_PCT", "0.015"))
KISMI_KAR_ORANI = float(os.getenv("KISMI_KAR_ORANI", "0.5"))
BREAKEVEN_KOMISYON_PAYI = float(os.getenv("BREAKEVEN_KOMISYON_PAYI", "0.001"))

# TREND DÖNÜŞ AJANI - varsayılan KAPALI (kullanıcı kararı, hem eski
# live_bot'ta hem paper_bot_v2'de net zarar verdiği görüldü).
TREND_AJANI_AKTIF = os.getenv("TREND_AJANI_AKTIF", "false").lower() == "true"
TREND_KONTROL_ARALIGI_SN = int(os.getenv("TREND_KONTROL_ARALIGI_SN", "900"))
TREND_TERS_TEYIT_SAYISI = int(os.getenv("TREND_TERS_TEYIT_SAYISI", "2"))
TREND_TERS_TEYIT_KISMI_SAYISI = int(os.getenv("TREND_TERS_TEYIT_KISMI_SAYISI", "4"))

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/live2_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/live2_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/live2_log.json")
BLOKE_PATH = os.getenv("BLOKE_PATH", "/data/live2_bloke.json")

# TEMKİNLİ MOD (21.08.2026 kararı)
TEMKINLI_MOD_AKTIF = os.getenv("TEMKINLI_MOD_AKTIF", "true").lower() == "true"
BTC_REJIM_KONTROL_ARALIGI_SN = int(os.getenv("BTC_REJIM_KONTROL_ARALIGI_SN", "900"))
_btc_rejim_durumu = {"temkinli": False, "son_kontrol": 0}

# İZLEME LİSTESİ AJANI (21.08.2026 kararı)
IZLEME_LISTESI_BOYUTU = int(os.getenv("IZLEME_LISTESI_BOYUTU", "10"))
IZLEME_TARAMA_ARALIGI_SN = int(os.getenv("IZLEME_TARAMA_ARALIGI_SN", "900"))
IZLEME_MAX_YAS_SAAT = float(os.getenv("IZLEME_MAX_YAS_SAAT", "24"))

trade_state = {}
state_lock = threading.Lock()
acilis_rezervasyonlari = {}
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()
bloke_coinler = set()
bloke_lock = threading.Lock()

izleme_listesi = {}  # sym -> {"eklenme_zamani": ts}
izleme_lock = threading.Lock()
_son_izleme_taramasi = {"ts": 0}


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


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def get_df(sym, tf, limit=60):
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


def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        usdt = bakiye.get("USDT", {})
        return safe(usdt.get("total", 0)) or safe(usdt.get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


def hesapla_marjin(bakiye):
    """v3.7 GÜNCELLEME (14.09.2026, kullanıcı kararı - 'kasa büyümesi'
    isteğiyle bulundu): küçük hesaplarda MARJIN_TABAN_USDT tek başına
    bakiyenin çok büyük bir kısmını tek işleme kilitleyebiliyordu (örn.
    4.26$ bakiyede taban $2 = bakiyenin %47'si). Bu, MAX_POS'un
    çeşitlendirme amacını fiilen boşa çıkarıyordu - pratikte 1-2
    pozisyondan fazla açılamıyordu, tek bir kötü SL kasanın büyük bir
    dilimini götürüyordu. Efektif taban artık
    min(MARJIN_TABAN_USDT, bakiye/MAX_POS) - bakiye küçükken pozisyon
    boyutu küçülür (çeşitlendirme korunur, tek işlem riski azalır),
    bakiye MARJIN_TABAN_USDT*MAX_POS'u (şu an $8) geçince normal tabana
    otomatik döner - bileşik büyüme mekanizmasına (RISK_PCT_BAKIYE)
    dokunulmadı, sadece küçük bakiye durumundaki taban davranışı
    düzeltildi."""
    if RISK_PCT_BAKIYE <= 0 or bakiye is None or bakiye <= 0:
        return SABIT_MARJIN_USDT
    efektif_taban = min(MARJIN_TABAN_USDT, max(bakiye / MAX_POS, 0.5))
    marjin = bakiye * RISK_PCT_BAKIYE
    marjin = max(efektif_taban, min(MARJIN_TAVAN_USDT, marjin))
    return marjin


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
    try:
        markets = market_bilgisi_al()
        m = markets.get(sym)
        if not m:
            return istenen_lev
        max_lev = (m.get("limits", {}) or {}).get("leverage", {}).get("max")
        if max_lev is None:
            return istenen_lev
        return min(istenen_lev, int(max_lev))
    except Exception:
        return istenen_lev


def guncel_tickerlari_al():
    """v3.6 YENİ: fetch_tickers() sonucunu kısa süreliğine önbellekler.
    aday_havuzu() ve pump_coin_mu() aynı önbelleği paylaşır - böylece
    pump filtresi eklenmesi ekstra API çağrısı yaratmaz."""
    if time.time() - _ticker_cache["ts"] < TICKER_CACHE_SN and _ticker_cache["veri"]:
        return _ticker_cache["veri"]
    try:
        _ticker_cache["veri"] = exchange.fetch_tickers()
        _ticker_cache["ts"] = time.time()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
    return _ticker_cache["veri"]


def aday_havuzu():
    tickers = guncel_tickerlari_al()
    if not tickers:
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


def genis_evren_listesi():
    tickers = guncel_tickerlari_al()
    if not tickers:
        return []
    markets = market_bilgisi_al()
    tumu = []
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
        tumu.append(sym)
    return tumu


def pump_coin_mu(sym):
    """v3.6 YENİ: coin son 24 saatte PUMP_FILTRE_ESIK_PCT üzerinde
    yükselmişse True döner - bu coinlere LONG girişi reddedilir.
    KULLANICI KARARI (14.09.2026, gerçek veri analiziyle bulundu): en
    sert SL kayıplarının ortak paterni, coin zaten aşırı pompalanmışken
    girilmiş olmasıydı (tepe civarında giriş -> sert geri çekilme).
    API yükü YOK: guncel_tickerlari_al() önbelleğinden okur, ekstra
    fetch_ticker çağrısı yapmaz."""
    if not PUMP_FILTRE_AKTIF:
        return False
    tickers = guncel_tickerlari_al()
    t = tickers.get(sym)
    if not t:
        return False
    chg = t.get("percentage")
    if chg is None:
        return False
    return chg > PUMP_FILTRE_ESIK_PCT


def hacim_teyit_var_mi(df_15m, periyot=HACIM_TEYIT_PERIYOT):
    """v3.6 YENİ: son 15m mumun hacmi, önceki `periyot` mumun ortalama
    hacminin en az HACIM_TEYIT_KATSAYI katı olmalı. KULLANICI KARARI
    (14.09.2026, gerçek veri analiziyle bulundu): işlemlerin %80'i
    max_hold_timeout ile (hafif eksi) kapanıyordu - bunların çoğu muhtemelen
    'sessiz', gerçek alım ilgisi olmayan fiyat hareketleriydi. Hacim teyidi
    bu sessiz sinyalleri elemeye çalışır."""
    if not HACIM_TEYIT_AKTIF:
        return True
    if df_15m is None or len(df_15m) < periyot + 1:
        return False
    ort_hacim = df_15m["volume"].iloc[-(periyot + 1):-1].mean()
    son_hacim = df_15m["volume"].iloc[-1]
    if pd.isna(ort_hacim) or ort_hacim <= 0:
        return False
    return son_hacim >= ort_hacim * HACIM_TEYIT_KATSAYI


def btc_temkinli_mod_mu():
    if time.time() - _btc_rejim_durumu["son_kontrol"] < BTC_REJIM_KONTROL_ARALIGI_SN:
        return _btc_rejim_durumu["temkinli"]
    try:
        df_1d = get_df("BTC/USDT:USDT", "1d", MA_PERIYOT + 10)
        df_4h = get_df("BTC/USDT:USDT", "4h", MA_PERIYOT + 5)
        y1d = trend_yonu(df_1d)
        y4h = trend_yonu(df_4h)
        yeni_durum = (y1d == "dusus" and y4h == "dusus")
    except Exception as e:
        log.warning(f"[BTC_REJIM] {e}")
        return _btc_rejim_durumu["temkinli"]

    onceki = _btc_rejim_durumu["temkinli"]
    _btc_rejim_durumu["temkinli"] = yeni_durum
    _btc_rejim_durumu["son_kontrol"] = time.time()
    if yeni_durum != onceki:
        if yeni_durum:
            durdurma_metni = ("YENİ POZİSYON AÇMA TAMAMEN DURDU" if TEMKINLI_MOD_TAM_DURDURMA
                               else "MAX_POS geçici olarak yarıya indi")
            tg(f"⚠️ BTC 1D+4H düşüşe döndü — TEMKİNLİ MOD aktif, "
               f"{durdurma_metni}. Açık pozisyonlar etkilenmez, kendi "
               f"SL/TP/kısmi kâr alma mantığıyla yönetilmeye devam eder.")
        else:
            tg("✅ BTC 1D+4H yeniden yükselişte — TEMKİNLİ MOD kapandı, "
               "yeni pozisyon açma normale döndü.")
    return yeni_durum


# v3.8 YENİ: TEMKİNLİ MOD DAVRANIŞI SIKILAŞTIRILDI
# KULLANICI KARARI (14.09.2026): "piyasa düşüşe dönünce bot bocalıyor,
# kârlar eriyip zarara dönüyor" gözlemi üzerine konuşuldu. Değerlendirilen
# alternatif ("trend dönünce pozisyonu tersine çevir / SHORT'a geç")
# BİLİNÇLİ OLARAK REDDEDİLDİ - kodun kendi geçmişinde zaten denenmiş ve
# başarısız olmuş bir yaklaşım (SHORT özelliği 10.09.2026'da eklenip
# ilk gerçek işlemde "short squeeze" ile kayıp verip 11.09.2026'da
# kapatılmıştı). Trend dönüş sinyali (1D+4H+1H'nin üçünün de dönmesi)
# doğası gereği GEÇ gelir - bu noktada pozisyon tersine çevirmek, geçici
# bir sıçramaya (whipsaw) yakalanıp hem eski hem yeni yönde kayıp verme
# riskini artırır (nitekim SLX işleminde tam bu olmuştu).
# Bunun yerine daha güvenli, tek yönlü bir önlem seçildi: BTC'nin kendi
# 1D+4H trendi düşüşe dönerse, YENİ pozisyon açmayı TAMAMEN durdur (önceden
# sadece MAX_POS yarıya iniyordu). Açık pozisyonlara DOKUNULMAZ - onlar
# kendi SL/TP/kısmi kâr alma mantığıyla normal şekilde yönetilmeye devam
# eder. Amaç: piyasa net olarak zayıflarken üstüne yeni risk eklememek,
# ama var olan pozisyonları panikle kapatıp yön değiştirerek ekstra risk
# yaratmamak.
# v3.9 GÜNCELLEME (14.09.2026, kullanıcı kararıyla): v3.8'deki "BTC düşerse
# yeni pozisyonu TAMAMEN durdur" kararı geri alındı. Neden: orijinal kodun
# kendi geçmişinde bu tam olarak denenmiş ve terk edilmişti - "bir altcoin
# BTC'den bağımsız gerçekten güçlü olabilir, coin'leri tamamen engellemek
# yanlış çıkmıştı" notuyla. Kullanıcı haklı olarak bunu hatırlattı: BTC
# düşerken bağımsız pump yapan güçlü bir coin fırsatını tamamen kaçırmak
# istemiyoruz.
# YENİ YAKLAŞIM: MAX_POS yine yarıya iner (v3.7 ve öncesi davranış), AMA
# o dönemde girecek coin için trend gücü eşiği YÜKSELTİLİR
# (MIN_4H_TREND_GUCU_PCT yerine MIN_4H_TREND_GUCU_PCT_TEMKINLI kullanılır).
# Mantık: "piyasa genel olarak zayıfken daha seçici ol" - zayıf/sınırda
# coinler elenir, sadece BTC'den GERÇEKTEN bağımsız, güçlü hareket eden
# coinler işleme girebilir. Bu, "hiçbir şey yapma" (eski v3.7) ile
# "her şeyi durdur" (v3.8) arasında bir orta yol.
TEMKINLI_MOD_TAM_DURDURMA = os.getenv("TEMKINLI_MOD_TAM_DURDURMA", "false").lower() == "true"
MIN_4H_TREND_GUCU_PCT_TEMKINLI = float(os.getenv("MIN_4H_TREND_GUCU_PCT_TEMKINLI", "4.0"))


def efektif_max_pos():
    if not TEMKINLI_MOD_AKTIF:
        return MAX_POS
    if btc_temkinli_mod_mu():
        if TEMKINLI_MOD_TAM_DURDURMA:
            return 0
        return max(1, MAX_POS // 2)
    return MAX_POS


# ════════════════════════════════════════════
# ÜÇLÜ ZAMAN DİLİMİ UYUM SİNYALİ (1D+4H+1H) + SADECE LONG
# ════════════════════════════════════════════
def trend_yonu(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma):
        return None
    return "yukselis" if fiyat > ma else "dusus"


def trend_gucu_pct(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma) or ma == 0:
        return None
    return (fiyat - ma) / ma * 100


def ucyon_sinyal(sym):
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    df_1h = get_df(sym, "1h", MA_PERIYOT + 5)

    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    yon_1h = trend_yonu(df_1h)
    guc_4h = trend_gucu_pct(df_4h)

    # v3.9 YENİ: BTC (piyasa geneli) düşüşteyken eşik yükseltilir - sadece
    # BTC'den gerçekten bağımsız, güçlü hareket eden coinler geçer. BTC
    # yükselişte/karışıkken normal eşik (MIN_4H_TREND_GUCU_PCT) kullanılır.
    if TEMKINLI_MOD_AKTIF and btc_temkinli_mod_mu():
        aktif_esik = MIN_4H_TREND_GUCU_PCT_TEMKINLI
    else:
        aktif_esik = MIN_4H_TREND_GUCU_PCT

    if yon_1d == "yukselis" and yon_4h == "yukselis" and yon_1h == "yukselis":
        if guc_4h is None or guc_4h < aktif_esik:
            return None
        return _ucyon_sinyal_yon(sym, "long", yon_1d, yon_4h, yon_1h)

    if SHORT_AKTIF and yon_1d == "dusus" and yon_4h == "dusus" and yon_1h == "dusus":
        if guc_4h is None or guc_4h > -aktif_esik:
            return None
        return _ucyon_sinyal_yon(sym, "short", yon_1d, yon_4h, yon_1h)

    return None


def _ucyon_sinyal_yon(sym, yon, yon_1d, yon_4h, yon_1h):
    df_15m = get_df(sym, "15m", max(LOOKBACK_15M, HACIM_TEYIT_PERIYOT) + 5)
    if df_15m is None or len(df_15m) < LOOKBACK_15M + 2:
        return None

    pencere = df_15m.iloc[-(LOOKBACK_15M + 1):-1]
    son_mum = df_15m.iloc[-1]
    son_3_idx = pencere.index[-3:]

    if yon == "long":
        swing_nokta = pencere["low"].min()
        ext_idx = pencere["low"].idxmin()
        tetik_yakin = ext_idx in son_3_idx
        kapanis_uygun = son_mum["close"] > son_mum["open"]
        gecerli = tetik_yakin and kapanis_uygun and son_mum["close"] > swing_nokta
        mesafe = (son_mum["close"] - swing_nokta) / swing_nokta if gecerli else None
    else:
        swing_nokta = pencere["high"].max()
        ext_idx = pencere["high"].idxmax()
        tetik_yakin = ext_idx in son_3_idx
        kapanis_uygun = son_mum["close"] < son_mum["open"]
        gecerli = tetik_yakin and kapanis_uygun and son_mum["close"] < swing_nokta
        mesafe = (swing_nokta - son_mum["close"]) / swing_nokta if gecerli else None

    if not gecerli:
        return None
    if mesafe > GIRIS_MAX_DIP_MESAFE:
        return None

    # ── v3.6 YENİ FİLTRE 1: HACİM TEYİDİ ──
    # Sessiz (gerçek alım ilgisi olmayan) hareketleri eler. Bunlar canlı
    # veride max_hold_timeout ile hafif eksi kapanan işlemlerin büyük
    # kısmını oluşturuyordu (128/161 işlem, net -7.11$, %44 kazanma).
    if not hacim_teyit_var_mi(df_15m):
        return None

    # ── v3.6 YENİ FİLTRE 2: PUMP FİLTRESİ ──
    # Coin zaten aşırı pompalanmışsa LONG girişini reddet - canlı veride
    # en sert SL kayıplarının ortak paterni buydu (tepede giriş -> sert
    # geri çekilme). SHORT'a bu filtre uygulanmıyor (mantığı ters olurdu,
    # ayrıca SHORT şu an zaten kapalı).
    if yon == "long" and pump_coin_mu(sym):
        return None

    return {"symbol": sym, "entry": float(son_mum["close"]), "swing_nokta": float(swing_nokta),
            "yon": yon, "1d": yon_1d, "4h": yon_4h, "1h": yon_1h}


def iki_uzerinden_uc_kontrol(sym):
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    if yon_1d == "yukselis" and yon_4h == "yukselis":
        return True
    if SHORT_AKTIF and yon_1d == "dusus" and yon_4h == "dusus":
        return True
    return False


# ════════════════════════════════════════════
# GERÇEK POZİSYON AÇMA/KAPATMA
# ════════════════════════════════════════════
def acilis_basarisiz_cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def gercek_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]

    if coin_bloke_mi(sym):
        log.info(f"[COIN_BLOKE] {sym} engelli, açılış atlanıyor")
        return

    with state_lock:
        if sym in trade_state or sym in acilis_rezervasyonlari:
            return
        if len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
            return
        acilis_rezervasyonlari[sym] = True

    try:
        _gercek_pozisyon_ac_ic(sym, sinyal)
    finally:
        with state_lock:
            acilis_rezervasyonlari.pop(sym, None)


def _gercek_pozisyon_ac_ic(sym, sinyal):
    if cooldown_da_mi(sym):
        return

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    yon = sinyal.get("yon", "long")
    long_mu = (yon == "long")
    entry_hedef = sinyal["entry"]
    swing_nokta = sinyal["swing_nokta"]

    if long_mu:
        sl = swing_nokta * (1 - SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT_TAVAN, (entry_hedef - sl) / entry_hedef))
        sl = entry_hedef * (1 - sl_mesafe)
    else:
        sl = swing_nokta * (1 + SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT_TAVAN, (sl - entry_hedef) / entry_hedef))
        sl = entry_hedef * (1 + sl_mesafe)

    if sl_mesafe <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    LEV_KULLANILAN = sembol_max_kaldirac(sym, LEV)
    marjin_kullanilan = hesapla_marjin(bakiye)
    notional = marjin_kullanilan * LEV_KULLANILAN
    amount = notional / entry_hedef

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        log.warning(f"[MIKTAR] {sym}: {e}")
        acilis_basarisiz_cooldown_uygula(sym)
        return
    if qty <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    try:
        exchange.set_leverage(LEV_KULLANILAN, sym)
        time.sleep(0.3)
    except Exception as e:
        log.warning(f"[KALDIRAC] {sym}: {e}")

    acilis_yonu = "buy" if long_mu else "sell"
    kapanis_yonu = "sell" if long_mu else "buy"

    try:
        exchange.create_market_order(sym, acilis_yonu, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giriş emri başarısız: {e}")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    time.sleep(0.8)
    entry = entry_hedef
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        if gercek_pos and safe(gercek_pos.get("entryPrice")) > 0:
            entry = safe(gercek_pos.get("entryPrice"))
            sl = entry * (1 - sl_mesafe) if long_mu else entry * (1 + sl_mesafe)
    except Exception as e:
        log.warning(f"[GERCEK_POZ] {sym}: {e}")

    r_risk = abs(entry - sl)
    tp = entry * (1 + HIZLI_HEDEF_PCT) if long_mu else entry * (1 - HIZLI_HEDEF_PCT)

    sl_emir_id = None
    sl_fiyat = float(exchange.price_to_precision(sym, sl))
    for deneme in range(3):
        try:
            sl_emri = exchange.create_order(sym, "market", kapanis_yonu, qty, None,
                                             {"reduceOnly": True, "stopLossPrice": sl_fiyat})
            sl_emir_id = sl_emri.get("id")
            if sl_emir_id:
                break
        except Exception as e:
            log.warning(f"[SL] {sym} deneme {deneme+1}/3: {e}")
        time.sleep(0.5)

    if not sl_emir_id:
        tg(f"🚨 {sym} SL yerleştirilemedi, güvenlik amaçlı kapatılıyor.")
        try:
            exchange.create_market_order(sym, kapanis_yonu, qty, params={"reduceOnly": True})
        except Exception:
            pass
        acilis_basarisiz_cooldown_uygula(sym)
        return

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl": sl, "tp": tp, "sl_emir_id": sl_emir_id, "yon": yon, "qty": qty,
            "r_risk": r_risk, "acilis_zamani": time.time(),
            "1d": sinyal["1d"], "4h": sinyal["4h"], "1h": sinyal["1h"], "notional": notional,
            "son_trend_kontrol": 0, "ters_trend_sayisi": 0, "kismi_ters_sayisi": 0,
            "kismi_alindi": False,
        }
    durumu_diske_yaz()

    yon_emoji = "🟢 LONG" if long_mu else "🔴 SHORT"
    tg(f"📈 GERÇEK POZİSYON (fırsatçı v3.9): {sym} {yon_emoji}\n"
       f"Giriş≈{entry:.6f} | SL:{sl_fiyat:.6f} (%{sl_mesafe*100:.1f}) | TP:{tp:.6f} (%{HIZLI_HEDEF_PCT*100:.1f} sabit)\n"
       f"1D:{sinyal['1d']} | 4H:{sinyal['4h']} | 1H:{sinyal['1h']} (üçlü uyumlu)\n"
       f"✅ Hacim teyidi geçti | ✅ Pump filtresi geçti\n"
       f"⚡ SABİT HEDEF: değer değmez HEMEN kapanır, iz sürme yok, bekleme yok\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Marjin: ${marjin_kullanilan:.2f} "
       f"(bileşik büyüme: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i, taban ${MARJIN_TABAN_USDT:.2f})")


def kismi_kar_al(sym, durum):
    """v3.7 YENİ: pozisyonun KISMI_KAR_ORANI kadarını piyasadan kapatır
    (o kâr garanti altına alınır), kalan kısmın SL'i girişe (breakeven +
    komisyon payı) çekilir. Orijinal SL emri iptal edilip yenisi
    yerleştirilir. Herhangi bir adımda hata olursa, pozisyon eski haliyle
    (tam miktar, eski SL) güvenli şekilde bırakılır - yarım işlem riski
    yok."""
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        if not gercek_pos:
            return False

        toplam_qty = safe(gercek_pos.get("contracts"))
        entry = durum["entry"]
        long_mu = durum.get("yon", "long") == "long"
        kapanis_yonu = "sell" if long_mu else "buy"

        kapanacak_qty = float(exchange.amount_to_precision(sym, toplam_qty * KISMI_KAR_ORANI))
        if kapanacak_qty <= 0:
            return False

        kapama_emri = exchange.create_market_order(sym, kapanis_yonu, kapanacak_qty, params={"reduceOnly": True})
        time.sleep(0.8)
        cikis_fiyat = None
        try:
            detay = exchange.fetch_order(kapama_emri.get("id"), sym)
            dolum = safe(detay.get("average")) or safe(detay.get("price"))
            if dolum > 0:
                cikis_fiyat = dolum
        except Exception:
            pass
        if not cikis_fiyat:
            try:
                t = exchange.fetch_ticker(sym)
                cikis_fiyat = safe(t["last"])
            except Exception:
                cikis_fiyat = entry

        kismi_pnl = (cikis_fiyat - entry) * kapanacak_qty if long_mu else (entry - cikis_fiyat) * kapanacak_qty
        trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": kismi_pnl,
                           "yon": durum.get("yon", "long"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                           "not": "kismi_kar_alma", "1d": durum.get("1d"), "4h": durum.get("4h"),
                           "1h": durum.get("1h")})

        # Kalan miktarın SL'ini breakeven'e (+ komisyon payı) çek
        kalan_qty = float(exchange.amount_to_precision(sym, toplam_qty - kapanacak_qty))

        if kalan_qty <= 0:
            # Yuvarlama sonucu kapatılacak miktar zaten tüm pozisyonu
            # kapsıyor demektir - pozisyon tamamen kapanmış sayılır,
            # state'ten tamamen çıkarılır (yarım/tanımsız durum bırakılmaz).
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            tg(f"🟢 {sym} KISMİ KÂR ALINDI (tam kapanış - yuvarlama): "
               f"{kapanacak_qty} kapatıldı, PnL≈{kismi_pnl:+.2f}$")
            return True

        eski_sl_id = durum.get("sl_emir_id")
        if eski_sl_id:
            try:
                exchange.cancel_order(eski_sl_id, sym)
            except Exception as e:
                log.warning(f"[KISMI_KAR_SL_IPTAL] {sym}: {e}")

        yeni_sl = entry * (1 + BREAKEVEN_KOMISYON_PAYI) if long_mu else entry * (1 - BREAKEVEN_KOMISYON_PAYI)
        yeni_sl_fiyat = float(exchange.price_to_precision(sym, yeni_sl))
        yeni_sl_id = None
        for deneme in range(3):
            try:
                sl_emri = exchange.create_order(sym, "market", kapanis_yonu, kalan_qty, None,
                                                 {"reduceOnly": True, "stopLossPrice": yeni_sl_fiyat})
                yeni_sl_id = sl_emri.get("id")
                if yeni_sl_id:
                    break
            except Exception as e:
                log.warning(f"[KISMI_KAR_SL_YENI] {sym} deneme {deneme+1}/3: {e}")
            time.sleep(0.5)

        if not yeni_sl_id:
            tg(f"🚨 {sym} kısmi kâr sonrası breakeven SL yerleştirilemedi, "
               f"güvenlik amaçlı kalan pozisyon kapatılıyor.")
            try:
                exchange.create_market_order(sym, kapanis_yonu, kalan_qty, params={"reduceOnly": True})
            except Exception:
                pass
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            return True

        with state_lock:
            if sym in trade_state:
                trade_state[sym]["kismi_alindi"] = True
                trade_state[sym]["qty"] = kalan_qty
                trade_state[sym]["sl"] = yeni_sl
                trade_state[sym]["sl_emir_id"] = yeni_sl_id
        durumu_diske_yaz()

        tg(f"🟢 {sym} KISMİ KÂR ALINDI: {kapanacak_qty} kapatıldı, PnL≈{kismi_pnl:+.2f}$\n"
           f"Kalan {kalan_qty} için SL breakeven'e çekildi ({yeni_sl:.6f}) - "
           f"kalan kısım en kötü ihtimalle nötr kapanır, tam hedef hâlâ geçerli.")
        return True
    except Exception as e:
        log.warning(f"[KISMI_KAR_HATA] {sym}: {e}")
        return False


def gercek_pozisyon_kapat(sym, sebep="manuel"):
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        with state_lock:
            durum = trade_state.get(sym)

        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            if sebep == "sl":
                with cooldown_lock:
                    son_kapanis_zamani[sym] = time.time()
                cooldown_diske_yaz()
            if durum:
                _kapanis_kaydet_gercek_veriyle(sym, durum, sebep)
            return True, "kapatildi"

        qty = safe(gercek_pos.get("contracts"))
        entry_fiyat = safe(gercek_pos.get("entryPrice"))
        yon_kayitli = (durum or {}).get("yon", "long")
        long_mu = (yon_kayitli == "long")
        kapanis_yonu = "sell" if long_mu else "buy"

        if durum and durum.get("sl_emir_id"):
            try:
                exchange.cancel_order(durum["sl_emir_id"], sym)
            except Exception:
                pass

        kapama_emri = exchange.create_market_order(sym, kapanis_yonu, qty, params={"reduceOnly": True})
        time.sleep(1)
        cikis_fiyat = None
        try:
            detay = exchange.fetch_order(kapama_emri.get("id"), sym)
            dolum = safe(detay.get("average")) or safe(detay.get("price"))
            if dolum > 0:
                cikis_fiyat = dolum
        except Exception:
            pass
        if not cikis_fiyat:
            try:
                t = exchange.fetch_ticker(sym)
                cikis_fiyat = safe(t["last"])
            except Exception:
                cikis_fiyat = entry_fiyat

        pnl = (cikis_fiyat - entry_fiyat) * qty if long_mu else (entry_fiyat - cikis_fiyat) * qty
        trade_log_kaydet({"symbol": sym, "entry": entry_fiyat, "exit": cikis_fiyat, "pnl": pnl,
                           "yon": yon_kayitli, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                           "not": sebep, "1d": (durum or {}).get("1d"), "4h": (durum or {}).get("4h"),
                           "1h": (durum or {}).get("1h")})
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        if sebep == "sl":
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
        tg(f"{'🟢' if pnl>=0 else '🔴'} GERÇEK kapandı: {sym} [{sebep}] PnL≈{pnl:+.2f}$")
        return True, f"✅ {sym} kapatıldı | PnL≈{pnl:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma hatası: {e}"


def _kapanis_kaydet_gercek_veriyle(sym, durum, sebep):
    entry = durum["entry"]
    qty = durum.get("qty", 0)
    cikis_fiyat = None
    sl_id = durum.get("sl_emir_id")
    if sl_id:
        try:
            detay = exchange.fetch_order(sl_id, sym)
            if detay.get("status") in ("closed", "filled"):
                dolum = safe(detay.get("average")) or safe(detay.get("price"))
                if dolum > 0:
                    cikis_fiyat = dolum
        except Exception as e:
            log.warning(f"[SL_KONTROL] {sym}: {e}")
    if not cikis_fiyat:
        try:
            son_islemler = exchange.fetch_my_trades(sym, limit=10)
            kapanis_zamani_ms = durum["acilis_zamani"] * 1000
            adaylar = [t for t in son_islemler if t.get("timestamp", 0) > kapanis_zamani_ms]
            if adaylar:
                son_islem = max(adaylar, key=lambda t: t.get("timestamp", 0))
                dolum = safe(son_islem.get("price"))
                if dolum > 0:
                    cikis_fiyat = dolum
        except Exception as e:
            log.warning(f"[ISLEM_GECMISI] {sym}: {e}")
    if not cikis_fiyat:
        try:
            t = exchange.fetch_ticker(sym)
            cikis_fiyat = safe(t["last"])
        except Exception:
            cikis_fiyat = entry

    long_mu = durum.get("yon", "long") == "long"
    pnl = (cikis_fiyat - entry) * qty if long_mu else (entry - cikis_fiyat) * qty
    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": pnl,
                       "yon": durum.get("yon", "long"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                       "not": sebep, "1d": durum.get("1d"), "4h": durum.get("4h"), "1h": durum.get("1h")})
    tg(f"{'🟢' if pnl>=0 else '🔴'} GERÇEK kapandı: {sym} [{sebep}] PnL≈{pnl:+.2f}$ (borsada önceden kapanmış)")


# ════════════════════════════════════════════
# PANEL
# ════════════════════════════════════════════
def panel_ozet_metni():
    with log_lock:
        gecmis = list(trade_log)
    gercek_bakiye = gercek_bakiye_al()
    bakiye_metni = f"{gercek_bakiye:,.2f}$" if gercek_bakiye is not None else "alınamadı"
    with state_lock:
        acik_sayi = len(trade_state)

    gerceklesmeyen_net = 0.0
    acik_detay = []
    with state_lock:
        durumlar = dict(trade_state)
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            poz_notional = d.get("notional", NOTIONAL)
            long_mu = d.get("yon", "long") == "long"
            anlik = (guncel - entry) / entry * poz_notional if long_mu else (entry - guncel) / entry * poz_notional
            gerceklesmeyen_net += anlik
            acik_detay.append((sym, anlik))
        except Exception:
            continue

    satirlar = [
        "💵 LIVE BOT v3.9 — CANLI ÖZET",
        f"(GERÇEK PARA, 1D+4H+1H {'LONG+SHORT' if SHORT_AKTIF else 'LONG-only'}, hacim+pump filtreli, kısmi kâr alma)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💼 Bakiye (borsa): {bakiye_metni}",
    ]
    if acik_sayi > 0:
        gc_emoji = "🟢" if gerceklesmeyen_net >= 0 else "🔴"
        satirlar.append(f"{gc_emoji} Açık pozisyonlarda (gerçekleşmemiş): {gerceklesmeyen_net:+.2f}$")
    satirlar.append("━━━━━━━━━━━━━━━━━━━━\n")

    if gecmis:
        toplam = len(gecmis)
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        net = sum(t["pnl"] for t in gecmis)
        wr = len(kazanan) / toplam * 100
        satirlar.append("📊 İstatistik")
        satirlar.append(f"  Toplam işlem: {toplam}  |  Kazanma: %{wr:.1f}")
        satirlar.append(f"  Net PnL: {net:+.2f}$  |  Ortalama: {net/toplam:+.3f}$\n")
        satirlar.append("📋 Son 5 işlem:")
        for t in list(reversed(gecmis))[:5]:
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            sebep = t.get("not", "")
            satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]:<8} {t['pnl']:+.2f}$  ({sebep})")
    else:
        satirlar.append("Henüz kapanan işlem yok.")

    satirlar.append(f"\n📈 Açık pozisyon: {acik_sayi}/{MAX_POS}")
    for sym, anlik in acik_detay:
        e = "🟢" if anlik >= 0 else "🔴"
        satirlar.append(f"  {e} {sym.split('/')[0]:<8} {anlik:+.2f}$")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    temkinli = btc_temkinli_mod_mu() if TEMKINLI_MOD_AKTIF else False
    with izleme_lock:
        izleme_boyut = len(izleme_listesi)
        izleme_coinler = sorted(s.split("/")[0] for s in izleme_listesi.keys())
    izleme_satiri = f"  Şu an listede: {', '.join(izleme_coinler)}" if izleme_coinler else "  Şu an liste boş"

    if SHORT_AKTIF:
        yon_basligi = "LONG+SHORT"
        yon_aciklama = ("  1) 1D, 4H, 1H üçü de AYNI yönde olmalı (hepsi YUKARI -> LONG, "
                         "hepsi AŞAĞI -> SHORT)\n")
    else:
        yon_basligi = "LONG-only"
        yon_aciklama = "  1) 1D, 4H, 1H üçü de YUKARI olmalı (SADECE LONG)\n"

    return ("⚙️ LIVE BOT v3.9 (FIRSATÇI + HACİM/PUMP + KISMİ KÂR + AKILLI TEMKİNLİ MOD) AYARLARI\n\n"
            f"Sürüm: v3.9 (14.09.2026 — temkinli mod akıllandı: BTC düşerken "
            f"yeni pozisyon açma tamamen durur. Önceki: v3.7 kısmi kâr alma + breakeven. "
            f"Önceki: 14.09.2026 hacim teyidi + pump filtresi → 01.09.2026 fırsatçı "
            f"geçiş → 08.09.2026 bileşik büyüme/8sa/akıllı cooldown/trend gücü → "
            f"10.09.2026 SHORT eklendi → 11.09.2026 SHORT kapatıldı. Şu an: {yon_basligi})\n\n"
            "💰 BU BOT GERÇEK PARA KULLANIYOR.\n\n"
            f"Giriş ({yon_basligi}): Üçlü zaman dilimi trend uyumu + trend gücü + "
            f"dip/tepe yakınlığı + hacim teyidi + pump filtresi\n"
            f"{yon_aciklama}"
            f"  2) 4H trend en az %{MIN_4H_TREND_GUCU_PCT:.1f} güçte olmalı (MA20'den uzaklık)\n"
            "  3) 15m'de swing dip/tepe + dönüş onayı gerekli\n"
            f"  4) Giriş fiyatı swing noktadan en fazla %{GIRIS_MAX_DIP_MESAFE*100:.0f} uzak olmalı\n"
            f"  5) [v3.6] Son 15m mum hacmi, {HACIM_TEYIT_PERIYOT} mum ortalamasının en az "
            f"{HACIM_TEYIT_KATSAYI:.1f} katı olmalı ({'AKTİF' if HACIM_TEYIT_AKTIF else 'KAPALI'})\n"
            f"  6) [v3.6] Coin son 24s'te %{PUMP_FILTRE_ESIK_PCT:.0f}'ten fazla pompalanmamış olmalı "
            f"(LONG için, {'AKTİF' if PUMP_FILTRE_AKTIF else 'KAPALI'})\n\n"
            "⚡ ÇIKIŞ:\n"
            f"  [v3.7] Kısmi kâr alma: pozisyon %{KISMI_KAR_ESIK_PCT*100:.1f}'e ulaşınca "
            f"miktarın %{KISMI_KAR_ORANI*100:.0f}'i kapatılır, kalan SL'i breakeven'e çekilir "
            f"({'AKTİF' if KISMI_KAR_AKTIF else 'KAPALI'})\n"
            f"  TAM HEDEF: SABİT %{HIZLI_HEDEF_PCT*100:.1f} - hedefe değer değmez HEMEN kapanır\n"
            f"  SL: swing bazlı, taban %{MIN_SL_PCT*100:.0f} (kısmi alım sonrası breakeven'e çekilir)\n"
            f"  Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
            f"💰 MARJİN (bileşik büyüme): bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i "
            f"(taban ${MARJIN_TABAN_USDT:.2f}, tavan ${MARJIN_TAVAN_USDT:.2f})\n"
            f"  [v3.7] Küçük bakiyede efektif taban = min(${MARJIN_TABAN_USDT:.2f}, bakiye/{MAX_POS}) "
            f"- çeşitlendirmeyi korumak için (bakiye ${MARJIN_TABAN_USDT*MAX_POS:.0f}'ı geçince normal tabana döner)\n"
            f"  Şu anki bakiyeyle hesaplanan marjin: ${hesapla_marjin(gercek_bakiye_al() or 0):.2f}\n"
            f"Kaldıraç: {LEV}x\n"
            f"MAX_POS (normal): {MAX_POS} | MAX_POS (şu an geçerli): {efektif_max_pos()}\n\n"
            f"🔄 TREND DÖNÜŞ AJANI: {'AKTİF' if TREND_AJANI_AKTIF else 'KAPALI (kullanıcı kararı)'}\n\n"
            f"🌡️ TEMKİNLİ MOD: {'AKTİF' if TEMKINLI_MOD_AKTIF else 'KAPALI'} "
            f"(BTC düşerse: {'yeni pozisyon TAMAMEN durur' if TEMKINLI_MOD_TAM_DURDURMA else 'MAX_POS yarıya iner, trend gücü eşiği yükselir (%' + str(MIN_4H_TREND_GUCU_PCT_TEMKINLI) + ')'})\n"
            f"  Şu anki durum: {'⚠️ DEVREDE (BTC 1D+4H düşüşte: MAX_POS yarıya indi, trend gücü eşiği yükseldi - sadece BTC-bağımsız güçlü coinler geçer)' if temkinli else '✅ pasif (BTC 1D+4H yükselişte/karışık, normal çalışıyor)'}\n\n"
            f"👁️ İZLEME LİSTESİ AJANI: max {IZLEME_LISTESI_BOYUTU} coin, "
            f"{IZLEME_TARAMA_ARALIGI_SN//60}dk'da bir genişletiliyor\n"
            f"{izleme_satiri} ({izleme_boyut}/{IZLEME_LISTESI_BOYUTU})\n\n"
            "⚠️ v3.6/v3.7 filtreleri (hacim teyidi, pump filtresi, kısmi kâr alma) "
            "henüz canlıda tam test edilmedi - geçmiş veri analizine dayanan ilk "
            "tahmin değerleridir. Birkaç günlük yeni veri sonrası panel_analiz ile "
            "gözden geçirilmesi gerekir.\n"
            "⚠️ SHORT_AKTIF=true ortam değişkeniyle SHORT tekrar açılabilir, "
            "ama kullanıcı kararıyla şu an kapalı.")


def panel_gecmis_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "📜 Henüz kapanan işlem yok."
    satirlar = ["📜 SON 15 İŞLEM\n"]
    for t in list(reversed(gecmis))[:15]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        yon_etiket = "LONG" if t.get("yon", "long") == "long" else "SHORT"
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {yon_etiket} {t['pnl']:+.2f}$ "
                         f"[{t.get('not','?')}]\n   {t['zaman']} | 1D:{t.get('1d','?')}/4H:{t.get('4h','?')}/1H:{t.get('1h','?')}")
    return "\n".join(satirlar)


def panel_analiz_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "🔬 ANALİZ\n\nHenüz kapanan işlem yok."
    satirlar = ["🔬 ANALİZ\n", "🚪 Kapanış sebebine göre:"]
    for sebep in sorted(set(t.get("not", "?") for t in gecmis)):
        alt = [t for t in gecmis if t.get("not") == sebep]
        net = sum(t["pnl"] for t in alt)
        w = len([t for t in alt if t["pnl"] > 0])
        satirlar.append(f"  {sebep}: {len(alt)} işlem, %{w/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

    coin_pnl = {}
    for t in gecmis:
        sym = t["symbol"].split("/")[0]
        coin_pnl[sym] = coin_pnl.get(sym, 0) + t["pnl"]
    siralanmis = sorted(coin_pnl.items(), key=lambda x: x[1], reverse=True)
    kazandiranlar = [x for x in siralanmis if x[1] > 0][:3]
    kaybettirenler = [x for x in siralanmis if x[1] < 0][-3:][::-1]
    if kazandiranlar:
        satirlar.append("\n🏆 En kazandıran coinler:")
        for sym, pnl in kazandiranlar:
            satirlar.append(f"  {sym}: {pnl:+.2f}$")
    if kaybettirenler:
        satirlar.append("💀 En kaybettiren coinler:")
        for sym, pnl in kaybettirenler:
            satirlar.append(f"  {sym}: {pnl:+.2f}$")
    return "\n".join(satirlar)


def panel_risk_metni():
    with state_lock:
        durumlar = dict(trade_state)
    satirlar = ["📉 AÇIK POZİSYON DETAYI\n"]
    if not durumlar:
        satirlar.append("Açık pozisyon yok.")
        return "\n".join(satirlar)
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            long_mu = d.get("yon", "long") == "long"
            yon_etiket = "LONG" if long_mu else "SHORT"
            pnl_pct = (guncel - entry) / entry * 100 if long_mu else (entry - guncel) / entry * 100
            anlik_kar = pnl_pct / 100 * d.get("notional", NOTIONAL)
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            kalan_dk = MAX_HOLD_SAAT * 60 - sure_dk
            satirlar.append(f"{sym} {yon_etiket} (1D:{d.get('1d')}/4H:{d.get('4h')}/1H:{d.get('1h')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f} | TP:{d.get('tp',0):.6f}\n"
                             f"  Açık süre: {sure_dk:.0f} dk | Max tutmaya kalan: {max(0,kalan_dk):.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="panel_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
    )
    markup.row(telebot.types.InlineKeyboardButton("📉 Açık Pozisyon Detayı", callback_data="panel_risk"))
    markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
    return markup


def geri_butonu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
    return markup


if bot:
    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
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
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[PANEL_BUTON] {e}")
            try: bot.answer_callback_query(call.id, "Tamam")
            except Exception: pass

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_risk_metni())

    @bot.message_handler(commands=["ozet"])
    def ozet_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni())

    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            acik = list(trade_state.keys())
        if not acik:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        if parca:
            hedef = next((s for s in acik if s.split("/")[0] == parca), None)
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' bulunamadı: {acik}")
                return
        else:
            if len(acik) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla pozisyon var: {acik}")
                return
            hedef = acik[0]
        bot.send_message(msg.chat.id, f"⏳ {hedef} kapatılıyor...")
        basari, mesaj = gercek_pozisyon_kapat(hedef)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["blokla"])
    def blokla_komutu(msg):
        if not yetkili_mi(msg):
            return
        parca = msg.text.replace("/blokla", "", 1).strip().upper()
        if not parca:
            bot.send_message(msg.chat.id, "Kullanım: /blokla COIN_ADI")
            return
        with bloke_lock:
            bloke_coinler.add(parca)
        bloke_diske_yaz()
        bot.send_message(msg.chat.id, f"🚫 {parca} engellendi.")

    @bot.message_handler(commands=["blokkaldir"])
    def blokkaldir_komutu(msg):
        if not yetkili_mi(msg):
            return
        parca = msg.text.replace("/blokkaldir", "", 1).strip().upper()
        if not parca:
            bot.send_message(msg.chat.id, "Kullanım: /blokkaldir COIN_ADI")
            return
        with bloke_lock:
            vardi = parca in bloke_coinler
            bloke_coinler.discard(parca)
        bloke_diske_yaz()
        bot.send_message(msg.chat.id, f"✅ {parca} engeli kaldırıldı." if vardi else f"ℹ️ {parca} zaten engelli değildi.")

    @bot.message_handler(commands=["sifirlagecmis"])
    def sifirlagecmis_komutu(msg):
        if not yetkili_mi(msg):
            return
        global trade_log
        with log_lock:
            trade_log = []
        atomik_yaz(TRADE_LOG_PATH, [])
        bot.send_message(msg.chat.id, "🗑️ İşlem geçmişi sıfırlandı.")

    @bot.message_handler(commands=["veri"])
    def veri_komutu(msg):
        if not yetkili_mi(msg):
            return
        with log_lock:
            veri = list(trade_log)
        if not veri:
            bot.send_message(msg.chat.id, "Henüz kapanan işlem yok.")
            return
        try:
            import io
            icerik = json.dumps(veri, ensure_ascii=False, indent=2)
            dosya = io.BytesIO(icerik.encode("utf-8"))
            dosya.name = f"live2_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
            bot.send_document(msg.chat.id, dosya, caption=f"📦 {len(veri)} işlem")
        except Exception as e:
            bot.send_message(msg.chat.id, f"⚠️ Hata: {e}")


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
    try:
        gercek_pozlar = exchange.fetch_positions()
        gercek_semboller = {p["symbol"] for p in gercek_pozlar if safe(p.get("contracts")) > 0}
    except Exception as e:
        log.warning(f"[UZLASTIRMA] {e}")
        return
    with state_lock:
        state_semboller = set(trade_state.keys())
    sadece_diskte = state_semboller - gercek_semboller
    for sym in sadece_diskte:
        with state_lock:
            trade_state.pop(sym, None)
        with cooldown_lock:
            son_kapanis_zamani[sym] = time.time()
    if sadece_diskte:
        durumu_diske_yaz()
        cooldown_diske_yaz()
    sadece_borsada = gercek_semboller - state_semboller
    if sadece_borsada:
        tg(f"⚠️ UYARI: borsada açık ama state'te olmayan pozisyonlar: {sorted(sadece_borsada)}\n"
           f"(Eski live_bot'tan kalma bir pozisyon olabilir - manuel kontrol et.)")


def manage_loop():
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            for sym in semboller:
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel = safe(t["last"])
                except Exception:
                    continue
                if guncel <= 0:
                    continue

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    gercek_pozisyon_kapat(sym, "max_hold_timeout")
                    continue

                yon_kayitli = durum.get("yon", "long")
                long_mu = (yon_kayitli == "long")
                aranan_yon = "yukselis" if long_mu else "dusus"

                if TREND_AJANI_AKTIF:
                    son_kontrol = durum.get("son_trend_kontrol", 0)
                    if time.time() - son_kontrol >= TREND_KONTROL_ARALIGI_SN:
                        try:
                            y1d = trend_yonu(get_df(sym, "1d", MA_PERIYOT + 10))
                            y4h = trend_yonu(get_df(sym, "4h", MA_PERIYOT + 5))
                            y1h = trend_yonu(get_df(sym, "1h", MA_PERIYOT + 5))
                            bozuk_sayisi = sum(1 for y in (y1d, y4h, y1h) if y != aranan_yon)
                            tam_ters = bozuk_sayisi >= 2
                            kismi_ters = bozuk_sayisi == 1

                            with state_lock:
                                if sym not in trade_state:
                                    continue
                                trade_state[sym]["son_trend_kontrol"] = time.time()
                                if tam_ters:
                                    trade_state[sym]["ters_trend_sayisi"] = trade_state[sym].get("ters_trend_sayisi", 0) + 1
                                    trade_state[sym]["kismi_ters_sayisi"] = 0
                                    sayac_tam = trade_state[sym]["ters_trend_sayisi"]
                                    sayac_kismi = 0
                                elif kismi_ters:
                                    trade_state[sym]["kismi_ters_sayisi"] = trade_state[sym].get("kismi_ters_sayisi", 0) + 1
                                    trade_state[sym]["ters_trend_sayisi"] = 0
                                    sayac_kismi = trade_state[sym]["kismi_ters_sayisi"]
                                    sayac_tam = 0
                                else:
                                    trade_state[sym]["ters_trend_sayisi"] = 0
                                    trade_state[sym]["kismi_ters_sayisi"] = 0
                                    sayac_tam = 0
                                    sayac_kismi = 0

                            if tam_ters and sayac_tam >= TREND_TERS_TEYIT_SAYISI:
                                tg(f"⚠️ {sym} — üst trend ÇOĞUNLUKLA bozuldu, kapatılıyor.")
                                gercek_pozisyon_kapat(sym, "trend_degisti")
                                continue
                            elif kismi_ters and sayac_kismi >= TREND_TERS_TEYIT_KISMI_SAYISI:
                                tg(f"⚠️ {sym} — üst trend KISMEN bozuldu, kapatılıyor.")
                                gercek_pozisyon_kapat(sym, "trend_kismi_degisti")
                                continue
                        except Exception as e:
                            log.warning(f"[TREND_KONTROL_HATA] {sym}: {e}")

                # ── v3.7 YENİ: KISMİ KÂR ALMA (SL kontrolünden ÖNCE) ──
                # Pozisyon KISMI_KAR_ESIK_PCT'e ulaştıysa (ve henüz kısmi
                # alınmadıysa), miktarın yarısı kapatılıp kalanın SL'i
                # breakeven'e çekilir. Bu, "hedefe ulaşmadan geri dönüp SL'e
                # gitme" riskini azaltmayı amaçlar.
                if KISMI_KAR_AKTIF and not durum.get("kismi_alindi", False):
                    kismi_esik_fiyat = (durum["entry"] * (1 + KISMI_KAR_ESIK_PCT) if long_mu
                                         else durum["entry"] * (1 - KISMI_KAR_ESIK_PCT))
                    kismi_esik_gecti = (guncel >= kismi_esik_fiyat) if long_mu else (guncel <= kismi_esik_fiyat)
                    if kismi_esik_gecti:
                        kismi_kar_al(sym, durum)
                        continue

                sl_tetiklendi = (guncel <= durum["sl"]) if long_mu else (guncel >= durum["sl"])
                if sl_tetiklendi:
                    gercek_pozisyon_kapat(sym, "sl")
                    continue

                tp = durum.get("tp")
                if tp is None:
                    log.warning(f"[ESKI_POZISYON] {sym} 'tp' alanı yok (v3.0 öncesi kalıntı olabilir) - güvenlik amaçlı kapatılıyor")
                    gercek_pozisyon_kapat(sym, "eski_format_guvenlik_kapanisi")
                    continue
                tp_tetiklendi = (guncel >= tp) if long_mu else (guncel <= tp)
                if tp_tetiklendi:
                    gercek_pozisyon_kapat(sym, "hizli_tp")
                    continue

                try:
                    pozlar = exchange.fetch_positions([sym])
                    gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
                    if not gercek_pos:
                        with state_lock:
                            durum2 = trade_state.pop(sym, None)
                        durumu_diske_yaz()
                        with cooldown_lock:
                            son_kapanis_zamani[sym] = time.time()
                        cooldown_diske_yaz()
                        if durum2:
                            _kapanis_kaydet_gercek_veriyle(sym, durum2, "sl_borsada_onceden")
                except Exception as e:
                    log.warning(f"[MANAGE_DOGRULA] {sym}: {e}")
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


def izleme_listesi_guncelle():
    if time.time() - _son_izleme_taramasi["ts"] < IZLEME_TARAMA_ARALIGI_SN:
        return
    _son_izleme_taramasi["ts"] = time.time()

    try:
        genis_liste = genis_evren_listesi()
    except Exception as e:
        log.warning(f"[IZLEME_TARAMA] {e}")
        return

    with izleme_lock:
        mevcut = set(izleme_listesi.keys())
    with state_lock:
        acik = set(trade_state.keys())

    adaylar = [s for s in genis_liste if s not in mevcut and s not in acik and not cooldown_da_mi(s)]
    if not adaylar:
        return

    eklenen = 0
    with ThreadPoolExecutor(max_workers=6) as havuz:
        gelecekler = {havuz.submit(iki_uzerinden_uc_kontrol, sym): sym for sym in adaylar}
        for gelecek in as_completed(gelecekler):
            sym = gelecekler[gelecek]
            try:
                uyumlu = gelecek.result()
            except Exception as e:
                log.warning(f"[IZLEME_KONTROL] {sym}: {e}")
                continue
            if not uyumlu:
                continue
            with izleme_lock:
                if sym in izleme_listesi:
                    continue
                if len(izleme_listesi) >= IZLEME_LISTESI_BOYUTU:
                    en_eski = min(izleme_listesi.items(), key=lambda kv: kv[1]["eklenme_zamani"])
                    izleme_listesi.pop(en_eski[0], None)
                izleme_listesi[sym] = {"eklenme_zamani": time.time()}
                eklenen += 1
    if eklenen:
        log.info(f"[IZLEME_LISTESI] {eklenen} yeni coin eklendi, liste boyutu={len(izleme_listesi)}")


def izleme_listesi_kontrol():
    with izleme_lock:
        izlenenler = dict(izleme_listesi)
    if not izlenenler:
        return 0

    acilanlar = 0
    for sym, kayit in izlenenler.items():
        with state_lock:
            if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
                continue
        if cooldown_da_mi(sym):
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            continue

        yas_saat = (time.time() - kayit["eklenme_zamani"]) / 3600
        if yas_saat > IZLEME_MAX_YAS_SAAT:
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            log.info(f"[IZLEME_LISTESI] {sym} bayatladı ({yas_saat:.1f}sa), listeden çıkarıldı")
            continue

        try:
            sinyal = ucyon_sinyal(sym)
        except Exception as e:
            log.warning(f"[IZLEME_SINYAL] {sym}: {e}")
            continue

        if sinyal:
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            with state_lock:
                if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
                    continue
            log.info(f"[IZLEME_LISTESI] {sym} tam uyuma ulaştı (1D+4H+1H+15m+hacim+pump), pozisyon açılıyor")
            gercek_pozisyon_ac(sinyal)
            acilanlar += 1
        else:
            try:
                if not iki_uzerinden_uc_kontrol(sym):
                    with izleme_lock:
                        izleme_listesi.pop(sym, None)
            except Exception:
                pass
    return acilanlar


def tarama_loop():
    tg(f"⚡ LIVE BOT v3.9 (FIRSATÇI + HACİM/PUMP + KISMİ KÂR + AKILLI TEMKİNLİ MOD, {'LONG+SHORT' if SHORT_AKTIF else 'LONG-only'}) başladı — GERÇEK PARA\n"
       f"MAX_POS={MAX_POS} | Marjin: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i (taban ${MARJIN_TABAN_USDT:.2f}, tavan ${MARJIN_TAVAN_USDT:.2f}), {LEV}x\n"
       f"Giriş: 1D+4H+1H uyum + hacim teyidi (x{HACIM_TEYIT_KATSAYI:.1f}) + pump filtresi (%{PUMP_FILTRE_ESIK_PCT:.0f} üstü reddedilir)\n"
       f"⚡ ÇIKIŞ: %{KISMI_KAR_ESIK_PCT*100:.1f}'te kısmi kâr al (%{KISMI_KAR_ORANI*100:.0f}) + breakeven, "
       f"tam hedef %{HIZLI_HEDEF_PCT*100:.1f} - iz sürme YOK\n"
       f"SL taban %{MIN_SL_PCT*100:.0f} | Max tutma: {MAX_HOLD_SAAT:.0f} saat\n"
       f"🔄 Trend dönüş ajanı: {'AKTİF' if TREND_AJANI_AKTIF else 'KAPALI (kullanıcı kararı)'}\n"
       f"🌡️ Temkinli mod: {'AKTİF' if TEMKINLI_MOD_AKTIF else 'KAPALI'} "
       f"(BTC düşerse MAX_POS yarıya iner, trend gücü eşiği %{MIN_4H_TREND_GUCU_PCT_TEMKINLI:.1f}'e yükselir - "
       f"BTC'den bağımsız güçlü coinler yine geçebilir)\n"
       f"👁️ İzleme listesi ajanı: max {IZLEME_LISTESI_BOYUTU} coin, {IZLEME_TARAMA_ARALIGI_SN//60}dk'da bir genişletiliyor\n\n"
       f"📌 v3.7 YENİ (14.09.2026): kısmi kâr alma + breakeven eklendi - "
       f"pozisyon %{KISMI_KAR_ESIK_PCT*100:.1f}'e ulaşınca yarısı kapatılıp kalan SL'i "
       f"girişe çekiliyor. Amaç: '%5 hedefe ulaşmadan geri dönüp kârı kaybetme' "
       f"riskini azaltmak. v3.6: hacim teyidi + pump filtresi (max_hold_timeout "
       f"grubundaki sessiz sinyalleri ve tepe-civarı girişleri elemek için).\n"
       f"⚠️ Tüm bu eşikler henüz canlıda tam test edilmedi, birkaç gün sonra "
       f"panel_analiz ile gözden geçirilecek.\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

    baslangic_uzlastirma()

    while True:
        try:
            emp = efektif_max_pos()
            with state_lock:
                bos_slot = emp - len(trade_state) - len(acilis_rezervasyonlari)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            try:
                izleme_listesi_guncelle()
                izleme_acilan = izleme_listesi_kontrol()
            except Exception as e:
                log.warning(f"[IZLEME_GENEL] {e}")
                izleme_acilan = 0

            emp = efektif_max_pos()
            with state_lock:
                bos_slot = emp - len(trade_state) - len(acilis_rezervasyonlari)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            adaylar = aday_havuzu()
            taranacaklar = []
            for sym in adaylar:
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym):
                    continue
                taranacaklar.append(sym)

            bulunan = 0
            if taranacaklar:
                with ThreadPoolExecutor(max_workers=4) as havuz:
                    gelecekler = {havuz.submit(ucyon_sinyal, sym): sym for sym in taranacaklar}
                    for gelecek in as_completed(gelecekler):
                        sym = gelecekler[gelecek]
                        try:
                            sinyal = gelecek.result()
                        except Exception as e:
                            log.warning(f"[TARAMA] {sym}: {e}")
                            continue
                        if sinyal:
                            with state_lock:
                                if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
                                    continue
                            gercek_pozisyon_ac(sinyal)
                            bulunan += 1

            with izleme_lock:
                izleme_boyut = len(izleme_listesi)
            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | bulunan={bulunan} | "
                     f"izleme_acilan={izleme_acilan} | izleme_liste={izleme_boyut}/{IZLEME_LISTESI_BOYUTU} | "
                     f"acik={emp-bos_slot}/{emp} (max_pos_normal={MAX_POS})")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("LIVE BOT v3.9 (1D+4H+1H, LONG-only, hacim+pump filtreli, kısmi kâr alma, akıllı temkinli mod) BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bloke_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
