import os, time, ccxt, telebot
import pandas as pd
import numpy as np

# ===== TELEGRAM =====
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TOKEN) if TOKEN else None

def send(msg):
    try:
        if bot and CHAT_ID:
            bot.send_message(CHAT_ID, msg, parse_mode="HTML")
        else:
            print(msg)
    except:
        print(msg)

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ===== MULTI COIN =====
BLACKLIST = ["BTC/USDT:USDT","ETH/USDT:USDT","XRP/USDT:USDT"]

def get_symbols():
    try:
        t = exchange.fetch_tickers()
        pairs = [(s,x["quoteVolume"]) for s,x in t.items()
                 if ":USDT" in s and s not in BLACKLIST and x["quoteVolume"]]

        pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in pairs[:20]]
    except:
        return ["BTC/USDT:USDT"]

# ===== RSI =====
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# ===== DATA =====
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        if not ohlcv:
            return None

        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        if len(df) < 20:
            return None

        df["ema"] = df["c"].ewm(span=20).mean()
        df["rsi"] = compute_rsi(df["c"])

        return df
    except:
        return None

# ===== 🐋 WHALE =====
def whale_signal(sym, df):
    try:
        ob = exchange.fetch_order_book(sym, limit=20)

        bids = sum([b[1] for b in ob["bids"]])
        asks = sum([a[1] for a in ob["asks"]])

        ratio = bids / (asks + 1e-9)

        # volume spike
        vol_spike = df["v"].iloc[-1] > df["v"].iloc[-3:].mean() * 2

        if ratio > 1.2 and vol_spike:
            return "BUY"
        elif ratio < 0.8 and vol_spike:
            return "SELL"
        else:
            return "NEUTRAL"
    except:
        return "NEUTRAL"

# ===== AI ANALYZE =====
def analyze(sym, df):
    try:
        last = df.iloc[-1]

        trend_up = last["c"] > last["ema"]
        rsi = last["rsi"]

        if trend_up and rsi < 70:
            signal = "LONG"
        elif not trend_up and rsi > 30:
            signal = "SHORT"
        else:
            return None, None, None

        whale = whale_signal(sym, df)

        # 🐋 FILTER
        if signal == "LONG" and whale != "BUY":
            return None, None, None

        if signal == "SHORT" and whale != "SELL":
            return None, None, None

        volatility = (last["h"] - last["l"]) / last["c"]
        confidence = volatility * 10000

        # whale boost
        if whale != "NEUTRAL":
            confidence += 5

        return signal, float(last["c"]), confidence

    except:
        return None, None, None

# ===== TRADE STATE =====
last_signal = {}
positions = []

# ===== OPEN TRADE =====
def open_trade(sym, signal, price, conf):
    positions.append({
        "sym": sym,
        "side": signal,
        "entry": price,
        "peak": 0,
        "tp1_hit": False
    })

    send(f"""
💀 <b>AI + WHALE TRADE</b>

📊 {sym}
📈 {signal}
💰 {round(price,4)}

🐋 Onaylandı
📊 Güç: %{round(conf,2)}

🎯 TP1: {round(price*1.01,4)}
🛑 SL: {round(price*0.99,4)}
""")

# ===== TRADE MANAGEMENT =====
def manage_positions():
    for pos in positions[:]:
        price = exchange.fetch_ticker(pos["sym"])["last"]
        entry = pos["entry"]

        pnl = ((price - entry) / entry) * 100 if pos["side"] == "LONG" \
            else ((entry - price) / entry) * 100

        pos["peak"] = max(pos["peak"], pnl)

        if not pos["tp1_hit"] and pnl > 1:
            pos["tp1_hit"] = True
            send(f"🎯 TP1 {pos['sym']} → %{round(pnl,2)}")

        if not pos["tp1_hit"] and pnl < -1:
            send(f"❌ SL {pos['sym']} → %{round(pnl,2)}")
            positions.remove(pos)
            continue

        if pos["tp1_hit"] and pnl < pos["peak"] - 0.5:
            send(f"📊 EXIT {pos['sym']} → %{round(pnl,2)}")
            positions.remove(pos)

# ===== TRADE CHECK =====
def check_trade(sym, signal, price, conf):
    if signal is None or conf < 5:
        return

    if sym in last_signal and last_signal[sym] == signal:
        return

    last_signal[sym] = signal

    if not any(p["sym"] == sym for p in positions):
        open_trade(sym, signal, price, conf)

# ===== MAIN =====
def run():
    send("💀 AI + WHALE AKTİF")

    while True:
        try:
            manage_positions()

            for sym in get_symbols():
                df = get_data(sym)
                if df is None:
                    continue

                signal, price, conf = analyze(sym, df)
                if signal is None:
                    continue

                print("🔍", sym, signal, conf)

                check_trade(sym, signal, price, conf)

                time.sleep(1)

            time.sleep(5)

        except Exception as e:
            print("ERR:", e)
            time.sleep(5)

run()
