#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
SCALP BOT v4.18 — 04 Ağustos 2026
5m/15m/1h çoklu zaman dilimi, HEM LONG HEM SHORT (v4.7), o an pump yapan coinleri
DİNAMİK olarak bulur (sabit coin listesi YOK — her taramada borsanın
TAMAMI taranır, RWA/tokenize hisse ve durgun majörler hariç).
════════════════════════════════════════════════════════
v4.18 DEĞİŞİKLİKLERİ (kullanıcı gözlemi: "panel yanlış", "31.20$ olup geri düştü"):
  1) PANEL KAYIP KAYIT DÜZELTMESİ: manage_loop artık her sembolü AYRI bir
     try/except içinde işliyor (_manage_tek_pozisyon fonksiyonu). Eskiden
     TÜM sembol döngüsü tek bir dış try/except içindeydi - bir sembolde
     hata olursa o turda SIRADAKİ TÜM semboller atlanıyordu, bu da bazı
     kapanışların (BANK, CYS örneği) trade_log'a hiç yazılmamasına yol
     açıyordu.
  2) GERÇEK PnL DOĞRULAMA: SL/güvenlik ağı kapanışlarında artık sadece
     ticker anlık fiyatına değil, exchange.fetch_my_trades() ile son
     gerçekleşen dolum fiyatına da bakılıyor (varsa öncelik ona veriliyor) -
     HFT örneğinde görülen yön/miktar sapmasını azaltmak için.
  3) ERKEN ÇIKIŞ (yeni, backtest EDİLMEDİ - kullanıcı talebiyle canlıya
     eklendi, izlenmeli): pozisyon açıldıktan sonraki ilk 90 saniyede HİÇ
     kâra geçmeden zarar SL mesafesinin %30'una ulaşırsa, tam SL'i beklemeden
     piyasa fiyatından kapatılır. Amaç: "daha başında yanlış çıkan" işlemlerde
     zararı büyütmeden kesmek. ⚠️ Riski: bazı işlemler bu erken kesmeyle
     kapanıp sonra dönüp kâra geçebilirdi (whipsaw) - panel_analiz'de
     "erken_cikis_ters_gidis" etiketiyle ayrı izlenebilir, sonuçlara göre
     eşik gevşetilip sıkılaştırılabilir.
════════════════════════════════════════════════════════
⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: HİÇBİR TP/SL AYARI KÂRI GARANTİ ETMEZ.
Aşağıdaki ayarlar geçmiş veride (60 likit coin, 15 gün, 5m mumlar,
gerçek Bitget verisi, komisyon dahil, bar-by-bar simülasyon) pozitif
edge gösterdi, ama örneklem küçük (131 işlem) ve gelecekte aynı
performansı vermesi garanti değildir.

DİNAMİK COİN TARAMA MANTIĞI:
Sabit bir coin listesi YOK. Her tarama turunda borsanın TAMAMI taranır,
RWA/durgun majörler elenir, en "canlı" ~40 aday seçilir, sadece bunların
5m/15m mumlarına bakılıp gerçek sinyal doğrulanır.

COOLDOWN: Bir coin kapandıktan sonra COOLDOWN_SAAT boyunca tekrar açılmaz.
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


SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

VOL_SPIKE_MULT = 5.0
RET_WINDOW_BARS = 3
RET_THRESHOLD = 0.03
ADX_ESIK_15M = 15
COOLDOWN_SAAT = float(os.getenv("COOLDOWN_SAAT", "4"))
MAX_HOLD_SAAT = 3.0

SUSTAINED_RET_WINDOW_BARS = 6
SUSTAINED_RET_THRESHOLD = 0.04
SUSTAINED_VOL_RATIO_THRESH = 1.2
SUSTAINED_ADX_ESIK = 15
SUSTAINED_ZIRVE_MESAFE_MIN = float(os.getenv("SUSTAINED_ZIRVE_MESAFE_MIN", "0.03"))
SUSTAINED_RSI_TAVAN = 75

DUSUS_DEVAM_DIP_MESAFE_MIN = 0.03
DUSUS_DEVAM_MUM_ESIK = 0.01
DUSUS_DEVAM_HACIM_ESIK = 1.5
DUSUS_DEVAM_RSI_TABAN = 25

ATR_CARPANI_SL = 2.0
MAX_SL_PCT = float(os.getenv("MAX_SL_PCT", "0.06"))
MIN_SL_PCT = float(os.getenv("MIN_SL_PCT", "0.02"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
HEDEF_NET_KAR_USDT = float(os.getenv("HEDEF_NET_KAR_USDT", "0.30"))
IZ_SURME_R_ORANI = float(os.getenv("IZ_SURME_R_ORANI", "0.15"))
TIERED_TP = [(0.30, 1.0), (0.30, 2.0), (0.40, 3.0)]

# v4.18 YENİ: erken çıkış (bkz. üst not) - backtest edilmedi, izlenmeli.
ERKEN_CIKIS_SURE_SN = float(os.getenv("ERKEN_CIKIS_SURE_SN", "90"))
ERKEN_CIKIS_SL_ORANI = float(os.getenv("ERKEN_CIKIS_SL_ORANI", "0.30"))

ADAY_HAVUZU_BUYUKLUGU = int(os.getenv("ADAY_HAVUZU_BUYUKLUGU", "40"))
GOSTERGE_MUM_5M = 60
GOSTERGE_MUM_15M = 40

LEV_HAM_DEGER = os.getenv("LEV")
LEV = int(LEV_HAM_DEGER) if LEV_HAM_DEGER else 10
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.10"))
MAX_POS = int(os.getenv("MAX_POS", "2"))
GUNLUK_ZARAR_LIMIT_PCT = 0.15
HAFTALIK_ZARAR_LIMIT_PCT = float(os.getenv("HAFTALIK_ZARAR_LIMIT_PCT", "0.25"))
KONTROL_ARALIGI_SN = 60

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/scalp_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/scalp_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/scalp_log.json")
GUNLUK_PATH = os.getenv("GUNLUK_PATH", "/data/scalp_gunluk.json")

trade_state = {}
state_lock = threading.Lock()
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()

gunluk_pnl = 0.0
gunluk_baslangic_bakiye = None
gunluk_gun_damgasi = None
haftalik_pnl = 0.0
haftalik_baslangic_bakiye = None
haftalik_hafta_damgasi = None
gunluk_lock = threading.Lock()

CONFIRM_BEKLEME_SN = 180
CONFIRM_MAX_RETRACE_PCT = 0.01
bekleyen_sinyaller = {}


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
# AJAN 1: PİYASA İZLEYİCİ
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


def piyasa_izleyici_sinyal_kontrol(sym, btc_bullish):
    df5 = get_df(sym, "5m", GOSTERGE_MUM_5M)
    if df5 is None or len(df5) < 25:
        return None

    df5["vol_ma20"] = df5["volume"].rolling(20).mean()
    df5["vol_ratio"] = df5["volume"] / df5["vol_ma20"].replace(0, np.nan)
    df5["ret_win"] = df5["close"].pct_change(RET_WINDOW_BARS)
    df5["atr"] = atr(df5, 14)

    row = df5.iloc[-1]
    if pd.isna(row["vol_ratio"]) or pd.isna(row["ret_win"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
        return None

    is_pump = row["vol_ratio"] >= VOL_SPIKE_MULT and row["ret_win"] >= RET_THRESHOLD
    if not is_pump:
        return None

    df15 = get_df(sym, "15m", GOSTERGE_MUM_15M)
    if df15 is None or len(df15) < 25:
        return None
    df15["ma20"] = df15["close"].rolling(20).mean()
    df15["adx"] = adx(df15, 14)
    row15 = df15.iloc[-1]
    if pd.isna(row15["ma20"]) or pd.isna(row15["adx"]):
        return None
    if not (row15["close"] > row15["ma20"] and row15["adx"] >= ADX_ESIK_15M):
        return None

    if not btc_bullish:
        return None

    fiyat = row["close"]
    atr_val = row["atr"]
    skor = row["ret_win"] * row["vol_ratio"]
    return {"symbol": sym, "entry": fiyat, "atr": atr_val, "skor": skor, "tur": "spike"}


def piyasa_izleyici_sustained_sinyal_kontrol(sym, btc_bullish):
    df15 = get_df(sym, "15m", GOSTERGE_MUM_15M)
    if df15 is None or len(df15) < 30:
        return None

    df15["ma20"] = df15["close"].rolling(20).mean()
    df15["adx"] = adx(df15, 14)
    df15["atr"] = atr(df15, 14)
    df15["vol_ma20"] = df15["volume"].rolling(20).mean()
    df15["vol_ma6"] = df15["volume"].rolling(6).mean()
    df15["vol_ratio_sustained"] = df15["vol_ma6"] / df15["vol_ma20"].replace(0, np.nan)
    df15["ret_6bar"] = df15["close"].pct_change(SUSTAINED_RET_WINDOW_BARS)
    df15["zirve_2sa"] = df15["high"].rolling(8).max()
    df15["rsi"] = rsi(df15, 14)

    row = df15.iloc[-1]
    if pd.isna(row["ma20"]) or pd.isna(row["adx"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
        return None
    if pd.isna(row["ret_6bar"]) or pd.isna(row["vol_ratio_sustained"]):
        return None

    trend_ok = row["close"] > row["ma20"] and row["adx"] >= SUSTAINED_ADX_ESIK
    momentum_ok = row["ret_6bar"] >= SUSTAINED_RET_THRESHOLD
    volume_ok = row["vol_ratio_sustained"] >= SUSTAINED_VOL_RATIO_THRESH
    if not (trend_ok and momentum_ok and volume_ok):
        return None

    if pd.isna(row["zirve_2sa"]) or row["zirve_2sa"] <= 0:
        return None
    zirve_mesafe = (row["zirve_2sa"] - row["close"]) / row["zirve_2sa"]
    if zirve_mesafe < SUSTAINED_ZIRVE_MESAFE_MIN:
        return None

    if not btc_bullish:
        return None

    if pd.isna(row["rsi"]) or row["rsi"] >= SUSTAINED_RSI_TAVAN:
        return None

    return {"symbol": sym, "entry": row["close"], "atr": row["atr"],
            "skor": row["ret_6bar"], "tur": "sustained"}


def piyasa_izleyici_dusus_devam_kontrol(sym):
    df15 = get_df(sym, "15m", GOSTERGE_MUM_15M)
    if df15 is None or len(df15) < 30:
        return None

    df15["ma20"] = df15["close"].rolling(20).mean()
    df15["adx"] = adx(df15, 14)
    df15["atr"] = atr(df15, 14)
    df15["vol_ma20"] = df15["volume"].rolling(20).mean()
    df15["vol_ma6"] = df15["volume"].rolling(6).mean()
    df15["vol_ratio_sustained"] = df15["vol_ma6"] / df15["vol_ma20"].replace(0, np.nan)
    df15["ret_6bar"] = df15["close"].pct_change(SUSTAINED_RET_WINDOW_BARS)
    df15["dip_2sa"] = df15["low"].rolling(8).min()
    df15["rsi"] = rsi(df15, 14)

    row = df15.iloc[-1]
    if pd.isna(row["ma20"]) or pd.isna(row["adx"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
        return None
    if pd.isna(row["ret_6bar"]) or pd.isna(row["vol_ratio_sustained"]):
        return None

    trend_ok = row["close"] < row["ma20"] and row["adx"] >= SUSTAINED_ADX_ESIK
    momentum_ok = row["ret_6bar"] <= -SUSTAINED_RET_THRESHOLD
    volume_ok = row["vol_ratio_sustained"] >= SUSTAINED_VOL_RATIO_THRESH
    if not (trend_ok and momentum_ok and volume_ok):
        return None

    dip_2sa = row["dip_2sa"]
    if pd.isna(dip_2sa) or dip_2sa <= 0:
        return None
    dip_mesafe = (row["close"] - dip_2sa) / dip_2sa
    if dip_mesafe < DUSUS_DEVAM_DIP_MESAFE_MIN:
        return None

    if pd.isna(row["open"]) or row["open"] <= 0:
        return None
    son_mum_ret = (row["close"] - row["open"]) / row["open"]
    son_mum_hacim = row["volume"] / row["vol_ma20"] if row["vol_ma20"] else 0
    capitulation_ok = son_mum_ret <= -DUSUS_DEVAM_MUM_ESIK and son_mum_hacim >= DUSUS_DEVAM_HACIM_ESIK
    if not capitulation_ok:
        return None

    if pd.isna(row["rsi"]) or row["rsi"] <= DUSUS_DEVAM_RSI_TABAN:
        return None

    return {"symbol": sym, "entry": row["close"], "atr": row["atr"],
            "skor": abs(row["ret_6bar"]) * row["vol_ratio_sustained"], "tur": "dusus_devam"}


def btc_1h_bullish():
    df = get_df("BTC/USDT:USDT", "1h", 40)
    if df is None or len(df) < 25:
        return None
    ma20 = df["close"].rolling(20).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma20):
        return None
    return fiyat > ma20


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
    with gunluk_lock:
        if gunluk_baslangic_bakiye is None:
            return False
        return gunluk_pnl <= -(gunluk_baslangic_bakiye * GUNLUK_ZARAR_LIMIT_PCT)


def haftalik_limit_kontrolu():
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
# GERÇEK ÇIKIŞ FİYATI YARDIMCISI (v4.18 YENİ)
# ════════════════════════════════════════════
def gercek_cikis_fiyati_bul(sym, kapama_emri_id=None, fallback=None):
    """v4.18 YENİ: HFT örneğinde görülen yön/miktar sapmasını azaltmak için
    üç kademeli doğrulama: (1) kapatma emrinin kendi dolum fiyatı,
    (2) exchange.fetch_my_trades ile SON birkaç dakikadaki gerçek fill,
    (3) son çare ticker anlık fiyatı. İlk bulunan güvenilir değer kullanılır."""
    if kapama_emri_id:
        try:
            emir_detay = exchange.fetch_order(kapama_emri_id, sym)
            gercek_dolum = safe(emir_detay.get("average")) or safe(emir_detay.get("price"))
            if gercek_dolum and gercek_dolum > 0:
                return gercek_dolum
        except Exception as e:
            log.warning(f"[CIKIS_FIYATI] {sym}: emir detayı alınamadı: {e}")

    try:
        yakin_trades = exchange.fetch_my_trades(sym, limit=5)
        if yakin_trades:
            son_trade = yakin_trades[-1]
            ts = son_trade.get("timestamp", 0) / 1000
            if ts and (time.time() - ts) < 120:  # son 2 dakika içindeyse güvenilir kabul et
                fiyat = safe(son_trade.get("price"))
                if fiyat > 0:
                    return fiyat
    except Exception as e:
        log.warning(f"[CIKIS_FIYATI] {sym}: fetch_my_trades başarısız: {e}")

    try:
        t = exchange.fetch_ticker(sym)
        fiyat = safe(t["last"])
        if fiyat > 0:
            return fiyat
    except Exception:
        pass

    return fallback


# ════════════════════════════════════════════
# AJAN 2: İŞLEM AÇICI
# ════════════════════════════════════════════
def acilis_basarisiz_cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def sinyal_yonu(tur):
    return "short" if tur == "dusus_devam" else "long"


def islem_acici_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    entry = sinyal["entry"]
    atr_val = sinyal["atr"]
    tur = sinyal.get("tur", "bilinmiyor")
    yon = sinyal_yonu(tur)

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

    qty = None
    for deneme in range(5):
        gereken_marj = notional / LEV_KULLANILAN
        MAX_MARJ_PCT = 0.25 if MAX_POS <= 1 else 0.15
        notional_bu_deneme = notional
        if gereken_marj > bakiye * MAX_MARJ_PCT:
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
                    "kurulum_tamamlanmadi": True, "en_iyi_kar": None,
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
               f"LÜTFEN HEMEN BORSAYA GİRİP MANUEL KONTROL ET.")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    tp_emirleri = []

    with state_lock:
        if sym in trade_state:
            trade_state[sym].update({
                "sl_orijinal": sl, "sl_guncel": sl, "sl_emir_id": sl_emir_id,
                "r_risk": r_risk, "tp_emirleri": tp_emirleri,
                "kurulum_tamamlanmadi": False, "en_iyi_kar": None,
            })
        else:
            trade_state[sym] = {
                "entry": entry, "sl_orijinal": sl, "sl_guncel": sl, "sl_emir_id": sl_emir_id,
                "qty_orijinal": qty, "r_risk": r_risk, "tp_emirleri": tp_emirleri,
                "acilis_zamani": time.time(), "breakeven_cekildi": False, "tur": tur,
                "kurulum_tamamlanmadi": False, "en_iyi_kar": None,
            }
    durumu_diske_yaz()

    tur_etiket = "ani patlama" if tur == "spike" else ("sürdürülebilir tırmanış" if tur == "sustained" else ("düşüş devamı" if tur == "dusus_devam" else tur))
    _risk_dolar_giris = r_risk * qty
    _iz_esik_giris = _risk_dolar_giris * IZ_SURME_R_ORANI if _risk_dolar_giris > 0 else HEDEF_NET_KAR_USDT
    tp_ozet = (f"TP: İZ SÜREN — ${_iz_esik_giris:.2f} kârda aktifleşir (0.15R), "
               f"en iyi kârdan ${_iz_esik_giris:.2f} geri çekilirse kapanır")
    yon_etiket = "LONG" if yon == "long" else "SHORT"
    yon_emoji = "📈" if yon == "long" else "📉"
    tg(f"{yon_emoji} SCALP POZİSYON: {sym} {yon_etiket} [{tur_etiket}]\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (2×ATR)\n"
       f"{tp_ozet}\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Risk≈${risk_dolar:.2f} (bakiyenin ~%{RISK_PCT_BAKIYE*100:.0f}'i)")


def pozisyonu_tamamen_kapat(sym, sebep="manuel"):
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        with state_lock:
            durum = trade_state.get(sym)
        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
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
        # v4.18: gercek_cikis_fiyati_bul() kademeli doğrulama yapıyor
        # (emir dolum -> fetch_my_trades -> ticker)
        cikis_fiyat = gercek_cikis_fiyati_bul(sym, kapama_emri.get("id"), fallback=entry_fiyat)
        pnl = (cikis_fiyat - entry_fiyat) * qty if pozisyon_yonu == "long" else (entry_fiyat - cikis_fiyat) * qty
        trade_log_kaydet({"symbol": sym, "entry": entry_fiyat, "exit": cikis_fiyat, "pnl": pnl,
                           "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "not": sebep,
                           "tur": (durum or {}).get("tur", "bilinmiyor")})
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
            satirlar.append(f"\n📈 Açık pozisyon: {len(trade_state)}/{MAX_POS}")
        return "\n".join(satirlar)

    def panel_ayarlar_metni():
        return ("⚙️ SCALP BOT AYARLARI\n\n"
                f"Sürüm: v4.18 (panel kayıp-kayıt düzeltmesi, gerçek PnL doğrulama, erken çıkış eklendi)\n"
                f"Kaldıraç: {LEV}x | MAX_POS: {MAX_POS}\n"
                f"İşlem başına risk: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i\n"
                f"SL: {ATR_CARPANI_SL}x ATR(5m,14)\n"
                f"Erken çıkış: ilk {ERKEN_CIKIS_SURE_SN:.0f}sn'de hiç kâra geçmeden SL'in %{ERKEN_CIKIS_SL_ORANI*100:.0f}'ına ulaşırsa kapat\n"
                f"İlk TP'de SL başabaşa çekilir\n"
                f"Coin cooldown: {COOLDOWN_SAAT} saat\n"
                f"Aday havuzu: her turda en canlı {ADAY_HAVUZU_BUYUKLUGU} coin taranır\n"
                f"Günlük zarar limiti: %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f} | Haftalık: %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f}\n"
                f"Tarama aralığı: {KONTROL_ARALIGI_SN}sn")

    def panel_gecmis_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "📜 Henüz kapanan işlem yok."
        satirlar = ["📜 SON 15 İŞLEM\n"]
        for t in list(reversed(gecmis))[:15]:
            tur = t.get("tur", "?")
            tur_kisa = "patlama" if tur == "spike" else ("sürdürülebilir" if tur == "sustained" else tur)
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
        for tur in ["spike", "sustained", "dusus_devam"]:
            alt = [t for t in gecmis if t.get("tur") == tur]
            if not alt:
                continue
            kazanan = [t for t in alt if t["pnl"] > 0]
            net = sum(t["pnl"] for t in alt)
            tur_ad = "Ani patlama" if tur == "spike" else ("Sürdürülebilir tırmanış" if tur == "sustained" else "Düşüş devamı")
            satirlar.append(f"  {tur_ad}: {len(alt)} işlem, %{len(kazanan)/len(alt)*100:.0f} kazanma, net {net:+.2f}$")
        satirlar.append("\n🚪 Kapanış sebebi bazında:")
        for sebep in ["tum_tp_tamamlandi", "SL_basabasta_TP1_sonrasi", "SL_ilk_TPden_once",
                      "erken_cikis_ters_gidis", "max_hold_timeout", "iz_suren_tp",
                      "yazilim_sl_guvenlik_agi", "manuel"]:
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
            satirlar.append("\n🏆 En kazandıran coinler:")
            for sym, pnl in siralanmis[:3]:
                satirlar.append(f"  {sym}: {pnl:+.2f}$")
            satirlar.append("💀 En kaybettiren coinler:")
            for sym, pnl in siralanmis[-3:][::-1]:
                satirlar.append(f"  {sym}: {pnl:+.2f}$")
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
            satirlar.append("⛔ GÜNLÜK LİMİT AŞILDI - tarama duruyor" if gunluk_limit_kontrolu() else "✅ Günlük limit aşılmadı")
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
        markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
        return markup

    def geri_butonu():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
        return markup

    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.message_handler(commands=["sifirla"])
    def sifirla_komutu(msg):
        if not yetkili_mi(msg):
            return
        global trade_log, gunluk_pnl, haftalik_pnl
        with state_lock:
            trade_log = []
        atomik_yaz(TRADE_LOG_PATH, [])
        with gunluk_lock:
            gunluk_pnl = 0.0
            haftalik_pnl = 0.0
        gunluk_haftalik_diske_yaz()
        bot.send_message(msg.chat.id, "🔄 Panel istatistikleri sıfırlandı (trade_log, günlük/haftalık PnL). "
                                        "Açık pozisyonlar ve risk mekanizmaları etkilenmedi.")

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
    global gunluk_pnl, haftalik_pnl
    try:
        gercek_pozlar = exchange.fetch_positions()
        gercek_semboller = {p["symbol"] for p in gercek_pozlar if safe(p.get("contracts")) > 0}
    except Exception as e:
        log.warning(f"[UZLASTIRMA] {e}")
        return
    with state_lock:
        state_semboller = set(trade_state.keys())
    sadece_diskte = state_semboller - gercek_semboller
    if sadece_diskte:
        for sym in sadece_diskte:
            with state_lock:
                durum = trade_state.pop(sym, None)
            if durum:
                guncel_fiyat = gercek_cikis_fiyati_bul(sym, fallback=durum.get("sl_guncel", durum["entry"]))
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
                                   "not": "uzlastirma_tahmini", "tur": durum.get("tur", "bilinmiyor")})
                tg(f"ℹ️ Uzlaştırma: {sym} bot çalışmazken kapanmış - tahmini PnL≈{pnl_tahmini:+.2f}$ "
                   f"kaydedildi. KESİN TUTAR İÇİN BORSA POZİSYON GEÇMİŞİNİ KONTROL ET.")
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
        durumu_diske_yaz()
    sadece_borsada = gercek_semboller - state_semboller
    if sadece_borsada:
        tg(f"⚠️ UYARI: borsada açık ama state'te olmayan pozisyonlar var: {sorted(sadece_borsada)}")


def tarama_loop():
    tg(f"🚀 SCALP BOT v4.18 başladı (MAX_POS={MAX_POS})\n"
       f"Yeni: panel kayıp-kayıt düzeltmesi, gerçek PnL doğrulama, erken çıkış "
       f"(ilk {ERKEN_CIKIS_SURE_SN:.0f}sn'de hiç kâra geçmeden SL'in %{ERKEN_CIKIS_SL_ORANI*100:.0f}'ına ulaşırsa kapat)\n"
       f"Coin cooldown: {COOLDOWN_SAAT} saat\n"
       f"⚠️ Erken çıkış kuralı backtest edilmedi - canlıda izlenmeli.")

    baslangic_uzlastirma()
    gunluk_haftalik_reset_kontrol()

    while True:
        try:
            gunluk_haftalik_reset_kontrol()

            if gunluk_limit_kontrolu() or haftalik_limit_kontrolu():
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            with state_lock:
                bos_slot = MAX_POS - len(trade_state)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            btc_bullish = True

            adaylar_havuzu = piyasa_izleyici_aday_havuzu()
            acilan_sayisi = 0

            for sym in list(bekleyen_sinyaller.keys()):
                if acilan_sayisi >= bos_slot:
                    break
                p = bekleyen_sinyaller[sym]
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel_fiyat = safe(t["last"])
                except Exception:
                    continue
                if guncel_fiyat <= 0:
                    continue
                dusme = (p["sinyal_fiyat"] - guncel_fiyat) / p["sinyal_fiyat"]
                if dusme > CONFIRM_MAX_RETRACE_PCT:
                    del bekleyen_sinyaller[sym]
                    continue
                if (time.time() - p["zaman"]) >= CONFIRM_BEKLEME_SN:
                    del bekleyen_sinyaller[sym]
                    with state_lock:
                        if sym in trade_state:
                            continue
                    if cooldown_da_mi(sym):
                        continue
                    tg(f"✅ AJAN 1: {sym} teyit edildi (fiyat tuttu) — AJAN 2'ye 'şimdi aç' komutu veriliyor")
                    try:
                        islem_acici_pozisyon_ac({"symbol": sym, "entry": guncel_fiyat, "atr": p["atr"],
                                                  "skor": p["skor"], "tur": p["tur"]})
                    except Exception as e:
                        log.error(f"[ISLEM_ACICI_BEKLENMEYEN_HATA] {sym}: {e}")
                        tg(f"🚨 {sym} açılışında beklenmeyen hata oluştu, cooldown'a alındı: {e}")
                        acilis_basarisiz_cooldown_uygula(sym)
                    acilan_sayisi += 1

            for sym in adaylar_havuzu:
                if acilan_sayisi >= bos_slot:
                    break
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym) or sym in bekleyen_sinyaller:
                    continue

                sinyal = piyasa_izleyici_sinyal_kontrol(sym, btc_bullish)
                if sinyal:
                    bekleyen_sinyaller[sym] = {"sinyal_fiyat": sinyal["entry"], "atr": sinyal["atr"],
                                                "skor": sinyal["skor"], "tur": sinyal["tur"], "zaman": time.time()}
                    tg(f"⏳ AJAN 1: {sym} ani patlama sinyali bulundu, {CONFIRM_BEKLEME_SN//60} dakika "
                       f"'tutuyor mu' diye izleniyor (fiyat düşerse iptal, tutarsa LONG açılır)")
                    continue

                sinyal = piyasa_izleyici_sustained_sinyal_kontrol(sym, btc_bullish)
                if sinyal:
                    tg(f"🔍 AJAN 1: {sym} güçlü LONG sinyali [sürdürülebilir tırmanış] bulundu — AJAN 2'ye 'hemen aç' komutu veriliyor")
                    try:
                        islem_acici_pozisyon_ac(sinyal)
                    except Exception as e:
                        log.error(f"[ISLEM_ACICI_BEKLENMEYEN_HATA] {sym}: {e}")
                        tg(f"🚨 {sym} açılışında beklenmeyen hata oluştu, cooldown'a alındı: {e}")
                        acilis_basarisiz_cooldown_uygula(sym)
                    acilan_sayisi += 1
                    continue

                sinyal2 = piyasa_izleyici_dusus_devam_kontrol(sym)
                if not sinyal2:
                    continue

                tg(f"🔍 AJAN 1: {sym} güçlü SHORT sinyali [düşüş devamı] bulundu — AJAN 2'ye 'hemen aç' komutu veriliyor")
                try:
                    islem_acici_pozisyon_ac(sinyal2)
                except Exception as e:
                    log.error(f"[ISLEM_ACICI_BEKLENMEYEN_HATA] {sym}: {e}")
                    tg(f"🚨 {sym} açılışında beklenmeyen hata oluştu, cooldown'a alındı: {e}")
                    acilis_basarisiz_cooldown_uygula(sym)
                acilan_sayisi += 1

            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


# ════════════════════════════════════════════
# AJAN 3: POZİSYON YÖNETİCİSİ (v4.18: sembol başına try/except ile ayrıldı)
# ════════════════════════════════════════════
def _manage_tek_pozisyon(sym):
    """v4.18 YENİ: eskiden manage_loop içindeki TÜM sembol döngüsü tek bir
    dış try/except'in içindeydi - bir sembolde beklenmedik hata olursa o
    turda sıradaki TÜM semboller atlanıyordu (BANK/CYS'in panelden kaybolma
    sebebi buydu). Artık her sembol kendi try/except'i içinde, tarama_loop
    çağıran fonksiyonda sarılıyor - bir coin patlarsa diğerleri etkilenmez."""
    global gunluk_pnl, haftalik_pnl

    with state_lock:
        durum = trade_state.get(sym)
    if not durum:
        return

    if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
        tg(f"⏱️ {sym} — max tutma süresi ({MAX_HOLD_SAAT}sa) aşıldı, piyasa fiyatından kapatılıyor")
        pozisyonu_tamamen_kapat(sym, sebep="max_hold_timeout")
        return

    if durum.get("kurulum_tamamlanmadi"):
        return

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
            return
    except Exception as e:
        log.warning(f"[SL_GUVENLIK_AGI] {sym}: fiyat kontrol edilemedi: {e}")
        guncel_fiyat = None

    # v4.18 YENİ: ERKEN ÇIKIŞ - ilk ERKEN_CIKIS_SURE_SN saniyede hiç kâra
    # geçmeden zarar SL mesafesinin ERKEN_CIKIS_SL_ORANI'na ulaşırsa kapat.
    # ⚠️ Backtest edilmedi - kullanıcı talebiyle eklendi, izlenmeli
    # (panel_analiz'de "erken_cikis_ters_gidis" etiketiyle takip edilebilir).
    if guncel_fiyat and guncel_fiyat > 0 and not durum.get("breakeven_cekildi"):
        gecen_sure = time.time() - durum["acilis_zamani"]
        if gecen_sure <= ERKEN_CIKIS_SURE_SN:
            erken_yon = sinyal_yonu(durum.get("tur"))
            entry_e = durum["entry"]
            r_risk_e = durum.get("r_risk") or 0
            en_iyi_simdi = durum.get("en_iyi_kar")
            if r_risk_e > 0 and not en_iyi_simdi:
                zarar_mesafe = (entry_e - guncel_fiyat) if erken_yon == "long" else (guncel_fiyat - entry_e)
                if zarar_mesafe >= r_risk_e * ERKEN_CIKIS_SL_ORANI:
                    tg(f"✂️ ERKEN ÇIKIŞ: {sym} açılışın ilk {ERKEN_CIKIS_SURE_SN:.0f}sn'sinde hiç kâra "
                       f"geçmeden SL mesafesinin %{ERKEN_CIKIS_SL_ORANI*100:.0f}'ına ulaştı — "
                       f"zarar büyümeden kapatılıyor.")
                    pozisyonu_tamamen_kapat(sym, sebep="erken_cikis_ters_gidis")
                    return

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
            if anlik_kar >= iz_esik:
                if not durum.get("breakeven_cekildi"):
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
                           f"Fiyat lehte gittikçe takip edecek, en iyi kârdan ${iz_esik:.2f} "
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
                elif en_iyi_kar is not None and anlik_kar <= en_iyi_kar - iz_esik:
                    tg(f"🎯 İZ SÜREN TP: {sym} en iyi kâr ${en_iyi_kar:.2f} idi, "
                       f"${iz_esik:.2f} geri çekildi (${anlik_kar:.2f}) — kapatılıyor.")
                    pozisyonu_tamamen_kapat(sym, sebep="iz_suren_tp")
                    return
        except Exception as e:
            log.warning(f"[IZ_SURME] {sym}: {e}")

    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
    except Exception as e:
        log.warning(f"[MANAGE] {sym} pozisyon sorgu hatası: {e}")
        return

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
            # v4.18: gercek_cikis_fiyati_bul() ile SL emri + fetch_my_trades +
            # ticker kademeli doğrulaması
            cikis_fiyat = gercek_cikis_fiyati_bul(sym, durum2.get("sl_emir_id"), fallback=durum2["sl_guncel"])
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
                               "not": sebep_etiket, "tur": durum2.get("tur", "bilinmiyor")})
            tg(f"✅ {sym} pozisyonu tamamen kapandı [{sebep_etiket}] (PnL≈{pnl_tahmini:+.2f}$ — "
               f"gerçek fill verisiyle doğrulanmaya çalışıldı, kesin tutar borsa Pozisyon "
               f"Geçmişi'nden teyit edilebilir)")
        return

    guncel_qty = safe(gercek_pos.get("contracts"))
    with state_lock:
        durum = trade_state.get(sym)
    if not durum:
        return

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


def manage_loop():
    """v4.18: her sembol artık _manage_tek_pozisyon() içinde AYRI try/except
    ile işleniyor - bir coin'de beklenmedik hata olursa sadece o coin atlanır,
    diğerleri (BANK/CYS örneğinde olduğu gibi) etkilenmez."""
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(10)
                continue

            for sym in semboller:
                try:
                    _manage_tek_pozisyon(sym)
                except Exception as e:
                    log.error(f"[MANAGE_SEMBOL] {sym}: {e}")
                    continue

            time.sleep(10)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(10)


if __name__ == "__main__":
    print("SCALP BOT v4.18 BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    gunluk_haftalik_diskten_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
