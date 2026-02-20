import os, time, telebot, ccxt, threading, re

# --- BAĞLANTILAR ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TOKEN)

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
        return float(re.sub(r'[^0-9.]', '', str(val)))
    except:
        return 0.0

# ================= MASTER AYARLAR =================

RISK_PERCENT = 0.08   # bakiyenin %8'i
MIN_MARGIN = 2        # minimum 2 USDT
MAX_MARGIN = 20       # maksimum 20 USDT
MAX_POSITIONS = 2
LEVERAGE = 5

TP_PERCENT = 0.03
SL_PERCENT = 0.06
TRAIL_PERCENT = 0.015

highest_profits = {}

# ================= AKILLI POZİSYON HESABI =================

def calc_margin(free_usdt):
    margin = free_usdt * RISK_PERCENT
    return max(MIN_MARGIN, min(MAX_MARGIN, margin))

# ================= GİRİŞ FİLTRESİ =================

def good_entry(exch, symbol):
    candles = exch.fetch_ohlcv(symbol, '1m', limit=20)
    prices = [c[4] for c in candles]
    last = prices[-1]
    avg = sum(prices) / len(prices)

    # Fiyat ortalamanın üstündeyse tepede say → long açma
    return last < avg

# ================= EMİR AÇMA =================

def open_trade(symbol):
    exch = get_exch()
    exch.load_markets()

    # aktif pozisyon kontrolü
    pos = exch.fetch_positions()
    active = [p for p in pos if safe_num(p.get('contracts')) > 0]
    if len(active) >= MAX_POSITIONS:
        return

    bal = exch.fetch_balance({'type': 'swap'})
    free_usdt = safe_num(bal.get('USDT', {}).get('free', 0))
    if free_usdt < MIN_MARGIN:
        return

    margin = calc_margin(free_usdt)

    exact_sym = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
    if not exact_sym:
        return

    if not good_entry(exch, exact_sym):
        return  # tepeden giriş engellendi

    exch.set_leverage(LEVERAGE, exact_sym)

    ticker = exch.fetch_ticker(exact_sym)
    price = ticker['last']

    qty = (margin * LEVERAGE) / price
    qty = float(exch.amount_to_precision(exact_sym, qty))

    order = exch.create_market_order(exact_sym, 'buy', qty)

    highest_profits[exact_sym] = 0

    bot.send_message(CHAT_ID,
        f"⚔️ MASTER İŞLEM AÇILDI\n"
        f"Sembol: {exact_sym}\n"
        f"Marjin: {margin:.2f} USDT\n"
        f"Kaldıraç: {LEVERAGE}x\n"
        f"ID: {order['id']}"
    )

# ================= KAR / ZARAR YÖNETİMİ =================

def auto_manager():
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()

            for p in [p for p in pos if safe_num(p.get('contracts')) > 0]:

                sym = p['symbol']
                side = p['side']
                qty = safe_num(p.get('contracts'))
                entry = safe_num(p.get('entryPrice'))

                ticker = exch.fetch_ticker(sym)
                last = ticker['last']

                profit = (last-entry)*qty if side=='long' else (entry-last)*qty

                if sym not in highest_profits or profit > highest_profits[sym]:
                    highest_profits[sym] = profit

                # STOP LOSS
                if profit <= -(entry * SL_PERCENT):
                    exch.create_market_order(sym, 'sell', qty, params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ STOP LOSS: {sym}")
                    highest_profits.pop(sym, None)

                # TAKE PROFIT + TRAILING
                elif profit >= (entry * TP_PERCENT):
                    if highest_profits[sym] - profit >= (entry * TRAIL_PERCENT):
                        exch.create_market_order(sym, 'sell', qty, params={'reduceOnly': True})
                        bot.send_message(CHAT_ID, f"💰 KAR ALINDI: {sym}")
                        highest_profits.pop(sym, None)

            time.sleep(3)
        except:
            time.sleep(3)

# ================= MARKET SCANNER =================

def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = [m['symbol'] for m in exch.load_markets().values()
                       if ':USDT' in m['symbol']
                       and all(x not in m['symbol'] for x in ['BTC','ETH','SOL'])]

            for sym in markets[:5]:
                open_trade(sym)

            time.sleep(10)
        except:
            time.sleep(10)

# ================= BOT BAŞLAT =================

if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    threading.Thread(target=market_scanner, daemon=True).start()
    bot.infinity_polling()
