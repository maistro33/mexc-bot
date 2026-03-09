import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone, timedelta

LEV = 10
MARGIN = 2
MAX_DAILY_TRADES = 6
MAX_POSITIONS = 3

TP1_PCT = 0.010
TP2_PCT = 0.020
TRAIL_GAP = 0.012

TP1_RATIO = 0.30
TP2_RATIO = 0.40

COOLDOWN_MIN = 60

MIN_VOLUME = 5000000
MAX_SPREAD = 0.003

WHALE_TP1 = 0.012
WHALE_TP2 = 0.025
MAX_WHALE_TRADES = 2

SCAN_DELAY = 25

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
"apiKey": os.getenv("BITGET_API"),
"secret": os.getenv("BITGET_SEC"),
"password": "Berfin33",
"options": {"defaultType": "swap"},
"enableRateLimit": True
})

markets = exchange.load_markets()

SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s]

trade_state = {}
cooldown = {}

whale_state = {}
whale_daily = 0

daily_trades = 0
current_day = datetime.now(timezone.utc).day

def safe(x):
    try:
        return float(x)
    except:
        return 0

def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

def reset_daily():
    global daily_trades, whale_daily, current_day
    now_day = datetime.now(timezone.utc).day
    if now_day != current_day:
        daily_trades = 0
        whale_daily = 0
        current_day = now_day

def trend_direction(sym):
    try:
        candles = exchange.fetch_ohlcv(sym,"1h",limit=60)
        closes=[c[4] for c in candles]
        ema=sum(closes[-50:])/50
        if closes[-1] > ema:
            return "long"
        if closes[-1] < ema:
            return "short"
    except:
        return None

def breakout(sym):
    try:
        m15=exchange.fetch_ohlcv(sym,"15m",limit=15)
        highs=[c[2] for c in m15]
        lows=[c[3] for c in m15]
        closes=[c[4] for c in m15]
        resistance=max(highs[:-1])
        support=min(lows[:-1])
        if closes[-1] > resistance:
            return "long"
        if closes[-1] < support:
            return "short"
    except:
        return None

def volume_spike(sym):
    try:
        candles = exchange.fetch_ohlcv(sym,"5m",limit=6)
        vols=[c[5] for c in candles]
        avg=sum(vols[:-1])/5
        if vols[-1] > avg*2:
            return True
        return False
    except:
        return False

def orderbook_pressure(sym):
    try:
        book = exchange.fetch_order_book(sym,limit=20)
        bids=sum([b[1] for b in book["bids"]])
        asks=sum([a[1] for a in book["asks"]])
        if bids > asks*1.5:
            return "long"
        if asks > bids*1.5:
            return "short"
    except:
        return None

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
        trade_state[sym] = {"entry":price,"direction":direction,"tp1":False,"tp2":False,"extreme":price}
        cooldown[sym]=datetime.now()+timedelta(minutes=COOLDOWN_MIN)
        daily_trades+=1
        bot.send_message(CHAT_ID,f"🚀 NORMAL {sym} {direction}")
    except Exception as e:
        print(e)

def open_whale(sym,direction):
    global whale_daily
    try:
        if whale_daily >= MAX_WHALE_TRADES:
            return
        price=exchange.fetch_ticker(sym)["last"]
        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))
        exchange.set_leverage(LEV,sym)
        side="buy" if direction=="long" else "sell"
        exchange.create_market_order(sym,side,qty)
        whale_state[sym]={"entry":price,"direction":direction,"extreme":price}
        whale_daily+=1
        bot.send_message(CHAT_ID,f"🐋 WHALE {sym} {direction}")
    except:
        pass

def manage():
    while True:
        try:
            pos=exchange.fetch_positions()
            for p in pos:
                qty=safe(p.get("contracts"))
                if qty<=0:
                    continue
                sym=p["symbol"]
                price=exchange.fetch_ticker(sym)["last"]

                if sym in trade_state:
                    state=trade_state[sym]
                    entry=state["entry"]
                    direction=state["direction"]
                    side="sell" if direction=="long" else "buy"

                    if direction=="long" and price>state["extreme"]:
                        state["extreme"]=price
                    if direction=="short" and price<state["extreme"]:
                        state["extreme"]=price

                    if not state["tp1"]:
                        if (direction=="long" and price>=entry*(1+TP1_PCT)) or (direction=="short" and price<=entry*(1-TP1_PCT)):
                            exchange.create_market_order(sym,side,qty*TP1_RATIO,params={"reduceOnly":True})
                            state["tp1"]=True
                    elif not state["tp2"]:
                        if (direction=="long" and price>=entry*(1+TP2_PCT)) or (direction=="short" and price<=entry*(1-TP2_PCT)):
                            exchange.create_market_order(sym,side,qty*TP2_RATIO,params={"reduceOnly":True})
                            state["tp2"]=True
                    elif state["tp2"]:
                        if direction=="long":
                            if price <= state["extreme"]*(1-TRAIL_GAP):
                                exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                                trade_state.pop(sym)
                        else:
                            if price >= state["extreme"]*(1+TRAIL_GAP):
                                exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                                trade_state.pop(sym)
            time.sleep(5)
        except:
            time.sleep(5)

def normal_bot():
    global daily_trades
    while True:
        try:
            reset_daily()
            if daily_trades >= MAX_DAILY_TRADES:
                time.sleep(60)
                continue
            for sym in SYMBOLS:
                if sym in trade_state:
                    continue
                if sym in cooldown and datetime.now() < cooldown[sym]:
                    continue
                direction=trend_direction(sym)
                if not direction:
                    continue
                br=breakout(sym)
                if br==direction:
                    open_trade(sym,direction)
                    break
            time.sleep(SCAN_DELAY)
        except:
            time.sleep(30)

def whale_bot():
    while True:
        try:
            for sym in SYMBOLS:
                if sym in whale_state:
                    continue
                if volume_spike(sym):
                    pressure=orderbook_pressure(sym)
                    if pressure:
                        open_whale(sym,pressure)
                        break
            time.sleep(15)
        except:
            time.sleep(20)

print("BOT STARTING")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=normal_bot,daemon=True).start()
threading.Thread(target=whale_bot,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
