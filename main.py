import os
import time
import ccxt
import telebot
import threading
import requests
from openai import OpenAI

# ===== API =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
COINGLASS_API = os.getenv("COINGLASS_API_KEY")

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 100
MAX_TRADES = 2

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {
        "defaultType": "swap"
    },
    "enableRateLimit": True
})

exchange.load_markets()

# ===== STATE =====
active_trades = set()
trade_state = {}
ai_memory = {}

current_margin = 5

lock = threading.Lock()

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try: return call()
    except Exception as e:
        print("API ERROR:", e)
        return None

# ===== MEMORY =====
def get_conf(sym, d):
    k = f"{sym}_{d}"
    m = ai_memory.get(k, {"w":1,"l":1})
    return m["w"]/(m["w"]+m["l"])

def update_mem(sym, d, pnl):
    k = f"{sym}_{d}"
    if k not in ai_memory:
        ai_memory[k] = {"w":1,"l":1}
    if pnl > 0:
        ai_memory[k]["w"] += 1
    else:
        ai_memory[k]["l"] += 1

# ===== COINGLASS =====
def coinglass_oi(sym):
    try:
        s = sym.replace("/USDT:USDT","").replace("/USDT","")
        url = f"https://open-api.coinglass.com/public/v2/open_interest?symbol={s}"
        headers = {"coinglassSecret": COINGLASS_API}
        r = requests.get(url, headers=headers, timeout=5)
        data = r.json()
        if not data.get("data"):
            return 0
        return float(data["data"][0]["open_interest"])
    except:
        return 0

def elite_data(sym):
    oi = coinglass_oi(sym)
    return 1 if oi > 0 else 0

# ===== ORDERBOOK =====
def orderbook_imbalance(sym):
    ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not ob:
        return 0
    bids = sum(b[1] for b in ob["bids"])
    asks = sum(a[1] for a in ob["asks"])
    return (bids - asks)/(bids + asks) if bids+asks else 0

# ===== MARKET PRESSURE =====
def market_pressure(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [x[4] for x in c]
        volumes = [x[5] for x in c]

        pc = (closes[-1] - closes[-5]) / closes[-5]
        avg = sum(volumes[:-1]) / len(volumes[:-1])
        spike = volumes[-1] > avg * 1.8

        score = 0
        if spike and abs(pc) > 0.003:
            score += 2
        if pc > 0:
            score += 1
        if spike and abs(pc) < 0.001:
            score -= 2

        return score
    except:
        return 0

# ===== WHALE =====
def elite_signal(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=30)
        closes = [x[4] for x in c]
        volumes = [x[5] for x in c]

        avg = sum(volumes[:-1]) / len(volumes[:-1])
        whale = volumes[-1] > avg * 2.5

        move = abs(closes[-1] - closes[-2]) / closes[-2]
        burst = move > 0.004

        score = 0
        if whale: score += 2
        if burst: score += 1

        return score >= 1   # agresif
    except:
        return False

# ===== SYMBOLS =====
def get_symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t:
        return []

    f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1] >= AGGR_VOLUME]
    f.sort(key=lambda x: x[1], reverse=True)

    return [x[0] for x in f[:TOP_COINS]]

# ===== AI ENTRY =====
def ai_decision(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=30)
        closes = [x[4] for x in c]

        trend = closes[-1] > sum(closes[-10:]) / 10
        momentum = closes[-1] > closes[-3]
        ob = orderbook_imbalance(sym)

        if trend and momentum and ob > 0:
            return "long"

        if not trend and not momentum and ob < 0:
            return "short"

        return None
    except:
        return None

# ===== ENGINE =====
def engine():
    global current_margin

    while True:
        try:
            for sym in get_symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                direction = ai_decision(sym)
                if not direction:
                    continue

                # ===== FILTERS =====
                if not elite_signal(sym):
                    continue

                if market_pressure(sym) < 0:
                    continue

                cg = elite_data(sym)

                conf = get_conf(sym, direction)
                if conf < 0.25:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])
                if price <= 0:
                    continue

                with lock:

                    lev = 10

                    if cg >= 1:
                        lev = min(lev + 3, 20)

                    try:
                        exchange.set_margin_mode("cross", sym)
                    except:
                        pass

                    try:
                        exchange.set_leverage(lev, sym)
                    except:
                        pass

                    risk = current_margin / (len(active_trades) + 1)

                    qty = (risk * lev) / price
                    qty = float(exchange.amount_to_precision(sym, qty))

                    order = safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction == "long" else "sell",
                        qty
                    ))

                    if not order:
                        continue

                    trade_state[sym] = {
                        "direction": direction,
                        "entry": price,
                        "max": 0,
                        "trail": False
                    }

                    active_trades.add(sym)

                    bot.send_message(CHAT_ID, f"🚀 {sym} {direction} x{lev}")
                    break

            time.sleep(4)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
    global current_margin

    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(5)
                continue

            for p in positions:

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]

                if sym not in trade_state:
                    continue

                pnl = safe(p.get("unrealizedPnl"))
                direction = "long" if p["side"] == "long" else "short"

                st = trade_state[sym]

                if pnl > st["max"]:
                    st["max"] = pnl

                close = False

                if pnl < -3:
                    close = True

                elif pnl > 2:
                    st["trail"] = True
                    if pnl < st["max"] * 0.6:
                        close = True

                if close:
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))

                    update_mem(sym, direction, pnl)

                    active_trades.discard(sym)
                    trade_state.pop(sym, None)

                    if pnl > 0:
                        current_margin += 1
                    else:
                        current_margin -= 1

                    current_margin = max(3, min(15, current_margin))

                    bot.send_message(CHAT_ID, f"❌ {sym} {round(pnl,2)}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 ELITE AGGRESSIVE AI BOT AKTİF")
bot.infinity_polling()
