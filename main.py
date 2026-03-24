import os
import time
import ccxt
import telebot
import threading

print("🔥 PRO BOT STARTING...")

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 8
SCAN_DELAY = 0.5
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

# ===== SYMBOL FILTER (NO BIG COIN - ONLY PUMP) =====
def get_symbols():
    try:
        arr=[]
        tickers = exchange.fetch_tickers()

        for sym,d in tickers.items():

            if "USDT" not in sym or ":USDT" not in sym:
                continue

            price = safe(d.get("last"))
            vol = safe(d.get("quoteVolume"))
            ch = abs(safe(d.get("percentage")))

            # 🔥 TAM PROFESYONEL FİLTRE
            if not (
                price < 0.3 and      # küçük / yeni coin
                vol > 80000 and      # hacim var
                vol < 5000000 and    # büyük coin değil
                ch > 3               # pump var
            ):
                continue

            arr.append(sym)

        return arr[:50]

    except:
        return []

# ===== SIGNAL (PRO PUMP ENGINE) =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym,"5m",limit=12)

        if not m5 or len(m5) < 10:
            return None

        closes=[c[4] for c in m5]
        volumes=[c[5] for c in m5]

        move = (closes[-1]-closes[-2]) / closes[-2]

        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])

        # 🔥 güçlü hacim (whale)
        volume_spike = volumes[-1] > avg_vol * 1.8

        # 🔥 trend
        strong_up = closes[-1] > closes[-2] > closes[-3]
        strong_down = closes[-1] < closes[-2] < closes[-3]

        # 🔥 breakout
        breakout_up = closes[-1] > max(closes[-6:-1])
        breakout_down = closes[-1] < min(closes[-6:-1])

        # 🔥 fake breakout koruma
        body = abs(closes[-1] - closes[-2])
        if body / closes[-2] > 0.035:
            return None

        # 🔥 erken pump yakalama
        early_pump = closes[-1] > closes[-4]

        # 🔥 momentum filtresi
        momentum = closes[-1] - closes[-3]
        if abs(momentum) < closes[-3] * 0.002:
            return None

        # LONG
        if move > 0.0025 and volume_spike and (strong_up or breakout_up or early_pump):
            return "long"

        # SHORT
        if move < -0.0025 and volume_spike and (strong_down or breakout_down):
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

    # 🔥 hard stop
    if pnl < -0.5:
        return True

    if roe > st["max_roe"]:
        st["max_roe"] = roe

    max_usdt = (st["max_roe"]/100)*BASE_MARGIN

    lock = 0

    if max_usdt >= 1.0:
        lock = 0.8
    elif max_usdt >= 0.6:
        lock = 0.5
    elif max_usdt >= 0.3:
        lock = 0.3

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

        # 🔥 daha sık işlem
        if sym in cooldown and time.time()-cooldown[sym] < 5:
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

        bot.send_message(CHAT_ID,f"🚀 {sym} {dir}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
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

                time.sleep(0.02)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(5)

# ===== START =====
threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 PRO BOT AKTİF")

while True:
    time.sleep(60)
