import os, time, telebot, ccxt, threading

# --- BAĞLANTILAR ---
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

# --- EXCHANGE ---
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

# --- AYARLAR ---
MARGIN = 1
LEV = 5
MAX_POS = 1
MAX_DAILY = 3
MIN_CHANGE = 12

STOP_P = 0.008      # %0.8 stop
TP1_P  = 0.015      # %1.5 yarım kapat
TP2_P  = 0.04       # %4 tam kapat
SPIKE_LIMIT = 0.03  # %3 tek mum üstü girme

BANNED = ['BTC','ETH','BNB','SOL','XRP','ADA','AVAX']

daily_count = 0
day_reset = time.time()

trade_state = {}  # {symbol: {"tp1_hit":False}}

# --- EMİR ---
def open_trade(sym):
    global daily_count
    if daily_count >= MAX_DAILY:
        return

    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()
        active = [p for p in pos if safe(p.get('contracts')) > 0]
        if len(active) >= MAX_POS:
            return

        price = safe(exch.fetch_ticker(sym)['last'])
        qty = (MARGIN * LEV) / price
        qty = float(exch.amount_to_precision(sym, qty))

        exch.create_market_order(sym, "buy", qty)

        trade_state[sym] = {"tp1_hit": False}
        daily_count += 1

        bot.send_message(MY_CHAT_ID, f"🎯 {sym} LONG açıldı")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"Hata: {e}")

# --- KAR YÖNETİMİ ---
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

                stop_price = entry * (1 - STOP_P)
                tp1_price  = entry * (1 + TP1_P)
                tp2_price  = entry * (1 + TP2_P)

                # STOP
                if last <= stop_price:
                    exch.create_market_order(
                        sym, 'sell', qty,
                        params={'reduceOnly': True}
                    )
                    trade_state.pop(sym, None)
                    bot.send_message(MY_CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP1 (yarım kapat)
                if not trade_state.get(sym, {}).get("tp1_hit") and last >= tp1_price:
                    half_qty = float(exch.amount_to_precision(sym, qty / 2))
                    exch.create_market_order(
                        sym, 'sell', half_qty,
                        params={'reduceOnly': True}
                    )
                    trade_state[sym]["tp1_hit"] = True
                    bot.send_message(MY_CHAT_ID, f"💰 TP1 {sym} %50 kapandı")

                # Break-even
                if trade_state.get(sym, {}).get("tp1_hit"):
                    if last <= entry:
                        exch.create_market_order(
                            sym, 'sell', qty,
                            params={'reduceOnly': True}
                        )
                        trade_state.pop(sym, None)
                        bot.send_message(MY_CHAT_ID, f"🔒 BE EXIT {sym}")
                        continue

                # TP2
                if last >= tp2_price:
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

# --- SCANNER ---
def scanner():
    global daily_count, day_reset

    while True:
        try:
            if time.time() - day_reset > 86400:
                daily_count = 0
                day_reset = time.time()

            exch = get_exch()
            tickers = exch.fetch_tickers()

            candidates = []

            for sym, data in tickers.items():

                if ':USDT' not in sym:
                    continue

                if any(x in sym for x in BANNED):
                    continue

                change = safe(data.get('percentage'))
                if change >= MIN_CHANGE:
                    candidates.append((sym, change))

            candidates.sort(key=lambda x: x[1], reverse=True)
            candidates = candidates[:150]

            pos = exch.fetch_positions()
            active = [p for p in pos if safe(p.get('contracts')) > 0]

            for sym, _ in candidates:

                if len(active) >= MAX_POS:
                    break

                candles = exch.fetch_ohlcv(sym, '5m', limit=20)

                closes = [c[4] for c in candles]
                opens  = [c[1] for c in candles]
                volumes = [c[5] for c in candles]

                last_close = closes[-1]
                last_open  = opens[-1]

                # --- SPIKE FİLTRESİ ---
                single_move = (last_close - last_open) / last_open
                if single_move > SPIKE_LIMIT:
                    continue

                range_size = max(closes[:-1]) - min(closes[:-1])
                avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
                volume_spike = volumes[-1] > avg_vol * 1.7
                breakout = closes[-1] > max(closes[:-1])

                if range_size / closes[-1] < 0.02 and breakout and volume_spike:
                    open_trade(sym)

            time.sleep(15)

        except:
            time.sleep(10)

# --- TELEGRAM ---
@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return
    if msg.text.lower() == "dur":
        bot.send_message(MY_CHAT_ID, "Bot durduruldu")
        os._exit(0)

# --- START ---
if __name__ == "__main__":
    threading.Thread(target=manager, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "🚀 PUMP AVCI KADEMELİ + SPIKE aktif")
    bot.infinity_polling()
