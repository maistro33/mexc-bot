import os
import time
import ccxt
import telebot
import threading

print("🔥 ULTRA MEME PUMP BOT STARTING...")

LEV = 10
BASE_MARGIN = 1
MAX_POSITIONS = 4
SCAN_DELAY = 0.7
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

# ===== LOAD OPEN POSITIONS =====
def load_open_positions():
    try:
        for p in exchange.fetch_positions():
            if safe(p.get("contracts")) <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p.get("entryPrice"))
            direction = "long" if "long" in str(p).lower() else "short"

            trade_state[sym] = {
                "entry": entry,
                "direction": direction,
                "max_pnl": 0,
                "time": time.time()
            }

            active_symbols.add(sym)

        print("✅ Açık işlemler yüklendi")

    except Exception as e:
        print("LOAD ERROR:", e)

# ===== ULTRA FILTER =====
def get_symbols():
    try:
        arr=[]
        tickers = exchange.fetch_tickers()

        for sym,d in tickers.items():

            if "USDT" not in sym:
                continue

            s = sym.upper()

            # 🔴 büyük & eski coinleri kes
            if any(x in s for x in [
                "BTC","ETH","BNB","SOL","XRP","ADA","DOGE","DOT",
                "LTC","TRX","AVAX","MATIC","LINK","ATOM","ETC",
                "BCH","FIL","APT","ARB","OP","NEAR","ICP"
            ]):
                continue

            # 🔴 eski meme
            if "1000" in s:
                continue

            price = safe(d.get("last"))
            vol = safe(d.get("quoteVolume"))
            ch = abs(safe(d.get("percentage")))

            # 🔥 meme + yeni davranış
            if not (
                price < 0.5 and
                vol > 20000 and
                vol < 2000000 and
                ch > 2.5
            ):
                continue

            arr.append(sym)

        print("ULTRA COINS:", len(arr))
        return arr[:40]

    except:
        return []

# ===== SIGNAL (PUMP DETECTION) =====
def signal(sym):
    try:
        m1 = exchange.fetch_ohlcv(sym,"1m",limit=12)

        if not m1 or len(m1) < 6:
            return None

        closes=[c[4] for c in m1]
        volumes=[c[5] for c in m1]

        move = (closes[-1]-closes[-2]) / closes[-2]
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])

        volume_spike = volumes[-1] > avg_vol * 1.3
        momentum = closes[-1] - closes[-4]

        breakout_up = closes[-1] > max(closes[-4:-1])
        breakout_down = closes[-1] < min(closes[-4:-1])

        body = abs(closes[-1] - closes[-2])
        if body > closes[-2] * 0.06:
            return None

        if move > 0.0008 and volume_spike and breakout_up and momentum > 0:
            return "long"

        if move < -0.0008 and volume_spike and breakout_down and momentum < 0:
            return "short"

        return None

    except:
        return None

# ===== EXIT =====
def should_exit(sym, price, roe):
    st = trade_state[sym]
    pnl = (roe/100)*BASE_MARGIN
    age = time.time() - st["time"]

    # ⏱️ HOLD
    if age < 20:
        return False

    # 🔴 STOP
    if pnl <= -0.35:
        return True

    # 🔥 MAX
    if pnl > st.get("max_pnl",0):
        st["max_pnl"] = pnl

    # 🔁 TRAILING
    if st.get("max_pnl",0) > 0.05:
        if pnl < st["max_pnl"] - 0.05:
            return True

    # 💰 TP
    if pnl >= 0.10:
        return True

    return False

# ===== OPEN =====
def open_trade(sym,dir):
    try:
        if sym in active_symbols:
            return

        if sym in cooldown and time.time()-cooldown[sym] < 5:
            return

        price=exchange.fetch_ticker(sym)["last"]
        qty=(BASE_MARGIN*LEV)/price

        exchange.set_leverage(LEV, sym)

        side="buy" if dir=="long" else "sell"
        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={
            "entry":price,
            "direction":dir,
            "max_pnl":0,
            "time":time.time()
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

            time.sleep(1)

        except Exception as e:
            print("MANAGE ERROR:", e)
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

                time.sleep(0.02)

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(2)

# ===== START =====
load_open_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()
threading.Thread(target=bot.infinity_polling,daemon=True).start()

bot.send_message(CHAT_ID,"🔥 ULTRA MEME PUMP BOT AKTİF")

while True:
    time.sleep(60)
