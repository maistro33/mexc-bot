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
    except:
        return 0.0

# --- AYARLAR ---
FIXED_MARGIN = 2      # SABİT 2 USDT
LEVERAGE = 5
MAX_POSITIONS = 2
MIN_HOLD_SEC = 60
highest_profits = {}

# --- İŞLEM AÇMA (EKLEME YOK) ---
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()

        pos = exch.fetch_positions()

        # ❌ AYNI COINDE VARSA GİRME
        for p in pos:
            if safe_num(p.get('contracts')) > 0 and symbol in p['symbol']:
                return

        # ❌ MAKS POZİSYON
        active = [p for p in pos if safe_num(p.get('contracts')) > 0]
        if len(active) >= MAX_POSITIONS:
            return

        exact_sym = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
        if not exact_sym:
            return

        try:
            exch.set_leverage(LEVERAGE, exact_sym)
        except:
            pass

        ticker = exch.fetch_ticker(exact_sym)
        last_price = safe_num(ticker['last'])

        qty = (FIXED_MARGIN * LEVERAGE) / last_price
        min_qty = exch.markets[exact_sym]['limits']['amount']['min']
        qty = max(qty, min_qty)
        qty = float(exch.amount_to_precision(exact_sym, qty))

        exch.create_market_order(exact_sym, 'buy' if side=='long' else 'sell', qty)

        highest_profits[exact_sym] = 0

        bot.send_message(MY_CHAT_ID,
            f"🛡️ MASTER GİRİŞ\n{exact_sym}\nYön: {side.upper()}\nMargin: {FIXED_MARGIN} USDT")

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"HATA: {e}")

# --- STOP + TP + TRAILING ---
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

                stop_loss = -1.5      # uzak SL
                take_profit = 2.0     # TP
                trailing = 1.0        # trailing

                # 🛑 STOP LOSS
                if profit <= stop_loss:
                    exch.create_market_order(sym,'sell' if side=='long' else 'buy',qty,params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID,f"🛑 STOP LOSS: {sym}")
                    highest_profits.pop(sym,None)

                # 💰 TAKE PROFIT
                elif profit >= take_profit:
                    exch.create_market_order(sym,'sell' if side=='long' else 'buy',qty,params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID,f"💰 TP ALINDI: {sym}")
                    highest_profits.pop(sym,None)

                # 🔄 TRAILING
                elif highest_profits[sym] >= trailing and (highest_profits[sym] - profit) >= 0.5:
                    exch.create_market_order(sym,'sell' if side=='long' else 'buy',qty,params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID,f"🔄 TRAILING: {sym}")
                    highest_profits.pop(sym,None)

            time.sleep(3)
        except:
            time.sleep(3)

# --- BASİT SCANNER ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = [m['symbol'] for m in exch.load_markets().values() if ':USDT' in m['symbol']]

            for sym in markets[:10]:
                ticker = exch.fetch_ticker(sym)
                change = safe_num(ticker.get('percentage',0))

                if change > 2:
                    open_trade(sym,'long')
                elif change < -2:
                    open_trade(sym,'short')

            time.sleep(15)
        except:
            time.sleep(15)

# --- BAŞLAT ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
