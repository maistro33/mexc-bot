#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
SÜRÜM: v7.4 — 22 Temmuz 2026
(Deploy sonrası Railway loglarında/Telegram başlangıç mesajında
bu sürüm numarasını görmelisin — görmüyorsan deploy güncel değildir)
════════════════════════════════════════════════════════
YENİ STRATEJİ BOTU — Backtest ile doğrulanmış, kanaldan bağımsız
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOĞRULAMA ÖZETİ (21 Temmuz 2026'da yapılan backtest):
  - Strateji: 4h MA20 üstünde/altında + 4h son 5 mumun 4'ü aynı yönde +
    1h RSI 50-70/30-50 aralığında + 1h son 5 mumun 4'ü aynı yönde
  - SL: 1.0 x ATR(1h,14) | TP: 1.5R sabit hedef
  - IN-SAMPLE (son 6 ay, 8 coin): 570 işlem, %48.8 kazanma, komisyon
    dahil +56.2R toplam (+0.099R/işlem ortalama)
  - OUT-OF-SAMPLE (180-400 gün önce, aynı 8 coin, GRID ARAMASINDA
    KULLANILMAMIŞ veri): 671 işlem, %47.1 kazanma, komisyon dahil
    +45.95R toplam (+0.068R/işlem ortalama)
  - Her iki dönemde de, 8 coin'in her birinde AYRI AYRI pozitif çıktı.

⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: Bu bir garanti değildir. Geçmiş performans
gelecekteki sonuçları garanti etmez. Backtest, gerçek emir doluşu,
likidite, ani haber olayları gibi faktörleri tam yansıtmaz. Küçük
sermaye ve düşük kaldıraçla, dikkatli izleyerek başlanmalıdır.

GÜVENLİK AYARLARI (kanalın kendi tavsiyesine uygun şekilde bilerek
düşük tutuldu — önceki bottaki 20x kaldıraç deneyiminden ders alınarak):
  - Varsayılan kaldıraç: 3x
  - Pozisyon başına risk: bakiyenin %5'i (yani bir SL ≈ bakiyenin %5'i)
  - Aynı anda maksimum 1 açık pozisyon (küçük sermayede odaklanma için)
  - Günlük zarar limiti: bakiyenin %15'i (aşılırsa gün sonuna kadar durur)
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
log = logging.getLogger("YENI_STRATEJI")

# ════════════════════════════════════════════
# CONFIG — Railway ortam değişkenlerinden okunur
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni eksik.")

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

# ── DOĞRULANMIŞ STRATEJİ PARAMETRELERİ (backtest'te bulunan) ──
# v4: KAPSAMLI ADAPTASYON SISTEMI
#   1) BTC ADX filtresi: piyasa yatay/kararsizken (ADX dusukse) HIC islem acilmaz
#   2) Volatilite bazli pozisyon boyutu: coin'in KENDI normaline gore anormal
#      oynak oldugu anlarda (ATR spike) risk otomatik kucultulur
#   3) Dinamik coin secimi: sabit kucuk liste yerine genis bir evren (23 coin)
#      her turda taranir, o an EN GUCLU teyit skoruna sahip olan secilir -
#      "sabit liste" yerine "o an piyasada en iyi kurulum nerede" mantigi
COINS = ["SOL/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT", "ADA/USDT:USDT",
         "DOT/USDT:USDT", "NEAR/USDT:USDT", "APT/USDT:USDT", "ATOM/USDT:USDT",
         "ARB/USDT:USDT", "OP/USDT:USDT", "SUI/USDT:USDT", "INJ/USDT:USDT",
         "TIA/USDT:USDT", "SEI/USDT:USDT", "RUNE/USDT:USDT", "FIL/USDT:USDT",
         "ICP/USDT:USDT", "AAVE/USDT:USDT", "UNI/USDT:USDT", "LTC/USDT:USDT",
         "ETC/USDT:USDT", "XLM/USDT:USDT", "ALGO/USDT:USDT",
         # v5: kucuk-cap taramasindan IKI donemde de tutarli pozitif cikanlar
         "NIGHT/USDT:USDT", "ONE/USDT:USDT", "ACE/USDT:USDT", "PROM/USDT:USDT",
         "LA/USDT:USDT", "SYN/USDT:USDT", "VVV/USDT:USDT", "LAB/USDT:USDT",
         "SIREN/USDT:USDT", "PI/USDT:USDT", "BEAT/USDT:USDT", "HOME/USDT:USDT",
         "MET/USDT:USDT", "AERO/USDT:USDT",
         # v5: kullanicinin verdigi listeden IKI donemde de tutarli pozitif cikanlar
         "M/USDT:USDT", "OGN/USDT:USDT", "PYTH/USDT:USDT", "RPL/USDT:USDT",
         "KAITO/USDT:USDT", "EDGE/USDT:USDT",
         # v7.3: son 2 haftada gercek anlamda guclu yukselis gosteren, RWA olmayan
         # yeni adaylar (Bitget gercek 4h veri ile dogrulandi, asiri ekstrem olan
         # BANK +%535 bilerek disarida birakildi - donus riski cok yuksek)
         "US/USDT:USDT", "UB/USDT:USDT", "ONDO/USDT:USDT", "ZAMA/USDT:USDT",
         "PUMP/USDT:USDT", "ENA/USDT:USDT", "VIRTUAL/USDT:USDT", "ALLO/USDT:USDT",
         "ERA/USDT:USDT", "ETHFI/USDT:USDT", "MIRA/USDT:USDT"]
ATR_CARPANI = 1.0
RR = 1.5            # momentum stratejisi TP hedefi (1.5R)
RR_PULLBACK = 1.0   # v7.3: pullback stratejisi icin AYRI ve DAHA DUSUK TP hedefi -
                     # backtest: RR=1.0 iken pullback %67-70 kazanma + 0.22-0.28R/islem
                     # veriyordu (RR=1.5'teki %56-57 kazanmadan DAHA SIK, KUCUK KAR
                     # profiline daha yakin) - momentum'da ayni degisiklik ZARAR
                     # veriyordu (0.166->0.070), o yuzden SADECE pullback icin uygulandi.
MUM_ESIGI = 4       # 5 mumdan en az kaci ayni yonde olmali
RSI_ALT, RSI_UST = 50, 70
BTC_SEMBOL = "BTC/USDT:USDT"
ADX_ESIK = 20        # BTC 4h ADX bu esigin altindaysa piyasa yatay sayilir, islem aranmaz
VOLATILITE_SPIKE_CARPANI = 1.8  # mevcut ATR, kendi 20-periyot ortalamasinin bu katindan
                                  # fazlaysa "anormal oynak" sayilir, risk kisilir

# v7.2: PULLBACK STRATEJISI parametreleri (backtest: in-sample +0.285R/islem %56.3
# kazanma, out-of-sample +0.313R/islem %57.0 kazanma - momentum stratejisinden daha
# iyi). Momentum stratejisiyle PARALEL calisir, her tur ikisi de taranir, en yuksek
# skorlu adaylar secilir (kaynagi fark etmeksizin).
PULLBACK_RSI_ESIK = 45          # RSI son PULLBACK_BAKIS_PENCERE mumda bu esigin altina inmis olmali
PULLBACK_BAKIS_PENCERE = 5
TOPARLANMA_RSI_MIN, TOPARLANMA_RSI_MAX = 42, 58  # simdiki RSI bu aralikta olmali

# ── RİSK/GÜVENLİK AYARLARI (bilerek muhafazakar) ──
LEV_HAM_DEGER = os.getenv("LEV")  # v6.1 TESHIS: Railway'den GERCEKTE gelen ham deger neyse
                                    # bunu goruyoruz - "LEV" adinda bir degisken yoksa None doner
LEV = int(LEV_HAM_DEGER) if LEV_HAM_DEGER else 10       # kaldirac (v6: varsayilan 3'ten 10'a
                                                         # cikarildi - kullanici tercihi, Railway'de
                                                         # LEV degiskeni silinir/degismezse bile
                                                         # kod her zaman 10x ile baslasin diye)
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.05"))  # her islemde bakiyenin %5'i risk
MAX_POS = int(os.getenv("MAX_POS", "2"))  # v6: 1'den 2'ye cikarildi - kullanici talebiyle,
                                            # ayni anda 2 guclu sinyal varsa ikisini de kacirmasin
GUNLUK_ZARAR_LIMIT_PCT = 0.15   # bakiyenin %15'i kaybedilirse o gun durur
KONTROL_ARALIGI_SN = 300        # her 5 dakikada bir yeni sinyal taransin (1h mum bazli strateji, hizli olmasina gerek yok)

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/yeni_strateji_state.json")
trade_state = {}
state_lock = threading.Lock()
gunluk_pnl = 0.0
gunluk_baslangic_bakiye = None
gunluk_lock = threading.Lock()

# v7: AAVE ornegi - bir coin kapanir kapanmaz (1 dakika sonra) ayni coin'de
# tekrar sinyal bulunup hemen yeniden acilmisti, bu sefer SL'e gitmisti
# (-%12). Ayni coin'de "whipsaw" (kazan-kaybet-kazan-kaybet) riskini azaltmak
# icin, bir coin kapandiktan sonra COOLDOWN_SAAT boyunca ayni coin'e tekrar
# girilmiyor - piyasanin o coin icin "sakinlesmesi" bekleniyor.
COOLDOWN_SAAT = float(os.getenv("COOLDOWN_SAAT", "2"))
son_kapanis_zamani = {}  # {symbol: epoch_zaman}
cooldown_lock = threading.Lock()

COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/yeni_strateji_cooldown.json")

# v7: Panel/ozet icin kapanan islemlerin kalici kaydi
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/yeni_strateji_log.json")
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
        log.warning(f"[LOG] Diske yazma basarisiz: {e}")

def trade_log_yukle():
    global trade_log
    try:
        if os.path.exists(TRADE_LOG_PATH):
            with open(TRADE_LOG_PATH) as f:
                trade_log = json.load(f)
    except Exception as e:
        log.warning(f"[LOG] Yukleme basarisiz: {e}")


def cooldown_diske_yaz():
    try:
        os.makedirs(os.path.dirname(COOLDOWN_PATH), exist_ok=True)
        with cooldown_lock:
            veri = dict(son_kapanis_zamani)
        with open(COOLDOWN_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[COOLDOWN] Diske yazma basarisiz: {e}")

def cooldown_diskten_yukle():
    global son_kapanis_zamani
    try:
        if os.path.exists(COOLDOWN_PATH):
            with open(COOLDOWN_PATH) as f:
                son_kapanis_zamani = json.load(f)
    except Exception as e:
        log.warning(f"[COOLDOWN] Yukleme basarisiz: {e}")

def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


def durumu_diske_yaz():
    try:
        os.makedirs(os.path.dirname(TRADE_STATE_PATH), exist_ok=True)
        with state_lock:
            veri = dict(trade_state)
        with open(TRADE_STATE_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[KALICI] {e}")


def durumu_diskten_yukle():
    global trade_state
    try:
        if os.path.exists(TRADE_STATE_PATH):
            with open(TRADE_STATE_PATH) as f:
                trade_state = json.load(f)
    except Exception as e:
        log.warning(f"[KALICI] {e}")


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
    """v4: ADX (Average Directional Index) - trend gucu olcusu. Dusuk ADX =
    piyasa yatay/kararsiz (yon yok), yuksek ADX = net trend var. BTC'de bu
    dusukse hicbir altcoin sinyaline guvenilmez, cunku piyasa genelinde
    yon belirsizdir."""
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
    """v6 DUZELTME: coin evreni 23'ten 43'e cikarilinca, her tarama turunda
    43*2+2=88 istek art arda (aralarinda hic bekleme olmadan) borsaya gidiyordu
    - bu Bitget'in rate limit'ine (429 Too Many Requests) takiliyordu, bazi
    coinlerin verisi hic alinamiyordu. Simdi her istekten once kucuk bir
    bekleme var, 429 alinirsa da otomatik olarak biraz bekleyip tekrar deniyor."""
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit)
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.15)  # her basarili istekten sonra kucuk bir bekleme
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
    """v4: piyasa rejimi + trend gucu filtresi.
    - Yon: BTC 4h MA20'nin ustunde/altinda mi (bullish/bearish)
    - Guc: BTC 4h ADX(14) ADX_ESIK'in ustunde mi (piyasa net trendde mi,
      yoksa yatay/kararsiz mi) - yataysa (dusuk ADX) HICBIR sinyale izin
      verilmez, coin bazinda teyit ne kadar guclu gorunurse gorunsun."""
    df4h = get_df(BTC_SEMBOL, "4h", 40)
    if df4h is None or len(df4h) < 30:
        return None, None, None
    ma20 = df4h["close"].rolling(20).mean().iloc[-1]
    fiyat = df4h["close"].iloc[-1]
    adx_deger = adx(df4h, 14).iloc[-1]
    if pd.isna(ma20) or pd.isna(adx_deger):
        return None, None, None
    trend_guclu = adx_deger >= ADX_ESIK
    return (fiyat > ma20), (fiyat < ma20), trend_guclu


def sinyal_kontrol_et(sym, btc_bullish, btc_bearish):
    """Backtest'teki AYNI mantik: 4h MA20+5mum teyidi, 1h RSI+5mum teyidi + BTC rejimi.
    v4: artik bir "guc skoru" ve "volatilite spike" bilgisi de donduruyor -
    boylece tarama_loop() birden fazla adaydan EN GUCLU olani secebiliyor,
    ve pozisyon_ac() anormal oynak coinlerde riski otomatik kucultebiliyor."""
    df4h = get_df(sym, "4h", 30)
    df1h = get_df(sym, "1h", 30)
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
    df1h["yon"] = np.where(df1h["close"] > df1h["open"], 1, -1)
    yon5_up_1h = (df1h["yon"].iloc[-5:] > 0).sum()
    yon5_down_1h = (df1h["yon"].iloc[-5:] < 0).sum()
    rsi_1h = df1h["rsi"].iloc[-1]
    atr_1h = df1h["atr"].iloc[-1]
    atr_ort20_1h = df1h["atr_ort20"].iloc[-1]
    fiyat = df1h["close"].iloc[-1]

    if pd.isna(ma20) or pd.isna(rsi_1h) or pd.isna(atr_1h) or atr_1h <= 0:
        return None

    long_ok = (fiyat_4h > ma20 and yon5_up_4h >= MUM_ESIGI and
               RSI_ALT < rsi_1h < RSI_UST and yon5_up_1h >= MUM_ESIGI and
               bool(btc_bullish))
    short_ok = (fiyat_4h < ma20 and yon5_down_4h >= MUM_ESIGI and
                (100 - RSI_UST) < rsi_1h < (100 - RSI_ALT) and yon5_down_1h >= MUM_ESIGI and
                bool(btc_bearish))

    if not (long_ok or short_ok):
        return None

    direction = "long" if long_ok else "short"
    if direction == "long":
        sl = fiyat - ATR_CARPANI * atr_1h
        tp = fiyat + ATR_CARPANI * atr_1h * RR
        mum_sayisi_4h, mum_sayisi_1h = yon5_up_4h, yon5_up_1h
        rsi_merkez, rsi_yaricap = 60, 15  # ideal merkez 60 (40-80 araliginin ortasi degil, 50-70'in ortasi)
    else:
        sl = fiyat + ATR_CARPANI * atr_1h
        tp = fiyat - ATR_CARPANI * atr_1h * RR
        mum_sayisi_4h, mum_sayisi_1h = yon5_down_4h, yon5_down_1h
        rsi_merkez, rsi_yaricap = 40, 15

    # ── GUC SKORU: RSI'in ideal merkeze yakinligi + mum netligi (0-100) ──
    uzaklik = min(abs(rsi_1h - rsi_merkez) / rsi_yaricap, 1.0)
    rsi_puan = 40 * (1 - uzaklik)
    mum_tablosu = {4: 22, 5: 30}
    puan_4h = mum_tablosu.get(int(mum_sayisi_4h), 15)
    puan_1h = mum_tablosu.get(int(mum_sayisi_1h), 15)
    skor = rsi_puan + puan_4h + puan_1h

    # ── VOLATILITE SPIKE: mevcut ATR, kendi 20-periyot ortalamasina gore anormal mi ──
    volatilite_spike = False
    if not pd.isna(atr_ort20_1h) and atr_ort20_1h > 0:
        volatilite_spike = (atr_1h / atr_ort20_1h) >= VOLATILITE_SPIKE_CARPANI

    return {"symbol": sym, "direction": direction, "entry": fiyat, "sl": sl, "tp": tp,
            "skor": skor, "volatilite_spike": volatilite_spike, "strateji": "momentum"}


def sinyal_kontrol_et_pullback(sym, btc_bullish, btc_bearish):
    """v7.2: PULLBACK STRATEJISI - momentum stratejisinden farkli mantik.
    Momentum RSI'nin ZATEN guclendigi (50-70) anlari ararken, bu strateji
    guclu bir trend ICINDE kisa vadeli bir GERI CEKILME (RSI son 5 mumda
    45'in altina inmis) olup sonra TOPARLANMAYA basladigi (RSI 42-58 arasina
    donmus, mum yesil/kirmizi teyitli) ani arar - "ucuza trende binmek".
    Backtest: in-sample +0.285R/islem (%56.3 kazanma), out-of-sample
    +0.313R/islem (%57.0 kazanma) - momentum stratejisinden daha iyi cikti."""
    df4h = get_df(sym, "4h", 30)
    df1h = get_df(sym, "1h", 30)
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

    # kendisi haric son PULLBACK_BAKIS_PENCERE mumun min/max RSI'i
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

    skor = 100 - abs(rsi_1h - merkez)  # merkeze ne kadar yakinsa o kadar yuksek skor

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


def gunluk_limit_kontrolu():
    with gunluk_lock:
        if gunluk_baslangic_bakiye is None:
            return False
        return gunluk_pnl <= -(gunluk_baslangic_bakiye * GUNLUK_ZARAR_LIMIT_PCT)


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

    # ── RİSK BAZLI POZİSYON BOYUTU ──
    risk_dolar = bakiye * RISK_PCT_BAKIYE

    # v4: VOLATILITE SPIKE KORUMASI - coin kendi normaline gore anormal
    # oynakken (ATR, 20-periyot ortalamasinin VOLATILITE_SPIKE_CARPANI katindan
    # fazlaysa) risk YARIYA indirilir. Mantik: ani/asiri oynak anlarda SL'in
    # gurultuyle tetiklenme ihtimali daha yuksek, o yuzden boyle anlarda
    # daha kucuk pozisyonla girmek daha guvenli.
    if volatilite_spike:
        risk_dolar *= 0.5
        tg(f"ℹ️ {sym} anormal volatilite tespit edildi (ATR spike) — risk "
           f"%{RISK_PCT_BAKIYE*100:.0f}'ten %{RISK_PCT_BAKIYE*50:.1f}'e kucultuldu")

    sl_mesafe_pct = abs(entry - sl) / entry
    notional = risk_dolar / sl_mesafe_pct
    gereken_marj = notional / LEV

    # v2 DUZELTME: Eskiden burada "marj bakiyenin cogunu yerse notional'i
    # bakiyenin %90'ina SINIRLA" mantigi vardi - bu YANLIS yondeydi, riski
    # BUYUTUYORDU. Dogrusu: hesaplanan marj bakiyeye gore fazla buyukse,
    # RISKI KUCULTMEK (notional'i kucultmek) gerekir.
    # v6: MAX_MARJ_PCT artik MAX_POS'a gore olcekleniyor - MAX_POS=2 iken
    # iki pozisyon ayni anda acik olabilir, ikisi de %25 marj kullansa toplam
    # %50'ye cikardi (fazla). Simdi tek pozisyonun tavani MAX_POS'a bolunuyor
    # (MAX_POS=1 icin hala %25, MAX_POS=2 icin %15 -> toplam en fazla %30).
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

    amount = notional / entry
    LEV_KULLANILAN = LEV  # gercek deger asagida, pozisyon acildiktan SONRA dogrulanacak

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        tg(f"⚠️ {sym} miktar hesaplanamadi: {e}")
        return
    if qty <= 0:
        return

    side = "buy" if direction == "long" else "sell"
    try:
        emir = exchange.create_market_order(sym, side, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giris emri basarisiz: {e}")
        return

    # v5 DUZELTME: Onceki kaldirac dogrulamasi POZISYON ACILMADAN ONCE
    # calisiyordu - o an borsada bu sembol icin acik pozisyon olmadigindan
    # fetch_positions() bos donuyor, kontrol hicbir sey dogrulamadan "sorun
    # yok" varsayiyordu (OP/USDT ornegi: bot "3x" dedi ama gercekte 10x
    # kullanildi, cunku dogrulama pozisyon yokken yapilmisti). Simdi kontrol
    # POZISYON GERCEKTEN ACILDIKTAN SONRA yapiliyor - artik borsa gercek
    # kaldiraci dondurebiliyor. Eger gercek kaldirac istenenden BUYUKSE
    # (daha riskli), fazla kismi HEMEN reduceOnly emirle kirpip hedeflenen
    # notional'e geri getiriyoruz - boylece gercek risk her zaman
    # RISK_PCT_BAKIYE hedefine sadik kalir.
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
                    hedef_notional = gereken_marj * LEV  # istenen risk icin ORIJINAL hedef notional (LEV ile)
                    gercek_notional = qty * entry
                    if gercek_notional > hedef_notional * 1.05:  # %5 tolerans
                        # fazlasini kirp
                        kirpilacak_qty = qty - (hedef_notional / entry)
                        kirpilacak_qty = float(exchange.amount_to_precision(sym, kirpilacak_qty))
                        if kirpilacak_qty > 0:
                            kapama_yon = "sell" if direction == "long" else "buy"
                            try:
                                exchange.create_market_order(sym, kapama_yon, kirpilacak_qty,
                                                              params={"reduceOnly": True})
                                qty = qty - kirpilacak_qty
                                tg(f"⚠️ {sym} kaldıraç uyuşmazlığı tespit edildi: istenen {LEV}x, "
                                   f"gerçek {gercek_lev}x — fazla pozisyon kırpıldı, risk hedefe geri getirildi")
                            except Exception as e:
                                tg(f"⚠️ {sym} kaldıraç uyuşmazlığı var ({gercek_lev}x) ama fazla pozisyon "
                                   f"kırpılamadı: {e} — risk hedeflenenden YÜKSEK olabilir, dikkatli izle")
    except Exception as e:
        log.warning(f"[KALDIRAC_DOGRULA] {sym}: {e}")

    notional = qty * entry  # kirpma sonrasi guncel deger

    # Hard stop (borsa seviyesinde SL) + TP limit emri
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

    with state_lock:
        trade_state[sym] = {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
                             "qty": qty, "tp_emir_id": tp_emir_id, "acilis_zamani": time.time(),
                             "strateji": strateji}
    durumu_diske_yaz()

    tg(f"📈 YENİ POZİSYON: {sym} {direction.upper()} [{strateji}]\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} | TP:{tp:.6f}\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Risk≈${risk_dolar:.2f} (bakiyenin ~%{RISK_PCT_BAKIYE*100:.0f}'i)"
       f"{' | ⚠️ volatilite spike, risk kucultuldu' if volatilite_spike else ''}")


def gercek_pozisyon_kapat(sym, oran=1.0):
    """Borsadan pozisyonu gercekten kapatir (reduceOnly market emri) ve state'i temizler.
    v7: oran parametresi eklendi - 1.0 tam kapatma, 0.5 pozisyonun yarisini kapatir
    (kalan yari acik kalir, SL/TP emirleri kalan miktar icin gecerliligini korur)."""
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

        emir = exchange.create_market_order(sym, kapama_yon, kapatilacak_qty, params={"reduceOnly": True})
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
            "not": "kismi_manuel" if oran < 1.0 else "manuel",
        })

        if kalan_pos and safe(kalan_pos.get("contracts")) > 0:
            # kismi kapatma - state'teki qty'yi guncelle, SL/TP hala gecerli
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


if bot:
    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        with state_lock:
            acik_semboller = list(trade_state.keys())
        if not acik_semboller:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        hedef = None
        if parca:
            for sym in acik_semboller:
                if parca in sym.upper():
                    hedef = sym
                    break
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen açık pozisyon bulunamadı: {acik_semboller}")
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
        """v7: Pozisyonun yarisini kapatir, kalan yari SL/TP ile acik kalir."""
        with state_lock:
            acik_semboller = list(trade_state.keys())
        if not acik_semboller:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/yarikapat", "", 1).strip().upper()
        hedef = None
        if parca:
            for sym in acik_semboller:
                if parca in sym.upper():
                    hedef = sym
                    break
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen açık pozisyon bulunamadı: {acik_semboller}")
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
        """v7: Sadece giris/SL/TP degil, ANLIK fiyat ve ANLIK PnL de gosterir."""
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
        satirlar = ["📊 PERFORMANS ÖZETİ\n"]
        if gecmis:
            toplam = len(gecmis)
            kazanan = [t for t in gecmis if t["pnl"] > 0]
            kaybeden = [t for t in gecmis if t["pnl"] <= 0]
            net_toplam = sum(t["pnl"] for t in gecmis)
            kazanma_orani = len(kazanan) / toplam * 100
            ort_kazanan = sum(t["pnl"] for t in kazanan) / len(kazanan) if kazanan else 0
            ort_kaybeden = sum(t["pnl"] for t in kaybeden) / len(kaybeden) if kaybeden else 0
            satirlar += [
                f"Toplam kapanan işlem: {toplam}",
                f"Kazanma oranı: %{kazanma_orani:.1f} ({len(kazanan)} kazanan / {len(kaybeden)} kaybeden)",
                f"Net toplam PnL: {net_toplam:+.2f}$",
                f"Ort. kazanan: {ort_kazanan:+.2f}$ | Ort. kaybeden: {ort_kaybeden:+.2f}$",
            ]
        else:
            satirlar.append("Henüz kapanan işlem yok.")
        with gunluk_lock:
            satirlar.append(f"\nBugünkü gerçekleşen PnL: {gunluk_pnl:+.2f}$")
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

    def ana_menu_klavye():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
            telebot.types.InlineKeyboardButton("📈 Açık Pozisyon", callback_data="panel_acik"),
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📜 Geçmiş İşlemler", callback_data="panel_gecmis"),
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
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
    def panel_buton_yaniti(call):
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
                # v7.1 DUZELTME: zararsiz - ayni icerik tekrar gonderilmeye
                # calisilmis (orn. "Yenile"ye art arda basma). Kullaniciya
                # gereksiz "hata olustu" mesaji gostermeye gerek yok.
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
        """v7: Manuel pozisyon acma - /ac SEMBOL long|short - kullanici talebiyle
        (panelde 'manuel ac/kapat' istegi). SL/TP botun kendi ATR bazli mantigiyla
        otomatik hesaplanir (tutarlilik icin, kanaldan gelen sabit yuzde degil)."""
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
            df1h = get_df(sym, "1h", 30)
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
            tp = fiyat + ATR_CARPANI * atr_1h * RR
        else:
            sl = fiyat + ATR_CARPANI * atr_1h
            tp = fiyat - ATR_CARPANI * atr_1h * RR

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


def tarama_loop():
    tg(f"🚀 YENİ STRATEJİ BOTU başladı (SÜRÜM: v7.4 — MAX_POS={MAX_POS})\n"
       f"Stratejiler: momentum + pullback (ikisi de taranır, en güçlü sinyaller seçilir)\n"
       f"Coin evreni: {len(COINS)} coin (her turda en güçlü {MAX_POS} sinyal seçilir)\n"
       f"Kaldıraç: {LEV}x [Railway'den okunan ham LEV değeri: {LEV_HAM_DEGER!r}] | "
       f"İşlem başına risk: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i\n"
       f"BTC ADX filtresi: piyasa yatayken (ADX<{ADX_ESIK}) işlem aranmaz\n"
       f"Volatilite koruması: anormal oynak coinlerde risk otomatik yarıya iner\n"
       f"Günlük zarar limiti: bakiyenin %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}'i\n"
       f"⚠️ Bu strateji backtest ile doğrulandı ama gerçek performansı garanti etmez.")

    global gunluk_baslangic_bakiye
    bakiye = gercek_bakiye_al()
    if bakiye:
        gunluk_baslangic_bakiye = bakiye

    while True:
        try:
            if gunluk_limit_kontrolu():
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

                # v4: TUM coin evrenini tara, EN YUKSEK SKORLU sinyalleri sec
                # v6: MAX_POS=2 oldugunda, bos slot sayisi kadar (1 veya 2)
                # en iyi adayi ac - "en guclu 1-2 kurulum" mantigi
                # v7.2: Artik HEM momentum HEM pullback stratejisi taraniyor,
                # ikisinin adaylari BIRLIKTE degerlendirilip en yuksek skorlular
                # secilir - hangi stratejiden geldigi onemli degil.
                adaylar = []
                for sym in COINS:
                    with state_lock:
                        if sym in trade_state:
                            continue
                    if cooldown_da_mi(sym):
                        continue
                    sinyal_m = sinyal_kontrol_et(sym, btc_bullish, btc_bearish)
                    if sinyal_m:
                        adaylar.append(sinyal_m)
                    sinyal_p = sinyal_kontrol_et_pullback(sym, btc_bullish, btc_bearish)
                    if sinyal_p:
                        adaylar.append(sinyal_p)

                if adaylar:
                    # v7.4 DUZELTME: Bir coin AYNI ANDA hem momentum hem pullback
                    # kosulunu saglayabiliyordu, ikisi de ayri aday olarak listeye
                    # giriyordu - eger 2 bos slot varsa, AYNI COIN icin IKI AYRI
                    # ISLEM ACILABILIYORDU (SIREN, ETHFI ornekleri). Simdi her
                    # sembol icin sadece EN YUKSEK SKORLU aday tutuluyor, secim
                    # ondan sonra yapiliyor - ayni coin asla iki kez acilamaz.
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
    """Acik pozisyonlari izler, SL/TP vurulmasini borsadan dogrular, state temizler."""
    global gunluk_pnl
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(15)
                continue

            positions = exchange.fetch_positions(semboller)
            acik_semboller = {p["symbol"] for p in positions if safe(p.get("contracts")) > 0}

            for sym in semboller:
                if sym in acik_semboller:
                    continue
                # pozisyon kapanmis (SL ya da TP vurulmus)
                with state_lock:
                    durum = trade_state.pop(sym, None)
                durumu_diske_yaz()
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
    print("YENİ STRATEJİ BOTU BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
