import os
import time
import telebot
import google.generativeai as genai
import ccxt
import threading

# --- [DEĞİŞKENLERİNLE TAM UYUM] ---
# Railway panelindeki isimlerinle birebir eşleşti:
api_key = os.getenv('BITGET_API')
secret = os.getenv('BITGET_SEC')
password = os.getenv('BITGET_PASSPHRASE')
tele_token = os.getenv('TELE_TOKEN')
chat_id = os.getenv('MY_CHAT_ID')
gemini_key = os.getenv('GEMINI_API_KEY')

# --- [BAĞLANTILAR] ---
# Bitget Bağlantısı
ex = ccxt.bitget({
    'apiKey': api_key,
    'secret': secret,
    'password': password,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# Telegram ve Gemini Bağlantısı
bot = telebot.TeleBot(tele_token)
genai.configure(api_key=gemini_key)
ai_brain = genai.GenerativeModel('gemini-pro')

def send_msg(text):
    try:
        bot.send_message(chat_id, text, parse_mode='Markdown')
    except:
        pass

# --- [GEMINI KARAR MEKANİZMASI] ---
def gemini_analiz():
    try:
        # Piyasadan verileri çekelim (Örn: ETH)
        ticker = ex.fetch_ticker('ETH/USDT:USDT')
        ohlcv = ex.fetch_ohlcv('ETH/USDT:USDT', timeframe='15m', limit=10)
        
        market_data = f"Fiyat: {ticker['last']}, Son Mumlar: {str(ohlcv[-5:])}"
        
        prompt = f"""
        Sen profesyonel bir tradersın. Veriler: {market_data}
        Kasa: 21 USDT. Görevin:
        1. Fiyat hareketini yorumla. PUMP/DUMP riski var mı?
        2. Eğer fırsat varsa 'AL' veya 'SAT' de.
        3. Kararsızsan 'BEKLE' de.
        4. Kaldıracı sen belirle (max 10x).
        Format: [KARAR] | [KALDIRAC] | [NEDEN]
        """
        
        response = ai_brain.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Analiz Hatası: {e}"

# --- [ANA DÖNGÜ] ---
def radar_loop():
    send_msg("🦅 **Gemini AI Core: Radarlar Açıldı!**\n\nDeğişkenlerin bağlandı, 21 doları büyütmek için pusuya yatıyorum. Her adımı sana raporlayacağım.")
    
    while True:
        try:
            karar = gemini_analiz()
            
            # Eğer karar AL veya SAT ise (Bekle değilse) Telegram'a yaz
            if "AL" in karar or "SAT" in karar:
                send_telegram_report(karar)
                # Buraya otomatik işlem emri eklenebilir
            
            print(f"Sanal Takip: {karar}")
            time.sleep(300) # 5 dakikada bir kontrol et
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

def send_telegram_report(analysis):
    report = (f"🎯 **GEMINI AI FIRSAT ANALİZİ**\n\n"
              f"{analysis}\n"
              f"━━━━━━━━━━━━━━\n"
              f"⚡ **Durum:** İzleniyor...")
    send_msg(report)

if __name__ == "__main__":
    # Telegram dinleyiciyi başlat
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    # Radarı başlat
    radar_loop()
