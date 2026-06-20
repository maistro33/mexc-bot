#!/usr/bin/env python3
"""
SADIK PAPER TRADING BOT v9
ICT Strateji + XGBoost AI (Kendi Kendine Öğrenen)
simple_trades + trades birleşik eğitim
"""

import os, time, threading, pickle
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
from supabase import create_client

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

# ─── RİSK (Paper) ───
LEVERAGE      = 5
MARGIN        = 10.0
TP1_PCT       = 0.010
TP2_PCT       = 0.020
TP3_PCT       = 0.035
SL_PCT        = 0.020
TRAIL_PCT     = 0.010
MAX_OPEN      = 10
SCAN_INTERVAL = 40

MIN_VOL_RATIO = 0.5
MIN_MOMENTUM  = 0.05
MIN_RSI       = 30
MAX_RSI       = 75
AI_MIN_SCORE  = 40
MIN_QUOTE_VOL = 2_000_000

MODEL_PATH    = "/tmp/sadik_model.pkl"
SCALER_PATH   = "/tmp/sadik_scaler.pkl"

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ",
}

MAX_PRICE = 30

# ─── XGBoost AI ───
_model  = None
_scaler = None
_model_trained = False

def load_ai_model():
    global _model, _scaler, _model_trained
    try:
        if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
            with open(MODEL_PATH, "rb") as f: _model = pickle.load(f)
            with open(SCALER_PATH, "rb") as f: _scaler = pickle.load(f)
            _model_trained = True
            print("[AI] XGBoost model yüklendi ✅")
        else:
            print("[AI] Model yok, fallback mod")
    except Exception as e:
        print(f"[AI] Model yükleme hatası: {e}")

def train_ai_model():
    global _model, _scaler, _model_trained
    try:
        from xgboost import XGBClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score

        print("[AI] Eğitim başlıyor...")
        if not supa: return

        # ─── v9 verisi ───
        r1 = supa.table("trades").select("*").execute()
        data1 = r1.data or []

        # ─── simple bot verisi ───
        r2 = supa.table("simple_trades").select("*").execute()
        data2 = r2.data or []

        print(f"[AI] v9: {len(data1)} | simple: {len(data2)} işlem")

        rows = []

        # v9 işlemleri
        for rec in data1:
            try:
                rows.append({
                    "rsi":          float(rec.get("rsi") or 50),
                    "volume_ratio": float(rec.get("volume_ratio") or 1),
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
                    "signal_long":  1 if rec.get("signal") == "LONG" else 0,
                    "win":          1 if float(rec.get("pnl") or 0) > 0 else 0,
                })
            except: pass

        # simple bot işlemleri (eksik alanlar 0)
        for rec in data2:
            try:
                rows.append({
                    "rsi":          float(rec.get("rsi") or 50),
                    "volume_ratio": float(rec.get("vol_ratio") or 1),
                    "momentum":     0,
                    "move_1":       0,
                    "move_3":       float(rec.get("move_3") or 0),
                    "volatility":   0,
                    "choch":        0,
                    "fvg_icinde":   0,
                    "fvg_buyukluk": 0,
                    "ob_bull":      0,
                    "ob_bear":      0,
                    "fake":         0,
                    "btc_up":       1 if rec.get("btc_trend") == "UP" else 0,
                    "btc_down":     1 if rec.get("btc_trend") == "DOWN" else 0,
                    "signal_long":  1 if rec.get("signal") == "LONG" else 0,
                    "win":          1 if float(rec.get("pnl") or 0) > 0 else 0,
                })
            except: pass

        if len(rows) < 50:
            print(f"[AI] Yeterli veri yok: {len(rows)} işlem")
            return

        df = pd.DataFrame(rows)
        features = ["rsi","volume_ratio","momentum","move_1","move_3",
                    "volatility","choch","fvg_icinde","fvg_buyukluk",
                    "ob_bull","ob_bear","fake","btc_up","btc_down","signal_long"]

        X = df[features]
        y = df["win"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y)

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s  = scaler.transform(X_test)

        model = XGBClassifier(
            n_estimators=100, max_depth=4,
            learning_rate=0.1, subsample=0.8,
            colsample_bytree=0.8, eval_metric="logloss",
            random_state=42, verbosity=0,
        )
        model.fit(X_train_s, y_train)

        acc = accuracy_score(y_test, model.predict(X_test_s))

        with open(MODEL_PATH, "wb") as f: pickle.dump(model, f)
        with open(SCALER_PATH, "wb") as f: pickle.dump(scaler, f)

        _model = model
        _scaler = scaler
        _model_trained = True

        print(f"[AI] Model eğitildi! Doğruluk: %{acc*100:.1f} | {len(df)} işlem")
        tg(f"🤖 XGBoost güncellendi!\nDoğruluk: %{acc*100:.1f} | {len(df)} işlem\n(v9: {len(data1)} + simple: {len(data2)})")

    except ImportError:
        print("[AI] xgboost kurulu değil!")
    except Exception as e:
        print(f"[AI] Eğitim hatası: {e}")

def retrain_loop():
    time.sleep(300)
    while True:
        train_ai_model()
        time.sleep(6 * 60 * 60)

def xgboost_score(ind, btc_trend):
    global _model, _scaler
    if not _model_trained or _model is None or _scaler is None:
        return None
    try:
        features = {
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
            "signal_long":  1,
        }
        X = pd.DataFrame([features])
        X_s = _scaler.transform(X)
        prob = _model.predict_proba(X_s)[0][1]
        return int(prob * 100)
    except Exception as e:
        print(f"[AI] Tahmin hatası: {e}")
        return None

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: print(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        print("[SUPA] OK")
    except Exception as e: print(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("trades").insert(data).execute()
    except Exception as e: print(f"[SAVE] {e}")

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API = 0

def safe_api(func, *args, **kwargs):
    global LAST_API
    for i in range(4):
        try:
            w = 0.6 - (time.time() - LAST_API)
            if w > 0: time.sleep(w)
            LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            print(f"[API {i}] {e}")
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
    except: return "NEUTRAL"

# ─── COINGLASS ───
def get_funding(symbol):
    if not CG_KEY: return 0.0
    try:
        sym = symbol.split("/")[0]
        r = req.get(
            "https://open-api-v3.coinglass.com/api/futures/fundingRate/current",
            headers={"CG-API-KEY": CG_KEY},
            params={"symbol": sym}, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                d = next((x for x in data if "bitget" in x.get("exchangeName","").lower()), data[0])
                return float(d.get("fundingRate", 0) or 0)
    except: pass
    return 0.0

def get_ls_ratio(symbol):
    if not CG_KEY: return 50.0, 50.0
    try:
        sym = symbol.split("/")[0]
        r = req.get(
            "https://open-api-v3.coinglass.com/api/futures/globalLongShortAccountRatio/history",
            headers={"CG-API-KEY": CG_KEY},
            params={"symbol": sym, "interval": "5m", "limit": 1}, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return float(data[-1].get("longAccount", 50)), float(data[-1].get("shortAccount", 50))
    except: pass
    return 50.0, 50.0

# ─── SEANS ───
def get_seans():
    saat = time.gmtime().tm_hour
    if 0 <= saat < 8:   return "ASYA"
    if 8 <= saat < 13:  return "AVRUPA"
    if 13 <= saat < 22: return "ABD"
    return "KAPANIS"

# ─── GÖSTERGELER ───
def calc_rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

def calc_macd(c):
    ema12 = c.ewm(span=12).mean()
    ema26 = c.ewm(span=26).mean()
    macd  = ema12 - ema26
    signal= macd.ewm(span=9).mean()
    hist  = macd - signal
    if float(hist.iloc[-1]) > 0 and float(hist.iloc[-2]) <= 0: return "YUKARI_KESIM"
    if float(hist.iloc[-1]) < 0 and float(hist.iloc[-2]) >= 0: return "ASAGI_KESIM"
    if float(hist.iloc[-1]) > 0: return "POZITIF"
    return "NEGATIF"

def calc_bb(c, n=20):
    ma  = c.rolling(n).mean()
    std = c.rolling(n).std()
    up  = ma + 2*std
    dn  = ma - 2*std
    price = float(c.iloc[-1])
    pct = (price - float(dn.iloc[-1])) / (float(up.iloc[-1]) - float(dn.iloc[-1])) * 100
    if pct > 80: return "UST"
    if pct < 20: return "ALT"
    return "ORTA"

# ─── ICT: FVG ───
def detect_fvg(df):
    results = []
    c = df["c"]; h = df["h"]; l = df["l"]
    for i in range(2, len(df)-1):
        if float(h.iloc[i-2]) < float(l.iloc[i]):
            gap_size = (float(l.iloc[i]) - float(h.iloc[i-2])) / float(c.iloc[i-1]) * 100
            results.append({"yon": "UP", "top": float(l.iloc[i]), "bot": float(h.iloc[i-2]), "size": gap_size, "idx": i})
        if float(l.iloc[i-2]) > float(h.iloc[i]):
            gap_size = (float(l.iloc[i-2]) - float(h.iloc[i])) / float(c.iloc[i-1]) * 100
            results.append({"yon": "DOWN", "top": float(l.iloc[i-2]), "bot": float(h.iloc[i]), "size": gap_size, "idx": i})
    return results[-3:] if results else []

def price_in_fvg(price, fvgs):
    for fvg in fvgs:
        if fvg["bot"] <= price <= fvg["top"]:
            return True, fvg
    return False, None

# ─── ICT: SWING ───
def swing_points(df, lookback=5):
    h = df["h"]; l = df["l"]
    swings = {"highs": [], "lows": []}
    for i in range(lookback, len(df)-lookback):
        if all(float(h.iloc[i]) >= float(h.iloc[i-j]) for j in range(1, lookback+1)) and \
           all(float(h.iloc[i]) >= float(h.iloc[i+j]) for j in range(1, lookback+1)):
            swings["highs"].append((i, float(h.iloc[i])))
        if all(float(l.iloc[i]) <= float(l.iloc[i-j]) for j in range(1, lookback+1)) and \
           all(float(l.iloc[i]) <= float(l.iloc[i+j]) for j in range(1, lookback+1)):
            swings["lows"].append((i, float(l.iloc[i])))
    return swings

# ─── ICT: CHoCH ───
def detect_choch(df, swings):
    c = df["c"]
    price = float(c.iloc[-1])
    if len(swings["highs"]) >= 2:
        last_high = swings["highs"][-1][1]
        prev_high = swings["highs"][-2][1]
        if price > last_high and last_high > prev_high: return "YUKARI"
    if len(swings["lows"]) >= 2:
        last_low = swings["lows"][-1][1]
        prev_low = swings["lows"][-2][1]
        if price < last_low and last_low < prev_low: return "ASAGI"
    return "YOK"

# ─── ICT: DISPLACEMENT ───
def detect_displacement(df):
    c = df["c"]; o = df["o"]; h = df["h"]; l = df["l"]
    last = len(df) - 1
    body = abs(float(c.iloc[last]) - float(o.iloc[last]))
    range_= float(h.iloc[last]) - float(l.iloc[last])
    avg_body = abs(c - o).rolling(20).mean().iloc[last]
    if body > avg_body * 2.0 and body > range_ * 0.7:
        return "UP" if float(c.iloc[last]) > float(o.iloc[last]) else "DOWN"
    return "YOK"

# ─── ICT: LİKİDİTE ───
def liquidity_taken(df, swings):
    h = df["h"]; l = df["l"]
    prev_high_price = float(h.iloc[-2])
    prev_low_price  = float(l.iloc[-2])
    if swings["highs"] and prev_high_price >= swings["highs"][-1][1] * 0.999: return "HIGH_ALINDI"
    if swings["lows"]  and prev_low_price  <= swings["lows"][-1][1]  * 1.001: return "LOW_ALINDI"
    return "YOK"

# ─── ANA GÖSTERGELER ───
def calc_indicators(symbol):
    try:
        raw1 = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=100)
        if not raw1 or len(raw1) < 50: return None
        df1 = pd.DataFrame(raw1, columns=["t","o","h","l","c","v"])

        raw5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=60)
        if not raw5: return None
        df5 = pd.DataFrame(raw5, columns=["t","o","h","l","c","v"])

        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=50)
        trend_1h = "NEUTRAL"
        if raw1h and len(raw1h) >= 20:
            c1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])["c"]
            e20 = float(c1h.ewm(span=20).mean().iloc[-1])
            e50 = float(c1h.ewm(span=50).mean().iloc[-1])
            p1h = float(c1h.iloc[-1])
            if p1h > e20 and e20 > e50: trend_1h = "UP"
            elif p1h < e20 and e20 < e50: trend_1h = "DOWN"

        c1 = df1["c"]; v1 = df1["v"]; c5 = df5["c"]
        price    = float(c1.iloc[-1])
        ema9     = float(c1.ewm(span=9).mean().iloc[-1])
        ema20    = float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5   = float(c5.ewm(span=9).mean().iloc[-1])
        ema20_5  = float(c5.ewm(span=20).mean().iloc[-1])
        rsi_v    = calc_rsi(c1)
        macd_d   = calc_macd(c1)
        bb_pos   = calc_bb(c1)

        vol_avg   = float(v1.rolling(20).mean().iloc[-1])
        if vol_avg <= 0: return None
        vol_ratio = float(v1.iloc[-1]) / vol_avg
        if vol_ratio != vol_ratio or vol_ratio <= 0: vol_ratio = 1.0

        prev1 = float(c1.iloc[-2])
        prev3 = float(c1.iloc[-4])
        if prev1 <= 0 or prev3 <= 0 or price <= 0: return None

        move_1    = (price - prev1) / prev1 * 100
        move_3    = (price - prev3) / prev3 * 100
        momentum  = abs(move_3)
        high1     = float(df1["h"].iloc[-1])
        low1      = float(df1["l"].iloc[-1])
        volatility= (high1 - low1) / price * 100 if price > 0 else 0
        avg5      = float(c1.tail(5).mean())

        try:
            fvgs             = detect_fvg(df5)
            in_fvg, fvg_data = price_in_fvg(price, fvgs)
            swings           = swing_points(df5)
            choch            = detect_choch(df5, swings)
            displace         = detect_displacement(df5)
            liq              = liquidity_taken(df5, swings)

            ob_bull = None; ob_bear = None
            c5s = df5["c"]; o5 = df5["o"]; h5 = df5["h"]; l5 = df5["l"]
            for i in range(len(df5)-3, max(len(df5)-15, 0), -1):
                if float(c5s.iloc[i]) < float(o5.iloc[i]):
                    next_move = (float(c5s.iloc[i+1]) - float(o5.iloc[i+1])) / float(o5.iloc[i+1]) * 100
                    if next_move > 0.5:
                        ob_bull = {"high": float(h5.iloc[i]), "low": float(l5.iloc[i])}
                        break
            for i in range(len(df5)-3, max(len(df5)-15, 0), -1):
                if float(c5s.iloc[i]) > float(o5.iloc[i]):
                    next_move = (float(c5s.iloc[i+1]) - float(o5.iloc[i+1])) / float(o5.iloc[i+1]) * 100
                    if next_move < -0.5:
                        ob_bear = {"high": float(h5.iloc[i]), "low": float(l5.iloc[i])}
                        break

            in_bull_ob = ob_bull and ob_bull["low"] <= price <= ob_bull["high"]
            in_bear_ob = ob_bear and ob_bear["low"] <= price <= ob_bear["high"]

            nearest_res = min([s[1] for s in swings["highs"] if s[1] > price], default=price*1.05)
            nearest_sup = max([s[1] for s in swings["lows"]  if s[1] < price], default=price*0.95)
            res_uzaklik = (nearest_res - price) / price * 100
            sup_uzaklik = (price - nearest_sup) / price * 100

        except:
            fvgs=[]; in_fvg=False; fvg_data=None
            choch="YOK"; displace="YOK"; liq="YOK"
            res_uzaklik=5.0; sup_uzaklik=5.0
            in_bull_ob=False; in_bear_ob=False

        last3_high = float(c1.tail(3).max())
        prev_high  = float(c1.tail(10).head(7).max())
        last3_low  = float(c1.tail(3).min())
        prev_low   = float(c1.tail(10).head(7).min())
        fake_up    = last3_high > prev_high and price < prev_high
        fake_down  = last3_low  < prev_low  and price > prev_low

        return {
            "symbol": symbol, "price": price,
            "ema9": ema9, "ema20": ema20,
            "ema9_5": ema9_5, "ema20_5": ema20_5,
            "trend_1h": trend_1h, "rsi": rsi_v,
            "macd": macd_d, "bb": bb_pos, "rsi_div": "YOK",
            "vol_ratio": vol_ratio, "move_1": move_1,
            "move_3": move_3, "momentum": momentum,
            "volatility": volatility, "avg5": avg5,
            "fake_up": fake_up, "fake_down": fake_down,
            "fvg_var": len(fvgs) > 0,
            "fvg_icinde": in_fvg,
            "fvg_yon": fvg_data["yon"] if in_fvg and fvg_data else "YOK",
            "fvg_buyukluk": fvg_data["size"] if in_fvg and fvg_data else 0,
            "choch": choch,
            "displacement": displace,
            "likidite": liq,
            "res_uzaklik": res_uzaklik,
            "sup_uzaklik": sup_uzaklik,
            "in_bull_ob": in_bull_ob,
            "in_bear_ob": in_bear_ob,
        }
    except Exception:
        return None

# ─── SİNYAL ───
def get_signal(ind, btc_trend="NEUTRAL"):
    p    = ind["price"];  e9 = ind["ema9"]; e20 = ind["ema20"]
    e9_5 = ind["ema9_5"]; e20_5 = ind["ema20_5"]
    t1h  = ind["trend_1h"]; rsi = ind["rsi"]
    vr   = ind["vol_ratio"]; m1 = ind["move_1"]
    mom  = ind["momentum"]; avg5 = ind["avg5"]

    if vr  < 1.5:  return None
    if mom < 0.3:  return None
    if rsi < 45:   return None
    if rsi > 70:   return None

    fvg_yon = ind.get("fvg_yon", "YOK")
    choch   = ind.get("choch", "YOK")

    if e9 > e20 and e9_5 > e20_5 and m1 > 0 and p >= avg5:
        if t1h == "DOWN": return None
        if btc_trend not in ["UP", "NEUTRAL"]: return None
        if ind.get("fvg_icinde") and fvg_yon != "UP": return None
        if choch != "YOK" and choch != "YUKARI": return None
        return "LONG"

    if e9 < e20 and e9_5 < e20_5 and m1 < 0 and p <= avg5:
        if btc_trend not in ["DOWN", "NEUTRAL"]: return None
        if ind.get("fvg_icinde") and fvg_yon != "DOWN": return None
        if choch != "YOK" and choch != "ASAGI": return None
        return "SHORT"

    return None

# ─── AI SKOR ───
def ai_score(symbol, ind, btc_trend, funding):
    xgb = xgboost_score(ind, btc_trend)
    if xgb is not None:
        print(f"[AI] {symbol.split('/')[0]} XGBoost: {xgb}")
        return xgb
    score = 60
    if ind.get("vol_ratio", 0) >= 3.0:      score += 8
    if ind.get("momentum", 0) >= 1.0:        score += 5
    if ind.get("fvg_icinde"):                score += 10
    if ind.get("choch") != "YOK":           score += 8
    if ind.get("displacement") != "YOK":    score += 5
    if btc_trend == "UP":                    score += 5
    if funding < 0:                          score += 5
    return min(95, score)

# ─── GPT KARAR ───
def gpt_karar(symbol, signal, ind, btc_trend, funding, long_pct, short_pct):
    if not OPENAI_KEY: return True, "GPT yok"
    try:
        sym = symbol.split("/")[0]
        prompt = f"""Kripto futures trading uzmanısın. ICT/Smart Money konseptini biliyorsun.

Coin: {sym}/USDT — Sinyal: {signal}
1h Trend: {ind['trend_1h']} | BTC: {btc_trend}
RSI: {ind['rsi']:.1f} | MACD: {ind['macd']} | BB: {ind['bb']}
Hacim: {ind['vol_ratio']:.1f}x | Momentum: {ind['move_3']:+.2f}%

--- ICT ANALİZ ---
CHoCH: {ind['choch']}
FVG İçinde: {'EVET' if ind['fvg_icinde'] else 'HAYIR'} ({ind['fvg_yon']})
Displacement: {ind['displacement']}
Likidite: {ind['likidite']}
Direnç uzaklık: %{ind['res_uzaklik']:.2f}
Destek uzaklık: %{ind['sup_uzaklik']:.2f}

--- PİYASA ---
Funding: {funding*100:.4f}%
Long/Short: %{long_pct:.1f} / %{short_pct:.1f}
Sahte pump: {'EVET' if ind['fake_up'] else 'HAYIR'}

Sadece:
GİR — [1 cümle neden]
veya
PAS — [1 cümle neden]"""

        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 80, "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=10)

        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            gir = yanit.upper().startswith("GİR") or yanit.upper().startswith("GIR")
            return gir, yanit
    except Exception as e:
        print(f"[GPT] {e}")
    return True, "GPT hata"

# ─── TARAMA ───
def scan_coins():
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return []
        active = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith("/USDT:USDT"): continue
            sym_name = symbol.split("/")[0]
            if sym_name in BLACKLIST: continue
            if ticker.get("quoteVolume", 0) < MIN_QUOTE_VOL: continue
            price = ticker.get("last", 0) or 0
            if price > MAX_PRICE: continue
            pct = abs(ticker.get("percentage", 0) or 0)
            if pct < 0.2: continue
            active.append({"symbol": symbol, "volume": ticker.get("quoteVolume", 0)})
        active.sort(key=lambda x: x["volume"], reverse=True)
        print(f"[SCAN] {len(active)} coin aktif")
        return active[:80]
    except Exception as e:
        print(f"[SCAN] {e}")
        return []

# ─── PAPER AÇ ───
def open_paper(symbol, signal, ind, score, gpt_yorum, btc_trend, funding, long_pct, short_pct, seans):
    with pos_lock:
        if symbol in positions: return
        if len(positions) >= MAX_OPEN: return

    price = ind["price"]
    if signal == "LONG":
        tp1=price*(1+TP1_PCT); tp2=price*(1+TP2_PCT)
        tp3=price*(1+TP3_PCT); sl=price*(1-SL_PCT)
    else:
        tp1=price*(1-TP1_PCT); tp2=price*(1-TP2_PCT)
        tp3=price*(1-TP3_PCT); sl=price*(1+SL_PCT)

    with pos_lock:
        positions[symbol] = {
            "signal": signal, "entry": price,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
            "tp1_done": False, "tp2_done": False,
            "max_pnl": 0.0, "trail_active": False,
            "score": score, "ind": ind,
            "btc_trend": btc_trend, "funding": funding,
            "long_pct": long_pct, "short_pct": short_pct,
            "seans": seans, "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    ict_tag = ""
    if ind["choch"] != "YOK":       ict_tag += "CHoCH✅ "
    if ind["fvg_icinde"]:            ict_tag += "FVG✅ "
    if ind["displacement"] != "YOK": ict_tag += "DISP✅ "
    if ind.get("in_bull_ob"):        ict_tag += "BullOB✅ "
    if ind.get("in_bear_ob"):        ict_tag += "BearOB✅ "

    ai_tag = "🤖 XGBoost" if _model_trained else "🤖 Fallback"

    tg(
        f"📋 [PAPER] {sym} {signal}\n"
        f"Giriş: {price:.6f}\n"
        f"TP1:{tp1:.6f} TP2:{tp2:.6f} TP3:{tp3:.6f}\n"
        f"SL: {sl:.6f}\n"
        f"RSI:{ind['rsi']:.0f} Hacim:{ind['vol_ratio']:.1f}x\n"
        f"ICT: {ict_tag if ict_tag else 'Standart'}\n"
        f"AI Skor: {score} ({ai_tag})\n"
        f"BTC:{btc_trend} Seans:{seans}\n"
        f"💬 {gpt_yorum}"
    )

# ─── PAPER KAPAT ───
def close_paper(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig = pos["signal"]; entry = pos["entry"]
    pnl = (exit_price-entry)/entry*MARGIN*LEVERAGE if sig=="LONG" else (entry-exit_price)/entry*MARGIN*LEVERAGE
    sure = int((time.time() - pos["open_time"]) / 60)
    ind  = pos.get("ind", {})

    save_trade({
        "symbol":       symbol,
        "signal":       sig,
        "pnl":          round(pnl, 4),
        "ai_score":     pos["score"],
        "momentum":     ind.get("momentum", 0),
        "volume_ratio": ind.get("vol_ratio", 0),
        "volatility":   ind.get("volatility", 0),
        "rsi":          ind.get("rsi", 0),
        "move_1":       ind.get("move_1", 0),
        "move_3":       ind.get("move_3", 0),
        "fake":         1 if ind.get("fake_up") or ind.get("fake_down") else 0,
        "choch":        1 if ind.get("choch") != "YOK" else 0,
        "choch_yon":    ind.get("choch", "YOK"),
        "fvg_icinde":   1 if ind.get("fvg_icinde") else 0,
        "fvg_buyukluk": ind.get("fvg_buyukluk", 0),
        "vol_devam":    1 if ind.get("vol_devam") else 0,
        "btc_trend":    pos.get("btc_trend", "NEUTRAL"),
        "ob_bull":      1 if ind.get("in_bull_ob") else 0,
        "ob_bear":      1 if ind.get("in_bear_ob") else 0,
    })

    sym  = symbol.split("/")[0]
    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} [PAPER] {sym} KAPANDI\n{reason}\nPnL: {pnl:+.2f} USDT | {sure}dk")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(5)
        try:
            with pos_lock: syms = list(positions.keys())
            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price  = t["last"]
                entry  = pos["entry"]
                signal = pos["signal"]

                pnl_pct = (price-entry)/entry*100 if signal=="LONG" else (entry-price)/entry*100
                if pnl_pct > pos["max_pnl"]: pos["max_pnl"] = pnl_pct
                max_pnl = pos["max_pnl"]

                if pnl_pct <= -SL_PCT*100:
                    close_paper(symbol, "STOP LOSS", price); continue

                if not pos["tp1_done"] and max_pnl >= 0.8 and pnl_pct <= max_pnl - 0.6:
                    close_paper(symbol, f"ERKEN TRAILING +{pnl_pct:.2f}%", price); continue

                if not pos["tp1_done"] and pnl_pct >= TP1_PCT*100:
                    pos["tp1_done"] = True
                    tg(f"🟡 [PAPER] {symbol.split('/')[0]} TP1 +%{TP1_PCT*100:.1f} — breakeven")
                    continue

                if pos["tp1_done"] and pnl_pct <= -0.2:
                    close_paper(symbol, "BREAKEVEN", price); continue

                if pos["tp1_done"] and not pos["tp2_done"] and pnl_pct >= TP2_PCT*100:
                    pos["tp2_done"] = True
                    pos["trail_active"] = True
                    tg(f"🟡 [PAPER] {symbol.split('/')[0]} TP2 +%{TP2_PCT*100:.1f} — trailing")
                    continue

                if pos["tp2_done"] and pnl_pct >= TP3_PCT*100:
                    close_paper(symbol, "TP3 🎯", price); continue

                if pos["trail_active"] and pnl_pct <= max_pnl - TRAIL_PCT*100:
                    close_paper(symbol, "TRAILING 🚀", price); continue

                if time.time() - pos["open_time"] > 60*60:
                    close_paper(symbol, "ZAMAN AŞIMI 60dk", price)

        except Exception as e:
            print(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    while True:
        try:
            with pos_lock:
                open_count = len(positions)
                open_syms  = set(positions.keys())

            if open_count >= MAX_OPEN:
                time.sleep(10); continue

            btc_trend = get_btc_trend()
            seans     = get_seans()
            active    = scan_coins()

            if not active:
                time.sleep(SCAN_INTERVAL); continue

            for coin in active:
                symbol = coin["symbol"]
                if symbol in open_syms: continue
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break

                ind = calc_indicators(symbol)
                if not ind: continue

                signal = get_signal(ind, btc_trend)
                if not signal: continue

                funding  = get_funding(symbol)
                long_pct, short_pct = get_ls_ratio(symbol)
                score    = ai_score(symbol, ind, btc_trend, funding)

                if score < AI_MIN_SCORE:
                    print(f"[SKIP] {symbol.split('/')[0]} AI:%{score}")
                    continue

                gir, yorum = gpt_karar(symbol, signal, ind, btc_trend, funding, long_pct, short_pct)
                sym = symbol.split("/")[0]
                print(f"[GPT] {sym} {signal} → {'GİR ✅' if gir else 'PAS ❌'} | {yorum}")

                if not gir: continue

                print(f"[SİNYAL] {sym} {signal} RSI={ind['rsi']:.0f} CHoCH={ind['choch']} FVG={ind['fvg_icinde']}")
                open_paper(symbol, signal, ind, score, yorum, btc_trend, funding, long_pct, short_pct, seans)
                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id, "📋 Paper pozisyon yok."); return
        lines = ["📋 PAPER POZİSYONLAR\n"]
        for sym, pos in positions.items():
            t = safe_api(exchange.fetch_ticker, sym)
            if t:
                price = t["last"]
                pnl_pct = (price-pos["entry"])/pos["entry"]*100 if pos["signal"]=="LONG" else (pos["entry"]-price)/pos["entry"]*100
                pnl = pnl_pct/100*MARGIN*LEVERAGE
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} {pos['signal']}\n"
                    f"Giriş:{pos['entry']:.6f} → {price:.6f}\n"
                    f"PnL:{pnl:+.2f} USDT ({pnl_pct:+.2f}%)\n"
                )
        bot.send_message(msg.chat.id, "\n".join(lines))

@bot.message_handler(commands=["istatistik","stats"])
def cmd_stats(msg):
    if not supa:
        bot.send_message(msg.chat.id, "Supabase yok."); return
    try:
        r = supa.table("trades").select("pnl,choch,fvg_icinde,created_at,ob_bull,ob_bear").execute()
        data = r.data or []
        if not data:
            bot.send_message(msg.chat.id, "Henüz kayıt yok."); return

        toplam = len(data)
        kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
        kayip  = toplam - kazan
        net    = sum(float(d.get("pnl") or 0) for d in data)

        from datetime import datetime, timezone
        simdi = datetime.now(timezone.utc)
        bugun = [d for d in data if d.get("created_at","")[:10] == simdi.strftime("%Y-%m-%d")]
        bugun_kazan = sum(1 for d in bugun if float(d.get("pnl") or 0) > 0)
        bugun_net   = sum(float(d.get("pnl") or 0) for d in bugun)

        fvg_top   = [d for d in data if d.get("fvg_icinde") == 1]
        fvg_win   = [d for d in fvg_top if float(d.get("pnl") or 0) > 0]
        choch_top = [d for d in data if d.get("choch") == 1]
        choch_win = [d for d in choch_top if float(d.get("pnl") or 0) > 0]
        ob_top    = [d for d in data if d.get("ob_bull") == 1 or d.get("ob_bear") == 1]
        ob_win    = [d for d in ob_top if float(d.get("pnl") or 0) > 0]

        ai_tag = "🤖 XGBoost aktif" if _model_trained else "🤖 Fallback mod"

        bot.send_message(msg.chat.id,
            f"📊 İSTATİSTİK\n\n"
            f"🗓 Bugün: {len(bugun)} işlem\n"
            f"  ✅ {bugun_kazan} kazanan\n"
            f"  Net: {bugun_net:+.2f} USDT\n\n"
            f"📈 Toplam: {toplam} işlem\n"
            f"  Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
            f"  Kaybeden: {kayip} (%{kayip/toplam*100:.0f})\n"
            f"  Net PnL: {net:+.2f} USDT\n\n"
            f"🔍 ICT Analiz:\n"
            f"  FVG: {len(fvg_top)} işlem → %{len(fvg_win)/max(len(fvg_top),1)*100:.0f} kazanç\n"
            f"  CHoCH: {len(choch_top)} işlem → %{len(choch_win)/max(len(choch_top),1)*100:.0f} kazanç\n"
            f"  OB: {len(ob_top)} işlem → %{len(ob_win)/max(len(ob_top),1)*100:.0f} kazanç\n\n"
            f"{ai_tag}"
        )
    except Exception as e:
        bot.send_message(msg.chat.id, f"Hata: {e}")

@bot.message_handler(commands=["aitrain"])
def cmd_aitrain(msg):
    bot.send_message(msg.chat.id, "🤖 XGBoost eğitimi başlıyor...")
    threading.Thread(target=train_ai_model, daemon=True).start()

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text = msg.text.replace("/kapat","").strip().upper()
    if not text:
        bot.send_message(msg.chat.id, "Kullanım: /kapat SOL"); return
    symbol = f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions:
            bot.send_message(msg.chat.id, f"❌ {text} yok."); return
    close_paper(symbol, "MANUEL")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms = list(positions.keys())
    for s in syms: close_paper(s, "MANUEL HEPSI")

# ─── MAIN ───
if __name__ == "__main__":
    print("📋 SADIK PAPER TRADING BOT v9 BAŞLIYOR...")
    load_ai_model()
    threading.Thread(target=health_server,  daemon=True).start()
    threading.Thread(target=manage_loop,    daemon=True).start()
    threading.Thread(target=scanner_loop,   daemon=True).start()
    threading.Thread(target=retrain_loop,   daemon=True).start()
    print("[OK] Health | Manage | Scanner | AI Retrain")
    tg(
        "📋 SADIK PAPER TRADING BOT v9\n\n"
        "⚠️ GERÇEK İŞLEM YOK\n\n"
        "✅ XGBoost AI (trades + simple_trades)\n"
        "✅ Her 6 saatte otomatik yeniden eğitim\n"
        "✅ ICT: FVG, CHoCH, OB, Displacement\n"
        "✅ GPT-4o-mini onayı\n"
        "✅ BTC trend + Funding rate\n\n"
        f"Max {MAX_OPEN} eş zamanlı\n\n"
        "/durum /istatistik /aitrain /kapat SOL /hepsikapat"
    )
    threading.Thread(target=train_ai_model, daemon=True).start()
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}"); time.sleep(5)
