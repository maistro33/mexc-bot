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

# 🧿 SABİT AYARLAR
MAX_POSITIONS = 2
MARGIN = 2
LEVERAGE = 5
highest_profits = {}
MIN_HOLD_SEC = 90

# ❌ GİRİLMESİN İSTENEN COINLER
BANNED = ['BTC','ETH','SOL','BCH','LTC','XRP','ADA','DOGE','BNB']

# --- EMİR AÇMA ---
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()

        # ❌ AYNI COIN VARSA GİRME
        for p in pos:
            if safe_num(p.get('contracts'))>0 and symbol in p['symbol']:
                return

        active = [p for p in pos if safe_num(p.get('contracts'))>0]
        if len(active) >= MAX_POSITIONS:
            return

        exact = next((s for s in exch.markets if symbol in s and ':USDT' in s), None)
        if not exact: return

        try: exch.set_leverage(LEVERAGE, exact)
        except: pass

        ticker = exch.fetch_ticker(exact)
        price = safe_num(ticker['last'])

        qty = (MARGIN * LEVERAGE) / price
        qty = float(exch.amount_to_precision(exact, qty))

        order = exch.create_market_order(
            exact,
            'buy' if side=='long' else 'sell',
            qty
        )

        highest_profits[exact] = 0

        bot.send_message(MY_CHAT_ID,
            f"⚔️ AKILLI GİRİŞ\n{exact}\n{side.upper()}\nMargin:{MARGIN} USDT")

    except:
        pass

# --- KAR & STOP YÖNETİMİ ---
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

                if sym not in highest_profits or profit>highest_profits[sym]:
                    highest_profits[sym]=profit

                margin = safe_num(p.get('margin'))

                # 🛡️ STOP LOSS (uzak)
                if profit <= -(margin*0.08):
                    exch.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True})

                # 💰 TAKE PROFIT
                elif profit >= margin*0.05:
                    exch.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True})

                # 🔄 TRAILING
                elif highest_profits.get(sym,0) >= margin*0.07 and \
                     highest_profits[sym]-profit >= margin*0.02:
                    exch.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True})

            time.sleep(4)
        except:
            time.sleep(4)

# --- AKILLI MARKET SCANNER ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()

            for m in markets.values():
                sym = m['symbol']

                if ':USDT' not in sym:
                    continue

                if any(b in sym for b in BANNED):
                    continue

                ticker = exch.fetch_ticker(sym)

                change = safe_num(ticker.get('percentage',0))
                volume = safe_num(ticker.get('quoteVolume',0))

                # ❌ hacim çoksa girme
                if volume > 50000:
                    continue

                # 🔴 TEPEDEN SHORT
                if change > 5:
                    open_trade(sym,'short')

                # 🟢 DİPTEN LONG
                elif change < -5:
                    open_trade(sym,'long')

            time.sleep(20)
        except:
            time.sleep(20)

# --- TELEGRAM ---
@bot.message_handler(func=lambda m: True)
def handle(m):
    if str(m.chat.id) != str(MY_CHAT_ID):
        return

    if 'dur' in m.text.lower():
        bot.send_message(MY_CHAT_ID,"Bot durduruldu")
        os._exit(0)

# --- BAŞLAT ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
