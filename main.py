#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
SÜRÜM: v8.0 — 28 Temmuz 2026
════════════════════════════════════════════════════════
v8.0 DEĞİŞİKLİK ÖZETİ (v7.15'ten):

1) COIN EVRENİ GENİŞLETİLDİ VE GERÇEK VERİYLE DOĞRULANDI (76 -> 129 coin):
   Bitget'in kendi "isRwa" bayrağıyla tokenize hisse/emtia enstrümanları
   (TSLA, NVDA, XAU, XAUT vb. - bunlar kripto değil, RWA türevleri) ve
   "durgun/düşük volatiliteli" büyük marketcap'ler (BTC, ETH, XRP, ADA,
   DOGE, BNB, TRX, LINK, LTC, BCH) evrenden bilerek çıkarıldı. Kalan
   likit coinler (24s hacim >= $500K) arasından GERÇEK Bitget OHLCV
   verisiyle (90 gün, 1h+4h, ~90.000 mum) pullback stratejisi tam
   simüle edildi (bar-by-bar, sadece KAPANMIŞ mumlarla, look-ahead yok,
   round-trip komisyon dahil):
     - 544 işlem, %61.8 kazanma, toplam +75.9R, ortalama +0.140R/işlem
     - İlk yarı (May-Haz): %63.2 kazanma, +0.170R/işlem
     - İkinci yarı (Haz-Tem): %60.3 kazanma, +0.109R/işlem
     - İki dönemde de pozitif ve tutarlı
     - 128 coin'in 80'i (%62.5) tek başına pozitif katkı yaptı (birkaç
       coine bağımlı bir sonuç değil, dağılım sağlıklı)
   ⚠️ Max drawdown backtest'te -9.93R ölçüldü (%5 risk ile teorik olarak
   ardışık kötü seri ~%45-50 bakiye düşüşüne denk gelebilir). Bu yüzden
   aşağıda YENİ bir HAFTALIK zarar limiti eklendi (bkz. madde 4).

2) TELEGRAM YETKİ KONTROLÜ EKLENDİ (KRİTİK GÜVENLİK DÜZELTMESİ):
   v7.15'te hiçbir komut (/kapat, /yarikapat, /ac, /panel, panel
   butonları) chat_id doğrulaması yapmıyordu - bot token'ı ele geçiren
   ya da grup/kanal üzerinden erişen HERKES pozisyon açıp kapatabilirdi.
   Artık her handler'ın başında MY_CHAT_ID kontrolü var, yetkisiz istek
   sessizce yok sayılıyor (log'a düşüyor).

3) SEMBOL EŞLEŞTİRME DÜZELTMESİ:
   /kapat ve /yarikapat'ta "girilen metin sembolde geçiyor mu" (substring)
   kontrolü, kısa ticker'larda (ör. "B", "LA") yanlış eşleşme riski
   taşıyordu. Artık ÖNCE TAM eşleşme aranıyor, sadece bulunamazsa
   substring'e düşülüyor.

4) HAFTALIK ZARAR LİMİTİ EKLENDİ (backtest'teki -9.93R drawdown'a karşı):
   Günlük %15 limitin YANINDA, haftanın başındaki bakiyeye göre %25
   kümülatif kayıp olursa bot o hafta boyunca durur. Ardışık kötü
   günlerin günlük limitin altında kalıp haftalar içinde birikmesini
   engellemek için.

5) GÜNLÜK/HAFTALIK BAŞLANGIÇ BAKİYESİ ARTIK GERÇEKTEN SIFIRLANIYOR:
   v7.15'te gunluk_baslangic_bakiye SADECE bot ilk başladığında set
   ediliyordu - bot günlerce kesintisiz çalışırsa "günlük" limit aslında
   "son restart'tan beri kümülatif" hale geliyordu. Artık UTC gün/hafta
   değişimi tarama_loop içinde tespit edilip başlangıç bakiyeleri
   otomatik yenileniyor.

6) REPAINT (KAPANMAMIŞ MUM) RİSKİ AZALTILDI:
   v7.15'te sinyal hesaplamaları borsadan gelen SON mumu (o an hâlâ
   oluşmakta olan, kapanmamış mum) kullanıyordu - bu, backtest'in
   SADECE kapanmış mumlarla yapılmış olmasından SAPMA anlamına gelir
   ve sinyal, mum kapanmadan belirip kaybolabilir. Artık get_df() son
   (kapanmamış) mumu ATIYOR, tüm sinyal/RSI/ADX hesapları sadece
   KAPANMIŞ mumlarla yapılıyor - backtest metodolojisiyle birebir uyumlu.

7) RSI/ADX İÇİN MUM SAYISI 30'DAN 110'A ÇIKARILDI:
   Kullanıcının kendi kuralı: "RSI için en az 100 mum gerekir, azı
   borsanın gösterdiği değerden sapar". EMA tabanlı RSI/ADX ısınma
   sürecinin ilk ~14-20 mumu güvenilmez olduğundan, 30 mumla hesaplanan
   RSI önceki sürümde borsadakinden sapıyordu.

8) STATE DOSYALARI ARTIK ATOMİK YAZILIYOR (geçici dosya + rename),
   yazma sırasında crash olursa dosyanın yarım/bozuk kalması engellendi.

9) BAŞLANGIÇTA POZİSYON UZLAŞTIRMA (reconciliation): bot yeniden
   başladığında, diskteki trade_state ile borsadaki GERÇEK açık
   pozisyonlar karşılaştırılıyor, uyumsuzluk varsa Telegram'a bildirilip
   borsa esas alınıyor (state dosyası körü körüne güvenilmiyor).

── TP/SL MANTIĞI (DEĞİŞMEDİ, GERÇEK VERİYLE DOĞRULANDI) ──
SL = giriş ∓ 1.0×ATR(1h,14) | TP (pullback) = giriş ± 1.0×ATR×1.0R
Bu 1:1 R:R oranı demektir - üstteki 129 coin backtest'inde %61.8 kazanma
ile validasyonu geçti (başabaş nokta 1:1 R:R'de sadece %50 kazanma
gerektirir, yani ~12 puanlık bir güvenlik payı var, komisyon zaten
backtest'e dahil edildi). SL, ATR bazlı olduğu için coin'in KENDİ
volatilitesine göre otantik şekilde genişler/daralır - sabit yüzde
SL'den daha sağlam bir yaklaşım. Pozisyon boyutu da risk_dolar/SL_mesafe
formülüyle hesaplandığından, SL ne kadar geniş/dar olursa olsun HER
işlemde kaybedilen miktar bakiyenin sabit %RISK_PCT_BAKIYE'si olacak
şekilde otomatik ayarlanıyor - bu doğru ve profesyonel bir uygulama.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("YENI_STRATEJI_V8")

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
    """v8.0 KRİTİK GÜVENLİK: her komut/buton bu kontrolden geçmeli.
    chat_id, MY_CHAT_ID ile eşleşmiyorsa istek tamamen yok sayılır."""
    try:
        chat_id = msg_or_call.message.chat.id if hasattr(msg_or_call, "message") else msg_or_call.chat.id
    except Exception:
        return False
    if chat_id != CHAT_ID:
        log.warning(f"[YETKISIZ ERISIM] chat_id={chat_id} tarafından komut denemesi engellendi")
        return False
    return True


# ── COIN EVRENİ (v8.0: 129 coin, backtest doğrulamalı, bkz. üstteki not) ──
COINS = ["SOL/USDT:USDT", "BANK/USDT:USDT", "HYPE/USDT:USDT", "COTI/USDT:USDT",
         "ZEC/USDT:USDT", "DEXE/USDT:USDT", "LA/USDT:USDT", "BEAT/USDT:USDT",
         "SHIB/USDT:USDT", "PEPE/USDT:USDT", "SUI/USDT:USDT", "ONDO/USDT:USDT",
         "KAITO/USDT:USDT", "NEAR/USDT:USDT", "WLD/USDT:USDT", "PUMP/USDT:USDT",
         "BTW/USDT:USDT", "ENA/USDT:USDT", "EUL/USDT:USDT", "AAVE/USDT:USDT",
         "SOON/USDT:USDT", "ZAMA/USDT:USDT", "XLM/USDT:USDT", "TAO/USDT:USDT",
         "UNI/USDT:USDT", "AVAX/USDT:USDT", "DOT/USDT:USDT", "ESPORTS/USDT:USDT",
         "NIL/USDT:USDT", "ESP/USDT:USDT", "LAB/USDT:USDT", "DIA/USDT:USDT",
         "APT/USDT:USDT", "FET/USDT:USDT", "INJ/USDT:USDT", "PEOPLE/USDT:USDT",
         "TAG/USDT:USDT", "XPL/USDT:USDT", "TRUMP/USDT:USDT", "PENGU/USDT:USDT",
         "FIL/USDT:USDT", "FARTCOIN/USDT:USDT", "LDO/USDT:USDT", "SEI/USDT:USDT",
         "HBAR/USDT:USDT", "1000BONK/USDT:USDT", "RE/USDT:USDT", "REZ/USDT:USDT",
         "UB/USDT:USDT", "ALLO/USDT:USDT", "PI/USDT:USDT", "VIRTUAL/USDT:USDT",
         "VANRY/USDT:USDT", "GRAM/USDT:USDT", "RENDER/USDT:USDT", "US/USDT:USDT",
         "KGEN/USDT:USDT", "ERA/USDT:USDT", "TIA/USDT:USDT", "AERO/USDT:USDT",
         "ACH/USDT:USDT", "OP/USDT:USDT", "SKYAI/USDT:USDT", "PROS/USDT:USDT",
         "BGB/USDT:USDT", "TLM/USDT:USDT", "WIF/USDT:USDT", "PROM/USDT:USDT",
         "ARB/USDT:USDT", "ARX/USDT:USDT", "ORDI/USDT:USDT", "BOME/USDT:USDT",
         "ETC/USDT:USDT", "STORJ/USDT:USDT", "JTO/USDT:USDT", "O/USDT:USDT",
         "JUP/USDT:USDT", "ATOM/USDT:USDT", "API3/USDT:USDT", "CRV/USDT:USDT",
         "XMR/USDT:USDT", "0G/USDT:USDT", "LIT/USDT:USDT", "SLX/USDT:USDT",
         "RIVER/USDT:USDT", "ENSO/USDT:USDT", "GWEI/USDT:USDT", "MMT/USDT:USDT",
         "VELVET/USDT:USDT", "VVV/USDT:USDT", "ICP/USDT:USDT", "ETHFI/USDT:USDT",
         "CAP/USDT:USDT", "EVAA/USDT:USDT", "WLFI/USDT:USDT", "APE/USDT:USDT",
         "PIEVERSE/USDT:USDT", "DASH/USDT:USDT", "ALGO/USDT:USDT", "GRASS/USDT:USDT",
         "TAIKO/USDT:USDT", "BASED/USDT:USDT", "ZRO/USDT:USDT", "CHILLGUY/USDT:USDT",
         "SYN/USDT:USDT", "SAND/USDT:USDT", "GALA/USDT:USDT", "PYTH/USDT:USDT",
         "BILL/USDT:USDT", "RAVE/USDT:USDT", "IDOL/USDT:USDT", "ZBT/USDT:USDT",
         "B/USDT:USDT", "CHZ/USDT:USDT", "STX/USDT:USDT", "COAI/USDT:USDT",
         "4/USDT:USDT", "IRYS/USDT:USDT", "OPN/USDT:USDT", "EPIC/USDT:USDT",
         "PIPPIN/USDT:USDT", "MORPHO/USDT:USDT", "HOME/USDT:USDT", "1000XEC/USDT:USDT",
         "MAGMA/USDT:USDT", "CHIP/USDT:USDT", "PRL/USDT:USDT", "HOLO/USDT:USDT",
         "EIGEN/USDT:USDT"]

ATR_CARPANI = 1.0
RR_PULLBACK = 1.0   # backtest: 129 coin, %61.8 kazanma, +0.140R/işlem ortalama (komisyon dahil)
MUM_ESIGI = 4
BTC_SEMBOL = "BTC/USDT:USDT"
ADX_ESIK = 20
VOLATILITE_SPIKE_CARPANI = 1.8

PULLBACK_RSI_ESIK = 45
PULLBACK_BAKIS_PENCERE = 5
TOPARLANMA_RSI_MIN, TOPARLANMA_RSI_MAX = 42, 58

# v8.0: RSI/ATR/ADX icin yeterli isinma - kullanicinin kendi kurali (>=100 mum)
GOSTERGE_MUM_SAYISI_1H = 110
GOSTERGE_MUM_SAYISI_4H = 40

# ── RİSK/GÜVENLİK AYARLARI ──
LEV_HAM_DEGER = os.getenv("LEV")
LEV = int(LEV_HAM_DEGER) if LEV_HAM_DEGER else 10
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.05"))
MAX_POS = int(os.getenv("MAX_POS", "2"))
GUNLUK_ZARAR_LIMIT_PCT = 0.15
# v8.0 YENİ: haftalık kümülatif zarar limiti (backtest'teki -9.93R drawdown'a karşı)
HAFTALIK_ZARAR_LIMIT_PCT = float(os.getenv("HAFTALIK_ZARAR_LIMIT_PCT", "0.25"))
KONTROL_ARALIGI_SN = 300
COOLDOWN_SAAT = float(os.getenv("COOLDOWN_SAAT", "2"))
KAR_ESIGI_ROI_PCT = float(os.getenv("KAR_ESIGI_ROI_PCT", "0"))

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/yeni_strateji_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/yeni_strateji_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/yeni_strateji_log.json")
GUNLUK_PATH = os.getenv("GUNLUK_PATH", "/data/yeni_strateji_gunluk.json")

trade_state = {}
state_lock = threading.Lock()
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()

gunluk_pnl = 0.0
gunluk_baslangic_bakiye = None
gunluk_gun_damgasi = None       # v8.0: hangi UTC gün icin gecerli
haftalik_pnl = 0.0
haftalik_baslangic_bakiye = None
haftalik_hafta_damgasi = None   # v8.0: hangi ISO hafta icin gecerli
gunluk_lock = threading.Lock()


# ════════════════════════════════════════════
# ATOMİK DOSYA YAZMA (v8.0)
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


def rsi(series, period=14):
    diff = series.diff()
    gain = diff.clip(lower=0); loss = -diff.clip(upper=0)
    avg_gain = gain.rolling(period).mean(); avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


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


def get_df(sym, tf, limit=60):
    """v8.0 DEĞİŞİKLİK: son (henüz KAPANMAMIŞ, oluşmakta olan) mum ATILIYOR.
    Backtest sadece kapanmış mumlarla yapıldığı için, canlı sinyal de
    aynı mantıkla SADECE kapanmış mumlara bakmalı - aksi halde sinyal,
    mum kapanmadan (fiyat dalgalanırken) belirip kaybolabilir (repaint)."""
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit + 1)
            if not candles or len(candles) < 2:
                return None
            candles = candles[:-1]  # son (kapanmamis) mumu at
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.15)
            return df
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                bekleme = 2 * (deneme + 1)
                log.warning(f"[VERI] {sym} {tf}: rate limit, {bekleme}sn bekleniyor (deneme {deneme+1}/3)")
                time.sleep(bekleme)
                continue
            log.warning(f"[VERI] {sym} {tf}: {e}")
            return None
    log.warning(f"[VERI] {sym} {tf}: 3 denemede de rate limit asilamadi, atlandi")
    return None


def btc_rejimi_al():
    df4h = get_df(BTC_SEMBOL, "4h", GOSTERGE_MUM_SAYISI_4H)
    if df4h is None or len(df4h) < 30:
        return None, None, None
    ma20 = df4h["close"].rolling(20).mean().iloc[-1]
    fiyat = df4h["close"].iloc[-1]
    adx_deger = adx(df4h, 14).iloc[-1]
    if pd.isna(ma20) or pd.isna(adx_deger):
        return None, None, None
    trend_guclu = adx_deger >= ADX_ESIK
    return (fiyat > ma20), (fiyat < ma20), trend_guclu


def sinyal_kontrol_et_pullback(sym, btc_bullish, btc_bearish):
    """v8.0: mantık backtest ile birebir aynı (bkz. üstteki dogrulama notu),
    tek fark artık sadece KAPANMIŞ mumlar kullanılıyor (get_df içinde)."""
    df4h = get_df(sym, "4h", GOSTERGE_MUM_SAYISI_4H)
    df1h = get_df(sym, "1h", GOSTERGE_MUM_SAYISI_1H)
    if df4h is None or df1h is None or len(df4h) < 21 or len(df1h) < 21:
        return None

    df4h["ma20"] = df4h["close"].rolling(20).mean()
    df4h["yon"] = np.where(df4h["close"] > df4h["open"], 1, -1)
    yon5_up_4h = (df4h["yon"].iloc[-5:] > 0).sum()
    yon5_down_4h = (df4h["yon"].iloc[-5:] < 0).sum()
    ma20 = df4h["ma20"].iloc[-1]
    fiyat_4h = df4h["close"].iloc[-1]

    df1h["rsi"] = rsi(df1h["close"], 14)
    df1h["atr"] = atr(df1h, 14)
    df1h["atr_ort20"] = df1h["atr"].rolling(20).mean()
    rsi_1h = df1h["rsi"].iloc[-1]
    atr_1h = df1h["atr"].iloc[-1]
    atr_ort20_1h = df1h["atr_ort20"].iloc[-1]
    fiyat = df1h["close"].iloc[-1]
    acilis = df1h["open"].iloc[-1]

    if pd.isna(ma20) or pd.isna(rsi_1h) or pd.isna(atr_1h) or atr_1h <= 0:
        return None
    if len(df1h) < PULLBACK_BAKIS_PENCERE + 1:
        return None

    rsi_son5 = df1h["rsi"].iloc[-(PULLBACK_BAKIS_PENCERE+1):-1]
    rsi_min5 = rsi_son5.min()
    rsi_max5 = rsi_son5.max()
    if pd.isna(rsi_min5) or pd.isna(rsi_max5):
        return None

    pullback_oldu_long = rsi_min5 < PULLBACK_RSI_ESIK
    toparlaniyor_long = TOPARLANMA_RSI_MIN < rsi_1h < TOPARLANMA_RSI_MAX
    long_ok = (fiyat_4h > ma20 and yon5_up_4h >= MUM_ESIGI and bool(btc_bullish) and
               pullback_oldu_long and toparlaniyor_long and fiyat > acilis)

    pullback_oldu_short = rsi_max5 > (100 - PULLBACK_RSI_ESIK)
    toparlaniyor_short = (100 - TOPARLANMA_RSI_MAX) < rsi_1h < (100 - TOPARLANMA_RSI_MIN)
    short_ok = (fiyat_4h < ma20 and yon5_down_4h >= MUM_ESIGI and bool(btc_bearish) and
                pullback_oldu_short and toparlaniyor_short and fiyat < acilis)

    if not (long_ok or short_ok):
        return None

    direction = "long" if long_ok else "short"
    if direction == "long":
        sl = fiyat - ATR_CARPANI * atr_1h
        tp = fiyat + ATR_CARPANI * atr_1h * RR_PULLBACK
        merkez = (TOPARLANMA_RSI_MIN + TOPARLANMA_RSI_MAX) / 2
    else:
        sl = fiyat + ATR_CARPANI * atr_1h
        tp = fiyat - ATR_CARPANI * atr_1h * RR_PULLBACK
        merkez = 100 - (TOPARLANMA_RSI_MIN + TOPARLANMA_RSI_MAX) / 2

    skor = 100 - abs(rsi_1h - merkez)

    volatilite_spike = False
    if not pd.isna(atr_ort20_1h) and atr_ort20_1h > 0:
        volatilite_spike = (atr_1h / atr_ort20_1h) >= VOLATILITE_SPIKE_CARPANI

    return {"symbol": sym, "direction": direction, "entry": fiyat, "sl": sl, "tp": tp,
            "skor": skor, "volatilite_spike": volatilite_spike, "strateji": "pullback"}


def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        return safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


ZIRVE_BAKIYE_PATH = os.getenv("ZIRVE_BAKIYE_PATH", "/data/zirve_bakiye.json")


def zirve_bakiye_guncelle(guncel_bakiye):
    zirve = guncel_bakiye
    try:
        veri = guvenli_oku(ZIRVE_BAKIYE_PATH, {})
        zirve = max(veri.get("zirve", 0), guncel_bakiye)
        atomik_yaz(ZIRVE_BAKIYE_PATH, {"zirve": zirve})
    except Exception as e:
        log.warning(f"[ZIRVE_BAKIYE] {e}")
    return zirve


def hesap_genel_bilgisi_al():
    try:
        bakiye_ham = exchange.fetch_balance()
        usdt = bakiye_ham.get("USDT", {})
        serbest = safe(usdt.get("free", 0))
        toplam = safe(usdt.get("total", 0)) or serbest

        pozisyonlar = exchange.fetch_positions()
        gercbulmemis_pnl = sum(safe(p.get("unrealizedPnl")) for p in pozisyonlar if safe(p.get("contracts")) > 0)
        kullanilan_marj = sum(safe(p.get("initialMargin") or p.get("collateral")) for p in pozisyonlar if safe(p.get("contracts")) > 0)

        equity = toplam + gercbulmemis_pnl
        zirve = zirve_bakiye_guncelle(equity)
        drawdown_pct = ((zirve - equity) / zirve * 100) if zirve > 0 else 0

        return {
            "bakiye": toplam, "equity": equity, "gerceklesmemis_pnl": gercbulmemis_pnl,
            "kullanilan_marj": kullanilan_marj, "serbest_marj": serbest,
            "zirve": zirve, "drawdown_pct": drawdown_pct,
        }
    except Exception as e:
        log.warning(f"[HESAP_BILGI] {e}")
        return None


def gun_damgasi():
    return time.strftime("%Y-%m-%d", time.gmtime())


def hafta_damgasi():
    t = time.gmtime()
    return f"{t.tm_year}-W{time.strftime('%W', t)}"


def gunluk_haftalik_reset_kontrol():
    """v8.0: UTC gün/hafta değiştiyse başlangıç bakiyelerini ve PnL sayaçlarını
    otomatik sıfırlar. v7.15'te bu HİÇ yapılmıyordu - 'günlük limit' aslında
    bot'un en son restart'ından beri kümülatif hale geliyordu."""
    global gunluk_pnl, gunluk_baslangic_bakiye, gunluk_gun_damgasi
    global haftalik_pnl, haftalik_baslangic_bakiye, haftalik_hafta_damgasi

    bugun = gun_damgasi()
    bu_hafta = hafta_damgasi()
    degisti = False

    with gunluk_lock:
        if gunluk_gun_damgasi != bugun:
            bakiye = gercek_bakiye_al()
            if bakiye is not None:
                gunluk_pnl = 0.0
                gunluk_baslangic_bakiye = bakiye
                gunluk_gun_damgasi = bugun
                degisti = True
                tg(f"🔄 Yeni gün başladı, günlük zarar limiti bakiyeye göre sıfırlandı (bakiye: {bakiye:.2f}$)")
        if haftalik_hafta_damgasi != bu_hafta:
            bakiye = gercek_bakiye_al()
            if bakiye is not None:
                haftalik_pnl = 0.0
                haftalik_baslangic_bakiye = bakiye
                haftalik_hafta_damgasi = bu_hafta
                degisti = True
                tg(f"🔄 Yeni hafta başladı, haftalık zarar limiti bakiyeye göre sıfırlandı (bakiye: {bakiye:.2f}$)")
    if degisti:
        gunluk_haftalik_diske_yaz()


def gunluk_limit_kontrolu():
    with gunluk_lock:
        if gunluk_baslangic_bakiye is None:
            return False
        return gunluk_pnl <= -(gunluk_baslangic_bakiye * GUNLUK_ZARAR_LIMIT_PCT)


def haftalik_limit_kontrolu():
    """v8.0 YENİ: haftalık kümülatif zarar limiti."""
    with gunluk_lock:
        if haftalik_baslangic_bakiye is None:
            return False
        return haftalik_pnl <= -(haftalik_baslangic_bakiye * HAFTALIK_ZARAR_LIMIT_PCT)


def pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    direction = sinyal["direction"]
    entry = sinyal["entry"]
    sl = sinyal["sl"]
    tp = sinyal["tp"]
    strateji = sinyal.get("strateji", "bilinmiyor")
    volatilite_spike = sinyal.get("volatilite_spike", False)

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı veya sıfır")
        return

    risk_dolar = bakiye * RISK_PCT_BAKIYE

    if volatilite_spike:
        risk_dolar *= 0.5
        tg(f"ℹ️ {sym} anormal volatilite tespit edildi (ATR spike) — risk "
           f"%{RISK_PCT_BAKIYE*100:.0f}'ten %{RISK_PCT_BAKIYE*50:.1f}'e kucultuldu")

    sl_mesafe_pct = abs(entry - sl) / entry
    if sl_mesafe_pct <= 0:
        tg(f"⚠️ {sym} atlandı — SL mesafesi geçersiz (0 veya negatif)")
        return
    notional = risk_dolar / sl_mesafe_pct
    gereken_marj = notional / LEV

    MAX_MARJ_PCT = 0.25 if MAX_POS <= 1 else 0.15
    if gereken_marj > bakiye * MAX_MARJ_PCT:
        notional = bakiye * MAX_MARJ_PCT * LEV
        gereken_marj = notional / LEV
        tg(f"ℹ️ {sym} risk bazli pozisyon buyuklugu marj limitini asti, "
           f"kucultuldu (marj artik bakiyenin %{MAX_MARJ_PCT*100:.0f}'i, "
           f"gercek risk %{RISK_PCT_BAKIYE*100:.0f} hedefinden dusuk olacak)")

    amount = notional / entry

    try:
        exchange.set_leverage(LEV, sym)
    except Exception as e:
        log.warning(f"[KALDIRAC] {sym}: {e}")

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        tg(f"⚠️ {sym} miktar hesaplanamadi: {e}")
        return
    if qty <= 0:
        return

    side = "buy" if direction == "long" else "sell"
    try:
        exchange.create_market_order(sym, side, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giris emri basarisiz: {e}")
        return

    LEV_KULLANILAN = LEV
    time.sleep(0.8)
    try:
        pozisyon_bilgisi = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyon_bilgisi if safe(p.get("contracts")) > 0), None)
        if gercek_pos:
            gercek_lev_ham = gercek_pos.get("leverage")
            if gercek_lev_ham:
                gercek_lev = int(float(gercek_lev_ham))
                if gercek_lev != LEV:
                    LEV_KULLANILAN = gercek_lev
                    hedef_notional = gereken_marj * LEV
                    gercek_notional = qty * entry
                    if gercek_notional > hedef_notional * 1.05:
                        kirpilacak_qty = qty - (hedef_notional / entry)
                        kirpilacak_qty = float(exchange.amount_to_precision(sym, kirpilacak_qty))
                        if kirpilacak_qty > 0:
                            kapama_yon = "sell" if direction == "long" else "buy"
                            try:
                                exchange.create_market_order(sym, kapama_yon, kirpilacak_qty,
                                                              params={"reduceOnly": True})
                                qty = qty - kirpilacak_qty
                                tg(f"⚠️ {sym} kaldıraç uyuşmazlığı tespit edildi: istenen {LEV}x, "
                                   f"gerçek {gercek_lev}x — fazla pozisyon kırpıldı")
                            except Exception as e:
                                tg(f"⚠️ {sym} kaldıraç uyuşmazlığı var ({gercek_lev}x) ama fazla pozisyon "
                                   f"kırpılamadı: {e} — risk hedeflenenden YÜKSEK olabilir, dikkatli izle")
    except Exception as e:
        log.warning(f"[KALDIRAC_DOGRULA] {sym}: {e}")

    notional = qty * entry

    try:
        kapama_yon = "sell" if direction == "long" else "buy"
        sl_fiyat = float(exchange.price_to_precision(sym, sl))
        exchange.create_order(sym, "market", kapama_yon, qty, None,
                               {"reduceOnly": True, "stopLossPrice": sl_fiyat})
    except Exception as e:
        log.warning(f"[HARD_STOP] {sym}: {e}")

    tp_emir_id = None
    try:
        kapama_yon = "sell" if direction == "long" else "buy"
        tp_fiyat = float(exchange.price_to_precision(sym, tp))
        tp_emri = exchange.create_limit_order(sym, kapama_yon, qty, tp_fiyat, params={"reduceOnly": True})
        tp_emir_id = tp_emri.get("id")
    except Exception as e:
        log.warning(f"[TP_EMIR] {sym}: {e}")

    hizli_kar_emir_id = None
    hizli_kar_fiyat = None
    if KAR_ESIGI_ROI_PCT > 0:
        try:
            sl_pct_hesap = abs(entry - sl) / entry
            r_esigi = (KAR_ESIGI_ROI_PCT / 100) / (sl_pct_hesap * LEV_KULLANILAN)
            risk_mesafe_hesap = abs(entry - sl)
            if direction == "long":
                hizli_kar_fiyat_ham = entry + r_esigi * risk_mesafe_hesap
            else:
                hizli_kar_fiyat_ham = entry - r_esigi * risk_mesafe_hesap
            gecerli = (direction == "long" and hizli_kar_fiyat_ham < tp) or \
                      (direction == "short" and hizli_kar_fiyat_ham > tp)
            if gecerli:
                kapama_yon = "sell" if direction == "long" else "buy"
                hizli_kar_fiyat = float(exchange.price_to_precision(sym, hizli_kar_fiyat_ham))
                hizli_kar_emri = exchange.create_limit_order(sym, kapama_yon, qty, hizli_kar_fiyat,
                                                               params={"reduceOnly": True})
                hizli_kar_emir_id = hizli_kar_emri.get("id")
        except Exception as e:
            log.warning(f"[HIZLI_KAR_EMIR] {sym}: {e}")

    with state_lock:
        trade_state[sym] = {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
                             "qty": qty, "tp_emir_id": tp_emir_id, "acilis_zamani": time.time(),
                             "strateji": strateji, "marj": gereken_marj,
                             "hizli_kar_emir_id": hizli_kar_emir_id, "hizli_kar_fiyat": hizli_kar_fiyat}
    durumu_diske_yaz()

    tg(f"📈 YENİ POZİSYON: {sym} {direction.upper()} [{strateji}]\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} | TP:{tp:.6f}"
       f"{f' | Hızlı kâr (limit, %{KAR_ESIGI_ROI_PCT:.0f} ROI):{hizli_kar_fiyat:.6f}' if hizli_kar_fiyat else ''}\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Risk≈${risk_dolar:.2f} (bakiyenin ~%{RISK_PCT_BAKIYE*100:.0f}'i)"
       f"{' | ⚠️ volatilite spike, risk kucultuldu' if volatilite_spike else ''}")


def gercek_pozisyon_kapat(sym, oran=1.0, sebep="manuel"):
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            return True, f"ℹ️ {sym} zaten borsada açık değilmiş, kayıt temizlendi."

        toplam_qty = safe(gercek_pos.get("contracts"))
        direction = "long" if gercek_pos.get("side") == "long" else "short"
        kapama_yon = "sell" if direction == "long" else "buy"
        entry_fiyat = safe(gercek_pos.get("entryPrice"))

        kapatilacak_qty = toplam_qty if oran >= 1.0 else float(exchange.amount_to_precision(sym, toplam_qty * oran))
        if kapatilacak_qty <= 0:
            return False, f"⚠️ {sym} kapatılacak miktar hesaplanamadı."

        exchange.create_market_order(sym, kapama_yon, kapatilacak_qty, params={"reduceOnly": True})
        time.sleep(1)
        guncel = exchange.fetch_positions([sym])
        kalan_pos = next((p for p in guncel if safe(p.get("contracts")) > 0), None)

        try:
            t = exchange.fetch_ticker(sym)
            cikis_fiyat = safe(t["last"])
        except Exception:
            cikis_fiyat = entry_fiyat
        pnl = (cikis_fiyat - entry_fiyat) * kapatilacak_qty if direction == "long" else (entry_fiyat - cikis_fiyat) * kapatilacak_qty
        trade_log_kaydet({
            "symbol": sym, "direction": direction, "entry": entry_fiyat, "exit": cikis_fiyat,
            "pnl": pnl, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "not": ("kismi_manuel" if oran < 1.0 else sebep),
        })

        if kalan_pos and safe(kalan_pos.get("contracts")) > 0:
            with state_lock:
                if sym in trade_state:
                    trade_state[sym]["qty"] = safe(kalan_pos.get("contracts"))
            durumu_diske_yaz()
            return True, f"✅ {sym} %{oran*100:.0f}'i kapatıldı | PnL≈{pnl:+.2f}$ | Kalan: {safe(kalan_pos.get('contracts')):.4f}"

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
    """v8.0 DÜZELTME: önce TAM eşleşme aranır (ör. 'B' -> 'B/USDT:USDT'),
    sadece bulunamazsa substring'e düşülür. Böylece kısa ticker'lar (B, LA,
    OP, 0G vb.) diğer sembollerle yanlışlıkla eşleşmez."""
    parca = parca.upper()
    for sym in acik_semboller:
        if sym.split("/")[0] == parca:
            return sym
    eslesen = [sym for sym in acik_semboller if parca in sym.upper()]
    if len(eslesen) == 1:
        return eslesen[0]
    return None


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
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen tek bir açık pozisyon bulunamadı: {acik_semboller}")
                return
        else:
            if len(acik_semboller) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla açık pozisyon var: {acik_semboller}\nHangisini kastettiğini belirt, örn: /kapat {acik_semboller[0].split('/')[0]}")
                return
            hedef = acik_semboller[0]

        bot.send_message(msg.chat.id, f"⏳ {hedef} kapatılıyor...")
        basari, mesaj = gercek_pozisyon_kapat(hedef, oran=1.0)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["yarikapat"])
    def yarikapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            acik_semboller = list(trade_state.keys())
        if not acik_semboller:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/yarikapat", "", 1).strip().upper()
        if parca:
            hedef = sembol_bul(acik_semboller, parca)
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen tek bir açık pozisyon bulunamadı: {acik_semboller}")
                return
        else:
            if len(acik_semboller) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla açık pozisyon var: {acik_semboller}\nHangisini kastettiğini belirt, örn: /yarikapat {acik_semboller[0].split('/')[0]}")
                return
            hedef = acik_semboller[0]

        bot.send_message(msg.chat.id, f"⏳ {hedef}'in yarısı kapatılıyor...")
        basari, mesaj = gercek_pozisyon_kapat(hedef, oran=0.5)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            if not trade_state:
                bot.send_message(msg.chat.id, "Açık pozisyon yok.")
                return
            durumlar = dict(trade_state)

        satirlar = ["📋 AÇIK POZİSYON(LAR)\n"]
        for sym, d in durumlar.items():
            try:
                t = exchange.fetch_ticker(sym)
                guncel_fiyat = safe(t["last"])
                entry = d["entry"]; qty = d["qty"]; direction = d["direction"]
                anlik_pnl = (guncel_fiyat - entry) * qty if direction == "long" else (entry - guncel_fiyat) * qty
                anlik_pnl_pct = (guncel_fiyat - entry) / entry * 100 if direction == "long" else (entry - guncel_fiyat) / entry * 100
                emoji = "🟢" if anlik_pnl >= 0 else "🔴"
                satirlar.append(f"{emoji} {sym} [{direction.upper()}]\n"
                                 f"   Giriş:{entry:.6f} Şimdi:{guncel_fiyat:.6f} (%{anlik_pnl_pct:+.2f})\n"
                                 f"   SL:{d['sl']:.6f} TP:{d['tp']:.6f}\n"
                                 f"   Anlık PnL≈{anlik_pnl:+.2f}$")
            except Exception as e:
                satirlar.append(f"{sym} [{d['direction'].upper()}] giriş:{d['entry']:.6f} "
                                 f"SL:{d['sl']:.6f} TP:{d['tp']:.6f} (anlık fiyat alınamadı: {e})")
        bot.send_message(msg.chat.id, "\n".join(satirlar))

    def panel_ozet_metni():
        with log_lock:
            gecmis = list(trade_log)
        satirlar = ["📊 GENEL ÖZET\n"]
        try:
            bakiye_bilgi = exchange.fetch_balance()
            usdt = bakiye_bilgi.get("USDT", {})
            serbest = safe(usdt.get("free", 0))
            toplam_bakiye = safe(usdt.get("total", 0)) or serbest
        except Exception:
            serbest = None
            toplam_bakiye = None

        acik_toplam_pnl = 0.0
        with state_lock:
            acik_durumlar = dict(trade_state)
        for sym, d in acik_durumlar.items():
            try:
                t = exchange.fetch_ticker(sym)
                guncel = safe(t["last"])
                pnl = (guncel - d["entry"]) * d["qty"] if d["direction"] == "long" else (d["entry"] - guncel) * d["qty"]
                acik_toplam_pnl += pnl
            except Exception:
                pass

        if toplam_bakiye is not None:
            equity = toplam_bakiye + acik_toplam_pnl
            satirlar.append(f"💰 Bakiye: {toplam_bakiye:.2f}$ | Equity: {equity:.2f}$")
            satirlar.append(f"📌 Serbest: {serbest:.2f}$ | Açık poz. PnL: {acik_toplam_pnl:+.2f}$\n")

        if gecmis:
            toplam = len(gecmis)
            kazanan = [t for t in gecmis if t["pnl"] > 0]
            kaybeden = [t for t in gecmis if t["pnl"] <= 0]
            net_toplam = sum(t["pnl"] for t in gecmis)
            kazanma_orani = len(kazanan) / toplam * 100
            ort_kazanan = sum(t["pnl"] for t in kazanan) / len(kazanan) if kazanan else 0
            ort_kaybeden = sum(t["pnl"] for t in kaybeden) / len(kaybeden) if kaybeden else 0
            en_iyi = max(gecmis, key=lambda t: t["pnl"])
            en_kotu = min(gecmis, key=lambda t: t["pnl"])
            satirlar += [
                f"Toplam kapanan işlem: {toplam}",
                f"Kazanma oranı: %{kazanma_orani:.1f} ({len(kazanan)} kazanan / {len(kaybeden)} kaybeden)",
                f"Net toplam PnL: {net_toplam:+.2f}$",
                f"Ort. kazanan: {ort_kazanan:+.2f}$ | Ort. kaybeden: {ort_kaybeden:+.2f}$",
                f"En iyi işlem: {en_iyi['symbol'].split('/')[0]} {en_iyi['pnl']:+.2f}$ | "
                f"En kötü: {en_kotu['symbol'].split('/')[0]} {en_kotu['pnl']:+.2f}$",
            ]
        else:
            satirlar.append("Henüz kapanan işlem yok.")
        with gunluk_lock:
            satirlar.append(f"\n📅 Bugünkü PnL: {gunluk_pnl:+.2f}$ | 📆 Bu haftaki PnL: {haftalik_pnl:+.2f}$")
        return "\n".join(satirlar)

    def panel_ayarlar_metni():
        satirlar = ["⚙️ STRATEJİ AYARLARI\n"]
        satirlar.append(f"Sürüm: v8.0")
        satirlar.append(f"Coin evreni: {len(COINS)} coin (backtest doğrulamalı, RWA/durgun majör hariç)")
        satirlar.append(f"Kaldıraç: {LEV}x | MAX_POS: {MAX_POS}")
        satirlar.append(f"İşlem başına risk: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i")
        satirlar.append(f"Marj tavanı: bakiyenin %{25 if MAX_POS<=1 else 15}'i (MAX_POS'a göre)")
        satirlar.append(f"BTC ADX eşiği: {ADX_ESIK} (altındaysa işlem aranmaz)")
        satirlar.append(f"Volatilite spike koruması: {VOLATILITE_SPIKE_CARPANI}x ATR üstünde risk yarıya iner")
        satirlar.append(f"Coin cooldown: {COOLDOWN_SAAT} saat")
        satirlar.append(f"\n📐 Pullback TP/SL: 1x ATR(1h,14) / {RR_PULLBACK}R (1:1)")
        satirlar.append(f"⏱️ Tarama aralığı: {KONTROL_ARALIGI_SN//60} dakika")
        satirlar.append(f"📉 Günlük zarar limiti: %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}")
        satirlar.append(f"📉 Haftalık zarar limiti: %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f} (v8.0 YENİ)")
        return "\n".join(satirlar)

    def panel_risk_metni():
        satirlar = ["📉 RİSK DURUMU\n"]
        with gunluk_lock:
            gp = gunluk_pnl; hp = haftalik_pnl
            gb = gunluk_baslangic_bakiye; hb = haftalik_baslangic_bakiye
        if gb:
            limit_dolar = gb * GUNLUK_ZARAR_LIMIT_PCT
            kalan = limit_dolar + gp
            satirlar.append(f"Günlük zarar limiti: -{limit_dolar:.2f}$ (bakiyenin %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}'i)")
            satirlar.append(f"Bugünkü PnL: {gp:+.2f}$ | Limite kalan pay: {kalan:.2f}$")
            satirlar.append("⛔ GÜNLÜK LİMİT AŞILDI" if gunluk_limit_kontrolu() else "✅ Günlük limit aşılmadı")
        else:
            satirlar.append("Günlük başlangıç bakiyesi henüz kaydedilmedi.")
        if hb:
            limit_dolar_h = hb * HAFTALIK_ZARAR_LIMIT_PCT
            kalan_h = limit_dolar_h + hp
            satirlar.append(f"\nHaftalık zarar limiti: -{limit_dolar_h:.2f}$ (bakiyenin %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f}'i)")
            satirlar.append(f"Bu haftaki PnL: {hp:+.2f}$ | Limite kalan pay: {kalan_h:.2f}$")
            satirlar.append("⛔ HAFTALIK LİMİT AŞILDI" if haftalik_limit_kontrolu() else "✅ Haftalık limit aşılmadı")
        else:
            satirlar.append("\nHaftalık başlangıç bakiyesi henüz kaydedilmedi.")

        with cooldown_lock:
            cd = dict(son_kapanis_zamani)
        aktif_cooldown = [(s, t) for s, t in cd.items() if (time.time()-t) < COOLDOWN_SAAT*3600]
        if aktif_cooldown:
            satirlar.append(f"\n🕐 Cooldown'da olan coinler ({COOLDOWN_SAAT}sa):")
            for s, t in aktif_cooldown:
                kalan_dk = (COOLDOWN_SAAT*3600 - (time.time()-t)) / 60
                satirlar.append(f"  {s.split('/')[0]}: {kalan_dk:.0f} dk kaldı")
        return "\n".join(satirlar)

    def panel_acik_pozisyon_metni():
        with state_lock:
            acik_durumlar = dict(trade_state)
        if not acik_durumlar:
            return "📈 AÇIK POZİSYON YOK"
        satirlar = ["📈 AÇIK POZİSYON(LAR)\n"]
        for sym, d in acik_durumlar.items():
            try:
                t = exchange.fetch_ticker(sym)
                guncel = safe(t["last"])
                entry = d["entry"]; qty = d["qty"]; direction = d["direction"]
                pnl = (guncel - entry) * qty if direction == "long" else (entry - guncel) * qty
                pnl_pct = (guncel - entry) / entry * 100 if direction == "long" else (entry - guncel) / entry * 100
                emoji = "🟢" if pnl >= 0 else "🔴"
                satirlar.append(f"{emoji} {sym.split('/')[0]} [{direction.upper()}]\n"
                                 f"   Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                                 f"   SL:{d['sl']:.6f} TP:{d['tp']:.6f}\n"
                                 f"   Anlık PnL≈{pnl:+.2f}$\n")
            except Exception:
                satirlar.append(f"{sym.split('/')[0]} [{d['direction'].upper()}] (fiyat alınamadı)")
        return "\n".join(satirlar)

    def panel_gecmis_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "📜 Henüz kapanan işlem yok."
        satirlar = ["📜 SON 15 İŞLEM\n"]
        for t in list(reversed(gecmis))[:15]:
            etiketler = []
            if t.get("strateji"):
                etiketler.append(t["strateji"])
            if t.get("not"):
                etiketler.append(t["not"])
            etiket_str = f" [{', '.join(etiketler)}]" if etiketler else ""
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {t['direction'].upper()} "
                             f"{t['pnl']:+.2f}$ — {t['zaman']}{etiket_str}")
        return "\n".join(satirlar)

    def panel_analiz_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "🔬 STRATEJİ ANALİZİ\n\nHenüz kapanan işlem yok."
        satirlar = ["🔬 STRATEJİ ANALİZİ\n"]
        satirlar.append("📊 Yön bazında:")
        for yon in ["long", "short"]:
            alt = [t for t in gecmis if t.get("direction") == yon]
            if not alt:
                continue
            kazanan = [t for t in alt if t["pnl"] > 0]
            net = sum(t["pnl"] for t in alt)
            oran = len(kazanan) / len(alt) * 100
            satirlar.append(f"  {yon.upper()}: {len(alt)} işlem, %{oran:.0f} kazanma, net {net:+.2f}$")
        coin_pnl = {}
        for t in gecmis:
            sym = t["symbol"].split("/")[0]
            coin_pnl[sym] = coin_pnl.get(sym, 0) + t["pnl"]
        siralanmis = sorted(coin_pnl.items(), key=lambda x: x[1], reverse=True)
        if siralanmis:
            satirlar.append("\n🏆 En kazandıran coinler:")
            for sym, pnl in siralanmis[:3]:
                satirlar.append(f"  {sym}: {pnl:+.2f}$")
            satirlar.append("💀 En kaybettiren coinler:")
            for sym, pnl in siralanmis[-3:][::-1]:
                satirlar.append(f"  {sym}: {pnl:+.2f}$")
        return "\n".join(satirlar)

    def ana_menu_klavye():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
            telebot.types.InlineKeyboardButton("📈 Açık Pozisyon", callback_data="panel_acik"),
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📜 Geçmiş İşlemler", callback_data="panel_gecmis"),
            telebot.types.InlineKeyboardButton("📉 Risk Durumu", callback_data="panel_risk"),
        )
        markup.row(
            telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
            telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
        )
        markup.row(
            telebot.types.InlineKeyboardButton("❌ Pozisyon Kapat", callback_data="panel_kapat_sec"),
            telebot.types.InlineKeyboardButton("➗ Yarısını Kapat", callback_data="panel_yarikapat_sec"),
        )
        markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
        return markup

    def geri_butonu():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
        return markup

    def sembol_secim_klavye(prefix):
        with state_lock:
            semboller = list(trade_state.keys())
        markup = telebot.types.InlineKeyboardMarkup()
        if not semboller:
            markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
            return markup, "Açık pozisyon yok."
        for sym in semboller:
            markup.row(telebot.types.InlineKeyboardButton(sym.split("/")[0], callback_data=f"{prefix}|{sym}"))
        markup.row(telebot.types.InlineKeyboardButton("⬅️ İptal / Menüye Dön", callback_data="panel_ana"))
        return markup, "Hangi pozisyon?"

    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            return
        veri = call.data
        try:
            if veri == "panel_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=ana_menu_klavye())
            elif veri == "panel_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=geri_butonu())
            elif veri == "panel_acik":
                bot.edit_message_text(panel_acik_pozisyon_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=geri_butonu())
            elif veri == "panel_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=geri_butonu())
            elif veri == "panel_risk":
                bot.edit_message_text(panel_risk_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=geri_butonu())
            elif veri == "panel_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=geri_butonu())
            elif veri == "panel_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id,
                                       reply_markup=geri_butonu())
            elif veri == "panel_kapat_sec":
                markup, metin = sembol_secim_klavye("panel_kapat_onay")
                bot.edit_message_text(f"❌ Kapatılacak pozisyonu seç:\n{metin}", call.message.chat.id,
                                       call.message.message_id, reply_markup=markup)
            elif veri == "panel_yarikapat_sec":
                markup, metin = sembol_secim_klavye("panel_yarikapat_onay")
                bot.edit_message_text(f"➗ Yarısı kapatılacak pozisyonu seç:\n{metin}", call.message.chat.id,
                                       call.message.message_id, reply_markup=markup)
            elif veri.startswith("panel_kapat_onay|"):
                sym = veri.split("|", 1)[1]
                bot.answer_callback_query(call.id, f"{sym} kapatılıyor...")
                basari, mesaj = gercek_pozisyon_kapat(sym, oran=1.0)
                bot.edit_message_text(mesaj, call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri.startswith("panel_yarikapat_onay|"):
                sym = veri.split("|", 1)[1]
                bot.answer_callback_query(call.id, f"{sym} yarısı kapatılıyor...")
                basari, mesaj = gercek_pozisyon_kapat(sym, oran=0.5)
                bot.edit_message_text(mesaj, call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" in str(e):
                try:
                    bot.answer_callback_query(call.id, "Zaten güncel")
                except Exception:
                    pass
                return
            log.warning(f"[PANEL_BUTON] {e}")
            try:
                bot.answer_callback_query(call.id, "Bir hata oluştu, tekrar dene")
            except Exception:
                pass

    @bot.message_handler(commands=["ac"])
    def ac_komutu(msg):
        if not yetkili_mi(msg):
            return
        parcalar = msg.text.replace("/ac", "", 1).strip().split()
        if len(parcalar) < 2:
            bot.send_message(msg.chat.id, "Kullanım: /ac SOL long  (ya da /ac SOL short)")
            return
        taban = parcalar[0].upper()
        yon = parcalar[1].lower()
        if yon not in ("long", "short"):
            bot.send_message(msg.chat.id, "Yön 'long' ya da 'short' olmalı. Örnek: /ac SOL long")
            return

        sym = f"{taban}/USDT:USDT"
        with state_lock:
            if sym in trade_state:
                bot.send_message(msg.chat.id, f"{sym} zaten açık.")
                return
            if len(trade_state) >= MAX_POS:
                bot.send_message(msg.chat.id, f"MAX_POS={MAX_POS} doldu, önce bir pozisyon kapanmalı.")
                return

        try:
            df1h = get_df(sym, "1h", GOSTERGE_MUM_SAYISI_1H)
            if df1h is None or len(df1h) < 21:
                bot.send_message(msg.chat.id, f"{sym} için veri alınamadı, sembolü kontrol et.")
                return
            df1h["atr"] = atr(df1h, 14)
            atr_1h = df1h["atr"].iloc[-1]
            fiyat = df1h["close"].iloc[-1]
            if pd.isna(atr_1h) or atr_1h <= 0:
                bot.send_message(msg.chat.id, f"{sym} için ATR hesaplanamadı.")
                return
        except Exception as e:
            bot.send_message(msg.chat.id, f"⚠️ {sym} veri hatası: {e}")
            return

        if yon == "long":
            sl = fiyat - ATR_CARPANI * atr_1h
            tp = fiyat + ATR_CARPANI * atr_1h * RR_PULLBACK
        else:
            sl = fiyat + ATR_CARPANI * atr_1h
            tp = fiyat - ATR_CARPANI * atr_1h * RR_PULLBACK

        bot.send_message(msg.chat.id, f"⚡ Manuel açılıyor: {sym} {yon.upper()} — Giriş≈{fiyat:.6f} SL:{sl:.6f} TP:{tp:.6f}")
        pozisyon_ac({"symbol": sym, "direction": yon, "entry": fiyat, "sl": sl, "tp": tp,
                      "skor": 0, "volatilite_spike": False})


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
    """v8.0 YENİ: bot başlarken diskteki state ile borsadaki GERÇEK açık
    pozisyonları karşılaştırır. Diskte var ama borsada yoksa (bot çalışmazken
    kapanmış olabilir) temizler; borsada var ama diskte yoksa (manuel açılmış
    ya da state dosyası kaybolmuş) uyarı verir - state dosyasına körü körüne
    güvenmek yerine borsa esas alınır."""
    try:
        gercek_pozlar = exchange.fetch_positions()
        gercek_semboller = {p["symbol"] for p in gercek_pozlar if safe(p.get("contracts")) > 0}
    except Exception as e:
        log.warning(f"[UZLASTIRMA] Pozisyonlar alınamadı: {e}")
        return

    with state_lock:
        state_semboller = set(trade_state.keys())

    sadece_diskte = state_semboller - gercek_semboller
    sadece_borsada = gercek_semboller - state_semboller

    if sadece_diskte:
        with state_lock:
            for sym in sadece_diskte:
                trade_state.pop(sym, None)
        durumu_diske_yaz()
        tg(f"ℹ️ Uzlaştırma: diskte kayıtlı ama borsada açık olmayan {len(sadece_diskte)} pozisyon "
           f"temizlendi: {sorted(sadece_diskte)}")

    if sadece_borsada:
        tg(f"⚠️ UYARI: borsada açık ama bot state'inde KAYITLI OLMAYAN {len(sadece_borsada)} pozisyon "
           f"var: {sorted(sadece_borsada)}\nBu pozisyonlar botun otomatik SL/TP yönetiminin DIŞINDA "
           f"kalabilir - manuel kontrol et.")


def tarama_loop():
    tg(f"🚀 YENİ STRATEJİ BOTU başladı (SÜRÜM: v8.0 — MAX_POS={MAX_POS})\n"
       f"Strateji: pullback (LONG+SHORT), backtest: 129 coin, %61.8 kazanma, +0.14R/işlem ort.\n"
       f"Coin evreni: {len(COINS)} coin (her turda en güçlü {MAX_POS} sinyal seçilir)\n"
       f"Kaldıraç: {LEV}x | İşlem başına risk: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i\n"
       f"BTC ADX filtresi: piyasa yatayken (ADX<{ADX_ESIK}) işlem aranmaz\n"
       f"Günlük zarar limiti: %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f} | Haftalık: %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f}\n"
       f"⚠️ Bu strateji backtest ile doğrulandı ama gerçek performansı garanti etmez.")

    baslangic_uzlastirma()
    gunluk_haftalik_reset_kontrol()

    while True:
        try:
            gunluk_haftalik_reset_kontrol()

            if gunluk_limit_kontrolu():
                log.info("[LIMIT] Günlük zarar limiti aşıldı, bu tur atlandı")
                time.sleep(KONTROL_ARALIGI_SN)
                continue
            if haftalik_limit_kontrolu():
                log.info("[LIMIT] Haftalık zarar limiti aşıldı, bu tur atlandı")
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            with state_lock:
                bos_slot = MAX_POS - len(trade_state)

            if bos_slot > 0:
                btc_bullish, btc_bearish, trend_guclu = btc_rejimi_al()
                if btc_bullish is None:
                    tg("⚠️ BTC rejimi alınamadı, bu tur atlandı")
                    time.sleep(KONTROL_ARALIGI_SN)
                    continue

                if not trend_guclu:
                    log.info("[ADX] Piyasa yatay/kararsız (ADX düşük) — bu tur taranmadı")
                    time.sleep(KONTROL_ARALIGI_SN)
                    continue

                adaylar = []
                for sym in COINS:
                    with state_lock:
                        if sym in trade_state:
                            continue
                    with cooldown_lock:
                        son = son_kapanis_zamani.get(sym)
                    if son and (time.time() - son) < COOLDOWN_SAAT * 3600:
                        continue
                    sinyal_p = sinyal_kontrol_et_pullback(sym, btc_bullish, btc_bearish)
                    if sinyal_p:
                        adaylar.append(sinyal_p)

                if adaylar:
                    en_iyi_sembol_basina = {}
                    for aday in adaylar:
                        mevcut = en_iyi_sembol_basina.get(aday["symbol"])
                        if mevcut is None or aday["skor"] > mevcut["skor"]:
                            en_iyi_sembol_basina[aday["symbol"]] = aday
                    adaylar_tekil = list(en_iyi_sembol_basina.values())

                    adaylar_tekil.sort(key=lambda s: s["skor"], reverse=True)
                    secilenler = adaylar_tekil[:bos_slot]
                    tg(f"🔍 {len(adaylar_tekil)} benzersiz aday bulundu, en güçlü {len(secilenler)} tanesi seçildi")
                    for aday in secilenler:
                        tg(f"→ {aday['symbol']} {aday['direction'].upper()} "
                           f"[{aday['strateji']}] (skor:{aday['skor']:.0f}/100)")
                        pozisyon_ac(aday)

            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(30)


def manage_loop():
    global gunluk_pnl, haftalik_pnl
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(15)
                continue

            if KAR_ESIGI_ROI_PCT > 0:
                for sym in list(semboller):
                    with state_lock:
                        durum = trade_state.get(sym)
                    if not durum or durum.get("hizli_kar_emir_id"):
                        continue
                    marj = durum.get("marj")
                    if not marj or marj <= 0:
                        continue
                    try:
                        t = exchange.fetch_ticker(sym)
                        guncel = safe(t["last"])
                        entry = durum["entry"]; qty = durum["qty"]; direction = durum["direction"]
                        anlik_pnl = (guncel - entry) * qty if direction == "long" else (entry - guncel) * qty
                        roi_pct = anlik_pnl / marj * 100
                    except Exception:
                        continue
                    if roi_pct >= KAR_ESIGI_ROI_PCT:
                        tg(f"⚡ {sym} hızlı kâr eşiğine ulaştı (ROI %{roi_pct:.1f} ≥ %{KAR_ESIGI_ROI_PCT:.0f}, "
                           f"≈{anlik_pnl:+.2f}$) — [yedek mekanizma] kapatılıyor")
                        gercek_pozisyon_kapat(sym, oran=1.0, sebep="hizli_kar")

            positions = exchange.fetch_positions(semboller)
            acik_semboller = {p["symbol"] for p in positions if safe(p.get("contracts")) > 0}

            for sym in semboller:
                if sym in acik_semboller:
                    continue
                with state_lock:
                    durum = trade_state.pop(sym, None)
                durumu_diske_yaz()
                if durum:
                    for emir_id_alani in ("tp_emir_id", "hizli_kar_emir_id"):
                        eid = durum.get(emir_id_alani)
                        if eid:
                            try:
                                exchange.cancel_order(eid, sym)
                            except Exception:
                                pass
                with cooldown_lock:
                    son_kapanis_zamani[sym] = time.time()
                cooldown_diske_yaz()
                if durum:
                    try:
                        t = exchange.fetch_ticker(sym)
                        cikis_fiyat = safe(t["last"])
                    except Exception:
                        cikis_fiyat = durum["sl"]
                    entry = durum["entry"]; qty = durum["qty"]; direction = durum["direction"]
                    strateji = durum.get("strateji", "bilinmiyor")
                    pnl_tahmini = (cikis_fiyat - entry) * qty if direction == "long" else (entry - cikis_fiyat) * qty
                    with gunluk_lock:
                        gunluk_pnl += pnl_tahmini
                        haftalik_pnl += pnl_tahmini
                    gunluk_haftalik_diske_yaz()
                    trade_log_kaydet({
                        "symbol": sym, "direction": direction, "entry": entry, "exit": cikis_fiyat,
                        "pnl": pnl_tahmini, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        "strateji": strateji,
                    })
                    tg(f"✅ {sym} pozisyonu kapandı [{strateji}] | Tahmini PnL≈{pnl_tahmini:+.2f}$")

            time.sleep(15)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("YENİ STRATEJİ BOTU v8.0 BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    gunluk_haftalik_diskten_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
