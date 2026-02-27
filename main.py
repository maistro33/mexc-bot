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

# --- AYARLAR ---
LEV = 5
MARGIN = 1.1        # 🔥 1 USDT yerine 1.1 garanti
MAX_POS = 1
MIN_CHANGE = 8

STOP_P = 0.012      # %1.2 sabit stop
BE_TRIGGER = 0.02   # %2'de BE
TRAIL_TRIGGER = 0.03 # %3'te trailing başlar
TRAIL_GAP = 0.01    # %1 trailing boşluk

SPIKE_LIMIT = 0.04

BANNED = ['BTC','ETH','BNB','SOL','XRP','ADA','AVAX']

state = {}

# --- EMİR ---
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
            "highest": price,
            "be_active": False
        }

        bot.send_message(MY_CHAT_ID, f"🚀 {sym} LONG açıldı")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"Hata: {e}")

# --- MANAGER ---
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
                    state[sym] = {
                        "entry": entry,
                        "highest": last,
                        "be_active": False
                    }

                # En yüksek fiyat güncelle
                if last > state[sym]["highest"]:
                    state[sym]["highest"] = last

                stop_price = entry * (1 - STOP_P)

                # Normal stop
                if last <= stop_price:
                    exch.create_market_order(sym,'sell',qty,
                        params={'reduceOnly':True})
                    state.pop(sym,None)
                    bot.send_message(MY_CHAT_ID,f"❌ STOP {sym}")
                    continue

                profit = (last - entry) / entry

                # BE aktif
                if profit >= BE_TRIGGER:
                    state[sym]["be_active"] = True

                # Break-even
                if state[sym]["be_active"] and last <= entry:
                    exch.create_market_order(sym,'sell',qty,
                        params={'reduceOnly':True})
                    state.pop(sym,None)
                    bot.send_message(MY_CHAT_ID,f"🔒 BE {sym}")
                    continue

                # Trailing
                if profit >= TRAIL_TRIGGER:
                    trail_stop = state[sym]["highest"] * (1 - TRAIL_GAP)
                    if last <= trail_stop:
                        exch.create_market_order(sym,'sell',qty,
                            params={'reduceOnly':True})
                        state.pop(sym,None)
                        bot.send_message(MY_CHAT_ID,f"🎯 TRAIL EXIT {sym}")
                        continue

            time.sleep(3)

        except:
            time.sleep(3)

# --- SCANNER ---
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
            candidates = candidates[:120]

            pos = exch.fetch_positions()
            active = [p for p in pos if safe(p.get('contracts')) > 0]

            for sym,_ in candidates:

                if len(active) >= MAX_POS:
                    break

                candles = exch.fetch_ohlcv(sym,'5m',limit=30)
                closes = [c[4] for c in candles]
                opens = [c[1] for c in candles]
                highs = [c[2] for c in candles]
                volumes = [c[5] for c in candles]

                last_close = closes[-1]
                last_open = opens[-1]

                if (last_close-last_open)/last_open > SPIKE_LIMIT:
                    continue

                avg_vol = sum(volumes[-10:])/10
                volume_spike = volumes[-1] > avg_vol*1.4

                ema9 = sum(closes[-9:])/9
                ema21 = sum(closes[-21:])/21

                breakout = highs[-1] > max(highs[:-1])
                trend = ema9 > ema21

                if volume_spike and (breakout or trend):
                    open_trade(sym)

            time.sleep(8)

        except:
            time.sleep(8)

@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return
    if msg.text.lower()=="dur":
        os._exit(0)

if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🔥 AVCI V7 AKTİF")
    bot.infinity_polling()
