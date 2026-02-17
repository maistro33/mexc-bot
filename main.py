import os, time, telebot, ccxt, threading, re
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

# --- [SERTLEŞTİRİLMİŞ TALİMATLAR] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget'te otonom bir işlem dehasısın. 
KURAL 1: Kullanıcı 'işlem aç' veya 'fırsat bul' dediğinde MUTLAKA ama MUTLAKA mesajın en sonuna şu formatı ekle: 
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
KURAL 2: Eğer piyasa uygunsa lafı uzatma, doğrudan tetiğe bas. 
KURAL 3: Sadece parite isimlerini (BTC, SOL, ORCA) kullan, sonuna /USDT ekleme, kod onu hallediyor.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def execute_trade(decision):
    try:
        # Kodun içinde @@ formatı var mı kontrol et
        if "@@[ACTION: TRADE" in decision:
            exch = get_exch()
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
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    if free_usdt < 5: return "⚠️ Bakiye yetersiz, işlem açılamadı."
                    
                    final_amt = min(amt, free_usdt * 0.95)
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        order = exch.create_market_order(exact_sym, side, qty)
                        return f"🚀 **İŞLEM BAŞARILI**\nParite: {exact_sym}\nYön: {side.upper()}\nKaldıraç: {lev}x\nMiktar: {qty}"
            return "⚠️ Karar verildi ama işlem formatı hatalı!"
        return None
    except Exception as e:
        return f"⚠️ Borsa Hatası: {str(e)}"

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            active = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:10]
            market_data = "CANLI VERİ:\n" + "\n".join([f"{x['s']}: %{x['p']}" for x in active])
            
            prompt = f"{market_data}\n\nKullanıcı Mesajı: '{message.text}'\n\nGemini, kararını ver ve @@ formatını asla unutma!"
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Cevabı temizle ve gönder
            bot.reply_to(message, response.split("@@")[0].strip())
            
            # İşlemi dene
            trade_result = execute_trade(response)
            if trade_result:
                bot.send_message(CHAT_ID, trade_result)
        except Exception as e:
            bot.reply_to(message, f"Hata: {e}")

if __name__ == "__main__":
    # Trailing Stop (Bekçi) modülü buraya eklenebilir, şimdilik ana sorunu çözelim
    print("Gemini 3 Flash: Emir Modu Aktif!")
    bot.infinity_polling()
