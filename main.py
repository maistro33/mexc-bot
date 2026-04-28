# ==============================
# 💀 SADIK BOT v27.2 PRO PANEL – COMPLETE
# ==============================

import os, time, threading
import ccxt, telebot
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# ENV
TOKEN   = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

API_KEY = os.getenv("BITGET_API")
API_SEC = os.getenv("BITGET_SEC")
API_PAS = os.getenv("BITGET_PASS")

if not TOKEN or not CHAT_ID:
    raise ValueError("TELE_TOKEN / MY_CHAT_ID eksik")

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SEC,
    "password": API_PAS,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ==============================
# GLOBALS
positions = []  # dict list
daily_pnl = 0.0

# ==============================
# UTILS

def safe_send(msg):
    for _ in range(3):
        try:
            bot.send_message(CHAT_ID, msg)
            return
        except Exception:
            time.sleep(2)

def safe_order(sym, side, amount):
    # küçük retry
    for _ in range(3):
        try:
            if amount and amount > 0:
                exchange.create_market_order(sym, side, amount)
            return True
        except Exception as e:
            print("ORDER ERROR:", e)
            time.sleep(1)
    return False

def get_real_size(sym):
    try:
        data = exchange.fetch_positions()
        for p in data:
            if p.get("symbol") == sym:
                return float(p.get("contracts", 0) or 0)
    except Exception as e:
        print("REAL SIZE ERR:", e)
    return 0.0

def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=120)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        if len(df) < 30:
            return None
        df["ema"] = df["c"].ewm(span=20).mean()
        return df
    except Exception:
        return None

def smart_tp_sl(price, signal):
    if signal == "LONG":
        return price*1.002, price*1.035, price*1.06, price*0.99
    else:
        return price*0.98, price*0.965, price*0.94, price*1.01

def calc_pnl(p, price):
    # approx PnL (10x)
    if p["signal"] == "LONG":
        return (price - p["entry"]) / p["entry"] * p["initial_size"] * 10
    else:
        return (p["entry"] - price) / p["entry"] * p["initial_size"] * 10

def is_bot_open():
    return any(p.get("bot") for p in positions)

# ==============================
# OPEN TRADE

def open_trade(data):
    try:
        side = "buy" if data["signal"]=="LONG" else "sell"
        amount = max(0.001, 30 / data["entry"])

        exchange.set_leverage(10, data["sym"])
        if not safe_order(data["sym"], side, amount):
            return

        time.sleep(1)
        size = get_real_size(data["sym"])
        if size <= 0:
            size = amount

        pos = {
            **data,
            "size": size,
            "initial_size": size,
            "tp1_done": False,
            "tp2_done": False,
            "max_profit": 0.0,
            "bot": True,
            "start_time": time.time()
        }
        positions.append(pos)

        safe_send(f"🚀 BOT {data['signal']} AÇTI\n{data['sym']} @ {round(data['entry'],4)}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ==============================
# MANUAL SYNC

def sync_positions():
    try:
        data = exchange.fetch_positions()
        for pos in data:
            size = float(pos.get("contracts", 0) or 0)
            if size <= 0:
                continue

            sym = pos.get("symbol")
            if any(p["sym"] == sym for p in positions):
                continue

            entry = float(pos.get("entryPrice") or 0)
            side  = pos.get("side")
            signal = "LONG" if side == "long" else "SHORT"

            tp1,tp2,tp3,sl = smart_tp_sl(entry, signal)

            positions.append({
                "sym": sym,
                "entry": entry,
                "signal": signal,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "sl": sl,
                "size": size,
                "initial_size": size,
                "tp1_done": False,
                "tp2_done": False,
                "max_profit": 0.0,
                "bot": False,
                "start_time": time.time()
            })

            safe_send(f"📥 MANUEL ALGILANDI: {sym}")

    except Exception as e:
        print("SYNC ERROR:", e)

def sync_loop():
    while True:
        sync_positions()
        time.sleep(10)

# ==============================
# SCANNER

def scanner():
    while True:
        try:
            if is_bot_open():
                time.sleep(5)
                continue

            tickers = exchange.fetch_tickers()

            for sym in tickers:
                if ":USDT" not in sym:
                    continue
                if any(x in sym for x in ["BTC","ETH","XRP","SOL"]):
                    continue
                if any(p["sym"] == sym for p in positions):
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]
                ema   = df["ema"].iloc[-1]
                momentum = (df["c"].iloc[-1] - df["c"].iloc[-3]) / df["c"].iloc[-3]

                vol = df["v"].iloc[-1]
                avg = df["v"].rolling(20).mean().iloc[-1]

                if price > ema and momentum > 0:
                    signal = "LONG"
                elif price < ema and momentum < 0:
                    signal = "SHORT"
                else:
                    continue

                if signal == "SHORT" and df["c"].iloc[-1] > df["c"].iloc[-2]:
                    continue

                if vol < avg * 1.3:
                    continue

                high = df["h"].rolling(10).max().iloc[-2]
                low  = df["l"].rolling(10).min().iloc[-2]

                if signal == "LONG" and price > high and vol < avg:
                    continue
                if signal == "SHORT" and price < low and vol < avg:
                    continue

                score = 0
                if abs(momentum) > 0.004: score += 30
                if vol > avg * 1.4: score += 40
                if abs(price - ema)/ema > 0.002: score += 30

                if score < 90:
                    continue

                tp1,tp2,tp3,sl = smart_tp_sl(price, signal)

                safe_send(f"💀 SİNYAL\n{sym} {signal}\nGüç: %{score}")

                open_trade({
                    "sym": sym,
                    "entry": price,
                    "signal": signal,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl
                })

                break

            time.sleep(25)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(5)

# ==============================
# MANAGER

def manage():
    global daily_pnl

    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except Exception:
                continue

            pnl = calc_pnl(p, price)

            if time.time() - p["start_time"] < 60:
                continue

            # TP1
            if not p["tp1_done"]:
                hit = (p["signal"]=="LONG" and price>=p["tp1"]) or (p["signal"]=="SHORT" and price<=p["tp1"])
                if hit:
                    close_size = p["size"] * 0.5
                    if safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", close_size):
                        p["size"] -= close_size
                        p["tp1_done"] = True
                        p["sl"] = p["entry"]
                        safe_send(f"🎯 TP1 {p['sym']}")

            # TP2
            if not p["tp2_done"]:
                hit = (p["signal"]=="LONG" and price>=p["tp2"]) or (p["signal"]=="SHORT" and price<=p["tp2"])
                if hit:
                    close_size = p["size"] * 0.5
                    if safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", close_size):
                        p["size"] -= close_size
                        p["tp2_done"] = True
                        safe_send(f"🎯 TP2 {p['sym']}")

            # trailing
            if p["tp1_done"]:
                if pnl > p["max_profit"]:
                    p["max_profit"] = pnl
                if p["max_profit"] > 15 and pnl < p["max_profit"]*0.6:
                    p["sl"] = price

            # final
            if (p["signal"]=="LONG" and (price<=p["sl"] or price>=p["tp3"])) or \
               (p["signal"]=="SHORT" and (price>=p["sl"] or price<=p["tp3"])):

                remaining = get_real_size(p["sym"])
                if remaining > 0:
                    safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", remaining)

                daily_pnl += pnl
                safe_send(f"⛔ KAPANDI {p['sym']} {round(pnl,2)} USDT")

                positions.remove(p)

        time.sleep(5)

# ==============================
# PANEL

def build_panel():
    text = f"💀 PANEL\nPnL: {round(daily_pnl,2)}\nAçık: {len(positions)}\n\n"
    for p in positions:
        who = "BOT" if p.get("bot") else "MANUAL"
        text += f"{p['sym']} {p['signal']} [{who}]\n"
    return text

@bot.message_handler(commands=['panel'])
def panel(msg):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🚨 EXIT BOT", callback_data="exit_bot"))
    bot.send_message(msg.chat.id, build_panel(), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def callback(call):
    if call.data == "exit_bot":
        for p in positions[:]:
            if not p.get("bot"):
                continue
            size = get_real_size(p["sym"])
            if size > 0:
                safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", size)
            positions.remove(p)
        safe_send("🚨 BOT POZİSYONLARI KAPATILDI")

# ==============================
# THREADS

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=sync_loop, daemon=True).start()

print("💀 BOT v27.2 AKTİF")
bot.infinity_polling()
