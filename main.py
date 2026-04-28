# ==============================
# 💀 SADIK BOT v24.4 PRO SAFE COMPLETE
# ==============================

import os, time, ccxt, telebot, threading
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

positions = []
daily_pnl = 0

# ==============================
def safe_send(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except Exception as e:
        print("TELEGRAM ERROR:", e)
        time.sleep(2)

# ==============================
def safe_order(sym, side, amount):
    try:
        if amount <= 0:
            return
        exchange.create_market_order(sym, side, amount)
    except Exception as e:
        print("ORDER ERROR:", e)

# ==============================
def get_real_size(sym):
    try:
        for p in exchange.fetch_positions():
            if p["symbol"] == sym:
                return float(p.get("contracts", 0))
    except:
        pass
    return 0

# ==============================
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=120)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        if len(df) < 30:
            return None
        df["ema"] = df["c"].ewm(span=20).mean()
        return df
    except:
        return None

# ==============================
def smart_tp_sl(price, signal):
    if signal == "LONG":
        return price*1.015, price*1.03, price*1.06, price*0.99
    else:
        return price*0.985, price*0.97, price*0.94, price*1.01

# ==============================
def calc_pnl(p, price):
    if p["signal"] == "LONG":
        return (price - p["entry"]) / p["entry"] * p["size"] * 10
    else:
        return (p["entry"] - price) / p["entry"] * p["size"] * 10

# ==============================
def open_trade(data):
    try:
        side = "buy" if data["signal"]=="LONG" else "sell"
        amount = max(0.001, 30/data["entry"])

        exchange.set_leverage(10, data["sym"])
        safe_order(data["sym"], side, amount)

        time.sleep(1)
        size = get_real_size(data["sym"])
        if size == 0:
            size = amount

        positions.append({
            **data,
            "size": size,
            "tp1_done": False,
            "tp2_done": False,
            "max_profit": 0,
            "bot": True
        })

        safe_send(f"""
🚀 BOT İŞLEM AÇTI

📊 {data['sym']}
📈 {data['signal']}
💰 {round(data['entry'],4)}
""")

    except Exception as e:
        print("OPEN ERROR:", e)

# ==============================
def scanner():
    while True:
        try:
            # sadece 1 bot trade
            if len([p for p in positions if p.get("bot")]) >= 1:
                time.sleep(5)
                continue

            for sym in exchange.fetch_tickers():

                if ":USDT" not in sym:
                    continue

                if any(x in sym for x in ["BTC","ETH","XRP","SOL"]):
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]

                momentum = abs(df["c"].iloc[-1]-df["c"].iloc[-3]) / df["c"].iloc[-3]
                if momentum < 0.004:
                    continue

                vol = df["v"].iloc[-1]
                avg = df["v"].rolling(20).mean().iloc[-1]
                if vol < avg*1.3:
                    continue

                ema = df["ema"].iloc[-1]
                signal = "LONG" if price > ema else "SHORT"

                score = 0
                if momentum > 0.004: score += 30
                if vol > avg*1.4: score += 40
                if abs(price-ema)/ema > 0.002: score += 30

                if score < 90:
                    continue

                tp1,tp2,tp3,sl = smart_tp_sl(price,signal)

                safe_send(f"💀 SİNYAL {sym} {signal} %{score}")

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

            time.sleep(15)

        except Exception as e:
            print("SCANNER ERROR:", e)
            time.sleep(5)

# ==============================
def manage():
    global daily_pnl

    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = calc_pnl(p, price)

            if pnl > p["max_profit"]:
                p["max_profit"] = pnl

            # trailing
            if p["max_profit"] > 5 and pnl < p["max_profit"]*0.7:
                p["sl"] = price

            # TP1
            if not p["tp1_done"]:
                if (p["signal"]=="LONG" and price>=p["tp1"]) or (p["signal"]=="SHORT" and price<=p["tp1"]):
                    safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", p["size"]*0.5)
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]
                    safe_send(f"🎯 TP1 {p['sym']}")

            # TP2
            if not p["tp2_done"]:
                if (p["signal"]=="LONG" and price>=p["tp2"]) or (p["signal"]=="SHORT" and price<=p["tp2"]):
                    safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", p["size"]*0.25)
                    p["tp2_done"] = True
                    safe_send(f"🎯 TP2 {p['sym']}")

            # FINAL
            if (p["signal"]=="LONG" and (price<=p["sl"] or price>=p["tp3"])) or \
               (p["signal"]=="SHORT" and (price>=p["sl"] or price<=p["tp3"])):

                size = get_real_size(p["sym"])
                if size > 0:
                    safe_order(p["sym"], "sell" if p["signal"]=="LONG" else "buy", size)

                daily_pnl += pnl
                safe_send(f"⛔ KAPANDI {p['sym']} {round(pnl,2)} USDT")
                positions.remove(p)

        time.sleep(5)

# ==============================
@bot.message_handler(commands=['panel'])
def panel(msg):
    text = f"""
💀 PANEL

📅 PnL: {round(daily_pnl,2)}
📈 Açık: {len(positions)}
"""
    bot.send_message(msg.chat.id, text)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

print("💀 BOT v24.4 AKTİF")
bot.infinity_polling()
