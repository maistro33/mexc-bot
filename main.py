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

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
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
    m = ai_memory.get(f"{sym}_{d}", {"w":1,"l":1})
    return m["w"]/(m["w"]+m["l"])

def update_mem(sym, d, pnl):
    key = f"{sym}_{d}"
    if key not in ai_memory:
        ai_memory[key]={"w":1,"l":1}
    if pnl>0:
        ai_memory[key]["w"]+=1
    else:
        ai_memory[key]["l"]+=1

# ===== COINGLASS =====
def elite_data(sym):
    try:
        s = sym.replace("/USDT:USDT","").replace("/USDT","")
        url = f"https://open-api.coinglass.com/public/v2/open_interest?symbol={s}"
        headers = {"coinglassSecret": COINGLASS_API}
        r = requests.get(url, headers=headers, timeout=5).json()
        return 1 if r.get("data") else 0
    except:
        return 0

# ===== ORDERBOOK =====
def orderbook_imbalance(sym):
    ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not ob:
        return 0
    bids = sum(x[1] for x in ob["bids"])
    asks = sum(x[1] for x in ob["asks"])
    return (bids-asks)/(bids+asks) if bids+asks else 0

# ===== FILTERS =====
def elite_signal(sym):
    try:
        c = exchange.fetch_ohlcv(sym,"5m",limit=30)
        v = [x[5] for x in c]
        avg = sum(v[:-1])/len(v[:-1])
        return v[-1] > avg*2
    except:
        return False

def market_pressure(sym):
    try:
        c = exchange.fetch_ohlcv(sym,"5m",limit=20)
        cl = [x[4] for x in c]
        return abs(cl[-1]-cl[-5])/cl[-5]
    except:
        return 0

# ===== SYMBOLS =====
def get_symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t: return []
    f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1]>=AGGR_VOLUME]
    f.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in f[:TOP_COINS]]

# ===== AI ENTRY =====
def ai_decision(sym):
    try:
        c = exchange.fetch_ohlcv(sym,"5m",limit=30)
        cl = [x[4] for x in c]

        trend = cl[-1] > sum(cl[-10:])/10
        momentum = cl[-1] > cl[-3]
        ob = orderbook_imbalance(sym)

        if trend and momentum and ob>0:
            return "long"
        if not trend and not momentum and ob<0:
            return "short"
        return None
    except:
        return None

# ===== INIT =====
def init_trade(sym, entry, direction, qty):
    trade_state[sym] = {
        "entry": entry,
        "direction": direction,
        "risk": entry * 0.01,
        "tp1": False,
        "step": 0,
        "sl": None,
        "qty": qty
    }

# ===== SYNC POSITIONS =====
def sync_positions():
    active_trades.clear()
    positions = safe_api(lambda: exchange.fetch_positions())
    if not positions:
        return []

    open_pos = []
    for p in positions:
        if safe(p.get("contracts")) > 0:
            sym = p["symbol"]
            active_trades.add(sym)
            open_pos.append(p)

    return open_pos

# ===== ENGINE =====
def engine():
    global current_margin

    while True:
        try:
            positions = sync_positions()

            if len(positions) >= MAX_TRADES:
                time.sleep(3)
                continue

            for sym in get_symbols():

                if sym in active_trades:
                    continue

                direction = ai_decision(sym)
                if not direction:
                    continue

                if not elite_signal(sym):
                    continue

                if market_pressure(sym) < 0.002:
                    continue

                if get_conf(sym, direction) < 0.25:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])
                if price <= 0:
                    continue

                with lock:

                    lev = 10
                    if elite_data(sym):
                        lev = min(lev + 3, 20)

                    try: exchange.set_margin_mode("cross", sym)
                    except: pass

                    try: exchange.set_leverage(lev, sym)
                    except: pass

                    risk_cap = current_margin / (len(active_trades)+1)
                    qty = float(exchange.amount_to_precision(sym, (risk_cap * lev) / price))

                    order = safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction=="long" else "sell",
                        qty
                    ))

                    if not order:
                        continue

                    init_trade(sym, price, direction, qty)
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
            positions = sync_positions()

            for p in positions:

                qty = safe(p.get("contracts"))
                sym = p["symbol"]

                entry = safe(p["entryPrice"])
                price = safe(p.get("markPrice") or entry)
                pnl = safe(p.get("unrealizedPnl"))
                direction = "long" if p["side"]=="long" else "short"

                if sym not in trade_state:
                    init_trade(sym, entry, direction, qty)

                st = trade_state[sym]

                risk = st["risk"]
                r = abs(price-entry)/risk if risk>0 else 0

                close = False

                # ===== TP1 =====
                if not st["tp1"] and r >= 1:
                    part = qty * 0.4
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    ))
                    st["tp1"] = True
                    st["sl"] = entry

                # ===== STEP =====
                if st["tp1"]:
                    if r >= 1 and st["step"] < 1:
                        st["step"] = 1
                        st["sl"] = entry

                    elif r >= 1.5 and st["step"] < 2:
                        st["step"] = 2
                        st["sl"] = entry + risk if direction=="long" else entry - risk

                    elif r >= 2 and st["step"] < 3:
                        st["step"] = 3
                        st["sl"] = entry + 2*risk if direction=="long" else entry - 2*risk

                # ===== STOP =====
                if st["sl"]:
                    if direction=="long" and price <= st["sl"]:
                        close = True
                    elif direction=="short" and price >= st["sl"]:
                        close = True

                # ===== HARD STOP =====
                if pnl < -1.2:
                    close = True

                if close:
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))

                    update_mem(sym, direction, pnl)

                    active_trades.discard(sym)
                    trade_state.pop(sym, None)

                    current_margin = max(3, min(15, current_margin + (1 if pnl>0 else -1)))

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

bot.send_message(CHAT_ID, "🔥 ULTRA STABLE AI BOT AKTİF")
bot.infinity_polling()
