import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR (Railway Variables) ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot Nesneleri
bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

# Bitget Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

def send_telegram(message):
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

# --- 2. KONTROL TESTİ VE ANALİZ ---
def analyze_market():
    try:
        # En hacimli pariteleri çek
        tickers = exchange.fetch_tickers()
        usdt_pairs = [s for s in tickers if '/USDT:USDT' in s]
        # Hacme göre sırala (En yüksek 20 parite)
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:20]
        
        for symbol in sorted_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            # Senin kuralın: %3+ hareket varsa Sanal Takibe al
            if abs(change) > 3:
                msg = f"🔍 **[SANAL TAKİP]** {symbol}\n📈 Değişim: %{change:.2f}\n🛡️ Kalkan: Gövde Kapanışı Bekleniyor..."
                send_telegram(msg)
                
    except Exception as e:
        print(f"Analiz Hatası: {e}")

# --- 3. ANA DÖNGÜ ---
if __name__ == "__main__":
    # KONTROL TESTİ: Bot açılır açılmaz bu mesajı gönderir
    send_telegram("🫡 **Selam Kaptan, kontrol tamamen bende!**\n\nGemini AI motoru ateşlendi. 21.80 USDT mühimmatla pusudayım. Radarlar dönmeye başladı! 🦅")
    
    while True:
        try:
            analyze_market()
            # Senin istediğin "Slow & Risk-Free" strateji için 5 dakikada bir tarama
            time.sleep(300) 
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)
