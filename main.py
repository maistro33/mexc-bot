import os
import time
import ccxt
import telebot
import threading

print("🔥 FINAL SCALP BOT STARTING...")

LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 4
SCAN_DELAY = 0.3
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

# ===== COIN FILTER (BÜYÜKLER YOK) =====
def get_symbols():
    try:
        arr=[]
        tickers = exchange.fetch_tickers()

        for sym,d in tickers.items():

            if "USDT" not in sym:
                continue

            price = safe(d.get("last"))
            vol = safe(d.get("quoteVolume"))
            ch = abs(safe(d.get("percentage")))

            # 🔥 SADECE SCALP COIN
            if not (
                price < 1.0 and
                vol > 80000 and
                vol < 4000000 and
                ch > 1.5
            ):
                continue

            arr.append(sym)

        return arr[:60]

    except:
        return []

# ===== SCALP SIGNAL =====
def signal(sym):
    try:
        m1 = exchange.fetch_ohlcv(sym,"1m",limit=10)

        if not m1 or len(m1) < 5:
            return None

        closes=[c[4] for c in m1]
        volumes=[c[5] for c in m1]

        move = (closes[-1]-closes[-2]) / closes[-2]
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])

        volume_spike = volumes[-1] > avg_vol * 1.2

        momentum = closes[-1] - closes[-3]

        # ❌ büyük mum engel
        body = abs(closes[-1] - closes[-2])
        if body > closes[-2] * 0.04:
            return None

        if move > 0.001 and volume_spike and momentum > 0:
            return "long"

        if move < -0.001 and volume_spike and momentum < 0:
            return "short"

        return None

    except:
        return None

# ===== EXIT (USDT SCALP) =====
def should_exit(sym, price, roe):
    st = trade_state[sym]
    pnl = (roe/100)*BASE_MARGIN

    # 🔴 HARD STOP
    if pnl <= -0.50:
        return True

    # 🔒 KAR GARANTİ
    if pnl >= 0.25 and st.get("lock",0) < 0.20:
        st["lock"] = 0.20

    # 🔥 MAX TAKİP
    if pnl > st.get("max_pnl",0):
        st["max_pnl"] = pnl

    # 🔁 TRAILING
    if pnl >= 0.25:
        if pnl < st.get("max_pnl",0) - 0.10:
            return True

    # 🔒 LOCK
    if pnl < st.get("lock",0):
        return True

    return False

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        if sym in trade_state:
            return

        if sym in cooldown and time.time()-cooldown[sym] < 5:
            return

        price=exchange.fetch_ticker(sym)["last"]
        qty=(BASE_MARGIN*LEV)/price

        side="buy" if dir=="long" else "sell"
        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={
            "entry":price,
            "direction":dir,
            "lock":0,
            "max_pnl":0
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

                    trade_state.pop(sym, None)

                    bot.send_message(CHAT_ID,f"🏁 EXIT {sym} {roe:.2f}%")

            time.sleep(1)

        except:
            time.sleep(2)

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

                time.sleep(0.01)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(2)

# ===== START =====
threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 FINAL SCALP BOT AKTİF")

while True:
    time.sleep(60)
