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
        'enableRateLimit': True
    })

def safe_num(x):
    try: 
        return float(x)
    except: 
        return 0.0

# --- AYARLAR ---
MARGIN_PER_TRADE = 2
LEVERAGE = 10
MAX_POSITIONS = 2   # 3 yerine 2 (daha güvenli)

STOP_USDT = 0.4
TRAIL_USDT = 0.45   # Daha büyük kâr bekle
highest_profits = {}

BANNED = ['BTC','ETH','XRP','SOL']

# --- EMİR ---
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()
        active = [p for p in pos if safe_num(p.get('contracts'))>0]

        if len(active) >= MAX_POSITIONS:
            return

        if any(p['symbol']==symbol for p in active):
            return

        ticker = exch.fetch_ticker(symbol)
        price = safe_num(ticker['last'])

        qty = (MARGIN_PER_TRADE * LEVERAGE) / price
        qty = float(exch.amount_to_precision(symbol, qty))

        exch.set_leverage(LEVERAGE, symbol)

        exch.create_market_order(
            symbol,
            "buy" if side=="long" else "sell",
            qty
        )

        highest_profits[symbol] = 0

        bot.send_message(
            MY_CHAT_ID,
            f"🎯 AVCI BOT {symbol} {side.upper()} açtı"
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
                side = p['side']
                qty = safe_num(p.get('contracts'))
                entry = safe_num(p.get('entryPrice'))

                ticker = exch.fetch_ticker(sym)
                last = safe_num(ticker['last'])

                profit = (last-entry)*qty if side=="long" else (entry-last)*qty

                if profit > highest_profits.get(sym,0):
                    highest_profits[sym] = profit

                # STOP
                if profit <= -STOP_USDT:
                    exch.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    highest_profits.pop(sym,None)

                # TRAILING (daha mantıklı)
                elif highest_profits.get(sym,0) >= TRAIL_USDT and \
                     (highest_profits[sym]-profit) >= 0.20:

                    exch.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    highest_profits.pop(sym,None)

            time.sleep(3)

        except:
            time.sleep(3)

# --- AVCI SCANNER ---
def market_scanner():
    while True:
        try:
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

                candles = exch.fetch_ohlcv(sym,'5m',limit=12)
                closes = [c[4] for c in candles]
                volumes = [c[5] for c in candles]

                # SIKIŞMA kontrolü (daha sıkı)
                range_size = max(closes[:-1]) - min(closes[:-1])

                volume_spike = volumes[-1] > sum(volumes[:-1]) / len(volumes[:-1])

                breakout_up = closes[-1] > max(closes[:-1])
                breakout_down = closes[-1] < min(closes[:-1])

                # LONG
                if range_size/closes[-1] < 0.006 and breakout_up and volume_spike:
                    open_trade(sym,"long")

                # SHORT
                if range_size/closes[-1] < 0.006 and breakout_down and volume_spike:
                    open_trade(sym,"short")

            time.sleep(5)

        except:
            time.sleep(5)

# --- TELEGRAM ---
@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID): 
        return

    if msg.text.lower()=="dur":
        bot.send_message(MY_CHAT_ID,"Bot durduruldu")
        os._exit(0)

# --- BAŞLAT ---
if __name__=="__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🚀 AVCI BOT DENGELİ SÜRÜM AKTİF")
    bot.infinity_polling()
