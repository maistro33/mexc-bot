import os, time, telebot, ccxt, threading, re

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

def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- SABİT AYARLAR ---
MAX_POSITIONS = 2
MARGIN_PER_TRADE = 2      # ✅ TAM 2 USDT
LEVERAGE = 5
STOP_LOSS_PERCENT = 0.05
TRAILING_PERCENT = 0.015
highest_profits = {}
MIN_HOLD_SEC = 60

# --- EMİR AÇMA ---
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()

        # açık pozisyon sayısı
        pos = exch.fetch_positions()
        active = [p for p in pos if safe_num(p.get('contracts')) > 0]
        if len(active) >= MAX_POSITIONS:
            return

        # bakiye kontrol
        bal = exch.fetch_balance({'type':'swap'})
        free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
        if free_usdt < MARGIN_PER_TRADE:
            return

        exact_sym = symbol

        try: exch.set_leverage(LEVERAGE, exact_sym)
        except: pass

        ticker = exch.fetch_ticker(exact_sym)
        last_price = safe_num(ticker['last'])

        # ✅ TAM 2 USDT işlem hesaplama
        qty = (MARGIN_PER_TRADE * LEVERAGE) / last_price
        qty_precision = float(exch.amount_to_precision(exact_sym, qty))

        # dipten long / tepeden short
        order_price = last_price * 0.998 if side=='long' else last_price * 1.002

        exch.create_limit_order(
            exact_sym,
            'buy' if side=='long' else 'sell',
            qty_precision,
            order_price
        )

        highest_profits[exact_sym] = 0

        bot.send_message(
            MY_CHAT_ID,
            f"⚔️ İşlem açıldı: {exact_sym}\nYön: {side.upper()}\nMiktar: 2 USDT"
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

                profit = (last-entry)*qty if side=='long' else (entry-last)*qty

                if sym not in highest_profits or profit > highest_profits[sym]:
                    highest_profits[sym] = profit

                stop_loss_usdt = 0.5
                trailing_usdt = 0.5

                if profit <= -stop_loss_usdt:
                    exch.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    highest_profits.pop(sym,None)

                elif highest_profits[sym] >= trailing_usdt and \
                     (highest_profits[sym] - profit) >= 0.2:

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

# --- MARKET SCANNER ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()

            for m in markets.values():

                sym = m['symbol']

                # sadece USDT vadeli
                if ':USDT' not in sym:
                    continue

                # büyük coinleri atla
                if any(x in sym for x in ['BTC','ETH','XRP','SOL']):
                    continue

                ticker = exch.fetch_ticker(sym)

                change_pct = safe_num(ticker.get('percentage',0))
                volume = safe_num(ticker.get('quoteVolume',0))

                # pump/dump adayı
                if volume < 200:
                    continue

                # 🔥 yükseliyorsa short fırsatı
                if change_pct >= 5:
                    open_trade(sym, 'short')

                # 🔥 sert düşmüşse dipten long
                elif change_pct <= -5:
                    open_trade(sym, 'long')

            time.sleep(5)

        except:
            time.sleep(5)

# --- TELEGRAM ---
@bot.message_handler(func=lambda message: True)
def handle(message):
    if str(message.chat.id) != str(MY_CHAT_ID): return

    if message.text.lower() == "dur":
        bot.send_message(MY_CHAT_ID,"Bot durduruldu")
        os._exit(0)

# --- BAŞLAT ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🚀 Bot başlatıldı")
    bot.infinity_polling()
