import os
import time
import ccxt
import telebot
import threading
import random

# ===== CONFIG =====
LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 2

SCAN_DELAY = 8
SL_PERCENT = 0.012
MIN_HOLD = 35
FEE = 0.08

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

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
                "time": time.time()-60,
                "max_roe": 0
            }
    except Exception as e:
        print("SYNC:", e)

# ===== MEME FILTER =====
def get_symbols():
    try:
        arr=[]
        for sym,d in exchange.fetch_tickers().items():

            if "USDT" not in sym or ":USDT" not in sym:
                continue

            if any(x in sym for x in ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","TRX","AVAX","DOT","LINK"]):
                continue

            price=safe(d.get("last"))
            vol=safe(d.get("quoteVolume"))
            ch=safe(d.get("percentage"))

            if price>5 or vol<300000 or abs(ch)<2:
                continue

            arr.append((sym,abs(ch)+vol/1_000_000))

        arr.sort(key=lambda x:x[1],reverse=True)
        return [x[0] for x in arr[:15]]
    except:
        return []

# ===== SIGNAL (ÇİFT KORUMA) =====
def signal(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym,"5m",limit=6)
        h1 = exchange.fetch_ohlcv(sym,"1h",limit=20)

        closes=[c[4] for c in m5]
        h1c=[c[4] for c in h1]

        move=(closes[-1]-closes[-4])/closes[-4]

        trend_up = h1c[-1] > sum(h1c[-10:])/10
        trend_down = h1c[-1] < sum(h1c[-10:])/10

        recent_low = min(closes[-5:])
        recent_high = max(closes[-5:])

        near_bottom = closes[-1] <= recent_low * 1.01
        near_top = closes[-1] >= recent_high * 0.99

        # SHORT (dipte değil)
        if move > 0.03 and closes[-1] < closes[-2] and trend_down and not near_bottom:
            return "short"

        # LONG (tepede değil)
        if move < -0.03 and closes[-1] > closes[-2] and trend_up and not near_top:
            return "long"

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

# ===== EXIT (SABIRLI) =====
def should_exit(sym,price,roe):
    st=trade_state[sym]
    entry=st["entry"]
    d=st["direction"]

    # ⏳ erken çıkma
    if time.time()-st["time"]<35:
        return False

    # 🔴 HARD SL
    if d=="long" and price<=entry*(1-SL_PERCENT): return True
    if d=="short" and price>=entry*(1+SL_PERCENT): return True

    # 🔼 max takip
    if roe>st["max_roe"]:
        st["max_roe"]=roe

    maxr=st["max_roe"]

    # 🔥 gevşek trailing
    if maxr>3 and roe<maxr-1.8:
        return True

    if maxr>6 and roe<maxr-2.5:
        return True

    if maxr>10 and roe<maxr-3.5:
        return True

    return False

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        if sym in cooldown and time.time()-cooldown[sym]<180:
            return

        price=exchange.fetch_ticker(sym)["last"]
        q=format_qty(sym,price)
        if q<=0:
            return

        exchange.set_leverage(LEV,sym)
        side="buy" if dir=="long" else "sell"
        exchange.create_market_order(sym,side,q)

        trade_state[sym]={
            "entry":price,
            "direction":dir,
            "time":time.time(),
            "max_roe":0
        }

        cooldown[sym]=time.time()
        bot.send_message(CHAT_ID,f"🎯 {sym} {dir}")

    except Exception as e:
        print("OPEN:",e)

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
            print("MANAGE:",e)
            time.sleep(3)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            for sym in get_symbols():
                if len(trade_state)>=MAX_POSITIONS:
                    break

                d=signal(sym)
                if d:
                    open_trade(sym,d)

                time.sleep(0.3)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(10)

# ===== START =====
print("🔥 FINAL SABIRLI SNIPER")

sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 SABIRLI SNIPER AKTİF")

while True:
    time.sleep(60)
