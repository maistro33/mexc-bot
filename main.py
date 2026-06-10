# =========================================================
# SADIK SCALP AI PRO — INJ & ZEC
# Surekli islem acar, en iyi risk ayarlari
# =========================================================

import ccxt
import time
import os
import telebot
import threading
import pandas as pd

from supabase import create_client
from sklearn.ensemble import RandomForestClassifier

# =========================================================
# TELEGRAM
# =========================================================

TOKEN   = os.getenv("TELE_TOKEN")
CHAT_ID = int(os.getenv("MY_CHAT_ID"))

bot = telebot.TeleBot(TOKEN)

def tg(msg: str):
    """Guvenli mesaj gonder."""
    try:
        bot.send_message(CHAT_ID, msg)
    except Exception as e:
        print(f"[TG] {e}")

# =========================================================
# SUPABASE
# =========================================================

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# =========================================================
# EXCHANGE
# =========================================================

exchange = ccxt.bitget({
    "apiKey":   os.getenv("BITGET_API"),
    "secret":   os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})

# =========================================================
# SEMBOLLER — INJ ve ZEC surekli dongusel islem
# =========================================================

SYMBOLS = [
    "INJ/USDT:USDT",
    "ZEC/USDT:USDT",
]

TIMEFRAME       = "1m"
TREND_TIMEFRAME = "5m"

# =========================================================
# RISK AYARLARI (optimize edilmis)
# =========================================================

MARGIN   = 1     # her islem icin USDT marjin
LEVERAGE = 15     # kaldırac — INJ/ZEC volatil, 15x dengeli

# Kar hedefleri (USDT net)
TP1_USDT   = 0.40    # ilk TP bildirimi
MEGA_TP    = 2.00    # tam kapat

# Trailing stop
TRAIL_TRIGGER = 0.50   # bu kara ulasinca trailing baslar
TRAIL_STOP    = 0.30   # max_pnl'den bu kadar dusunce kapat

# Stop loss
STOP_LOSS = -0.20   # maksimum zarar

# Breakeven ve kilitler
BREAKEVEN_TRIGGER = 0.20   # bu kara ulasinca 0'in altinda kapat
LOCK1_TRIGGER     = 0.40   # bu karda en az 0.15 kilitle
LOCK1_FLOOR       = 0.15
LOCK2_TRIGGER     = 0.70   # bu karda en az 0.35 kilitle
LOCK2_FLOOR       = 0.35

# AI ve filtreler
MARKET_AI_MIN  = 60
MIN_MOMENTUM   = 0.10
MIN_VOLATILITY = 0.06
VOLUME_MIN     = 1.20

# =========================================================
# GLOBAL STATE — her sembol icin ayri
# =========================================================

positions: dict = {s: None for s in SYMBOLS}   # sembol -> pozisyon dict
ai_models: dict = {s: None for s in SYMBOLS}   # sembol -> model
locks:     dict = {s: False for s in SYMBOLS}
LAST_API   = 0

# =========================================================
# API SAFE
# =========================================================

def safe_api(func, *args, **kwargs):
    global LAST_API
    for _ in range(5):
        try:
            wait = 0.35 - (time.time() - LAST_API)
            if wait > 0:
                time.sleep(wait)
            LAST_API = time.time()
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[API] {e}")
            time.sleep(2)
    return None

# =========================================================
# AI — her sembol icin ayri model
# =========================================================

def load_ai_data(symbol: str):
    try:
        rows = supabase.table("trades").select("*").eq("symbol", symbol).execute()
        clean = []
        for r in rows.data or []:
            try:
                clean.append({
                    "momentum":     float(r.get("momentum")     or 0),
                    "volume_ratio": float(r.get("volume_ratio") or 0),
                    "volatility":   float(r.get("volatility")   or 0),
                    "move_1":       float(r.get("move_1")       or 0),
                    "move_3":       float(r.get("move_3")       or 0),
                    "result":       1 if float(r.get("pnl") or 0) > 0 else 0,
                })
            except Exception:
                pass
        return pd.DataFrame(clean) if clean else None
    except Exception as e:
        print(f"[AI LOAD] {e}")
        return None


def train_ai(symbol: str):
    global ai_models
    try:
        df = load_ai_data(symbol)
        if df is None or len(df) < 30:
            print(f"[AI] {symbol} veri yetersiz ({0 if df is None else len(df)})")
            return
        X = df[["momentum","volume_ratio","volatility","move_1","move_3"]]
        y = df["result"]
        m = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42)
        m.fit(X, y)
        ai_models[symbol] = m
        print(f"[AI] {symbol} egitildi ({len(df)} kayit)")
    except Exception as e:
        print(f"[AI TRAIN] {e}")


def ai_score(symbol: str, features: dict) -> int:
    model = ai_models.get(symbol)
    if model is None:
        return 70   # varsayilan
    try:
        df = pd.DataFrame([features])
        prob = model.predict_proba(df)[0]
        return int(max(prob) * 100)
    except Exception:
        return 70

# =========================================================
# VERI CEKME
# =========================================================

def get_data(symbol: str, tf: str):
    try:
        ohlcv = safe_api(exchange.fetch_ohlcv, symbol, timeframe=tf, limit=120)
        if not ohlcv:
            return None
        return pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
    except Exception as e:
        print(f"[DATA] {e}")
        return None

# =========================================================
# ANALİZ
# =========================================================

def analyze(symbol: str):
    try:
        df      = get_data(symbol, TIMEFRAME)
        df_trend = get_data(symbol, TREND_TIMEFRAME)
        if df is None or df_trend is None:
            return None

        closes  = df["c"]
        volumes = df["v"]
        tc      = df_trend["c"]

        ema9     = closes.ewm(span=9).mean()
        ema20    = closes.ewm(span=20).mean()
        t_ema20  = tc.ewm(span=20).mean()

        price   = closes.iloc[-1]
        move_1  = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
        move_3  = (closes.iloc[-1] - closes.iloc[-4]) / closes.iloc[-4] * 100
        momentum = abs(move_3)

        vol_avg  = volumes.rolling(20).mean().iloc[-1]
        if vol_avg <= 0:
            return None
        vol_ratio   = volumes.iloc[-1] / vol_avg
        volatility  = (df["h"].iloc[-1] - df["l"].iloc[-1]) / price * 100

        # Temel filtreler
        if volatility  < MIN_VOLATILITY: return None
        if vol_ratio   < VOLUME_MIN:     return None
        if momentum    < MIN_MOMENTUM:   return None

        feats = {
            "momentum":     momentum,
            "volume_ratio": vol_ratio,
            "volatility":   volatility,
            "move_1":       move_1,
            "move_3":       move_3,
        }

        score = ai_score(symbol, feats)

        # Fake breakout filtresi
        avg5 = closes.tail(5).mean()

        # LONG
        if (
            price > ema20.iloc[-1]
            and ema9.iloc[-1] > ema20.iloc[-1]
            and tc.iloc[-1] > t_ema20.iloc[-1]
            and move_1 > 0
            and price >= avg5           # fake breakout degil
        ):
            return {"signal": "LONG",  "score": score, **feats}

        # SHORT
        if (
            price < ema20.iloc[-1]
            and ema9.iloc[-1] < ema20.iloc[-1]
            and tc.iloc[-1] < t_ema20.iloc[-1]
            and move_1 < 0
            and price <= avg5
        ):
            return {"signal": "SHORT", "score": score, **feats}

        return None

    except Exception as e:
        print(f"[ANALYZE] {e}")
        return None

# =========================================================
# MULTI-AGENT KARAR
# =========================================================

def decision(result: dict) -> int:
    trend  = min(50 + (25 if result["momentum"]     >= 0.15 else 0)
                    + (25 if result["volume_ratio"]  >= 1.5  else 0), 100)
    market = min(50 + (25 if result["volume_ratio"]  >= 1.8  else 0)
                    + (25 if result["volatility"]    >= 0.10 else 0), 100)
    whale  = min(50 + (25 if result["volume_ratio"]  >= 2.0  else 0)
                    + (25 if result["momentum"]      >= 0.25 else 0), 100)
    return round((trend + market + whale) / 3)

# =========================================================
# POZISYON AC
# =========================================================

def open_trade(symbol: str, data: dict):
    global positions, locks

    if locks[symbol] or positions[symbol]:
        return

    locks[symbol] = True
    try:
        # Borsada zaten pozisyon var mi?
        if get_real_size(symbol) > 0:
            return

        side = "buy" if data["signal"] == "LONG" else "sell"

        safe_api(exchange.set_leverage, LEVERAGE, symbol)

        ticker = safe_api(exchange.fetch_ticker, symbol)
        if not ticker:
            return

        price  = ticker["last"]
        amount = float(exchange.amount_to_precision(
            symbol, (MARGIN * LEVERAGE) / price
        ))

        order = safe_api(exchange.create_market_order, symbol, side, amount)
        if not order:
            return

        entry = float(order.get("average") or price)

        positions[symbol] = {
            "type":      data["signal"],
            "entry":     entry,
            "max_pnl":   0,
            "tp1_done":  False,
            "open_time": time.time(),
            "ai_score":  data["score"],
            "features":  {k: data[k] for k in
                          ["momentum","volume_ratio","volatility","move_1","move_3"]},
        }

        sym_short = symbol.split("/")[0]
        tg(
            f"🚀 {sym_short} ACILDI\n"
            f"Yon: {data['signal']}\n"
            f"AI: %{data['score']}\n"
            f"Giris: {round(entry, 4)}\n"
            f"Kaldırac: {LEVERAGE}X"
        )

    except Exception as e:
        print(f"[OPEN] {e}")
    finally:
        locks[symbol] = False

# =========================================================
# KAYIT
# =========================================================

def save_memory(symbol: str, pnl: float):
    try:
        pos = positions[symbol]
        if not pos:
            return
        f = pos["features"]
        supabase.table("trades").insert({
            "symbol":       symbol,
            "signal":       pos["type"],
            "momentum":     f["momentum"],
            "volume_ratio": f["volume_ratio"],
            "volatility":   f["volatility"],
            "move_1":       f["move_1"],
            "move_3":       f["move_3"],
            "pnl":          pnl,
            "ai_score":     pos["ai_score"],
        }).execute()
    except Exception as e:
        print(f"[SAVE] {e}")

# =========================================================
# POZISYON KAPAT
# =========================================================

def close_trade(symbol: str, reason: str):
    global positions

    pos = positions[symbol]
    if not pos:
        return

    try:
        side = "sell" if pos["type"] == "LONG" else "buy"
        size = get_real_size(symbol)
        if size > 0:
            safe_api(exchange.create_market_order, symbol, side, size,
                     params={"reduceOnly": True})

        ticker = safe_api(exchange.fetch_ticker, symbol)
        pnl    = 0.0
        if ticker:
            cp = ticker["last"]
            if pos["type"] == "LONG":
                pnl_pct = (cp - pos["entry"]) / pos["entry"] * 100
            else:
                pnl_pct = (pos["entry"] - cp) / pos["entry"] * 100
            pnl = pnl_pct / 100 * (MARGIN * LEVERAGE)

        save_memory(symbol, pnl)
        train_ai(symbol)

        sym_short = symbol.split("/")[0]
        icon = "🟢" if pnl >= 0 else "🔴"
        sign = "+" if pnl >= 0 else ""
        tg(
            f"{icon} {sym_short} KAPANDI\n"
            f"Sebep: {reason}\n"
            f"PnL: {sign}{round(pnl, 2)} USDT"
        )

    except Exception as e:
        print(f"[CLOSE] {e}")

    positions[symbol] = None

# =========================================================
# GERCEK POZISYON BUYUKLUGU
# =========================================================

def get_real_size(symbol: str) -> float:
    try:
        ps = safe_api(exchange.fetch_positions, [symbol])
        if not ps:
            return 0
        for p in ps:
            sz = abs(float(p.get("contracts") or p.get("size") or 0))
            if sz > 0:
                return sz
    except Exception as e:
        print(f"[SIZE] {e}")
    return 0

# =========================================================
# POZISYON YONETICI — her sembol icin ayri thread
# =========================================================

def manage(symbol: str):
    global positions

    while True:
        try:
            pos = positions[symbol]

            if not pos:
                time.sleep(3)
                continue

            # Manuel kapatma kontrolu
            if get_real_size(symbol) <= 0:
                save_memory(symbol, 0)
                train_ai(symbol)
                tg(f"⚠️ {symbol.split('/')[0]} MANUEL KAPATILDI")
                positions[symbol] = None
                time.sleep(2)
                continue

            ticker = safe_api(exchange.fetch_ticker, symbol)
            if not ticker:
                time.sleep(2)
                continue

            price = ticker["last"]

            if pos["type"] == "LONG":
                pnl_pct = (price - pos["entry"]) / pos["entry"] * 100
            else:
                pnl_pct = (pos["entry"] - price) / pos["entry"] * 100

            pnl     = pnl_pct / 100 * (MARGIN * LEVERAGE)
            max_pnl = pos["max_pnl"]

            if pnl > max_pnl:
                pos["max_pnl"] = pnl
                max_pnl = pnl

            # ── STOP LOSS ──────────────────────────────
            if pnl <= STOP_LOSS:
                close_trade(symbol, "STOP LOSS")
                continue

            # ── BREAKEVEN ─────────────────────────────
            if max_pnl >= BREAKEVEN_TRIGGER and pnl <= 0:
                close_trade(symbol, "BREAKEVEN KORUMA")
                continue

            # ── KAR KİLİTLEME 1 ───────────────────────
            if max_pnl >= LOCK1_TRIGGER and pnl <= LOCK1_FLOOR:
                close_trade(symbol, f"KAR KİLİT {LOCK1_FLOOR} USDT")
                continue

            # ── KAR KİLİTLEME 2 ───────────────────────
            if max_pnl >= LOCK2_TRIGGER and pnl <= LOCK2_FLOOR:
                close_trade(symbol, f"KAR KİLİT {LOCK2_FLOOR} USDT")
                continue

            # ── TP1 BİLDİRİMİ ─────────────────────────
            if pnl >= TP1_USDT and not pos["tp1_done"]:
                pos["tp1_done"] = True
                tg(f"✅ {symbol.split('/')[0]} TP1\nKar: +{round(pnl,2)} USDT")

            # ── TRAILING STOP ──────────────────────────
            if max_pnl >= TRAIL_TRIGGER and pnl <= TRAIL_STOP:
                close_trade(symbol, "TRAILING STOP")
                continue

            # ── MEGA TP ────────────────────────────────
            if pnl >= MEGA_TP:
                close_trade(symbol, "MEGA TP 🎯")
                continue

            time.sleep(3)

        except Exception as e:
            print(f"[MANAGE {symbol}] {e}")
            time.sleep(5)

# =========================================================
# TARAYICI — her sembol icin ayri thread
# =========================================================

def scanner(symbol: str):
    sym_short = symbol.split("/")[0]

    while True:
        try:
            if positions[symbol]:
                time.sleep(5)
                continue

            result = analyze(symbol)

            if not result:
                time.sleep(8)
                continue

            # AI filtresi
            if result["score"] < MARKET_AI_MIN:
                time.sleep(5)
                continue

            # Multi-agent karar
            final = decision(result)

            tg(
                f"🧠 {sym_short} SİNYAL\n"
                f"Yon: {result['signal']}\n"
                f"AI: %{result['score']}\n"
                f"Agent: %{final}\n"
                f"Momentum: {round(result['momentum'],2)}\n"
                f"Hacim: {round(result['volume_ratio'],2)}X\n"
                f"Volatilite: {round(result['volatility'],2)}%"
            )

            if final >= 70:
                open_trade(symbol, result)

            time.sleep(10)

        except Exception as e:
            print(f"[SCANNER {symbol}] {e}")
            time.sleep(5)

# =========================================================
# BASLANGIC
# =========================================================

# Her sembol icin AI egit
for sym in SYMBOLS:
    train_ai(sym)

# Her sembol icin scanner + manager thread
for sym in SYMBOLS:
    threading.Thread(target=scanner, args=(sym,), daemon=True).start()
    threading.Thread(target=manage,  args=(sym,), daemon=True).start()

tg(
    "🚀 SADIK SCALP AI BASLADI\n\n"
    "Semboller: INJ + ZEC\n"
    f"Kaldırac: {LEVERAGE}X\n"
    f"Marjin: {MARGIN} USDT\n"
    f"TP1: +{TP1_USDT} USDT\n"
    f"Mega TP: +{MEGA_TP} USDT\n"
    f"Stop: {STOP_LOSS} USDT\n"
    "AI: AKTIF"
)

# Polling
while True:
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as e:
        print(f"[POLLING] {e}")
        time.sleep(5)
