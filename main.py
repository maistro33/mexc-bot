#!/usr/bin/env python3
"""
SADIK PAPER TRADING BOT v11c
XGBoost Ana Karar Verici — Ayrı LONG/SHORT modelleri
"""

import os, time, threading, pickle, logging
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK")

# ─── CONFIG ───
TELE_TOKEN   = os.getenv("TELE_TOKEN","")
CHAT_ID      = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API   = os.getenv("BITGET_API","")
BITGET_SEC   = os.getenv("BITGET_SEC","")
BITGET_PASS  = os.getenv("BITGET_PASS","")
SUPA_URL     = os.getenv("SUPABASE_URL","")
SUPA_KEY     = os.getenv("SUPABASE_KEY","")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY","")
CG_KEY       = os.getenv("COINGLASS_API_KEY", os.getenv("COINGL_API_KEY",""))

# ─── RİSK ───
LEVERAGE      = 5
MARGIN        = 10.0
TP1_PCT       = 0.010
TP2_PCT       = 0.020
TP3_PCT       = 0.035
SL_PCT        = 0.020
TRAIL_PCT     = 0.010
MAX_OPEN      = 7
SCAN_INTERVAL = 40
AI_MIN_SCORE  = 65
MIN_QUOTE_VOL = 2_000_000
MAX_PRICE     = 30
COMMISSION    = 0.0006  # %0.06 açış + %0.06 kapanış = %0.12 toplam

MODEL_LONG_PATH  = "/tmp/sadik_model_long.pkl"
MODEL_SHORT_PATH = "/tmp/sadik_model_short.pkl"
SCALER_PATH      = "/tmp/sadik_scaler.pkl"

# LONG ve SHORT için ayrı feature setleri — signal_long yok
FEATURES = [
    "rsi", "volume_ratio", "momentum", "move_1", "move_3",
    "volatility", "choch", "fvg_icinde", "fvg_buyukluk",
    "ob_bull", "ob_bear", "fake", "btc_up", "btc_down"
]

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ",
}

# ─── AYRИ LONG/SHORT MODELLERİ ───
_model_long    = None
_model_short   = None
_scaler        = None
_model_trained = False
_model_lock    = threading.Lock()

def load_ai_model():
    global _model_long, _model_short, _scaler, _model_trained
    try:
        if os.path.exists(MODEL_LONG_PATH) and os.path.exists(MODEL_SHORT_PATH) and os.path.exists(SCALER_PATH):
            with open(MODEL_LONG_PATH,  "rb") as f: _model_long  = pickle.load(f)
            with open(MODEL_SHORT_PATH, "rb") as f: _model_short = pickle.load(f)
            with open(SCALER_PATH,      "rb") as f: _scaler      = pickle.load(f)
            _model_trained = True
            log.info("[AI] LONG + SHORT modeller yüklendi ✅")
        else:
            log.info("[AI] Model yok, fallback mod")
    except Exception as e:
        log.error(f"[AI] Model yükleme: {e}")

def _build_row(rec, is_v9=True):
    if is_v9:
        vol = float(rec.get("volume_ratio") or 1)
    else:
        vol = float(rec.get("vol_ratio") or rec.get("volume_ratio") or 1)
    return {
        "rsi":          float(rec.get("rsi") or 50),
        "volume_ratio": vol,
        "momentum":     float(rec.get("momentum") or 0),
        "move_1":       float(rec.get("move_1") or 0),
        "move_3":       float(rec.get("move_3") or 0),
        "volatility":   float(rec.get("volatility") or 0),
        "choch":        int(rec.get("choch") or 0),
        "fvg_icinde":   int(rec.get("fvg_icinde") or 0),
        "fvg_buyukluk": float(rec.get("fvg_buyukluk") or 0),
        "ob_bull":      int(rec.get("ob_bull") or 0),
        "ob_bear":      int(rec.get("ob_bear") or 0),
        "fake":         int(rec.get("fake") or 0),
        "btc_up":       1 if rec.get("btc_trend") == "UP" else 0,
        "btc_down":     1 if rec.get("btc_trend") == "DOWN" else 0,
        "signal":       rec.get("signal", "LONG"),
        "win":          1 if float(rec.get("pnl") or 0) > 0 else 0,
    }

def train_ai_model():
    global _model_long, _model_short, _scaler, _model_trained
    try:
        from xgboost import XGBClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score

        log.info("[AI] Eğitim başlıyor...")
        if not supa:
            log.warning("[AI] Supabase yok")
            return

        r1 = supa.table("trades").select("*").execute()
        data1 = r1.data or []
        r2 = supa.table("simple_trades").select("*").execute()
        data2 = r2.data or []

        rows = []
        for rec in data1:
            try: rows.append(_build_row(rec, is_v9=True))
            except Exception as e: log.warning(f"[AI] v9 satır: {e}")
        for rec in data2:
            try: rows.append(_build_row(rec, is_v9=False))
            except Exception as e: log.warning(f"[AI] simple satır: {e}")

        if len(rows) < 50:
            log.warning(f"[AI] Yetersiz veri: {len(rows)}")
            return

        df = pd.DataFrame(rows)

        # LONG ve SHORT verilerini ayır
        df_long  = df[df["signal"] == "LONG"].copy()
        df_short = df[df["signal"] == "SHORT"].copy()

        log.info(f"[AI] LONG:{len(df_long)} SHORT:{len(df_short)} işlem")

        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        scaler.fit(df[FEATURES])

        def train_one(df_sub, label):
            if len(df_sub) < 30:
                log.warning(f"[AI] {label} için yeterli veri yok: {len(df_sub)}")
                return None
            X = df_sub[FEATURES]; y = df_sub["win"]
            if y.sum() < 5 or (y==0).sum() < 5:
                log.warning(f"[AI] {label} sınıf dengesizliği")
                return None
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y)
            model = XGBClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, colsample_bytree=0.8,
                eval_metric="logloss", random_state=42, verbosity=0)
            model.fit(scaler.transform(X_train), y_train)
            acc = accuracy_score(y_test, model.predict(scaler.transform(X_test)))
            log.info(f"[AI] {label} model: %{acc*100:.1f} | {len(df_sub)} işlem")
            return model

        model_long  = train_one(df_long,  "LONG")
        model_short = train_one(df_short, "SHORT")

        if model_long is None and model_short is None:
            log.warning("[AI] Her iki model de eğitilemedi")
            return

        with _model_lock:
            if model_long:
                with open(MODEL_LONG_PATH,  "wb") as f: pickle.dump(model_long,  f)
                _model_long = model_long
            if model_short:
                with open(MODEL_SHORT_PATH, "wb") as f: pickle.dump(model_short, f)
                _model_short = model_short
            with open(SCALER_PATH, "wb") as f: pickle.dump(scaler, f)
            _scaler = scaler
            _model_trained = True

        long_acc  = "✅" if model_long  else "❌"
        short_acc = "✅" if model_short else "❌"
        tg(f"🤖 XGBoost güncellendi!\nLONG model: {long_acc} ({len(df_long)} işlem)\nSHORT model: {short_acc} ({len(df_short)} işlem)")

    except ImportError:
        log.error("[AI] xgboost kurulu değil!")
    except Exception as e:
        log.error(f"[AI] Eğitim: {e}")

def online_update(ind, btc_trend, signal, pnl):
    global _model_long, _model_short, _scaler, _model_trained
    if not _model_trained or _scaler is None: return
    try:
        row = {
            "rsi":          ind.get("rsi", 50),
            "volume_ratio": ind.get("vol_ratio", 1),
            "momentum":     ind.get("momentum", 0),
            "move_1":       ind.get("move_1", 0),
            "move_3":       ind.get("move_3", 0),
            "volatility":   ind.get("volatility", 0),
            "choch":        1 if ind.get("choch") != "YOK" else 0,
            "fvg_icinde":   1 if ind.get("fvg_icinde") else 0,
            "fvg_buyukluk": ind.get("fvg_buyukluk", 0),
            "ob_bull":      1 if ind.get("in_bull_ob") else 0,
            "ob_bear":      1 if ind.get("in_bear_ob") else 0,
            "fake":         1 if ind.get("fake_up") or ind.get("fake_down") else 0,
            "btc_up":       1 if btc_trend == "UP" else 0,
            "btc_down":     1 if btc_trend == "DOWN" else 0,
        }
        X_new = pd.DataFrame([row])[FEATURES]
        y_new = [1 if pnl > 0 else 0]
        with _model_lock:
            X_s = _scaler.transform(X_new)
            if signal == "LONG" and _model_long:
                _model_long.fit(X_s, y_new, xgb_model=_model_long.get_booster(),
                               eval_metric="logloss", verbose=False)
            elif signal == "SHORT" and _model_short:
                _model_short.fit(X_s, y_new, xgb_model=_model_short.get_booster(),
                                eval_metric="logloss", verbose=False)
        log.info(f"[AI] Online update {signal}: pnl={pnl:+.2f}")
    except Exception as e:
        log.warning(f"[AI] Online update: {e}")

def retrain_loop():
    time.sleep(300)
    while True:
        train_ai_model()
        time.sleep(6 * 60 * 60)

def xgboost_decision(ind, btc_trend):
    """Ayrı LONG/SHORT modelleriyle karar ver"""
    if not _model_trained or _scaler is None:
        return None, 0

    try:
        row = {
            "rsi":          ind.get("rsi", 50),
            "volume_ratio": ind.get("vol_ratio", 1),
            "momentum":     ind.get("momentum", 0),
            "move_1":       ind.get("move_1", 0),
            "move_3":       ind.get("move_3", 0),
            "volatility":   ind.get("volatility", 0),
            "choch":        1 if ind.get("choch") != "YOK" else 0,
            "fvg_icinde":   1 if ind.get("fvg_icinde") else 0,
            "fvg_buyukluk": ind.get("fvg_buyukluk", 0),
            "ob_bull":      1 if ind.get("in_bull_ob") else 0,
            "ob_bear":      1 if ind.get("in_bear_ob") else 0,
            "fake":         1 if ind.get("fake_up") or ind.get("fake_down") else 0,
            "btc_up":       1 if btc_trend == "UP" else 0,
            "btc_down":     1 if btc_trend == "DOWN" else 0,
        }

        with _model_lock:
            X = pd.DataFrame([row])[FEATURES]
            X_s = _scaler.transform(X)

            score_long  = 0
            score_short = 0

            if _model_long:
                score_long  = int(_model_long.predict_proba(X_s)[0][1]  * 100)
            if _model_short:
                score_short = int(_model_short.predict_proba(X_s)[0][1] * 100)

        log.info(f"[AI] {ind.get('symbol','').split('/')[0]} LONG:{score_long} SHORT:{score_short}")

        # BTC trende göre filtrele
        if btc_trend == "UP"   and score_long  >= AI_MIN_SCORE: return "LONG",  score_long
        if btc_trend == "DOWN" and score_short >= AI_MIN_SCORE: return "SHORT", score_short
        if btc_trend == "NEUTRAL":
            if score_long >= AI_MIN_SCORE and score_long >= score_short:  return "LONG",  score_long
            if score_short >= AI_MIN_SCORE and score_short > score_long:  return "SHORT", score_short

        return None, max(score_long, score_short)

    except Exception as e:
        log.warning(f"[AI] Karar: {e}")
        return None, 0

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] OK")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("trades").insert(data).execute()
    except Exception as e: log.error(f"[SAVE] {e}")

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API = 0
api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global LAST_API
    for i in range(4):
        try:
            with api_lock:
                w = 0.6 - (time.time() - LAST_API)
                if w > 0: time.sleep(w)
                LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            log.warning(f"[API {i}] {e}")
            time.sleep(2)
    return None

# ─── STATE ───
positions = {}
pos_lock  = threading.Lock()

# ─── BTC TREND ───
def get_btc_trend():
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=20)
        if not raw: return "NEUTRAL"
        c = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])["c"]
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        p   = float(c.iloc[-1])
        if p > e20 * 1.001: return "UP"
        if p < e20 * 0.999: return "DOWN"
        return "NEUTRAL"
    except Exception as e:
        log.warning(f"[BTC] {e}"); return "NEUTRAL"

# ─── COINGLASS ───
def get_funding(symbol):
    if not CG_KEY: return 0.0
    try:
        sym = symbol.split("/")[0]
        r = req.get("https://open-api-v3.coinglass.com/api/futures/fundingRate/current",
            headers={"CG-API-KEY": CG_KEY}, params={"symbol": sym}, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                d = next((x for x in data if "bitget" in x.get("exchangeName","").lower()), data[0])
                return float(d.get("fundingRate", 0) or 0)
    except Exception as e: log.warning(f"[FUNDING] {e}")
    return 0.0

def get_ls_ratio(symbol):
    if not CG_KEY: return 50.0, 50.0
    try:
        sym = symbol.split("/")[0]
        r = req.get("https://open-api-v3.coinglass.com/api/futures/globalLongShortAccountRatio/history",
            headers={"CG-API-KEY": CG_KEY},
            params={"symbol": sym, "interval": "5m", "limit": 1}, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data: return float(data[-1].get("longAccount", 50)), float(data[-1].get("shortAccount", 50))
    except Exception as e: log.warning(f"[LS] {e}")
    return 50.0, 50.0

def get_seans():
    saat = time.gmtime().tm_hour
    if 0 <= saat < 8:   return "ASYA"
    if 8 <= saat < 13:  return "AVRUPA"
    if 13 <= saat < 22: return "ABD"
    return "KAPANIS"

# ─── GÖSTERGELER ───
def calc_rsi(c, n=14):
    d=c.diff(); g=d.clip(lower=0).rolling(n).mean(); l=(-d.clip(upper=0)).rolling(n).mean()
    return float((100-100/(1+g/l.replace(0,0.001))).iloc[-1])

def calc_macd(c):
    hist=(c.ewm(span=12).mean()-c.ewm(span=26).mean())-(c.ewm(span=12).mean()-c.ewm(span=26).mean()).ewm(span=9).mean()
    if float(hist.iloc[-1])>0 and float(hist.iloc[-2])<=0: return "YUKARI_KESIM"
    if float(hist.iloc[-1])<0 and float(hist.iloc[-2])>=0: return "ASAGI_KESIM"
    return "POZITIF" if float(hist.iloc[-1])>0 else "NEGATIF"

def calc_bb(c, n=20):
    ma=c.rolling(n).mean(); std=c.rolling(n).std()
    up=ma+2*std; dn=ma-2*std; price=float(c.iloc[-1])
    denom=float(up.iloc[-1])-float(dn.iloc[-1])
    if denom==0: return "ORTA"
    pct=(price-float(dn.iloc[-1]))/denom*100
    return "UST" if pct>80 else "ALT" if pct<20 else "ORTA"

def detect_fvg(df):
    results=[]; c=df["c"]; h=df["h"]; l=df["l"]
    for i in range(2,len(df)-1):
        if float(h.iloc[i-2])<float(l.iloc[i]):
            results.append({"yon":"UP","top":float(l.iloc[i]),"bot":float(h.iloc[i-2]),"size":(float(l.iloc[i])-float(h.iloc[i-2]))/float(c.iloc[i-1])*100})
        if float(l.iloc[i-2])>float(h.iloc[i]):
            results.append({"yon":"DOWN","top":float(l.iloc[i-2]),"bot":float(h.iloc[i]),"size":(float(l.iloc[i-2])-float(h.iloc[i]))/float(c.iloc[i-1])*100})
    return results[-3:] if results else []

def price_in_fvg(price, fvgs):
    for fvg in fvgs:
        if fvg["bot"]<=price<=fvg["top"]: return True, fvg
    return False, None

def swing_points(df, lookback=5):
    h=df["h"]; l=df["l"]; swings={"highs":[],"lows":[]}
    for i in range(lookback,len(df)-lookback):
        if all(float(h.iloc[i])>=float(h.iloc[i-j]) for j in range(1,lookback+1)) and all(float(h.iloc[i])>=float(h.iloc[i+j]) for j in range(1,lookback+1)):
            swings["highs"].append((i,float(h.iloc[i])))
        if all(float(l.iloc[i])<=float(l.iloc[i-j]) for j in range(1,lookback+1)) and all(float(l.iloc[i])<=float(l.iloc[i+j]) for j in range(1,lookback+1)):
            swings["lows"].append((i,float(l.iloc[i])))
    return swings

def detect_choch(df, swings):
    price=float(df["c"].iloc[-1])
    if len(swings["highs"])>=2:
        lh=swings["highs"][-1][1]; ph=swings["highs"][-2][1]
        if price>lh and lh>ph: return "YUKARI"
    if len(swings["lows"])>=2:
        ll=swings["lows"][-1][1]; pl=swings["lows"][-2][1]
        if price<ll and ll<pl: return "ASAGI"
    return "YOK"

def detect_displacement(df):
    c=df["c"]; o=df["o"]; h=df["h"]; l=df["l"]; last=len(df)-1
    body=abs(float(c.iloc[last])-float(o.iloc[last]))
    rng=float(h.iloc[last])-float(l.iloc[last])
    avg=abs(c-o).rolling(20).mean().iloc[last]
    if avg>0 and body>avg*2.0 and rng>0 and body>rng*0.7:
        return "UP" if float(c.iloc[last])>float(o.iloc[last]) else "DOWN"
    return "YOK"

def liquidity_taken(df, swings):
    h=df["h"]; l=df["l"]
    if swings["highs"] and float(h.iloc[-2])>=swings["highs"][-1][1]*0.999: return "HIGH_ALINDI"
    if swings["lows"]  and float(l.iloc[-2])<=swings["lows"][-1][1]*1.001:  return "LOW_ALINDI"
    return "YOK"

def calc_indicators(symbol):
    try:
        raw1=safe_api(exchange.fetch_ohlcv,symbol,"1m",limit=100)
        if not raw1 or len(raw1)<50: return None
        df1=pd.DataFrame(raw1,columns=["t","o","h","l","c","v"])

        raw5=safe_api(exchange.fetch_ohlcv,symbol,"5m",limit=60)
        if not raw5: return None
        df5=pd.DataFrame(raw5,columns=["t","o","h","l","c","v"])

        raw1h=safe_api(exchange.fetch_ohlcv,symbol,"1h",limit=50)
        trend_1h="NEUTRAL"
        if raw1h and len(raw1h)>=20:
            c1h=pd.DataFrame(raw1h,columns=["t","o","h","l","c","v"])["c"]
            e20=float(c1h.ewm(span=20).mean().iloc[-1]); e50=float(c1h.ewm(span=50).mean().iloc[-1]); p1h=float(c1h.iloc[-1])
            if p1h>e20 and e20>e50: trend_1h="UP"
            elif p1h<e20 and e20<e50: trend_1h="DOWN"

        c1=df1["c"]; v1=df1["v"]; c5=df5["c"]
        price=float(c1.iloc[-1])
        if price<=0: return None

        ema9=float(c1.ewm(span=9).mean().iloc[-1]); ema20=float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5=float(c5.ewm(span=9).mean().iloc[-1]); ema20_5=float(c5.ewm(span=20).mean().iloc[-1])
        rsi_v=calc_rsi(c1); macd_d=calc_macd(c1); bb_pos=calc_bb(c1)

        vol_avg=float(v1.rolling(20).mean().iloc[-1])
        if vol_avg<=0: return None
        vol_ratio=float(v1.iloc[-1])/vol_avg
        if not np.isfinite(vol_ratio) or vol_ratio<=0: vol_ratio=1.0

        prev1=float(c1.iloc[-2]); prev3=float(c1.iloc[-4])
        if prev1<=0 or prev3<=0: return None

        move_1=(price-prev1)/prev1*100; move_3=(price-prev3)/prev3*100
        momentum=abs(move_3); volatility=(float(df1["h"].iloc[-1])-float(df1["l"].iloc[-1]))/price*100
        avg5=float(c1.tail(5).mean())

        try:
            fvgs=detect_fvg(df5); in_fvg,fvg_data=price_in_fvg(price,fvgs)
            swings=swing_points(df5); choch=detect_choch(df5,swings)
            displace=detect_displacement(df5); liq=liquidity_taken(df5,swings)
            ob_bull=ob_bear=None
            c5s=df5["c"]; o5=df5["o"]; h5=df5["h"]; l5=df5["l"]
            for i in range(len(df5)-3,max(len(df5)-15,0),-1):
                if float(c5s.iloc[i])<float(o5.iloc[i]):
                    if (float(c5s.iloc[i+1])-float(o5.iloc[i+1]))/float(o5.iloc[i+1])*100>0.5:
                        ob_bull={"high":float(h5.iloc[i]),"low":float(l5.iloc[i])}; break
            for i in range(len(df5)-3,max(len(df5)-15,0),-1):
                if float(c5s.iloc[i])>float(o5.iloc[i]):
                    if (float(c5s.iloc[i+1])-float(o5.iloc[i+1]))/float(o5.iloc[i+1])*100<-0.5:
                        ob_bear={"high":float(h5.iloc[i]),"low":float(l5.iloc[i])}; break
            in_bull_ob=bool(ob_bull and ob_bull["low"]<=price<=ob_bull["high"])
            in_bear_ob=bool(ob_bear and ob_bear["low"]<=price<=ob_bear["high"])
            nearest_res=min([s[1] for s in swings["highs"] if s[1]>price],default=price*1.05)
            nearest_sup=max([s[1] for s in swings["lows"]  if s[1]<price],default=price*0.95)
            res_uzaklik=(nearest_res-price)/price*100; sup_uzaklik=(price-nearest_sup)/price*100
        except Exception as e:
            log.debug(f"[ICT] {symbol}: {e}")
            fvgs=[]; in_fvg=False; fvg_data=None; choch="YOK"; displace="YOK"; liq="YOK"
            res_uzaklik=5.0; sup_uzaklik=5.0; in_bull_ob=False; in_bear_ob=False

        last3_high=float(c1.tail(3).max()); prev_high=float(c1.tail(10).head(7).max())
        last3_low=float(c1.tail(3).min());  prev_low=float(c1.tail(10).head(7).min())
        fake_up=last3_high>prev_high and price<prev_high
        fake_down=last3_low<prev_low and price>prev_low

        return {
            "symbol":symbol,"price":price,"ema9":ema9,"ema20":ema20,"ema9_5":ema9_5,"ema20_5":ema20_5,
            "trend_1h":trend_1h,"rsi":rsi_v,"macd":macd_d,"bb":bb_pos,"rsi_div":"YOK",
            "vol_ratio":vol_ratio,"move_1":move_1,"move_3":move_3,"momentum":momentum,
            "volatility":volatility,"avg5":avg5,"fake_up":fake_up,"fake_down":fake_down,
            "fvg_var":len(fvgs)>0,"fvg_icinde":in_fvg,
            "fvg_yon":fvg_data["yon"] if in_fvg and fvg_data else "YOK",
            "fvg_buyukluk":fvg_data["size"] if in_fvg and fvg_data else 0,
            "choch":choch,"displacement":displace,"likidite":liq,
            "res_uzaklik":res_uzaklik,"sup_uzaklik":sup_uzaklik,
            "in_bull_ob":in_bull_ob,"in_bear_ob":in_bear_ob,
        }
    except Exception as e:
        log.warning(f"[IND] {symbol}: {e}"); return None

# ─── KORUMA FİLTRELERİ ───
def safety_check(ind):
    if ind.get("fake_up") or ind.get("fake_down"): return False, "Fake pump/dump"
    if ind.get("vol_ratio", 0) < 0.5: return False, "Hacim düşük"
    rsi = ind.get("rsi", 50)
    if rsi < 35 or rsi > 80: return False, f"RSI dışında: {rsi:.0f}"
    return True, "OK"

# ─── GPT ───
def gpt_karar(symbol, signal, ind, btc_trend, funding, long_pct, short_pct):
    if not OPENAI_KEY: return True, "GPT yok"
    try:
        sym=symbol.split("/")[0]
        prompt=f"""Kripto futures uzmanısın.
Coin:{sym} Sinyal:{signal} BTC:{btc_trend}
RSI:{ind['rsi']:.1f} Hacim:{ind['vol_ratio']:.1f}x CHoCH:{ind['choch']} FVG:{'EVET' if ind['fvg_icinde'] else 'HAYIR'}
Funding:{funding*100:.4f}% L/S:%{long_pct:.0f}/%{short_pct:.0f}
Sadece GİR veya PAS yaz, 1 cümle."""
        r=req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},
            json={"model":"gpt-4o-mini","max_tokens":60,"temperature":0.2,
                  "messages":[{"role":"user","content":prompt}]},timeout=8)
        if r.status_code==200:
            yanit=r.json()["choices"][0]["message"]["content"].strip()
            return yanit.upper().startswith("GİR") or yanit.upper().startswith("GIR"), yanit[:100]
        return True, f"GPT {r.status_code}"
    except Exception as e:
        log.warning(f"[GPT] {e}"); return True, "GPT timeout"

# ─── TARAMA ───
def scan_coins():
    try:
        tickers=safe_api(exchange.fetch_tickers)
        if not tickers: return []
        active=[]
        for symbol,ticker in tickers.items():
            if not symbol.endswith("/USDT:USDT"): continue
            if symbol.split("/")[0] in BLACKLIST: continue
            qv=ticker.get("quoteVolume") or 0
            if qv<MIN_QUOTE_VOL: continue
            price=ticker.get("last") or 0
            if not price or price>MAX_PRICE: continue
            if abs(ticker.get("percentage") or 0)<0.2: continue
            active.append({"symbol":symbol,"volume":qv})
        active.sort(key=lambda x:x["volume"],reverse=True)
        log.info(f"[SCAN] {len(active)} coin aktif")
        return active[:80]
    except Exception as e:
        log.error(f"[SCAN] {e}"); return []

# ─── PAPER AÇ ───
def open_paper(symbol,signal,ind,score,gpt_yorum,btc_trend,funding,long_pct,short_pct,seans):
    with pos_lock:
        if symbol in positions: return
        if len(positions)>=MAX_OPEN: return
        price=ind["price"]
        if signal=="LONG":
            tp1=price*(1+TP1_PCT); tp2=price*(1+TP2_PCT); tp3=price*(1+TP3_PCT); sl=price*(1-SL_PCT)
        else:
            tp1=price*(1-TP1_PCT); tp2=price*(1-TP2_PCT); tp3=price*(1-TP3_PCT); sl=price*(1+SL_PCT)
        positions[symbol]={"signal":signal,"entry":price,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,
            "tp1_done":False,"tp2_done":False,"max_pnl":0.0,"trail_active":False,
            "score":score,"ind":ind,"btc_trend":btc_trend,"funding":funding,
            "long_pct":long_pct,"short_pct":short_pct,"seans":seans,"open_time":time.time()}

    sym=symbol.split("/")[0]
    ict_tag=""
    if ind.get("choch","YOK")!="YOK": ict_tag+="CHoCH✅ "
    if ind.get("fvg_icinde"):          ict_tag+="FVG✅ "
    if ind.get("in_bull_ob"):          ict_tag+="BullOB✅ "
    if ind.get("in_bear_ob"):          ict_tag+="BearOB✅ "
    tg(f"📋 [PAPER] {sym} {signal}\nGiriş:{price:.6f}\nTP1:{tp1:.6f} TP2:{tp2:.6f} TP3:{tp3:.6f}\nSL:{sl:.6f}\nRSI:{ind['rsi']:.0f} Hacim:{ind['vol_ratio']:.1f}x\nICT:{ict_tag if ict_tag else 'Standart'}\n🤖 XGBoost:{score} BTC:{btc_trend}\n💬{gpt_yorum}")

# ─── PAPER KAPAT ───
def close_paper(symbol,reason,exit_price=None):
    with pos_lock: pos=positions.pop(symbol,None)
    if not pos: return
    if exit_price is None:
        t=safe_api(exchange.fetch_ticker,symbol)
        exit_price=t["last"] if t else pos["entry"]
    sig=pos["signal"]; entry=pos["entry"]
    # Komisyon dahil PnL (%0.06 açış + %0.06 kapanış)
    position_size = MARGIN * LEVERAGE
    commission = position_size * COMMISSION
    if sig == "LONG":
        pnl = (exit_price-entry)/entry * position_size - commission
    else:
        pnl = (entry-exit_price)/entry * position_size - commission
    sure=int((time.time()-pos["open_time"])/60)
    ind=pos.get("ind",{})
    threading.Thread(target=online_update,args=(ind,pos.get("btc_trend","NEUTRAL"),sig,pnl),daemon=True).start()
    save_trade({"symbol":symbol,"signal":sig,"pnl":round(pnl,4),"ai_score":pos["score"],
        "momentum":ind.get("momentum",0),"volume_ratio":ind.get("vol_ratio",0),
        "volatility":ind.get("volatility",0),"rsi":ind.get("rsi",0),
        "move_1":ind.get("move_1",0),"move_3":ind.get("move_3",0),
        "fake":1 if ind.get("fake_up") or ind.get("fake_down") else 0,
        "choch":1 if ind.get("choch","YOK")!="YOK" else 0,"choch_yon":ind.get("choch","YOK"),
        "fvg_icinde":1 if ind.get("fvg_icinde") else 0,"fvg_buyukluk":ind.get("fvg_buyukluk",0),
        "vol_devam":0,"btc_trend":pos.get("btc_trend","NEUTRAL"),
        "ob_bull":1 if ind.get("in_bull_ob") else 0,"ob_bear":1 if ind.get("in_bear_ob") else 0})
    tg(f"{'🟢' if pnl>=0 else '🔴'} [PAPER] {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL:{pnl:+.2f} USDT | {sure}dk")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(5)
        try:
            with pos_lock: syms=list(positions.keys())
            for symbol in syms:
                with pos_lock: pos=positions.get(symbol)
                if not pos: continue
                t=safe_api(exchange.fetch_ticker,symbol)
                if not t: continue
                price=t["last"]; entry=pos["entry"]; signal=pos["signal"]
                pnl_pct=(price-entry)/entry*100 if signal=="LONG" else (entry-price)/entry*100
                with pos_lock:
                    if symbol not in positions: continue
                    if pnl_pct>positions[symbol]["max_pnl"]: positions[symbol]["max_pnl"]=pnl_pct
                    max_pnl=positions[symbol]["max_pnl"]
                    tp1_done=positions[symbol]["tp1_done"]
                    tp2_done=positions[symbol]["tp2_done"]
                    trail_active=positions[symbol]["trail_active"]
                if pnl_pct<=-SL_PCT*100: close_paper(symbol,"STOP LOSS",price); continue
                if not tp1_done and max_pnl>=0.8 and pnl_pct<=max_pnl-0.6: close_paper(symbol,f"ERKEN TRAILING +{pnl_pct:.2f}%",price); continue
                if not tp1_done and pnl_pct>=TP1_PCT*100:
                    with pos_lock:
                        if symbol in positions: positions[symbol]["tp1_done"]=True
                    tg(f"🟡 [PAPER] {symbol.split('/')[0]} TP1 — breakeven"); continue
                # TP1 sonrası SL sıfıra çekildi — en kötü ihtimal 0
                if tp1_done and pnl_pct <= 0.0:
                    close_paper(symbol, "BREAKEVEN SIFIR", price); continue
                if tp1_done and not tp2_done and pnl_pct>=TP2_PCT*100:
                    with pos_lock:
                        if symbol in positions: positions[symbol]["tp2_done"]=True; positions[symbol]["trail_active"]=True
                    tg(f"🟡 [PAPER] {symbol.split('/')[0]} TP2 — trailing"); continue
                if tp2_done and pnl_pct>=TP3_PCT*100: close_paper(symbol,"TP3 🎯",price); continue
                if trail_active and pnl_pct<=max_pnl-TRAIL_PCT*100: close_paper(symbol,"TRAILING 🚀",price); continue
                if time.time()-pos["open_time"]>60*60: close_paper(symbol,"ZAMAN AŞIMI 60dk",price)
        except Exception as e: log.error(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    while True:
        try:
            with pos_lock:
                open_count=len(positions); open_syms=set(positions.keys())
            if open_count>=MAX_OPEN: time.sleep(10); continue

            btc_trend=get_btc_trend(); seans=get_seans(); active=scan_coins()
            if not active: time.sleep(SCAN_INTERVAL); continue

            for coin in active:
                symbol=coin["symbol"]
                if symbol in open_syms: continue
                with pos_lock:
                    if len(positions)>=MAX_OPEN: break

                ind=calc_indicators(symbol)
                if not ind: continue

                safe,reason=safety_check(ind)
                if not safe: log.debug(f"[SAFETY] {symbol.split('/')[0]}: {reason}"); continue

                signal,score=xgboost_decision(ind,btc_trend)
                if signal is None: log.info(f"[SKIP] {symbol.split('/')[0]} pas:{score}"); continue

                funding=get_funding(symbol); long_pct,short_pct=get_ls_ratio(symbol)
                gir,yorum=gpt_karar(symbol,signal,ind,btc_trend,funding,long_pct,short_pct)
                if not gir: log.info(f"[GPT PAS] {symbol.split('/')[0]}"); continue

                log.info(f"[SİNYAL] {symbol.split('/')[0]} {signal} RSI={ind['rsi']:.0f} score={score}")
                open_paper(symbol,signal,ind,score,yorum,btc_trend,funding,long_pct,short_pct,seans)
                time.sleep(1)

            time.sleep(SCAN_INTERVAL)
        except Exception as e:
            log.error(f"[SCANNER] {e}"); time.sleep(10)

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer,BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(f"OK|pos:{len(positions)}|ai:{_model_trained}".encode())
        def log_message(self,*a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions: bot.send_message(msg.chat.id,"📋 Pozisyon yok."); return
        lines=["📋 PAPER POZİSYONLAR\n"]
        for sym,pos in positions.items():
            t=safe_api(exchange.fetch_ticker,sym)
            if t:
                price=t["last"]
                pnl_pct=(price-pos["entry"])/pos["entry"]*100 if pos["signal"]=="LONG" else (pos["entry"]-price)/pos["entry"]*100
                pnl=pnl_pct/100*MARGIN*LEVERAGE
                lines.append(f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} {pos['signal']}\nGiriş:{pos['entry']:.6f}→{price:.6f}\nPnL:{pnl:+.2f}({pnl_pct:+.2f}%)\n")
        bot.send_message(msg.chat.id,"\n".join(lines))

@bot.message_handler(commands=["istatistik","stats"])
def cmd_stats(msg):
    if not supa: bot.send_message(msg.chat.id,"Supabase yok."); return
    try:
        r=supa.table("trades").select("pnl,choch,fvg_icinde,created_at,ob_bull,ob_bear").execute()
        data=r.data or []
        if not data: bot.send_message(msg.chat.id,"Kayıt yok."); return
        toplam=len(data); kazan=sum(1 for d in data if float(d.get("pnl") or 0)>0)
        net=sum(float(d.get("pnl") or 0) for d in data)
        from datetime import datetime,timezone
        simdi=datetime.now(timezone.utc)
        bugun=[d for d in data if d.get("created_at","")[:10]==simdi.strftime("%Y-%m-%d")]
        bugun_kazan=sum(1 for d in bugun if float(d.get("pnl") or 0)>0)
        bugun_net=sum(float(d.get("pnl") or 0) for d in bugun)
        fvg_top=[d for d in data if d.get("fvg_icinde")==1]; fvg_win=[d for d in fvg_top if float(d.get("pnl") or 0)>0]
        choch_top=[d for d in data if d.get("choch")==1]; choch_win=[d for d in choch_top if float(d.get("pnl") or 0)>0]
        ob_top=[d for d in data if d.get("ob_bull")==1 or d.get("ob_bear")==1]; ob_win=[d for d in ob_top if float(d.get("pnl") or 0)>0]
        long_m="✅" if _model_long else "❌"; short_m="✅" if _model_short else "❌"
        bot.send_message(msg.chat.id,
            f"📊 İSTATİSTİK\n\n🗓 Bugün:{len(bugun)} | ✅{bugun_kazan} | Net:{bugun_net:+.2f}\n\n"
            f"📈 Toplam:{toplam} | Kazanan:{kazan}(%{kazan/toplam*100:.0f})\nNet PnL:{net:+.2f} USDT\n\n"
            f"🔍 FVG:{len(fvg_top)}→%{len(fvg_win)/max(len(fvg_top),1)*100:.0f} | CHoCH:{len(choch_top)}→%{len(choch_win)/max(len(choch_top),1)*100:.0f} | OB:{len(ob_top)}→%{len(ob_win)/max(len(ob_top),1)*100:.0f}\n\n"
            f"🤖 LONG model:{long_m} | SHORT model:{short_m}")
    except Exception as e: bot.send_message(msg.chat.id,f"Hata:{e}")

@bot.message_handler(commands=["aitrain"])
def cmd_aitrain(msg):
    bot.send_message(msg.chat.id,"🤖 Eğitim başlıyor..."); threading.Thread(target=train_ai_model,daemon=True).start()

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text=msg.text.replace("/kapat","").strip().upper()
    if not text: bot.send_message(msg.chat.id,"Kullanım: /kapat SOL"); return
    symbol=f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions: bot.send_message(msg.chat.id,f"❌ {text} yok."); return
    close_paper(symbol,"MANUEL")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms=list(positions.keys())
    for s in syms: close_paper(s,"MANUEL HEPSI")

# ─── MAIN ───
if __name__=="__main__":
    print("📋 SADIK PAPER TRADING BOT v11c BAŞLIYOR...")
    load_ai_model()
    threading.Thread(target=health_server,daemon=True).start()
    threading.Thread(target=manage_loop,daemon=True).start()
    threading.Thread(target=scanner_loop,daemon=True).start()
    threading.Thread(target=retrain_loop,daemon=True).start()
    print("[OK] Health | Manage | Scanner | AI Retrain | Online Learning")
    tg("📋 SADIK PAPER TRADING BOT v11c\n\n🤖 Ayrı LONG + SHORT modelleri!\n✅ LONG model kendi verisinden öğrenir\n✅ SHORT model kendi verisinden öğrenir\n✅ RSI filtresi: 35-80\n✅ Online Learning\n✅ Her 6 saatte yeniden eğitim\n\n/durum /istatistik /aitrain /kapat SOL /hepsikapat")
    threading.Thread(target=train_ai_model,daemon=True).start()
    while True:
        try: bot.infinity_polling(timeout=30,long_polling_timeout=30)
        except Exception as e: log.error(f"[POLLING] {e}"); time.sleep(5)
