import os, time, telebot, ccxt, threading, re
from google import genai

TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# ===============================
# ⚙️ YENİ AKILLI AYARLAR
# ===============================

MAX_POSITIONS = 2           # Aynı anda max 2 işlem
MIN_PROFIT_USDT = 0.8       # 0.8 USDT olmadan kapatma
TRAILING_GAP = 0.35         # Kâr geri çekilme mesafesi
MIN_HOLD_SEC = 60           # En az 60 sn açık kalır

highest_profits = {}

# ===============================
# EXCHANGE
# ===============================
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

# ===============================
# 🚀 AKILLI İŞLEM AÇMA (BAKİYEYE GÖRE)
# ===============================
def open_trade(symbol, side):

    exch = get_exch()
    exch.load_markets()

    # Açık pozisyon sayısını kontrol et
    pos = exch.fetch_positions()
    active = [p for p in pos if safe_num(p.get('contracts')) > 0]

    if len(active) >= MAX_POSITIONS:
        return "⚠️ Maksimum 2 işlem açık"

    bal = exch.fetch_balance({'type':'swap'})
    free_usdt = safe_num(bal.get('USDT', {}).get('free',0))

    if free_usdt < 5:
        return "⚠️ Bakiye çok düşük"

    # Bakiyenin %45'i
    margin = free_usdt * 0.45
    lev = 10

    exact_sym = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
    if not exact_sym:
        return "⚠️ Coin bulunamadı"

    exch.set_leverage(lev, exact_sym)

    ticker = exch.fetch_ticker(exact_sym)
    price = safe_num(ticker['last'])

    qty = (margin * lev) / price
    qty = float(exch.amount_to_precision(exact_sym, qty))

    order = exch.create_market_order(
        exact_sym,
        'buy' if side == "long" else 'sell',
        qty
    )

    highest_profits[exact_sym] = 0
    order['openTime'] = time.time()

    return f"⚔️ İşlem açıldı: {exact_sym}"

# ===============================
# 🧠 GELİŞMİŞ TRAILING YÖNETİCİ
# ===============================
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
                last = safe_num(ticker['last'])

                profit = (last-entry)*qty if side=='long' else (entry-last)*qty

                # En az açık kalma süresi
                if time.time() - p['timestamp']/1000 < MIN_HOLD_SEC:
                    continue

                if profit > highest_profits.get(sym,0):
                    highest_profits[sym] = profit

                # Küçük kârda kapatma
                if profit < MIN_PROFIT_USDT:
                    continue

                # Trailing stop
                if highest_profits[sym] - profit > TRAILING_GAP:

                    exch.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly': True}
                    )

                    bot.send_message(CHAT_ID, f"💰 KAR ALINDI {sym}: {profit:.2f} USDT")
                    highest_profits.pop(sym, None)

            time.sleep(5)

        except:
            time.sleep(5)

# ===============================
# 🤖 MARKET SCANNER (ALT/MEME)
# ===============================
def market_scanner():

    while True:
        try:
            exch = get_exch()
            markets = [m['symbol'] for m in exch.load_markets().values()
                       if ':USDT' in m['symbol']
                       and safe_num(m.get('quoteVolume',0)) < 100000]

            best = None
            best_score = -999

            for sym in markets[:50]:
                t = exch.fetch_ticker(sym)
                change = safe_num(t.get('percentage',0))

                if abs(change) > best_score:
                    best_score = abs(change)
                    best = sym

            if best:
                open_trade(best, "long" if best_score > 0 else "short")

            time.sleep(20)

        except:
            time.sleep(10)

# ===============================
# 🚀 BAŞLAT
# ===============================
if __name__ == "__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
