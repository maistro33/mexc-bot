import os
import time
import ccxt
import telebot
import threading

# ===== AYAR =====
RISK_PERCENT = 0.01
LEV = 10
MIN_VOLUME = 5_000_000
TOP_COINS = 80
RR = 2
CRISIS_DROP = -5

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

def send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except:
        pass

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

trade_active = False

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0

def candles(sym, tf, limit=100):
    try: return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except: return []

def balance():
    try:
        b = exchange.fetch_balance()
        return safe(b["USDT"]["free"])
    except:
        return 0

# ===== MARKET FILTER =====
def volatility(sym):
    h1 = candles(sym, "1h", 30)
    if len(h1) < 20: return False
    avg = sum((c[2]-c[3])/c[4] for c in h1[-20:]) / 20
    return avg > 0.008

def new_or_momentum(sym):
    d = candles(sym, "1d", 200)
    if len(d) < 120:
        return True
    h4 = candles(sym, "4h", 20)
    if len(h4) < 10: return False
    move = (h4[-1][4]-h4[-10][4])/h4[-10][4]
    return abs(move) > 0.05

def symbols():
    tickers = exchange.fetch_tickers()
    data = []
    for s,t in tickers.items():
        if ":USDT" not in s: continue
        if safe(t.get("quoteVolume")) < MIN_VOLUME: continue
        if not volatility(s): continue
        if not new_or_momentum(s): continue
        data.append((s, safe(t.get("quoteVolume"))))
    data.sort(key=lambda x:x[1], reverse=True)
    return [x[0] for x in data[:TOP_COINS]]

# ===== SMC CORE =====
def sweep(sym, direction):
    h1 = candles(sym,"1h",30)
    if len(h1)<10: return False
    highs=[c[2] for c in h1]
    lows=[c[3] for c in h1]
    if direction=="long":
        return lows[-1] < min(lows[-5:-1])
    else:
        return highs[-1] > max(highs[-5:-1])

def displacement(c):
    body=abs(c[-1][4]-c[-1][1])
    avg=sum(abs(x[4]-x[1]) for x in c[-6:-1])/5
    return body>avg*1.5

def bos(c, direction):
    highs=[x[2] for x in c]
    lows=[x[3] for x in c]
    if direction=="long":
        return highs[-1]>max(highs[-10:-1])
    else:
        return lows[-1]<min(lows[-10:-1])

def fvg_zone(c, direction):
    c1,c2,c3=c[-3],c[-2],c[-1]
    if direction=="long":
        if c1[2] < c3[3]:
            return (c1[2], c3[3])
    else:
        if c1[3] > c3[2]:
            return (c3[2], c1[3])
    return None

def retest(price, zone, direction):
    low,high=zone
    if direction=="long":
        return low<=price<=high
    else:
        return high>=price>=low

# ===== ENTRY =====
def try_trade(sym):
    global trade_active
    if trade_active: return

    m15=candles(sym,"15m",60)
    if len(m15)<20: return

    # trend basit filtre
    d=candles(sym,"1d",5)
    if len(d)<2: return
    direction="long" if d[-1][4]>d[-2][4] else "short"

    if not sweep(sym,direction): return
    if not displacement(m15): return
    if not bos(m15,direction): return

    zone=fvg_zone(m15,direction)
    if not zone: return

    price=safe(exchange.fetch_ticker(sym)["last"])
    if not retest(price,zone,direction): return

    entry=price
    sl=zone[0] if direction=="long" else zone[1]
    risk=abs(entry-sl)
    if risk<=0: return

    tp=entry + RR*risk if direction=="long" else entry - RR*risk

    bal=balance()
    risk_amt=bal*RISK_PERCENT
    qty=risk_amt/risk
    qty=float(exchange.amount_to_precision(sym, qty))

    if qty<=0: return

    exchange.set_leverage(LEV,sym)

    side="buy" if direction=="long" else "sell"
    exchange.create_market_order(sym,side,qty)

    # STOP
    exchange.create_order(
        sym,
        "stop_market",
        "sell" if direction=="long" else "buy",
        qty,
        None,
        {"stopPrice": sl, "reduceOnly": True}
    )

    trade_active=True
    send(f"{sym} {direction.upper()} AÇILDI\nSL:{sl}\nTP:{tp}")

# ===== LOOP =====
def run():
    global trade_active
    send("SMC PRO AKTIF")
    while True:
        try:
            pos=exchange.fetch_positions()
            trade_active=any(safe(p.get("contracts"))>0 for p in pos)

            if not trade_active:
                for s in symbols():
                    try_trade(s)
                    if trade_active:
                        break
            time.sleep(25)
        except:
            time.sleep(25)

threading.Thread(target=run,daemon=True).start()
bot.infinity_polling()
