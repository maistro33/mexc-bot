import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [AUTONOMOUS SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın otonom scalp beynisin. 
Görevin: Tüm borsadaki hacimli altcoinleri tara, yönü belirle, kaldıraç ve miktarı ayarla.

KARAR FORMATI (KESİN):
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
Örnek: @@[ACTION: TRADE, SOL, BUY, 10, 20]@@

Kurallar:
1. Sembolü sadece 'SOL' veya 'ORCA' gibi kısa ismiyle yazabilirsin.
2. Kaldıraç (1-50x) ve Miktar (USDT) tamamen senin analizine bağlı.
3. Bakiye kontrolü yap, tüm kasayı tek işleme basma.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *GEMINI OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def find_correct_symbol(exch, input_sym):
    """Borsadaki gerçek sembol ismini bulur (Hata önleyici)"""
    try:
        markets = exch.load_markets()
        clean_name = input_sym.split('/')[0].split(':')[0].upper().strip() # 'ORCA/USDT' -> 'ORCA'
        
        # Olası eşleşmeleri tara
        for s in markets:
            if markets[s]['swap'] and (clean_name == markets[s]['base'] or clean_name + "USDT" == markets[s]['id']):
                return s
        return None
    except: return None

def execute_autonomous_trade(decision):
    try:
        exch = get_exch()
        pattern = r"@@\[ACTION: TRADE, (.*?), (.*?), (.*?), (.*?)\]@@"
        match = re.search(pattern, decision)
        
        if match:
            raw_sym = match.group(1).strip()
            side = 'buy' if 'buy' in match.group(2).lower() or 'long' in match.group(2).lower() else 'sell'
            lev = int(float(match.group(3).strip()))
            amt = float(match.group(4).strip())
            
            # Sembolü borsaya göre düzelt
            exact_sym = find_correct_symbol(exch, raw_sym)
            if not exact_sym:
                return f"❌ Sembol bulunamadı: {raw_sym}"

            # 1. Kaldıraç Ayarla
            try: exch.set_leverage(lev, exact_sym)
            except: pass
            
            # 2. Market Bilgisi ve Miktar
            ticker = exch.fetch_ticker(exact_sym)
            price = ticker['last']
            qty = (amt * lev) / price
            qty = float(exch.amount_to_precision(exact_sym, qty))
            
            # 3. Emir Gönder
            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                return f"✅ *İŞLEM BAŞARILI*\nSembol: {exact_sym}\nYön: {side.upper()}\nKaldıraç: {lev}x\nMiktar: {amt} USDT"
            else:
                return f"⚠️ {exact_sym} için miktar çok düşük."
                
    except Exception as e:
        return f"🚨 İşlem Hatası: {str(e)}"

def scanner_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            
            # Hacim ve değişim verilerini topla
            market_data = []
            for s, d in tickers.items():
                if ':USDT' in s: # Sadece USDT pariteleri
                    market_data.append({'s': s, 'c': d.get('percentage', 0), 'v': d.get('quoteVolume', 0)})
            
            # En aktif 25'i Gemini'ye gönder
            top_list = sorted(market_data, key=lambda x: abs(x['c']), reverse=True)[:25]
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in top_list])

            prompt = f"Bakiye: {balance} USDT\n\nMarket Özeti:\n{snapshot}\n\nFırsat görüyorsan kaldıraç ve miktarla birlikte @@[ACTION: TRADE...]@@ komutunu ateşle!"
            
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=[SYSTEM_SOUL, prompt]
            ).text
            
            if "@@" in response:
                result = execute_autonomous_trade(response)
                safe_send(f"{response.split('@@')[0]}\n\n{result}")
            
            time.sleep(30)
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    safe_send("🚀 Gemini 3 Otonom v2 Aktif! Sembol tanıma hatası giderildi, borsa taranıyor...")
    threading.Thread(target=scanner_loop, daemon=True).start()
    bot.infinity_polling()
