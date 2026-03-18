import os
import time
import ccxt
import telebot
import threading
import requests
import random

LEV = 10
MARGIN = 3

MAX_POSITIONS = 4
BALINA_LIMIT = 1

TP1_PCT = 0.006
STEP_PCT = 0.005
TP1_RATIO = 0.50

HARD_SL = 0.05

MIN_VOLUME = 2000000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

TIMEOUT = 21600

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
SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:200]

trade_state = {}
cooldown = {}
COOLDOWN_TIME = 1800


def safe(x):
    try:
        return float(x)
    except:
        return 0


def api_safe(func,*args):
    for _ in range(3):
        try:
            return func(*args)
        except:
            time.sleep(2)
    return None


def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0


def sync_positions():
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            side = "long" if p["side"] == "long" else "short"

            trade_state[sym] = {
                "entry": entry,
                "direction": side,
                "tp1": False,
                "step": 0,
                "start": time.time()
            }
    except:
        pass


def btc_trend():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT","1h",limit=50)
        closes=[c[4] for c in candles]
        ema=sum(closes[-20:])/20
        if closes[-1] > ema:
            return "bull"
        return "bear"
    except:
        return "neutral"


def volatility_filter(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=10)
        ranges=[c[2]-c[3] for c in candles]
        avg=sum(ranges)/len(ranges)
        return avg > candles[-1][4]*0.002
    except:
        return False


def volume_spike(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=6)
        vols=[c[5] for c in candles]
        avg=sum(vols[:-1])/5
        return vols[-1] > avg*1.3
    except:
        return False


def orderbook_pressure(sym):
    try:
        ob=exchange.fetch_order_book(sym,limit=20)
        bid=sum([b[1] for b in ob["bids"]])
        ask=sum([a[1] for a in ob["asks"]])
        if bid > ask*1.5:
            return "long"
        if ask > bid*1.5:
            return "short"
        return None
    except:
        return None


def fake_breakout(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=5)
        highs=[c[2] for c in candles]
        lows=[c[3] for c in candles]
        last=candles[-1]

        if last[4] < highs[-2] and last[2] > highs[-2]:
            return True

        if last[4] > lows[-2] and last[3] < lows[-2]:
            return True

        return False
    except:
        return False


def fake_breakout_pro(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=6)
        last=candles[-1]
        body=abs(last[4]-last[1])
        wick=last[2]-last[3]
        return wick > body*2
    except:
        return False


def liquidity_sweep(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"15m",limit=10)
        highs=[c[2] for c in candles]
        lows=[c[3] for c in candles]
        return highs[-1] > max(highs[:-1]) or lows[-1] < min(lows[:-1])
    except:
        return False


def micro_momentum(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"1m",limit=4)
        closes=[c[4] for c in candles]
        return closes[-1] > closes[-2] > closes[-3]
    except:
        return False


def funding_filter(sym):
    try:
        data=exchange.fetch_funding_rate(sym)
        rate=float(data["fundingRate"])
        if rate > 0.01:
            return "short"
        if rate < -0.01:
            return "long"
        return None
    except:
        return None


def market_regime(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"1h",limit=30)
        closes=[c[4] for c in candles]
        ma=sum(closes[-20:])/20
        if closes[-1] > ma:
            return "bull"
        return "bear"
    except:
        return "neutral"


def mtf_confirm(sym,direction):
    try:
        c5=exchange.fetch_ohlcv(sym,"5m",limit=3)
        c15=exchange.fetch_ohlcv(sym,"15m",limit=3)

        if direction=="long":
            return c5[-1][4] > c5[-2][4] and c15[-1][4] > c15[-2][4]

        if direction=="short":
            return c5[-1][4] < c5[-2][4] and c15[-1][4] < c15[-2][4]

        return False
    except:
        return False


def early_pump_pro(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"1m",limit=6)
        vols=[c[5] for c in candles]
        avg=sum(vols[:-1])/5
        return vols[-1] > avg*2
    except:
        return False


def open_trade(sym,direction,label):
    try:
        if get_qty(sym) > 0:
            return

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

        trade_state[sym]={
        "entry":price,
        "direction":direction,
        "tp1":False,
        "step":0,
        "start":time.time()
        }

        cooldown[sym]=time.time()

        bot.send_message(CHAT_ID,f"🚀 {label.upper()} {sym} {direction}")

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

                if sym not in trade_state:
                    continue

                state=trade_state[sym]

                price=exchange.fetch_ticker(sym)["last"]

                entry=state["entry"]

                direction=state["direction"]

                side="sell" if direction=="long" else "buy"

                if direction=="long" and price <= entry*(1-HARD_SL):
                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 HARD SL {sym}")
                    continue

                if direction=="short" and price >= entry*(1+HARD_SL):
                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})
                    trade_state.pop(sym)
                    bot.send_message(CHAT_ID,f"🛑 HARD SL {sym}")
                    continue

                elapsed=time.time()-state["start"]

                if elapsed > TIMEOUT:

                    exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})

                    trade_state.pop(sym)

                    bot.send_message(CHAT_ID,f"⏰ TIMEOUT {sym}")

                    continue

            time.sleep(4)

        except:
            time.sleep(6)


def scanner():

    while True:

        try:

            random.shuffle(SYMBOLS)

            btc=btc_trend()

            positions=exchange.fetch_positions()

            active=sum(1 for p in positions if safe(p.get("contracts"))>0)

            if active >= MAX_POSITIONS:
                time.sleep(SCAN_DELAY)
                continue

            for sym in SYMBOLS:

                if sym in cooldown:

                    if time.time()-cooldown[sym] < COOLDOWN_TIME:
                        continue

                if not volatility_filter(sym):
                    continue

                if not micro_momentum(sym):
                    continue

                pressure=orderbook_pressure(sym)

                if not pressure:
                    continue

                fund=funding_filter(sym)

                if fund and fund!=pressure:
                    continue

                if not mtf_confirm(sym,pressure):
                    continue

                if fake_breakout_pro(sym):
                    continue

                if early_pump_pro(sym):
                    open_trade(sym,"long","pump")
                    break

                open_trade(sym,pressure,"signal")

                break

            time.sleep(SCAN_DELAY)

        except:

            time.sleep(15)


print("BOT STARTING")

sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
