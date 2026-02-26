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

def safe_num(x):
    try: return float(x)
    except: return 0.0

# --- AYARLAR ---
MARGIN_PER_TRADE = 1        # 1 USDT TEST
LEVERAGE = 5                # 5x
MAX_POSITIONS = 1           # Aynı anda 1
STOP_USDT = 0.3
TRAIL_USDT = 0.25

MIN_24H_CHANGE = 20         # %20 üstü pump adayı
MAX_DAILY_TRADES = 3

highest_profits = {}
daily_trades = 0
day_reset = time.time()

BANNED = ['BTC','ETH','XRP','SOL','BNB','ADA','AVAX']

# --- EMİR ---
def open_trade(symbol, side):
    global daily_trades

    if daily_trades >= MAX_DAILY_TRADES:
        return

    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()
        active = [p for p in pos if safe_num(p.get('contracts'))>0]

        if len(active) >= MAX_POSITIONS:
            return

        ticker = exch.fetch_ticker(symbol)
        price = safe_num(ticker['last'])

        qty = (MARGIN_PER_TRADE * LEVERAGE) / price
        qty = float(exch.amount_to_precision(symbol, qty))

        exch.create_market_order(symbol,"buy",qty)

        highest_profits[symbol] = 0
        daily_trades += 1

        bot.send_message(
            MY_CHAT_ID,
            f"🎯 PUMP AVCI {symbol} LONG açtı"
        )

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"Hata: {e}")

# --- KAR YÖNETİMİ ---
def auto_manager():
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()

            for p in [p for p in pos if safe_num(p.get('contracts'))>0]:

                sym = p['symbol']
                qty = safe_num(p.get('contracts'))
                entry = safe_num(p.get('entryPrice'))

                ticker = exch.fetch_ticker(sym)
                last = safe_num(ticker['last'])

                profit = (last-entry)*qty

                if profit > highest_profits.get(sym,0):
                    highest_profits[sym] = profit

                # STOP
                if profit <= -STOP_USDT:
                    exch.create_market_order(
                        sym,'sell',qty,
                        params={'reduceOnly':True}
                    )
                    highest_profits.pop(sym,None)

                # TRAILING
                elif highest_profits[sym] >= TRAIL_USDT and \
                     (highest_profits[sym]-profit)>=0.15:

                    exch.create_market_order(
                        sym,'sell',qty,
                        params={'reduceOnly':True}
                    )
                    highest_profits.pop(sym,None)

            time.sleep(3)

        except:
            time.sleep(3)

# --- AVCI SCANNER ---
def market_scanner():
    global daily_trades, day_reset

    while True:
        try:
            # Günlük reset
            if time.time() - day_reset > 86400:
                daily_trades = 0
                day_reset = time.time()

            exch = get_exch()
            markets = exch.load_markets()

            pos = exch.fetch_positions()
            active = [p for p in pos if safe_num(p.get('contracts'))>0]

            for m in markets.values():

                sym = m['symbol']

                if ':USDT' not in sym:
                    continue

                if any(x in sym for x in BANNED):
                    continue

                if len(active) >= MAX_POSITIONS:
                    break

                ticker = exch.fetch_ticker(sym)
                change = safe_num(ticker.get('percentage'))

                if change < MIN_24H_CHANGE:
                    continue

                candles = exch.fetch_ohlcv(sym,'5m',limit=15)
                closes = [c[4] for c in candles]
                volumes = [c[5] for c in candles]

                # SIKIŞMA
                range_size = max(closes[:-1]) - min(closes[:-1])

                # Hacim patlaması
                avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
                volume_spike = volumes[-1] > avg_vol * 1.8

                # KIRILIM
                breakout_up = closes[-1] > max(closes[:-1])

                if range_size/closes[-1] < 0.01 and breakout_up and volume_spike:
                    open_trade(sym,"long")

            time.sleep(10)

        except:
            time.sleep(10)

# --- TELEGRAM ---
@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID): return

    if msg.text.lower()=="dur":
        bot.send_message(MY_CHAT_ID,"Bot durduruldu")
        os._exit(0)

# --- BAŞLAT ---
if __name__=="__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🚀 PUMP AVCI BOT aktif")
    bot.infinity_polling()
