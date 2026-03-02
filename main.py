import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone, timedelta

# ===== SETTINGS =====
LEV = 10
MIN_VOLUME = 20_000_000
TOP_COINS = 80
SPREAD_LIMIT = 0.0015
MAX_DAILY_STOPS = 3
GLOBAL_MAX_RISK = 0.07

RISK_TREND = 0.05
RISK_SCALP = 0.02
RISK_REVERSION = 0.015

SCALP_TP = 0.006
SCALP_SL = 0.005
REV_TP = 0.005
REV_SL = 0.004

COOLDOWN_SCALP = 30
COOLDOWN_TREND = 60

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"), threaded=True)
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== BITGET =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})

# ===== STATE =====
positions_state = {}
cooldowns = {}
daily_stops = 0
last_day = datetime.now(timezone.utc).day

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0.0

def now():
    return datetime.now(timezone.utc)

def get_balance():
    return safe(exchange.fetch_balance()['total']['USDT'])

def get_symbols():
    tickers = exchange.fetch_tickers()
    filt = []
    for s, d in tickers.items():
        if ":USDT" not in s: continue
        if safe(d.get("quoteVolume")) >= MIN_VOLUME:
            filt.append((s, safe(d.get("quoteVolume"))))
    filt.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filt[:TOP_COINS]]

def spread_ok(sym):
    t = exchange.fetch_ticker(sym)
    sp = (t["ask"] - t["bid"]) / t["last"]
    return sp <= SPREAD_LIMIT

def global_risk_used(balance):
    total = 0
    for p in positions_state.values():
        total += p["risk_pct"]
    return total

def can_open(balance, risk):
    return (global_risk_used(balance) + risk) <= GLOBAL_MAX_RISK

def cooldown_active(sym):
    if sym not in cooldowns: return False
    return now() < cooldowns[sym]

def set_cooldown(sym, minutes):
    cooldowns[sym] = now() + timedelta(minutes=minutes)

# ===== TREND DIRECTION =====
def trend_direction(sym):
    h4 = exchange.fetch_ohlcv(sym, "4h", limit=60)
    closes = [c[4] for c in h4]
    ema = sum(closes[-50:]) / 50
    if closes[-1] > ema: return "long"
    if closes[-1] < ema: return "short"
    return None

# ===== MOMENTUM SCALP =====
def momentum_signal(sym, direction):
    m5 = exchange.fetch_ohlcv(sym, "5m", limit=10)
    last = m5[-1]
    prev = m5[-2]
    body = abs(last[4] - last[1])
    avg = sum(abs(c[4]-c[1]) for c in m5[:-1]) / 9
    if body > avg*1.8:
        if direction == "long" and last[4] > prev[2]:
            return True
        if direction == "short" and last[4] < prev[3]:
            return True
    return False

# ===== REVERSION =====
def reversion_signal(sym):
    m5 = exchange.fetch_ohlcv(sym, "5m", limit=30)
    closes = [c[4] for c in m5]
    mean = sum(closes)/len(closes)
    dev = (closes[-1]-mean)/mean
    if dev > 0.01: return "short"
    if dev < -0.01: return "long"
    return None

# ===== ORDER OPEN =====
def open_position(sym, direction, risk_pct, tp_pct, sl_pct, mode):
    balance = get_balance()
    if not can_open(balance, risk_pct): return

    price = safe(exchange.fetch_ticker(sym)["last"])
    risk_amount = balance * risk_pct
    sl_distance = price * sl_pct
    qty = risk_amount / sl_distance
    qty = float(exchange.amount_to_precision(sym, qty))

    exchange.set_leverage(LEV, sym)
    side = "buy" if direction=="long" else "sell"
    exchange.create_market_order(sym, side, qty)

    sl = price*(1-sl_pct) if direction=="long" else price*(1+sl_pct)
    tp = price*(1+tp_pct) if direction=="long" else price*(1-tp_pct)

    positions_state[sym] = {
        "mode": mode,
        "direction": direction,
        "sl": sl,
        "tp": tp,
        "risk_pct": risk_pct
    }

    bot.send_message(CHAT_ID, f"🚀 {mode.upper()} {sym} {direction}")

# ===== MANAGER =====
def manage():
    global daily_stops, last_day
    while True:
        try:
            if now().day != last_day:
                daily_stops = 0
                last_day = now().day

            for sym in list(positions_state.keys()):
                p = positions_state[sym]
                price = safe(exchange.fetch_ticker(sym)["last"])
                direction = p["direction"]

                # STOP
                if (direction=="long" and price<=p["sl"]) or \
                   (direction=="short" and price>=p["sl"]):

                    side = "sell" if direction=="long" else "buy"
                    pos = exchange.fetch_positions([sym])[0]
                    qty = safe(pos.get("contracts"))
                    if qty>0:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly":True})

                    daily_stops+=1
                    set_cooldown(sym, COOLDOWN_TREND if p["mode"]=="trend" else COOLDOWN_SCALP)
                    positions_state.pop(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP
                if (direction=="long" and price>=p["tp"]) or \
                   (direction=="short" and price<=p["tp"]):

                    side = "sell" if direction=="long" else "buy"
                    pos = exchange.fetch_positions([sym])[0]
                    qty = safe(pos.get("contracts"))
                    if qty>0:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly":True})

                    set_cooldown(sym, COOLDOWN_TREND if p["mode"]=="trend" else COOLDOWN_SCALP)
                    positions_state.pop(sym)
                    bot.send_message(CHAT_ID, f"💰 TP {sym}")
                    continue

            time.sleep(3)
        except Exception as e:
            print("MANAGE ERROR", e)
            time.sleep(3)

# ===== ENTRY LOOP =====
def run():
    global daily_stops
    while True:
        try:
            if daily_stops>=MAX_DAILY_STOPS:
                time.sleep(30)
                continue

            if len(positions_state)>=2:
                time.sleep(5)
                continue

            symbols = get_symbols()

            for sym in symbols:
                if cooldown_active(sym): continue
                if sym in positions_state: continue
                if not spread_ok(sym): continue

                direction = trend_direction(sym)
                if not direction: continue

                # TREND (priority)
                if len(positions_state)<2:
                    if direction:
                        open_position(sym,direction,RISK_TREND,0.02,0.01,"trend")
                        break

                # MOMENTUM
                if momentum_signal(sym,direction):
                    open_position(sym,direction,RISK_SCALP,SCALP_TP,SCALP_SL,"scalp")
                    break

                # REVERSION
                rev = reversion_signal(sym)
                if rev:
                    open_position(sym,rev,RISK_REVERSION,REV_TP,REV_SL,"reversion")
                    break

            time.sleep(10)
        except Exception as e:
            print("RUN ERROR", e)
            time.sleep(10)

# ===== START =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID,"🔥 3 MOTORLU HİBRİT AKTİF")
bot.infinity_polling()
