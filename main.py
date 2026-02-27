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
        'enableRateLimit': True
    })

def safe(x):
    try: return float(x)
    except: return 0.0

# --- AYAR ---
LEV = 5
MARGIN = 1.1
MAX_POS = 1
MIN_CHANGE = 8

STOP_P = 0.009        # %0.9 stop
TRAIL_START = 0.012   # %1.2'de trailing başlar
TRAIL_GAP = 0.006     # %0.6 geri gelirse satar
SPIKE_LIMIT = 0.04

BANNED = ['BTC','ETH','BNB','SOL','XRP','ADA','AVAX']

state = {}

def open_trade(sym):
    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()
        active = [p for p in pos if safe(p.get('contracts')) > 0]
        if len(active) >= MAX_POS:
            return

        price = safe(exch.fetch_ticker(sym)['last'])
        notional = MARGIN * LEV
        qty = notional / price
        qty = float(exch.amount_to_precision(sym, qty))

        exch.create_market_order(sym, "buy", qty)

        state[sym] = {
            "entry": price,
            "highest": price
        }

        bot.send_message(MY_CHAT_ID, f"⚡ SCALP LONG {sym}")

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

                if sym not in state:
                    state[sym] = {"entry": entry, "highest": last}

                if last > state[sym]["highest"]:
                    state[sym]["highest"] = last

                # STOP
                if last <= entry * (1 - STOP_P):
                    exch.create_market_order(sym,'sell',qty,
                        params={'reduceOnly':True})
                    state.pop(sym,None)
                    bot.send_message(MY_CHAT_ID,f"❌ STOP {sym}")
                    continue

                profit = (last - entry) / entry

                # TRAILING
                if profit >= TRAIL_START:
                    trail_price = state[sym]["highest"] * (1 - TRAIL_GAP)
                    if last <= trail_price:
                        exch.create_market_order(sym,'sell',qty,
                            params={'reduceOnly':True})
                        state.pop(sym,None)
                        bot.send_message(MY_CHAT_ID,f"💰 SCALP EXIT {sym}")
                        continue

            time.sleep(2)

        except:
            time.sleep(2)

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
            candidates = candidates[:100]

            pos = exch.fetch_positions()
            active = [p for p in pos if safe(p.get('contracts')) > 0]

            for sym,_ in candidates:
                if len(active) >= MAX_POS:
                    break

                candles = exch.fetch_ohlcv(sym,'5m',limit=20)
                closes = [c[4] for c in candles]
                opens = [c[1] for c in candles]
                volumes = [c[5] for c in candles]

                last_close = closes[-1]
                last_open = opens[-1]

                if (last_close-last_open)/last_open > SPIKE_LIMIT:
                    continue

                avg_vol = sum(volumes[-8:])/8
                if volumes[-1] > avg_vol*1.3:
                    open_trade(sym)

            time.sleep(6)

        except:
            time.sleep(6)

@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return
    if msg.text.lower()=="dur":
        os._exit(0)

if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"⚡ AVCI V8 SCALP AKTİF")
    bot.infinity_polling()
