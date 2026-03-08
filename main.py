import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone, timedelta

# ================= SETTINGS =================

LEV = 10
MARGIN = 2

MAX_DAILY_TRADES = 6
MAX_POSITIONS = 4

TP1_PCT = 0.008
TP2_PCT = 0.016
TRAIL_GAP = 0.012

TP1_RATIO = 0.30
TP2_RATIO = 0.40

BREAKEVEN_BUFFER = 0.0015

COOLDOWN_MIN = 60

MIN_VOLUME = 5_000_000
MAX_SPREAD = 0.003

# ================= COINS =================

SYMBOLS = [
"INJ/USDT:USDT","SEI/USDT:USDT","SUI/USDT:USDT","APT/USDT:USDT",
"TIA/USDT:USDT","PYTH/USDT:USDT","AVAX/USDT:USDT","DOT/USDT:USDT",
"ATOM/USDT:USDT","NEAR/USDT:USDT","ARB/USDT:USDT","OP/USDT:USDT",
"IMX/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","GRT/USDT:USDT",
"GALA/USDT:USDT","ALGO/USDT:USDT","KAS/USDT:USDT","JASMY/USDT:USDT",
"PEPE/USDT:USDT","FLOKI/USDT:USDT","BOME/USDT:USDT","WIF/USDT:USDT"
]

# ================= TELEGRAM =================

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ================= EXCHANGE =================

exchange = ccxt.bitget({
"apiKey": os.getenv("BITGET_API"),
"secret": os.getenv("BITGET_SEC"),
"password": os.getenv("BITGET_PASS"),
"options": {"defaultType": "swap"},
"enableRateLimit": True
})

# ================= STATE =================

trade_state = {}
cooldown = {}

daily_trades = 0
current_day = datetime.now(timezone.utc).day

# ================= EMA =================

def ema(values, period):

    k = 2/(period+1)
    ema_val = values[0]

    for price in values[1:]:
        ema_val = price*k + ema_val*(1-k)

    return ema_val

# ================= HELPERS =================

def safe(x):
    try:
        return float(x)
    except:
        return 0

# ================= BTC TREND =================

def btc_trend():

    try:

        btc = exchange.fetch_ohlcv("BTC/USDT:USDT","1h",limit=50)

        closes=[c[4] for c in btc]

        ema_val = ema(closes,50)

        if closes[-1] > ema_val:
            return "bull"
        else:
            return "bear"

    except:
        return "neutral"

# ================= ATR =================

def atr_filter(sym):

    try:

        candles=exchange.fetch_ohlcv(sym,"15m",limit=20)

        ranges=[c[2]-c[3] for c in candles]

        atr=sum(ranges)/len(ranges)

        price=candles[-1][4]

        if atr/price > 0.004:
            return True

        return False

    except:
        return False

# ================= ORDERBOOK =================

def orderbook_pressure(sym):

    try:

        book=exchange.fetch_order_book(sym,limit=20)

        bids=sum([b[1] for b in book["bids"]])
        asks=sum([a[1] for a in book["asks"]])

        if bids==0 or asks==0:
            return None

        ratio=bids/asks

        if ratio>1.4:
            return "long"

        if ratio<0.7:
            return "short"

        return None

    except:
        return None

# ================= TREND =================

def trend_direction(sym):

    try:

        h4=exchange.fetch_ohlcv(sym,"4h",limit=60)

        closes=[c[4] for c in h4]

        ema_val=ema(closes[-50:],50)

        if closes[-1]>ema_val:
            return "long"

        if closes[-1]<ema_val:
            return "short"

    except:
        return None

# ================= RETEST =================

def retest(sym,direction):

    try:

        h1=exchange.fetch_ohlcv(sym,"1h",limit=20)

        highs=[c[2] for c in h1]
        lows=[c[3] for c in h1]

        if direction=="long":
            return lows[-1] <= min(lows[-5:-1])
        else:
            return highs[-1] >= max(highs[-5:-1])

    except:
        return False

# ================= ENTRY =================

def open_trade(sym,direction):

    global daily_trades

    try:

        ticker=exchange.fetch_ticker(sym)

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]

        if spread > MAX_SPREAD:
            return

        price=ticker["last"]

        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)

        side="buy" if direction=="long" else "sell"

        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={"entry":price,"direction":direction,"tp1":False,"tp2":False,"extreme":price}

        cooldown[sym]=datetime.now()+timedelta(minutes=COOLDOWN_MIN)

        daily_trades+=1

        bot.send_message(CHAT_ID,f"🚀 {sym} {direction}")

    except Exception as e:
        print("ENTRY ERROR",e)

# ================= MANAGE =================

def manage():

    while True:

        try:

            if not trade_state:
                time.sleep(5)
                continue

            pos=exchange.fetch_positions()

            for p in pos:

                qty=safe(p.get("contracts"))

                if qty<=0:
                    continue

                sym=p["symbol"]

                if sym not in trade_state:
                    continue

                state=trade_state[sym]

                price=exchange.fetch_ticker(sym)["last"]

                entry=state["entry"]
                direction=state["direction"]

                side="sell" if direction=="long" else "buy"

                if direction=="long" and price>state["extreme"]:
                    state["extreme"]=price

                if direction=="short" and price<state["extreme"]:
                    state["extreme"]=price

                # TP1
                if not state["tp1"]:

                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,qty*TP1_RATIO,params={"reduceOnly":True})

                        state["tp1"]=True

                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                # BREAK EVEN
                elif state["tp1"] and not state["tp2"]:

                    if direction=="long" and price <= entry*(1+BREAKEVEN_BUFFER):

                        exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID,f"⚖️ BREAKEVEN {sym}")

                    if direction=="short" and price >= entry*(1-BREAKEVEN_BUFFER):

                        exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID,f"⚖️ BREAKEVEN {sym}")

                # TP2
                if not state["tp2"]:

                    if (direction=="long" and price>=entry*(1+TP2_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP2_PCT)):

                        exchange.create_market_order(sym,side,qty*TP2_RATIO,params={"reduceOnly":True})

                        state["tp2"]=True

                        bot.send_message(CHAT_ID,f"💰 TP2 {sym}")

                # TRAILING
                elif state["tp2"]:

                    if direction=="long":

                        if price <= state["extreme"]*(1-TRAIL_GAP):

                            exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

                    else:

                        if price >= state["extreme"]*(1+TRAIL_GAP):

                            exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

            time.sleep(3)

        except:
            time.sleep(3)

# ================= RUN =================

def run():

    global daily_trades

    while True:

        try:

            btc_state=btc_trend()

            for sym in SYMBOLS:

                if sym in trade_state:
                    continue

                if sym in cooldown and datetime.now() < cooldown[sym]:
                    continue

                if not atr_filter(sym):
                    continue

                pressure=orderbook_pressure(sym)

                direction=trend_direction(sym)

                if direction and retest(sym,direction):

                    if direction=="long" and btc_state=="bear":
                        continue

                    if pressure and pressure!=direction:
                        continue

                    open_trade(sym,direction)
                    break

            time.sleep(30)

        except:
            time.sleep(30)

# ================= START =================

print("BOT STARTING")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=run,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
