import os, time, telebot, ccxt, threading, re, json
from decimal import Decimal, getcontext

# Hassasiyeti artırıyoruz ki sayı kayması olmasın
getcontext().prec = 20

from google import genai

# --- [BAGLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [EVRENSEL SAYI TEMİZLEYİCİ] ---
def safe_num(val):
    """Her türlü karakter karmaşasından sadece sayıyı süzer."""
    try:
        if val is None: return 0.0
        # Sayı dışındaki her şeyi (virgül dahil) temizle, noktayı tut
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except:
        return 0.0

SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget operatörüsün.
Kullanıcıyla 'dostum' diye konuş.
KOMUTLAR:
1. @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
2. @@[ACTION: CLOSE, SYMBOL]@@
3. @@[ACTION: SL, SYMBOL, PERCENT]@@
Hata istemiyorum, doğrudan tetiğe bas!
"""

def execute_trade(decision):
    try:
        exch = get_exch()
        exch.load_markets()

        # --- [1. POZİSYON KAPATMA] ---
        if "@@[ACTION: CLOSE" in decision:
            match = re.search(r"@@\[ACTION: CLOSE,\s*([^,\]]+)\]@@", decision)
            if match:
                symbol = match.group(1).strip().upper()
                exact_sym = next((s for s in exch.markets if symbol in s and ':USDT' in s), None)
                if exact_sym:
                    pos = exch.fetch_positions()
                    cp = next((p for p in pos if p['symbol'] == exact_sym and safe_num(p.get('contracts')) > 0), None)
                    if cp:
                        side = 'sell' if cp['side'] == 'long' else 'buy'
                        exch.create_market_order(exact_sym, side, safe_num(cp['contracts']), params={'reduceOnly': True})
                        return f"✅ {exact_sym} piyasadan kapatıldı dostum."

        # --- [2. GERÇEK STOP LOSS (SL)] ---
        if "@@[ACTION: SL" in decision:
            match = re.search(r"@@\[ACTION: SL,\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                symbol, pct = match.groups()
                exact_sym = next((s for s in exch.markets if symbol.strip().upper() in s and ':USDT' in s), None)
                if exact_sym:
                    pos = exch.fetch_positions()
                    cp = next((p for p in pos if p['symbol'] == exact_sym and safe_num(p.get('contracts')) > 0), None)
                    if cp:
                        entry = safe_num(cp['entryPrice'])
                        side = cp['side']
                        dist = safe_num(pct) / 100
                        sl_price = entry * (1 - dist) if side == 'long' else entry * (1 + dist)
                        sl_price = float(exch.price_to_precision(exact_sym, sl_price))
                        
                        # Bitget Trigger Order
                        params = {'stopPrice': sl_price, 'reduceOnly': True}
                        exch.create_order(exact_sym, 'market', ('sell' if side == 'long' else 'buy'), safe_num(cp['contracts']), None, params)
                        return f"🛡️ **STOP KOYULDU:** {exact_sym} için SL seviyesi: {sl_price}"

        # --- [3. YENİ İŞLEM AÇMA] ---
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                symbol, side_raw, lev_raw, amt_raw = match.groups()
                exact_sym = next((s for s in exch.markets if symbol.strip().upper() in s and ':USDT' in s), None)
                if exact_sym:
                    lev = int(safe_num(lev_raw))
                    amt = safe_num(amt_raw)
                    side = 'buy' if 'BUY' in side_raw.upper() or 'LONG' in side_raw.upper() else 'sell'
                    
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (amt * lev) / safe_num(ticker['last'])
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
                        return f"🚀 **İŞLEM AÇILDI:** {exact_sym} | {side.upper()} | {lev}x"
        return None
    except Exception as e:
        return f"⚠️ Operasyon Hatası: {str(e)}"

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            active_p = [f"{p['symbol']} ROE:%{p.get('percentage', 0)}" for p in pos if safe_num(p.get('contracts')) > 0]
            
            prompt = f"CÜZDAN BİLGİSİ: {active_p}\nKullanıcı: '{message.text}'\n\nAnaliz et ve @@ formatıyla aksiyon al."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            bot.reply_to(message, response.split("@@")[0].strip())
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        except Exception as e:
            bot.reply_to(message, f"Hata: {e}")

if __name__ == "__main__":
    print("Gemini 3 Flash: Karakter Filtresi Aktif!")
    bot.infinity_polling()
