# ==============================
# 💀 SADIK BOT v22.6 PRO STABLE
# ==============================

import os, time, ccxt, telebot, threading
import pandas as pd

VERSION = "v22.6 PRO STABLE"

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
def smart_tp_sl(price, signal):
    fee = 0.0012
    if signal == "LONG":
        return (
            price*(1+fee+0.015),
            price*(1+fee+0.03),
            price*(1+fee+0.06),
            price*0.99
        )
    else:
        return (
            price*(1-fee-0.015),
            price*(1-fee-0.03),
            price*(1-fee-0.06),
            price*1.01
        )

# ==============================
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=100)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        if len(df) < 20:
            return None

        df["ema"] = df["c"].ewm(span=20).mean()
        return df
    except:
        return None

# ==============================
def calc_pnl(p, price):
    if p["signal"] == "LONG":
        return (price - p["entry"]) / p["entry"] * p["size"]
    else:
        return (p["entry"] - price) / p["entry"] * p["size"]

# ==============================
def scanner():
    while True:
        try:
            tickers = exchange.fetch_tickers()

            # 🤖 BOT SADECE 1 İŞLEM
            bot_positions = [p for p in positions if p.get("bot")]
            if len(bot_positions) >= 1:
                time.sleep(5)
                continue

            for sym in tickers:

                if ":USDT" not in sym:
                    continue

                # ❌ Büyük coin filtre
                if any(x in sym for x in ["BTC", "ETH", "XRP", "SOL"]):
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                price = df["c"].iloc[-1]

                # 📈 MOMENTUM
                momentum = abs(df["c"].iloc[-1] - df["c"].iloc[-3]) / df["c"].iloc[-3]
                if momentum < 0.003:
                    continue

                # 📊 HACİM
                vol_now = df["v"].iloc[-1]
                vol_avg = df["v"].rolling(20).mean().iloc[-1]
                if vol_now < vol_avg * 1.2:
                    continue

                # 🐋 WHALE
                vol_prev = df["v"].iloc[-2]
                if vol_now < vol_prev * 1.5:
                    continue

                # ⚡ HAREKET
                move = abs(df["c"].iloc[-1] - df["c"].iloc[-5]) / df["c"].iloc[-5]
                if move < 0.004:
                    continue

                # 📈 TREND
                ema = df["ema"].iloc[-1]
                signal = "LONG" if price > ema else "SHORT"

                # 🚫 FAKE BREAKOUT
                last_high = df["h"].rolling(10).max().iloc[-2]
                last_low = df["l"].rolling(10).min().iloc[-2]

                if signal == "LONG" and price > last_high:
                    if vol_now < df["v"].rolling(5).mean().iloc[-1]:
                        continue

                if signal == "SHORT" and price < last_low:
                    if vol_now < df["v"].rolling(5).mean().iloc[-1]:
                        continue

                # 🧠 SCORE
                score = 0
                if momentum > 0.004:
                    score += 30
                if vol_now > vol_avg * 1.3:
                    score += 40
                if price > ema or price < ema:
                    score += 30

                if score < 70:
                    continue

                tp1, tp2, tp3, sl = smart_tp_sl(price, signal)

                # 📩 TELEGRAM
                bot.send_message(CHAT_ID, f"""
💀 AKILLI SİNYAL

📊 {sym}
📈 {signal}
💰 {round(price,4)}

🔥 Hacim: Yüksek
⚡ Momentum: Güçlü

🎯 TP1: {round(tp1,4)}
🎯 TP2: {round(tp2,4)}
🎯 TP3: {round(tp3,4)}
🛑 SL: {round(sl,4)}

🤖 Güç: %{score}
""")

                # 🤖 BOT TRADE (1 ADET)
                open_trade({
                    "sym": sym,
                    "entry": price,
                    "signal": signal,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl,
                    "bot": True
                })

                break

            time.sleep(15)

        except Exception as e:
            print("SCANNER:", e)

# ==============================
def open_trade(data):
    try:
        side = "buy" if data["signal"] == "LONG" else "sell"
        amount = 30 / data["entry"]

        exchange.create_market_order(data["sym"], side, amount)

        time.sleep(1)
        real_size = get_real_size(data["sym"])

        positions.append({
            **data,
            "tp1_done": False,
            "tp2_done": False,
            "initial_size": real_size,
            "max_profit": 0,
            "size": 30
        })

    except Exception as e:
        print("ORDER ERROR:", e)

# ==============================
def manage():
    while True:
        for p in positions[:]:
            try:
                price = exchange.fetch_ticker(p["sym"])["last"]
            except:
                continue

            pnl = calc_pnl(p, price)

            # 📈 TRAILING
            if pnl > p["max_profit"]:
                p["max_profit"] = pnl

            if p["max_profit"] > 5 and pnl < p["max_profit"] * 0.7:
                p["sl"] = price

            # TP1
            if not p["tp1_done"]:
                if (p["signal"]=="LONG" and price>=p["tp1"]) or (p["signal"]=="SHORT" and price<=p["tp1"]):
                    exchange.create_market_order(
                        p["sym"],
                        "sell" if p["signal"]=="LONG" else "buy",
                        p["initial_size"]*0.5
                    )
                    p["tp1_done"] = True
                    p["sl"] = p["entry"]

            # TP2
            if not p["tp2_done"]:
                if (p["signal"]=="LONG" and price>=p["tp2"]) or (p["signal"]=="SHORT" and price<=p["tp2"]):
                    exchange.create_market_order(
                        p["sym"],
                        "sell" if p["signal"]=="LONG" else "buy",
                        p["initial_size"]*0.25
                    )
                    p["tp2_done"] = True
                    p["sl"] = p["tp1"]

            # FINAL
            if (p["signal"]=="LONG" and (price <= p["sl"] or price >= p["tp3"])) or \
               (p["signal"]=="SHORT" and (price >= p["sl"] or price <= p["tp3"])):

                exchange.create_market_order(
                    p["sym"],
                    "sell" if p["signal"]=="LONG" else "buy",
                    get_real_size(p["sym"])
                )

                positions.remove(p)

        time.sleep(5)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

print("💀 BOT AKTİF")
bot.infinity_polling()
