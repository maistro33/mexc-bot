import os, time, telebot, ccxt, threading

TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True,
        'timeout': 30000
    })

def safe(x):
    try: return float(x)
    except: return 0.0

# === AYAR ===
MARGIN = 1
LEV = 5
MAX_POS = 1

STOP_P = 0.008
TP1_P = 0.015
TP2_P = 0.04

SPIKE_LIMIT = 0.04
MIN_CHANGE = 8

BANNED = ['BTC','ETH','BNB','SOL','XRP','ADA','AVAX']

trade_state = {}
cooldown = {}

# === OPEN ===
def open_trade(sym):
    try:
        now = time.time()

        if sym in cooldown and now - cooldown[sym] < 3600:
            return

        exch = get_exch()
        exch.load_markets()

        positions = exch.fetch_positions()
        active = [p for p in positions if safe(p.get('contracts')) > 0]
        if len(active) >= MAX_POS:
            return

        exch.set_margin_mode('isolated', sym)
        exch.set_leverage(LEV, sym)

        price = safe(exch.fetch_ticker(sym)['last'])
        qty = (MARGIN * LEV) / price
        qty = float(exch.amount_to_precision(sym, qty))

        exch.create_market_order(sym, "buy", qty)

        trade_state[sym] = {"tp1": False}
        cooldown[sym] = now

        bot.send_message(MY_CHAT_ID, f"🚀 {sym} LONG 5x ISOLATED")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"Hata: {e}")

# === MANAGER ===
def manager():
    while True:
        try:
            exch = get_exch()
            positions = exch.fetch_positions()

            for p in [p for p in positions if safe(p.get('contracts')) > 0]:

                sym = p['symbol']
                qty = safe(p.get('contracts'))
                entry = safe(p.get('entryPrice'))
                last = safe(exch.fetch_ticker(sym)['last'])

                stop = entry * (1 - STOP_P)
                tp1 = entry * (1 + TP1_P)
                tp2 = entry * (1 + TP2_P)

                if last <= stop:
                    exch.create_market_order(
                        sym, 'sell', qty,
                        params={'reduceOnly': True}
                    )
                    trade_state.pop(sym, None)
                    bot.send_message(MY_CHAT_ID, f"❌ STOP {sym}")
                    continue

                if not trade_state.get(sym, {}).get("tp1") and last >= tp1:
                    half = float(exch.amount_to_precision(sym, qty/2))
                    exch.create_market_order(
                        sym, 'sell', half,
                        params={'reduceOnly': True}
                    )
                    trade_state[sym]["tp1"] = True
                    bot.send_message(MY_CHAT_ID, f"💰 TP1 {sym}")

                if trade_state.get(sym, {}).get("tp1"):
                    if last <= entry:
                        exch.create_market_order(
                            sym, 'sell', qty,
                            params={'reduceOnly': True}
                        )
                        trade_state.pop(sym, None)
                        bot.send_message(MY_CHAT_ID, f"🔒 BE EXIT {sym}")
                        continue

                if last >= tp2:
                    exch.create_market_order(
                        sym, 'sell', qty,
                        params={'reduceOnly': True}
                    )
                    trade_state.pop(sym, None)
                    bot.send_message(MY_CHAT_ID, f"🚀 TP2 {sym}")
                    continue

            time.sleep(3)

        except:
            time.sleep(3)

# === SCANNER ===
def scanner():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()

            positions = exch.fetch_positions()
            active = [p for p in positions if safe(p.get('contracts')) > 0]
            if len(active) >= MAX_POS:
                time.sleep(5)
                continue

            for sym, data in tickers.items():

                if ':USDT' not in sym:
                    continue
                if any(x in sym for x in BANNED):
                    continue

                change = safe(data.get('percentage'))
                if change < MIN_CHANGE:
                    continue

                candles = exch.fetch_ohlcv(sym, '5m', limit=30)

                closes = [c[4] for c in candles]
                opens = [c[1] for c in candles]
                highs = [c[2] for c in candles]
                volumes = [c[5] for c in candles]

                single_move = (closes[-1] - opens[-1]) / opens[-1]
                if single_move > SPIKE_LIMIT:
                    continue

                avg_vol = sum(volumes[-10:]) / 10
                volume_spike = volumes[-1] > avg_vol * 1.8

                ema9 = sum(closes[-9:]) / 9
                ema21 = sum(closes[-21:]) / 21

                higher_high = highs[-1] > highs[-3]
                breakout = highs[-1] > max(highs[:-1])

                if (ema9 > ema21 and higher_high and volume_spike) or breakout:
                    open_trade(sym)

            time.sleep(10)

        except:
            time.sleep(10)

@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return
    if msg.text.lower() == "dur":
        bot.send_message(MY_CHAT_ID, "Bot durduruldu")
        os._exit(0)

if __name__ == "__main__":
    threading.Thread(target=manager, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "🔥 AGRESIF MOD AKTİF (5x ISOLATED)")
    bot.infinity_polling()
