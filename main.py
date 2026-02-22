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
    try: return float(x)
    except: return 0.0

# --- AYARLAR ---
MARGIN_PER_TRADE = 2
LEVERAGE = 10
MAX_POSITIONS = 3
STOP_USDT = 0.4
TRAIL_USDT = 0.2
highest_profits = {}

BANNED = ['BTC','ETH','XRP','SOL']  # Büyük coinler hariç

# --- EMİR ---
def open_trade(symbol, side, entry_price):
    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()
        active = [p for p in pos if safe_num(p.get('contracts'))>0]
        if len(active) >= MAX_POSITIONS: return
        if any(p['symbol']==symbol for p in active): return

        # Açık limit emir kontrolü
        open_orders = exch.fetch_open_orders(symbol)
        if open_orders: return

        ticker = exch.fetch_ticker(symbol)
        price = entry_price or safe_num(ticker['last'])

        qty = (MARGIN_PER_TRADE * LEVERAGE) / price
        qty = float(exch.amount_to_precision(symbol, qty))

        # Limit emir → düşük masraf
        order_price = price*0.998 if side=="long" else price*1.002

        exch.create_limit_order(
            symbol,
            "buy" if side=="long" else "sell",
            qty,
            order_price
        )

        highest_profits[symbol] = 0

        bot.send_message(
            MY_CHAT_ID,
            f"⚔️ {symbol} {side.upper()} açıldı — {MARGIN_PER_TRADE} USDT"
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

                # STOP LOSS
                if profit <= -STOP_USDT:
                    exch.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    highest_profits.pop(sym,None)
                    continue

                # TRAILING
                elif highest_profits[sym] >= TRAIL_USDT and \
                     (highest_profits[sym]-profit)>=0.2:
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

# --- SCANNER (TREND + MOMENTUM + MINI PULLBACK) ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()
            pos = exch.fetch_positions()
            active = [p for p in pos if safe_num(p.get('contracts'))>0]

            for m in markets.values():
                sym = m['symbol']
                if ':USDT' not in sym: continue
                if any(x in sym for x in BANNED): continue
                if len(active) >= MAX_POSITIONS: break

                candles = exch.fetch_ohlcv(sym,'5m',limit=21)
                closes = [c[4] for c in candles]
                volumes = [c[5] for c in candles]

                # EMA ve Trend
                ema_short = sum(closes[-9:])/9
                ema_long = sum(closes[-21:])/21
                macd_line = ema_short - ema_long
                trend_up = macd_line > 0 and ema_short > ema_long
                trend_down = macd_line < 0 and ema_short < ema_long

                # Hacim patlaması
                if volumes[-1] > sum(volumes[:-1]):

                    # Momentum + mini pullback + trend uyumu
                    if trend_up and closes[-2] > closes[-3] and closes[-1] > closes[-2]:
                        entry_price = closes[-1]
                        open_trade(sym,"long",entry_price)

                    elif trend_down and closes[-2] < closes[-3] and closes[-1] < closes[-2]:
                        entry_price = closes[-1]
                        open_trade(sym,"short",entry_price)

            time.sleep(5)
        except:
            time.sleep(5)

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
    bot.send_message(MY_CHAT_ID,"🚀 Bot aktif")
    bot.infinity_polling()
