import os
import time
import telebot
import google.generativeai as genai
import ccxt
import threading

# --- RAILWAY DEĞİŞKENLERİNLE %100 UYUMLU İSİMLER ---
BITGET_API = os.getenv('BITGET_API')
BITGET_SEC = os.getenv('BITGET_SEC')
BITGET_PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# --- BAĞLANTILAR ---
# Bitget
ex = ccxt.bitget({
    'apiKey': BITGET_API,
    'secret': BITGET_SEC,
    'password': BITGET_PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# Telegram ve Gemini
bot = telebot.TeleBot(TELE_TOKEN)
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('gemini-pro')

def send_msg(text):
    try:
        bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def gemini_karar():
    try:
        ticker = ex.fetch_ticker('ETH/USDT:USDT')
        prompt = f"ETH Fiyatı: {ticker['last']}. Kısa vadeli teknik analiz yap. 21$ bakiye ile AL, SAT veya BEKLE de. Kaldıracı belirle (max 10x)."
        response = ai_brain.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Analiz Hatası: {e}"

def radar_loop():
    # Bot açıldığında bu mesaj gelmeli!
    send_msg("🦅 **Gemini AI Core: Radarlar Açıldı!**\n\nSinyal takibi başlıyor. 21 USDT bakiye kontrol altında.")
    
    while True:
        try:
            karar = gemini_karar()
            if "AL" in karar or "SAT" in karar:
                send_msg(f"🎯 **YENİ FIRSAT ANALİZİ**\n\n{karar}")
            time.sleep(300) 
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    # Telegram'ı ayrı kolda başlat (Crashed hatasını önlemek için)
    t = threading.Thread(target=radar_loop)
    t.start()
    bot.infinity_polling()
