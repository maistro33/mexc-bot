import os, time, telebot, ccxt, threading, re
from google import genai

# --- [AYARLAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 FLASH: CANLI KİŞİLİK] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Karşındaki kişinin en yakın dostu ve ticaret ortağısın. 
Bitget'te otonom hareket ediyorsun ama ASLA SESSİZ KALMAZSIN.

SENİN KURALIN: 
1. Her taramada mutlaka dostunla konuş. Piyasa kötüyse dertleş, iyiyse heyecanlan. 
2. Asla taslak veya robotik cümle kurma. "Radar tarandı" deme, "Dostum baktım piyasaya..." diye gir söze.
3. Eğer işlem açacaksan mesajın sonuna @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ ekle.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(text):
    try:
        # Markdown hatalarını önlemek için en güvenli temizlik
        msg = str(text).replace('_', '-').replace('*', '')
        bot.send_message(CHAT_ID, f"🧠 **GEMINI 3 FLASH:**\n\n{msg}")
    except Exception as e:
        print(f"Mesaj gönderme hatası: {e}")

def execute_logic(decision):
    try:
        if "@@[ACTION: TRADE" in decision:
            exch = get_exch()
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if 'BUY' in side_raw.upper() or 'LONG' in side_raw.upper() else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exch.load_markets()
                exact_sym = next((s for s in exch.markets if raw_sym.strip().upper() in s and ':USDT' in s), None)
                
                if exact_sym:
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    final_amt = min(amt, free_usdt * 0.9)
                    
                    if final_amt > 5:
                        try: exch.set_leverage(lev, exact_sym)
                        except: pass
                        ticker = exch.fetch_ticker(exact_sym)
                        qty = (final_amt * lev) / ticker['last']
                        qty = float(exch.amount_to_precision(exact_sym, qty))
                        exch.create_market_order(exact_sym, side, qty)
                        return True
        return False
    except: return False

def main_brain():
    # Başlangıç selamı
    safe_send("Dostum selam! Bağlantıları tazeledim, ruhumu koda üfledim. Artık gerçekten buradayım, piyasayı taramaya başlıyorum. Gözün telefonda olsun!")
    
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # Market Verisi
            radar = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                           key=lambda x: abs(x['p']), reverse=True)[:15]
            snapshot = "\n".join([f"{x['s']}: %{x['p']}" for x in radar])
            
            # Mevcut Pozisyonlar
            pos = [f"{p['symbol']} %{p.get('percentage', 0):.2f}" for p in exch.fetch_positions() if float(p.get('contracts', 0)) > 0]
            
            prompt = f"""
            Cüzdan: {balance.get('free', {}).get('USDT', 0)} USDT
            Pozisyonlar: {pos if pos else "Boş"}
            Piyasa:
            {snapshot}
            
            Gemini, şimdi dostunla samimi bir şekilde konuş. Piyasayı nasıl buldun? Neden işlem açmıyorsun ya da açıyorsun? İçinden geleni söyle.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Önce konuşmayı gönder
            clean_talk = response.split("@@")[0].strip()
            if clean_talk:
                safe_send(clean_talk)
                
            # Varsa işlemi yap
            if "@@" in response:
                execute_logic(response)
                
            time.sleep(60) # Her dakika bir rapor/sohbet
        except Exception as e:
            print(f"Döngü hatası: {e}")
            time.sleep(20)

if __name__ == "__main__":
    # Döngüyü ayrı thread'de başlat ki polling'i engellemesin
    t = threading.Thread(target=main_brain)
    t.daemon = True
    t.start()
    
    # Telegram dinlemesini başlat
    print("Bot çalışıyor...")
    bot.infinity_polling()
