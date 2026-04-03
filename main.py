import os
import time
import ccxt
import telebot
import threading
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

AGGR_VOLUME = 200_000
LEVERAGE = 7
MARGIN = 5
TOP_COINS = 120

ANTI_DUMP_PCT = 0.04
MAX_TRADES = 2

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000
})

exchange.load_markets()

active_trades = set()
trade_state = {}
lock = threading.Lock()

trade_history = []
MAX_HISTORY = 20

# ===== SAFE API =====
def safe_api(call, retries=3):
    for _ in range(retries):
        try:
            return call()
        except Exception as e:
            print("API ERROR:", e)
            time.sleep(2)
    return None

def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    return safe_api(lambda: exchange.fetch_ohlcv(sym, tf, limit=limit)) or []

def orderbook_imbalance(sym):
    ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not ob:
        return 0
    bids = sum(b[1] for b in ob["bids"])
    asks = sum(a[1] for a in ob["asks"])
    return (bids - asks)/(bids + asks) if bids+asks else 0

# ===== AI CHAT =====
def ai_chat(prompt):
    try:
        res = safe_api(lambda: client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.6
        ))
        if not res:
            return "AI cevap veremedi"
        return res.choices[0].message.content
    except:
        return "AI hata verdi"

# ===== ULTIMATE AI =====
def ai_decision(sym):
    try:
        h1 = get_candles(sym, "1h", 50)
        m5 = get_candles(sym, "5m", 30)

        if len(h1) < 30 or len(m5) < 20:
            return None

        closes1 = [c[4] for c in h1]
        closes5 = [c[4] for c in m5]

        trend = "UP" if closes1[-1] > sum(closes1[-20:])/20 else "DOWN"
        momentum = "UP" if closes5[-1] > closes5[-3] else "DOWN"

        volatility = abs(closes5[-1]-closes5[-2]) / closes5[-2]

        highs = [c[2] for c in m5]
        lows = [c[3] for c in m5]

        range_pct = (max(highs[-10:]) - min(lows[-10:])) / closes5[-1]

        ob = orderbook_imbalance(sym)

        recent_high = max(highs[-10:])
        recent_low = min(lows[-10:])

        fake_up = closes5[-1] > recent_high and closes5[-2] < recent_high
        fake_down = closes5[-1] < recent_low and closes5[-2] > recent_low

        last = m5[-1]
        body = abs(last[4] - last[1])
        wick_up = last[2] - max(last[4], last[1])
        wick_down = min(last[4], last[1]) - last[3]
        liquidity = wick_up > body*2 or wick_down > body*2

        trend_strength = abs(closes5[-1] - closes5[-5]) / closes5[-5]

        history_str = ",".join(trade_history[-10:])

        prompt = f"""
You are a professional trader.

Recent trades: {history_str}

Trend: {trend}
Momentum: {momentum}
Volatility: {volatility}
Range: {range_pct}
Orderbook: {ob}

FakeBreakUp: {fake_up}
FakeBreakDown: {fake_down}
LiquidityGrab: {liquidity}
TrendStrength: {trend_strength}

Answer:
ENTER_LONG
ENTER_SHORT
SKIP
"""

        res = safe_api(lambda: client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.2
        ))

        if not res:
            return None

        txt = res.choices[0].message.content.upper()

        if "ENTER_LONG" in txt:
            return "long"
        elif "ENTER_SHORT" in txt:
            return "short"

        return None

    except Exception as e:
        print("AI ERROR:", e)
        return None

def get_symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t:
        return []

    f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1] >= AGGR_VOLUME]
    f.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in f[:TOP_COINS]]

# ===== ANTI-DUMP =====
def anti_dump(sym, pnl):
    st = trade_state.get(sym)
    if not st:
        return False

    if time.time() - st["open_time"] < 60:
        return False

    if pnl > -0.3:
        return False

    c = get_candles(sym, "3m", 3)
    if len(c) < 3:
        return False

    change = abs(c[-1][4] - c[-3][4]) / c[-3][4]
    return change > ANTI_DUMP_PCT

# ===== ENTRY =====
def engine():
    while True:
        try:
            for sym in get_symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])

                if price > 200 or price < 0.001:
                    continue

                direction = ai_decision(sym)
                if not direction:
                    continue

                with lock:
                    if len(active_trades) >= MAX_TRADES:
                        break

                    market = exchange.market(sym)
                    min_qty = market['limits']['amount']['min'] or 0.001

                    raw_qty = (MARGIN * LEVERAGE) / price
                    qty = max(raw_qty, min_qty)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction=="long" else "sell",
                        qty
                    ))

                    sl = price * 0.98 if direction=="long" else price * 1.02

                    trade_state[sym] = {
                        "entry": price,
                        "sl": sl,
                        "risk": abs(price - sl),
                        "step": 0,
                        "direction": direction,
                        "open_time": time.time()
                    }

                    active_trades.add(sym)

                    analysis = ai_chat(f"Why enter {sym} {direction}? short aggressive style")

                    bot.send_message(CHAT_ID, f"""
🚀 TRADE

{sym}
Yön: {direction}

🧠 {analysis}
""")
                    break

            time.sleep(15)

        except Exception as e:
            print("ENTRY ERROR:", e)
            time.sleep(10)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(7)
                continue

            for p in positions:

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                st = trade_state[sym]
                entry = st["entry"]
                direction = st["direction"]

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])
                pnl = safe(p.get("unrealizedPnl"))

                if anti_dump(sym, pnl):
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    ))

                    trade_state.pop(sym,None)
                    active_trades.discard(sym)

                    bot.send_message(CHAT_ID, f"⚠️ ANTI-DUMP {sym}")
                    continue

                # AGGRESSIVE TP
                if pnl > 0.8:
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty*0.3,
                        params={"reduceOnly":True}
                    ))
                    bot.send_message(CHAT_ID, f"💰 QUICK TP {sym} {round(pnl,2)}")

                r = abs(price - entry) / st["risk"] if st["risk"] > 0 else 0

                if r >= 0.5 and st["step"] < 1:
                    st["step"] = 1
                    st["sl"] = entry

                elif r >= 1 and st["step"] < 2:
                    st["step"] = 2
                    st["sl"] = entry + st["risk"] if direction=="long" else entry - st["risk"]

                elif r >= 2 and st["step"] < 3:
                    st["step"] = 3
                    st["sl"] = entry + 2*st["risk"] if direction=="long" else entry - 2*st["risk"]

                if (direction=="long" and price <= st["sl"]) or (direction=="short" and price >= st["sl"]):
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    ))

                    trade_state.pop(sym,None)
                    active_trades.discard(sym)

                    yorum = ai_chat(f"Trade closed {sym}, pnl {pnl}, explain")

                    bot.send_message(CHAT_ID, f"""
❌ CLOSE

{sym}
PnL: {round(pnl,2)}

🧠 {yorum}
""")

            time.sleep(7)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(7)

# ===== TELEGRAM =====
@bot.message_handler(commands=['ai'])
def ai_cmd(msg):
    text = msg.text.replace("/ai","").strip()
    bot.send_message(CHAT_ID, ai_chat(text))

@bot.message_handler(commands=['durum'])
def durum(msg):
    bot.send_message(CHAT_ID, ai_chat("Short aggressive crypto market analysis"))

# ===== START =====
safe_api(lambda: exchange.fetch_balance())

bot.remove_webhook()
time.sleep(1)

load_positions()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 ULTIMATE AI BOT LIVE")
bot.infinity_polling()
