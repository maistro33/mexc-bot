#!/usr/bin/env python3
"""
SADIK PAPER TRADING BOT v8
ICT Strateji + Hızlı Öğrenme (günde 30+ işlem)
"""

import os, time, threading
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
TP1_PCT       = 0.015
TP2_PCT       = 0.025
TP3_PCT       = 0.040
SL_PCT        = 0.020
TRAIL_PCT     = 0.010
MAX_OPEN      = 10       # Daha fazla eş zamanlı
SCAN_INTERVAL = 15      # 429 koruması

MIN_VOL_RATIO = 0.5     # Çok gevşek
MIN_MOMENTUM  = 0.05
MIN_RSI       = 30
MAX_RSI       = 75
AI_MIN_SCORE  = 40
MIN_QUOTE_VOL = 2_000_000  # $2M — daha fazla coin

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI",
}

MAX_PRICE = 30  # $30 üstü büyük ihtimal hisse tokenı

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

def load_history(symbol):
    if not supa: return pd.DataFrame()
    try:
        r = supa.table("trades").select("*").eq("symbol", symbol).execute()
        rows = []
        for rec in r.data or []:
            try:
                rows.append({
                    "momentum":     float(rec.get("momentum") or 0),
                    "volume_ratio": float(rec.get("volume_ratio") or 0),
                    "rsi":          float(rec.get("rsi") or 50),
                    "funding":      float(rec.get("funding_rate") or 0),
                    "fvg_var":      int(rec.get("fvg_var") or 0),
                    "choch":        int(rec.get("choch") or 0),
                    "win":          1 if float(rec.get("pnl") or 0) > 0 else 0,
                })
            except: pass
        return pd.DataFrame(rows)
    except: return pd.DataFrame()

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

def calc_rsi_div(c, rsi_s):
    # RSI diverjansı: fiyat yüksek ama RSI düşük (bearish) veya tersi (bullish)
    price_trend = float(c.iloc[-1]) > float(c.iloc[-5])
    rsi_trend   = float(rsi_s.iloc[-1]) > float(rsi_s.rolling(14).mean().iloc[-5])
    if price_trend and not rsi_trend: return "BEARISH_DIV"
    if not price_trend and rsi_trend: return "BULLISH_DIV"
    return "YOK"

# ─── ICT: FVG ───
def detect_fvg(df):
    """Fair Value Gap tespiti"""
    results = []
    c = df["c"]; h = df["h"]; l = df["l"]
    for i in range(2, len(df)-1):
        # Yukarı FVG: mum1 high < mum3 low
        if float(h.iloc[i-2]) < float(l.iloc[i]):
            gap_size = (float(l.iloc[i]) - float(h.iloc[i-2])) / float(c.iloc[i-1]) * 100
            results.append({
                "yon": "UP", "top": float(l.iloc[i]),
                "bot": float(h.iloc[i-2]), "size": gap_size,
                "idx": i
            })
        # Aşağı FVG: mum1 low > mum3 high
        if float(l.iloc[i-2]) > float(h.iloc[i]):
            gap_size = (float(l.iloc[i-2]) - float(h.iloc[i])) / float(c.iloc[i-1]) * 100
            results.append({
                "yon": "DOWN", "top": float(l.iloc[i-2]),
                "bot": float(h.iloc[i]), "size": gap_size,
                "idx": i
            })
    return results[-3:] if results else []  # Son 3 FVG

def price_in_fvg(price, fvgs):
    """Fiyat FVG içinde mi?"""
    for fvg in fvgs:
        if fvg["bot"] <= price <= fvg["top"]:
            return True, fvg
    return False, None

# ─── ICT: SWING HIGH/LOW ───
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

# ─── ICT: CHoCH (Change of Character) ───
def detect_choch(df, swings):
    """Market yapısı değişimi — son swing kırıldı mı?"""
    c = df["c"]
    price = float(c.iloc[-1])

    if len(swings["highs"]) >= 2:
        last_high = swings["highs"][-1][1]
        prev_high = swings["highs"][-2][1]
        # Düşüş trendinde son high kırıldı = CHoCH yukarı
        if price > last_high and last_high > prev_high:
            return "YUKARI"

    if len(swings["lows"]) >= 2:
        last_low = swings["lows"][-1][1]
        prev_low = swings["lows"][-2][1]
        # Yükseliş trendinde son low kırıldı = CHoCH aşağı
        if price < last_low and last_low < prev_low:
            return "ASAGI"

    return "YOK"

# ─── ICT: DISPLACEMENT ───
def detect_displacement(df):
    """Güçlü tek mum hareketi — displacement"""
    c = df["c"]; o = df["o"]; h = df["h"]; l = df["l"]
    last = len(df) - 1
    body = abs(float(c.iloc[last]) - float(o.iloc[last]))
    range_= float(h.iloc[last]) - float(l.iloc[last])
    avg_body = abs(c - o).rolling(20).mean().iloc[last]

    if body > avg_body * 2.0 and body > range_ * 0.7:
        return "UP" if float(c.iloc[last]) > float(o.iloc[last]) else "DOWN"
    return "YOK"

# ─── ICT: LİKİDİTE SEVİYESİ ───
def liquidity_taken(df, swings):
    """Önceki swing high/low alındı mı? (stop hunt)"""
    c = df["c"]; h = df["h"]; l = df["l"]
    price = float(c.iloc[-1])
    prev_high_price = float(h.iloc[-2])
    prev_low_price  = float(l.iloc[-2])

    if swings["highs"] and prev_high_price >= swings["highs"][-1][1] * 0.999:
        return "HIGH_ALINDI"
    if swings["lows"] and prev_low_price <= swings["lows"][-1][1] * 1.001:
        return "LOW_ALINDI"
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
        rsi_div  = "YOK"  # Şimdilik basit tut

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

        # ICT analizleri (5m üzerinde)
        try:
            fvgs             = detect_fvg(df5)
            in_fvg, fvg_data = price_in_fvg(price, fvgs)
            swings           = swing_points(df5)
            choch            = detect_choch(df5, swings)
            displace         = detect_displacement(df5)
            liq              = liquidity_taken(df5, swings)
            nearest_res      = min([s[1] for s in swings["highs"] if s[1] > price], default=price*1.05)
            nearest_sup      = max([s[1] for s in swings["lows"]  if s[1] < price], default=price*0.95)
            res_uzaklik      = (nearest_res - price) / price * 100
            sup_uzaklik      = (price - nearest_sup) / price * 100
        except:
            fvgs=[]; in_fvg=False; fvg_data=None
            choch="YOK"; displace="YOK"; liq="YOK"
            res_uzaklik=5.0; sup_uzaklik=5.0

        # Sahte pump
        last3_high = float(c1.tail(3).max())
        prev_high  = float(c1.tail(10).head(7).max())
        last3_low  = float(c1.tail(3).min())
        prev_low   = float(c1.tail(10).head(7).min())
        fake_up    = last3_high > prev_high and price < prev_high
        fake_down  = last3_low  < prev_low  and price > prev_low

        # Destek/direnç seviyeleri (swing high/low'dan)
        nearest_res = min([s[1] for s in swings["highs"] if s[1] > price], default=price*1.05)
        nearest_sup = max([s[1] for s in swings["lows"]  if s[1] < price], default=price*0.95)
        res_uzaklik = (nearest_res - price) / price * 100
        sup_uzaklik = (price - nearest_sup) / price * 100

        return {
            "symbol": symbol, "price": price,
            "ema9": ema9, "ema20": ema20,
            "ema9_5": ema9_5, "ema20_5": ema20_5,
            "trend_1h": trend_1h, "rsi": rsi_v,
            "macd": macd_d, "bb": bb_pos, "rsi_div": rsi_div,
            "vol_ratio": vol_ratio, "move_1": move_1,
            "move_3": move_3, "momentum": momentum,
            "volatility": volatility, "avg5": avg5,
            "fake_up": fake_up, "fake_down": fake_down,
            # ICT
            "fvg_var": len(fvgs) > 0,
            "fvg_icinde": in_fvg,
            "fvg_yon": fvg_data["yon"] if in_fvg and fvg_data else "YOK",
            "fvg_buyukluk": fvg_data["size"] if in_fvg and fvg_data else 0,
            "choch": choch,
            "displacement": displace,
            "likidite": liq,
            "res_uzaklik": res_uzaklik,
            "sup_uzaklik": sup_uzaklik,
        }
    except Exception as e:
        print(f"[IND {symbol}] {e}")
        return None

# ─── SİNYAL ───
def get_signal(ind, btc_trend="NEUTRAL"):
    p    = ind["price"];  e9 = ind["ema9"]; e20 = ind["ema20"]
    e9_5 = ind["ema9_5"]; e20_5 = ind["ema20_5"]
    t1h  = ind["trend_1h"]; rsi = ind["rsi"]
    vr   = ind["vol_ratio"]; m1 = ind["move_1"]
    mom  = ind["momentum"]; avg5 = ind["avg5"]

    if vr  < MIN_VOL_RATIO: return None
    if mom < MIN_MOMENTUM:  return None
    if rsi < MIN_RSI:       return None
    if rsi > MAX_RSI:       return None
    if ind["fake_up"] and m1 > 0: return None
    if ind["fake_down"] and m1 < 0: return None

    # ICT bonus sinyal — CHoCH + FVG içinde = güçlü giriş
    ict_long  = ind["choch"] == "YUKARI" and ind["fvg_icinde"]
    ict_short = ind["choch"] == "ASAGI"  and ind["fvg_icinde"]

    # Standart sinyal
    std_long  = (p > e20 and e9 > e20 and e9_5 > e20_5
                 and m1 > 0 and p >= avg5 and t1h != "DOWN")
    std_short = (p < e20 and e9 < e20 and e9_5 < e20_5
                 and m1 < -0.2 and p <= avg5
                 and vr >= 2.0 and t1h == "DOWN")

    if ict_long or std_long:
        if btc_trend == "DOWN": return None  # BTC düşerken LONG açma
        return "LONG"
    if ict_short or std_short:
        if btc_trend == "UP": return None    # BTC yükselirken SHORT açma
        return "SHORT"
    return None

# ─── AI SKOR ───
def ai_score(symbol, ind, btc_trend, funding):
    try:
        df = load_history(symbol)
        if df is None or len(df) < 10: return 60
        mask = (
            (df["volume_ratio"] >= ind["vol_ratio"] * 0.6) &
            (df["volume_ratio"] <= ind["vol_ratio"] * 1.4) &
            (df["momentum"]     >= ind["momentum"]  * 0.4)
        )
        sim = df[mask]
        if len(sim) < 3: return 60
        wr = sim["win"].mean() * 100
        bonus = 0
        if ind["vol_ratio"] >= 3.0:      bonus += 8
        if ind["momentum"]  >= 1.0:      bonus += 5
        if ind["fvg_icinde"]:            bonus += 10  # FVG içinde güçlü
        if ind["choch"] != "YOK":        bonus += 8   # CHoCH var
        if ind["displacement"] != "YOK": bonus += 5   # Displacement var
        if btc_trend == "UP":            bonus += 5
        if funding < 0:                  bonus += 5
        if ind["rsi_div"] == "BULLISH_DIV": bonus += 7
        return min(95, int(wr + bonus))
    except: return 60

# ─── GPT KARAR ───
def gpt_karar(symbol, signal, ind, btc_trend, funding, long_pct, short_pct):
    if not OPENAI_KEY: return True, "GPT yok"
    try:
        sym = symbol.split("/")[0]
        prompt = f"""Kripto futures trading uzmanısın. ICT/Smart Money konseptini biliyorsun.

Coin: {sym}/USDT — Sinyal: {signal}
1h Trend: {ind['trend_1h']} | BTC: {btc_trend}
RSI: {ind['rsi']:.1f} | MACD: {ind['macd']} | BB: {ind['bb']}
RSI Diverjans: {ind['rsi_div']}
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
            headers={"Authorization": f"Bearer {OPENAI_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 80,
                  "temperature": 0.2,
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
            active.append({
                "symbol": symbol,
                "volume": ticker.get("quoteVolume", 0),
            })
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
    if ind["choch"] != "YOK":    ict_tag += "CHoCH✅ "
    if ind["fvg_icinde"]:         ict_tag += "FVG✅ "
    if ind["displacement"] != "YOK": ict_tag += "DISP✅"

    tg(
        f"📋 [PAPER] {sym} {signal}\n"
        f"Giriş: {price:.6f}\n"
        f"TP1:{tp1:.6f} TP2:{tp2:.6f} TP3:{tp3:.6f}\n"
        f"SL: {sl:.6f}\n"
        f"RSI:{ind['rsi']:.0f} Hacim:{ind['vol_ratio']:.1f}x\n"
        f"ICT: {ict_tag if ict_tag else 'Standart sinyal'}\n"
        f"BTC:{btc_trend} Seans:{seans}\n"
        f"🤖 {gpt_yorum}"
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
        "btc_trend":    pos.get("btc_trend", "NEUTRAL"),
        "funding_rate": pos.get("funding", 0),
        "long_pct":     pos.get("long_pct", 50),
        "short_pct":    pos.get("short_pct", 50),
        "sure_dk":      sure,
        "cikis_sebebi": reason,
        "seans":        pos.get("seans", ""),
        "fvg_var":      1 if ind.get("fvg_var") else 0,
        "fvg_icinde":   1 if ind.get("fvg_icinde") else 0,
        "fvg_yon":      ind.get("fvg_yon", "YOK"),
        "choch":        1 if ind.get("choch") != "YOK" else 0,
        "macd_durum":   ind.get("macd", ""),
        "bb_pozisyon":  ind.get("bb", ""),
        "mum_form":     ind.get("displacement", "YOK"),
        "paper":        1,
    })

    sym  = symbol.split("/")[0]
    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} [PAPER] {sym} KAPANDI\n{reason}\nPnL: {pnl:+.2f} USDT | {sure}dk")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(5)
        try:
            with pos_lock:
                syms = list(positions.keys())

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
                    close_paper(symbol, f"STOP LOSS", price); continue

                if not pos["tp1_done"] and pnl_pct >= TP1_PCT*100:
                    pos["tp1_done"] = True
                    tg(f"🟡 [PAPER] {symbol.split('/')[0]} TP1 +%{TP1_PCT*100:.1f} — breakeven")
                    continue

                if pos["tp1_done"] and pnl_pct <= 0:
                    close_paper(symbol, "BREAKEVEN", price); continue

                if pos["tp1_done"] and not pos["tp2_done"] and pnl_pct >= TP2_PCT*100:
                    pos["tp2_done"] = True
                    pos["trail_active"] = True
                    tg(f"🟡 [PAPER] {symbol.split('/')[0]} TP2 +%{TP2_PCT*100:.1f} — trailing")
                    continue

                if pos["tp2_done"] and pnl_pct >= TP3_PCT*100:
                    close_paper(symbol, "TP3 🎯", price); continue

                if pos["trail_active"] and pnl_pct <= max_pnl - TRAIL_PCT*100:
                    close_paper(symbol, f"TRAILING 🚀", price); continue

                if time.time() - pos["open_time"] > 20*60:
                    close_paper(symbol, "ZAMAN AŞIMI 20dk", price)

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
                time.sleep(10)
                continue

            btc_trend = get_btc_trend()
            seans     = get_seans()
            active    = scan_coins()

            if not active:
                time.sleep(SCAN_INTERVAL)
                continue

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
        r = supa.table("trades").select("*").eq("paper", 1).execute()
        data = r.data or []
        if not data:
            bot.send_message(msg.chat.id, "Henüz paper kayıt yok."); return
        toplam = len(data)
        kazan  = sum(1 for d in data if float(d.get("pnl",0)) > 0)
        kayip  = toplam - kazan
        net    = sum(float(d.get("pnl",0)) for d in data)

        # ICT analizi
        fvg_win = [d for d in data if d.get("fvg_icinde") == 1 and float(d.get("pnl",0)) > 0]
        fvg_top = [d for d in data if d.get("fvg_icinde") == 1]
        choch_win = [d for d in data if d.get("choch") == 1 and float(d.get("pnl",0)) > 0]
        choch_top = [d for d in data if d.get("choch") == 1]

        bot.send_message(msg.chat.id,
            f"📊 PAPER TRADİNG İSTATİSTİK\n\n"
            f"Toplam: {toplam} işlem\n"
            f"Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
            f"Kaybeden: {kayip} (%{kayip/toplam*100:.0f})\n"
            f"Net PnL: {net:+.2f} USDT\n\n"
            f"ICT Analiz:\n"
            f"FVG içinde: {len(fvg_top)} işlem, %{len(fvg_win)/max(len(fvg_top),1)*100:.0f} kazanç\n"
            f"CHoCH var: {len(choch_top)} işlem, %{len(choch_win)/max(len(choch_top),1)*100:.0f} kazanç"
        )
    except Exception as e:
        bot.send_message(msg.chat.id, f"Hata: {e}")

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
    print("📋 SADIK PAPER TRADING BOT v8 BAŞLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    print("[OK] Health | Manage | Scanner")
    tg(
        "📋 SADIK PAPER TRADING BOT v8\n\n"
        "⚠️ GERÇEK İŞLEM YOK\n\n"
        "Öğrenilecekler:\n"
        "✅ RSI, EMA, MACD, Bollinger Band\n"
        "✅ RSI Diverjansı\n"
        "✅ FVG (Fair Value Gap)\n"
        "✅ CHoCH (Market yapısı değişimi)\n"
        "✅ Displacement (Güçlü mum)\n"
        "✅ Likidite seviyeleri\n"
        "✅ BTC trend + Funding rate\n"
        "✅ Long/Short oranı\n"
        "✅ Seans bilgisi (Asya/Avrupa/ABD)\n"
        "✅ Sahte pump tespiti\n"
        "✅ GPT ICT analizi\n\n"
        f"Max {MAX_OPEN} eş zamanlı — günde 30+ işlem hedefi\n\n"
        "/durum /istatistik /kapat SOL /hepsikapat"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}"); time.sleep(5)
