import os
import time
import ccxt
import telebot
import threading
import requests
from datetime import datetime, timedelta

LEV = 10
MARGIN = 2
MAX_POSITIONS = 5

TP1_PCT = 0.006
TP2_PCT = 0.012
TRAIL_GAP = 0.008

TP1_RATIO = 0.30
TP2_RATIO = 0.40

COOLDOWN_MIN = 60

MIN_VOLUME = 5000000
MAX_SPREAD = 0.003

SCAN_DELAY = 20

OI_SPIKE_THRESHOLD = 5.0
OI_DROP_THRESHOLD = -2.0

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

SYMBOLS = [s for s in markets if markets[s].get("swap") and "USDT" in s][:120]

trade_state = {}
cooldown = {}

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

def oi_change_percent():
    try:
        url = "https://open-api.coinglass.com/api/pro/v1/futures/openInterest/ohlc"
        headers = {
            "accept": "application/json",
            "coinglassSecret": os.getenv("COINGLASS_API")
        }
        r = requests.get(url, headers=headers, timeout=10).json()
        data = r.get("data", [])
        if not data:
            return 0
        oi_vals = [safe(x.get("openInterest",0)) for x in data[:2]]
        if len(oi_vals) < 2 or oi_vals[1] == 0:
            return 0
        return (oi_vals[0]-oi_vals[1])/oi_vals[1]*100
    except:
        return 0

def orderbook_pressure(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=20)
        bid_vol = sum(b[1] for b in ob["bids"])
        ask_vol = sum(a[1] for a in ob["asks"])
        if bid_vol > ask_vol*1.5:
            return "long"
        if ask_vol > bid_vol*1.5:
            return "short"
        return None
    except:
        return None

def volume_spike(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym,"5m",limit=6)
        vols=[c[5] for c in m5]
        avg=sum(vols[:-1])/5
        return vols[-1] > avg*2
    except:
        return False

def sync_existing():
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue
            sym = p["symbol"]
            entry = safe(p.get("entryPrice"))
            side = "long" if p.get("side") == "long" else "short"
            trade_state[sym] = {
                "entry": entry,
                "direction": side,
                "tp1": False,
                "tp2": False,
                "extreme": entry,
                "whale": False
            }
        print("Synced existing positions")
    except Exception as e:
        print("SYNC ERROR", e)

def open_trade(sym,direction,whale=False):
    try:
        if get_qty(sym)>0:
            return

        ticker = exchange.fetch_ticker(sym)

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]

        if spread>MAX_SPREAD:
            return

        price=ticker["last"]

        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)

        side="buy" if direction=="long" else "sell"

        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={
            "entry":price,
            "direction":direction,
            "tp1":False,
            "tp2":False,
            "extreme":price,
            "whale":whale
        }

        cooldown[sym]=datetime.now()+timedelta(minutes=COOLDOWN_MIN)

        if whale:
            bot.send_message(CHAT_ID,f"🐋 WHALE {sym} {direction}")
        else:
            bot.send_message(CHAT_ID,f"🚀 NORMAL {sym} {direction}")

    except Exception as e:
        print("ENTRY ERROR",e)

def manage():
    while True:
        try:
            pos=exchange.fetch_positions()
            oi_pct = oi_change_percent()

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

                if state.get("whale") and oi_pct <= OI_DROP_THRESHOLD:

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)

                    bot.send_message(CHAT_ID,f"🐋 WHALE EXIT {sym}")
                    continue

                if direction=="long" and price>state["extreme"]:
                    state["extreme"]=price

                if direction=="short" and price<state["extreme"]:
                    state["extreme"]=price

                if not state["tp1"]:

                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,qty*TP1_RATIO,params={"reduceOnly":True})

                        state["tp1"]=True

                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                elif not state["tp2"]:

                    if (direction=="long" and price>=entry*(1+TP2_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP2_PCT)):

                        exchange.create_market_order(sym,side,qty*TP2_RATIO,params={"reduceOnly":True})

                        state["tp2"]=True

                        bot.send_message(CHAT_ID,f"💰 TP2 {sym}")

                else:

                    if direction=="long":

                        if price<=state["extreme"]*(1-TRAIL_GAP):

                            exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

                    else:

                        if price>=state["extreme"]*(1+TRAIL_GAP):

                            exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

            time.sleep(3)

        except:
            time.sleep(5)

def run():

    while True:

        try:

            positions=exchange.fetch_positions()

            active=sum(1 for p in positions if safe(p.get("contracts"))>0)

            oi_pct = oi_change_percent()

            for sym in SYMBOLS:

                if active>=MAX_POSITIONS:
                    break

                if sym in cooldown and datetime.now()<cooldown[sym]:
                    continue

                if get_qty(sym)>0:
                    continue

                pressure=orderbook_pressure(sym)

                if oi_pct >= OI_SPIKE_THRESHOLD and pressure:

                    open_trade(sym,pressure,True)
                    break

                if pressure and volume_spike(sym):

                    open_trade(sym,pressure,False)
                    break

            time.sleep(SCAN_DELAY)

        except:
            time.sleep(20)

print("BOT STARTING")

sync_existing()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=run,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
