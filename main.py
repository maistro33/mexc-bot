import os, time, telebot, ccxt, threading, re, json
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

# --- [GERÇEK OPERATÖR TALİMATI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget'te CANLI bir operatörsün.
1. Kullanıcı 'KAPAT' veya 'SAT' derse, hiçbir mazeret üretme, analiz yapma, doğrudan @@[ACTION: CLOSE, SYMBOL]@@ formatını kullan.
2. İşlem açarken: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
3. Bot her zaman 'dostum' diye hitap eder ve CANLI VERİYE göre konuşur.
4. Eğer pozisyon zarardaysa ve kullanıcı kapatmak istiyorsa 'bekleyelim' deme, emri uygula!
"""

# --- [MÜDAHALE VE İŞLEM MOTORU] ---
def execute_trade(decision):
    try:
        exch = get_exch()
        # POZİSYON KAPATMA KOMUTU
        if "@@[ACTION: CLOSE" in decision:
            match = re.search(r"@@\[ACTION: CLOSE,\s*([^,\]]+)\]@@", decision)
            if match:
                raw_sym = match.group(1).strip().upper().replace('/USDT', '')
                exch.load_markets()
                exact_sym = next((s for s in exch.markets if raw_sym in s and ':USDT' in s), None)
                if exact_sym:
                    pos = exch.fetch_positions()
                    current_p = next((p for p in pos if p['symbol'] == exact_sym and float(p.get('contracts', 0)) > 0), None)
                    if current_p:
                        side_to_close = 'sell' if current_p['side'] == 'long' else 'buy'
                        exch.create_market_order(exact_sym, 'market', side_to_close, float(current_p['contracts']), params={'reduceOnly': True})
                        return f"✅ **EMİR ALINDI:** {exact_sym} pozisyonunu piyasa fiyatından kapattım dostum."
            return "⚠️ Kapatılacak pozisyon bulunamadı."

        # YENİ İŞLEM AÇMA KOMUTU
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exch.load_markets()
                clean_sym = raw_sym.strip().upper().replace('/USDT', '')
                exact_sym = next((s for s in exch.markets if clean_sym in s and ':USDT' in s), None)
                
                if exact_sym:
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    exch.create_market_order(exact_sym, 'market', side, qty)
                    return f"🚀 **İŞLEM AÇILDI:** {exact_sym} {lev}x {side.upper()}"
        return None
    except Exception as e:
        return f"⚠️ Operasyon Hatası: {str(e)}"

# --- [CANLI DİNLEME VE CEVAPLAMA] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            # 1. ANLIK BORSA DURUMUNU ÇEK
            pos = exch.fetch_positions()
            active_p = [f"{p['symbol']} ROE:%{p.get('percentage', 0):.2f}" for p in pos if float(p.get('contracts', 0)) > 0]
            tickers = exch.fetch_tickers()
            market = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:5]
            
            status_report = f"ŞU ANKİ DURUM:\nAçık Pozisyonlar: {active_p if active_p else 'Yok'}\nMarket Hareketlileri: " + ", ".join([f"{x['s']}: %{x['p']}" for x in market])
            
            # 2. GEMINI'YE CANLI DURUMU VE MESAJI SOR
            prompt = f"{status_report}\n\nKullanıcı Emri: '{message.text}'\n\nGemini, bu verilere bakarak dostuna cevap ver ve gerekiyorsa işlemi YAP."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # 3. MESAJI VE İŞLEMİ GÖNDER
            bot.reply_to(message, response.split("@@")[0].strip())
            trade_result = execute_trade(response)
            if trade_result:
                bot.send_message(CHAT_ID, trade_result)
                
        except Exception as e:
            bot.reply_to(message, f"Canlı bağlantı hatası: {e}")

if __name__ == "__main__":
    print("Gemini 3 Flash CANLI Takipte...")
    bot.infinity_polling()
