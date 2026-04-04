import os
import time
import ccxt
import telebot
import threading
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
LEVERAGE = 7
MARGIN = 5
TOP_COINS = 50
MAX_TRADES = 1

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# 💣 CRITICAL FIX BURADA
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {
        "defaultType": "swap",
        "createMarketBuyOrderRequiresPrice": False  # 🔥 FIX
    },
    "enableRateLimit": True,
    "timeout": 20000
})

exchange.load_markets()

active_trades = set()
trade_state = {}
lock = threading.Lock()

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    try: return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except: return []

# ===== AI =====
def ai_decision(sym, score, ob):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Score:{score} OB:{ob}. ONLY answer LONG SHORT or SKIP"
            }],
            temperature=0
        )

        d = res.choices[0].message.content.strip().upper()

        if "LONG" in d:
            return "LONG"
        if "SHORT" in d:
            return "SHORT"

        return "SKIP"

    except:
        return "SKIP"

# ===== MARKET =====
def get_symbols():
    try:
        t = exchange.fetch_tickers()
        f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
        f = [x for x in f if x[1] >= AGGR_VOLUME]
        f.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in f[:TOP_COINS]]
    except:
        return []

def volume_spike(sym):
    c = get_candles(sym, "5m", 20)
    if len(c) < 10:
        return False
    v = [x[5] for x in c]
    return v[-1] > (sum(v[:-1]) / len(v[:-1])) * 1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym, 10)
        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"])
        return (bids - asks)/(bids + asks) if bids+asks else 0
    except:
        return 0

def score(sym):
    s = 0
    if volume_spike(sym): s += 2
    ob = orderbook_imbalance(sym)
    if abs(ob) > 0.1: s += 2
    return s

# ===== ENTRY =====
def engine():
    while True:
        try:
            for sym in get_symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                sc = score(sym)
                if sc < 2:
                    continue

                ob = orderbook_imbalance(sym)
                ai = ai_decision(sym, sc, ob)

                # 🔥 FALLBACK (ASLA DURMAZ)
                if ai == "SKIP":
                    direction = "long" if ob > 0 else "short"
                else:
                    direction = "long" if ai == "LONG" else "short"

                with lock:
                    price = safe(exchange.fetch_ticker(sym)["last"])
                    if price <= 0:
                        continue

                    qty = float(exchange.amount_to_precision(sym, (MARGIN * LEVERAGE) / price))

                    clean_sym = sym.replace(":USDT", "")

                    print("ORDER:", clean_sym, direction, qty)

                    order = exchange.create_market_order(
                        clean_sym,
                        "buy" if direction=="long" else "sell",
                        qty
                    )

                    if not order:
                        continue

                    trade_state[sym] = {
                        "entry": price,
                        "time": time.time()
                    }

                    active_trades.add(sym)

                    bot.send_message(CHAT_ID, f"🤖 {clean_sym} {direction}")
                    break

            time.sleep(8)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for p in exchange.fetch_positions():

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                clean_sym = sym.replace(":USDT", "")

                if sym not in trade_state:
                    continue

                pnl = safe(p.get("unrealizedPnl"))
                direction = "long" if p.get("side")=="long" else "short"

                if pnl < -1 or pnl > 2:

                    exchange.create_market_order(
                        clean_sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )

                    trade_state.pop(sym, None)
                    active_trades.discard(sym)

                    bot.send_message(CHAT_ID, f"❌ {clean_sym} {round(pnl,2)}")

            time.sleep(6)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL PRO AI BOT AKTİF")
bot.infinity_polling()
