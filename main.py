import os
import time
import ccxt
import telebot
import threading

print("🔥 V10 TURBO STARTING...")

# ===== ENV =====
if not os.getenv("TELE_TOKEN") or not os.getenv("MY_CHAT_ID"):
    print("ENV ERROR")
    exit()

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 4

SCAN_DELAY = 2
FEE = 0.08

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = int(os.getenv("MY_CHAT_ID"))

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

trade_state = {}
cooldown = {}
active_symbols = set()

def safe(x):
    try: return float(x)
    except: return 0

# ===== SYNC =====
def sync_positions():
    try:
        for p in exchange.fetch_positions():
            if safe(p.get("contracts")) <= 0:
                continue

            sym = p["symbol"]

            trade_state[sym] = {
                "entry": safe(p["entryPrice"]),
                "direction": "long" if p["side"]=="long" else "short",
                "time": time.time(),
                "max_roe": 0,
                "last_lock": 0
            }

            active_symbols.add(sym)

    except Exception as e:
        print("SYNC ERROR:", e)

# ===== SYMBOLS =====
def get_symbols():
    try:
        arr=[]
        for sym,d in exchange.fetch_tickers().items():

            if "USDT" not in sym or ":USDT" not in sym:
                continue

            if any(x in sym for x in ["BTC","ETH","SOL","BNB","XRP","ADA"]):
                continue

            price=safe(d.get("last"))
            vol=safe(d.get("quoteVolume"))
            ch=safe(d.get("percentage"))

            if price > 2:
                continue

            if vol < 80000 or vol > 7000000:
                continue

            if abs(ch) < 0.8:
                continue

            arr.append(sym)

        return arr[:30]

    except:
        return []

# ===== SIGNAL (TURBO) =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym,"5m",limit=6)

        if not m5 or len(m5) < 6:
            return None

        closes=[c[4] for c in m5]
        volumes=[c[5] for c in m5]

        move = (closes[-1]-closes[-2]) / closes[-2]

        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
        volume_spike = volumes[-1] > avg_vol * 1.5

        trend_up = closes[-1] > closes[-2] > closes[-3]
        trend_down = closes[-1] < closes[-2] < closes[-3]

        if abs(move) > 0.12:
            return None

        if move > 0.015 and volume_spike and not trend_down:
            return "long"

        if move < -0.015 and volume_spike and not trend_up:
            return "short"

        return None

    except:
        return None

# ===== QTY =====
def format_qty(sym,price):
    try:
        raw=(BASE_MARGIN*LEV)/price
        return float(exchange.amount_to_precision(sym,raw))
    except:
        return 0

# ===== EXIT =====
def should_exit(sym, price, roe):
    st = trade_state[sym]

    pnl = (roe/100)*BASE_MARGIN

    if pnl < -0.5:
        return True

    if roe > st["max_roe"]:
        st["max_roe"] = roe

    max_usdt = (st["max_roe"]/100)*BASE_MARGIN

    lock = 0

    if max_usdt >= 1.0:
        lock = 0.7
    elif max_usdt >= 0.6:
        lock = 0.4
    elif max_usdt >= 0.3:
        lock = 0.15

    if lock > st["last_lock"]:
        st["last_lock"] = lock
        try:
            bot.send_message(CHAT_ID, f"🔒 {sym} lock {lock}$")
        except:
            pass

    if lock > 0 and pnl < lock:
        return True

    return False

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        if sym in active_symbols:
            return

        if sym in trade_state:
            return

        for p in exchange.fetch_positions():
            if p["symbol"] == sym and safe(p.get("contracts")) > 0:
                return

        if sym in cooldown and time.time()-cooldown[sym] < 60:
            return

        price=exchange.fetch_ticker(sym)["last"]
        qty=format_qty(sym,price)

        if qty <= 0:
            return

        exchange.set_leverage(LEV,sym)

        side="buy" if dir=="long" else "sell"
        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={
            "entry":price,
            "direction":dir,
            "time":time.time(),
            "max_roe":0,
            "last_lock":0
        }

        active_symbols.add(sym)
        cooldown[sym]=time.time()

        bot.send_message(CHAT_ID,f"🚀 TURBO {sym} {dir}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for p in exchange.fetch_positions():
                qty=safe(p.get("contracts"))
                if qty<=0:
                    continue

                sym=p["symbol"]

                if sym not in trade_state:
                    continue

                price=exchange.fetch_ticker(sym)["last"]
                entry=trade_state[sym]["entry"]
                d=trade_state[sym]["direction"]

                raw=((price-entry)/entry*100)*LEV if d=="long" else ((entry-price)/entry*100)*LEV
                roe=raw-FEE

                if should_exit(sym,price,roe):
                    side="sell" if d=="long" else "buy"
                    exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})

                    trade_state.pop(sym, None)
                    active_symbols.discard(sym)

                    bot.send_message(CHAT_ID,f"🏁 EXIT {sym} {roe:.2f}%")

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(3)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            for sym in get_symbols():

                if len(trade_state) >= MAX_POSITIONS:
                    break

                d=signal(sym)

                if d:
                    open_trade(sym,d)

                time.sleep(0.05)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)

# ===== START =====
sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 V10 TURBO AKTİF")

while True:
    time.sleep(60)
