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

# --- AYARLAR ---
LEV = 5
MAX_POS = 1
MIN_CHANGE = 8
STOP_P = 0.012
TP_P   = 0.04
SPIKE_LIMIT = 0.04

BANNED = ['BTC','ETH','BNB','SOL','XRP','ADA','AVAX']

def open_trade(sym):
    try:
        exch = get_exch()
        markets = exch.load_markets()
        market = markets[sym]

        pos = exch.fetch_positions()
        active = [p for p in pos if safe(p.get('contracts')) > 0]
        if len(active) >= MAX_POS:
            return

        price = safe(exch.fetch_ticker(sym)['last'])

        min_cost = 5
        if market.get('limits') and market['limits'].get('cost'):
            if market['limits']['cost'].get('min'):
                min_cost = market['limits']['cost']['min']

        notional = max(min_cost * 1.2, 6)

        qty = notional / price
        qty = float(exch.amount_to_precision(sym, qty))

        exch.create_market_order(
            sym,
            "buy",
            qty,
            params={"leverage": LEV}
        )

        bot.send_message(MY_CHAT_ID, f"🚀 {sym} LONG açıldı")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"Hata: {e}")

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
                tp_price   = entry * (1 + TP_P)

                # STOP
                if last <= stop_price:
                    exch.create_market_order(
                        sym, 'sell', qty,
                        params={'reduceOnly': True}
                    )
                    bot.send_message(MY_CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP
                if last >= tp_price:
                    exch.create_market_order(
                        sym, 'sell', qty,
                        params={'reduceOnly': True}
                    )
                    bot.send_message(MY_CHAT_ID, f"🎯 TP {sym}")
                    continue

            time.sleep(3)

        except:
            time.sleep(3)

def scanner():
    while True:
        try:
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

                candles = exch.fetch_ohlcv(sym,'5m',limit=30)
                closes = [c[4] for c in candles]
                opens  = [c[1] for c in candles]
                highs  = [c[2] for c in candles]
                volumes = [c[5] for c in candles]

                last_close = closes[-1]
                last_open  = opens[-1]

                single_move = (last_close - last_open) / last_open
                if single_move > SPIKE_LIMIT:
                    continue

                avg_vol = sum(volumes[-10:]) / 10
                volume_spike = volumes[-1] > avg_vol * 1.4

                ema9 = sum(closes[-9:]) / 9
                ema21 = sum(closes[-21:]) / 21

                higher_high = highs[-1] > highs[-3]
                breakout = highs[-1] > max(highs[:-1])
                squeeze = (max(closes[-15:]) - min(closes[-15:])) / closes[-1] < 0.03

                model1 = breakout and squeeze and volume_spike
                model2 = ema9 > ema21 and higher_high and volume_spike

                if model1 or model2:
                    open_trade(sym)

            time.sleep(10)

        except:
            time.sleep(10)

@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return
    if msg.text.lower()=="dur":
        bot.send_message(MY_CHAT_ID,"Bot durduruldu")
        os._exit(0)

if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🔥 BÜYÜME MODU AKTİF")
    bot.infinity_polling()
