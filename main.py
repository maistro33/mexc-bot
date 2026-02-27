import os, time, telebot, ccxt, threading

# --- BAĞLANTILAR ---
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASS')

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

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

# --- AYARLAR (10x CROSS OPTIMIZE) ---
MARGIN_PER_TRADE = 0.55
LEVERAGE = 10
MAX_POSITIONS = 2

STOP_USDT = 0.25          # max zarar
TRAIL_START = 0.40        # trailing başlat
TRAIL_GAP = 0.15          # geri verme toleransı

BANNED = ['BTC','ETH','BNB','SOL','XRP']
highest_profit = {}

# --- EMİR AÇ ---
def open_trade(symbol):

    try:
        exch = get_exch()
        exch.load_markets()

        positions = exch.fetch_positions()
        active = [p for p in positions if safe(p.get('contracts')) > 0]

        if len(active) >= MAX_POSITIONS:
            return

        if any(p['symbol'] == symbol for p in active):
            return

        ticker = exch.fetch_ticker(symbol)
        price = safe(ticker['last'])

        qty = (MARGIN_PER_TRADE * LEVERAGE) / price
        qty = float(exch.amount_to_precision(symbol, qty))

        exch.create_market_order(symbol, 'buy', qty)

        highest_profit[symbol] = 0

        bot.send_message(MY_CHAT_ID, f"🚀 LONG AÇILDI\n{symbol}")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"HATA OPEN: {e}")

# --- KAR YÖNETİMİ ---
def auto_manager():
    while True:
        try:
            exch = get_exch()
            positions = exch.fetch_positions()

            for p in positions:
                if safe(p.get('contracts')) <= 0:
                    continue

                sym = p['symbol']
                qty = safe(p.get('contracts'))
                entry = safe(p.get('entryPrice'))

                ticker = exch.fetch_ticker(sym)
                last = safe(ticker['last'])

                profit = (last - entry) * qty

                # En yüksek kar kaydı
                if profit > highest_profit.get(sym, 0):
                    highest_profit[sym] = profit

                # STOP
                if profit <= -STOP_USDT:
                    exch.create_market_order(
                        sym,
                        'sell',
                        qty,
                        params={'reduceOnly': True}
                    )
                    highest_profit.pop(sym, None)
                    bot.send_message(MY_CHAT_ID, f"❌ STOP\n{sym}")
                    continue

                # TRAILING
                if highest_profit.get(sym, 0) >= TRAIL_START:
                    if (highest_profit[sym] - profit) >= TRAIL_GAP:
                        exch.create_market_order(
                            sym,
                            'sell',
                            qty,
                            params={'reduceOnly': True}
                        )
                        highest_profit.pop(sym, None)
                        bot.send_message(MY_CHAT_ID, f"💰 TRAIL KAR\n{sym}")

            time.sleep(3)

        except:
            time.sleep(3)

# --- PUMP ERKEN YAKALAMA ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()

            positions = exch.fetch_positions()
            active = [p for p in positions if safe(p.get('contracts')) > 0]

            for m in markets.values():

                sym = m['symbol']

                if ':USDT' not in sym:
                    continue

                if any(b in sym for b in BANNED):
                    continue

                if len(active) >= MAX_POSITIONS:
                    break

                candles = exch.fetch_ohlcv(sym, '5m', limit=6)
                closes = [c[4] for c in candles]
                volumes = [c[5] for c in candles]

                if len(closes) < 6:
                    continue

                # Erken pump sinyali
                last_change = (closes[-1] - closes[-2]) / closes[-2]
                volume_spike = volumes[-1] > (sum(volumes[:-1]) / 5) * 1.5

                if last_change > 0.015 and volume_spike:
                    open_trade(sym)

            time.sleep(4)

        except:
            time.sleep(4)

# --- TELEGRAM ---
@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return

    if msg.text.lower() == "dur":
        bot.send_message(MY_CHAT_ID, "Bot durduruldu")
        os._exit(0)

# --- BAŞLAT ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    threading.Thread(target=market_scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "🔥 AVCI BOT V3 AKTİF")
    bot.infinity_polling()
