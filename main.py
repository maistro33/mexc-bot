import os
import time
import ccxt
import telebot
import threading

print("🔥 FINAL BOT STARTING...")

# ===== ENV CHECK =====
if not os.getenv("TELE_TOKEN") or not os.getenv("MY_CHAT_ID"):
    print("❌ TELEGRAM ENV HATALI")
    exit()

if not os.getenv("BITGET_API") or not os.getenv("BITGET_SEC"):
    print("❌ API ENV HATALI")
    exit()

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 3

SCAN_DELAY = 3
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

            if price > 1.5:
                continue

            if vol < 120000 or vol > 5000000:
                continue

            if abs(ch) < 1:
                continue

            arr.append(sym)

        return arr[:25]

    except Exception as e:
        print("SYMBOL ERROR:", e)
        return []

# ===== SIGNAL (PUMP + FAKE FILTER) =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym,"5m",limit=6)

        if not m5 or len(m5) < 6:
            return None

        closes=[c[4] for c in m5]
        volumes=[c[5] for c in m5]

        move = (closes[-1]-closes[-2]) / closes[-2]

        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
        volume_spike = volumes[-1] > avg_vol * 2

        # fake pump filtre (çok dik spike engelle)
        if abs(move) > 0.08:
            return None

        if move > 0.02 and volume_spike:
            return "long"

        if move < -0.02 and volume_spike:
            return "short"

        return None

    except Exception as e:
        print("SIGNAL ERROR:", e)
        return None

# ===== QTY =====
def format_qty(sym,price):
    try:
        raw=(BASE_MARGIN*LEV)/price
        return float(exchange.amount_to_precision(sym,raw))
    except Exception as e:
        print("QTY ERROR:", e)
        return 0

# ===== EXIT =====
def should_exit(sym, price, roe):
    st = trade_state[sym]

    pnl_usdt = (roe / 100) * BASE_MARGIN

    # 🔴 HARD STOP
    if pnl_usdt < -0.5:
        return True

    if roe > st["max_roe"]:
        st["max_roe"] = roe

    maxr = st["max_roe"]
    max_usdt = (maxr / 100) * BASE_MARGIN

    lock = 0

    if max_usdt >= 1.0:
        lock = 0.7
    elif max_usdt >= 0.6:
        lock = 0.4
    elif max_usdt >= 0.3:
        lock = 0.15

    # 🔒 KİLİT MESAJ
    if lock > st["last_lock"]:
        st["last_lock"] = lock
        try:
            bot.send_message(CHAT_ID, f"🔒 {sym} profit lock {lock}$")
        except:
            pass

    if lock > 0 and pnl_usdt < lock:
        return True

    return False

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        # STATE kontrol
        if sym in trade_state:
            return

        # GERÇEK pozisyon kontrol
        for p in exchange.fetch_positions():
            if p["symbol"] == sym and safe(p.get("contracts")) > 0:
                return

        # cooldown
        if sym in cooldown and time.time()-cooldown[sym] < 120:
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

        cooldown[sym]=time.time()

        bot.send_message(CHAT_ID,f"🚀 {sym} {dir}")

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

                    trade_state.pop(sym)
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

                time.sleep(0.1)

            time.sleep(SCAN_DELAY)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(5)

# ===== START =====
sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 FINAL BOT AKTİF")

while True:
    time.sleep(60)
