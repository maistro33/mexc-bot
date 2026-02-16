import os
import time
import telebot
import ccxt
from google import genai
import threading

# --- [YAPILANDIRMA] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Başlatma
bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)
exchange = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}
})

# --- [KAPTANIN STRATEJİ AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75, # %75 Kar Al
    'anti_manipulation': True
}

def execute_trade(side, symbol="BTC/USDT:USDT"):
    """Borsada gerçek işlemi başlatan fonksiyon"""
    try:
        # Kaldıraç Ayarla
        exchange.set_leverage(CONFIG['leverage'], symbol)
        
        # Miktar Hesapla
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
        
        # Emri Gönder
        order = exchange.create_market_order(symbol, side, amount)
        
        msg = f"🚀 **OPERASYON BAŞLADI**\nİşlem: {side.upper()}\nSembol: {symbol}\nMiktar: {CONFIG['entry_usdt']} USDT x {CONFIG['leverage']}"
        bot.send_message(CHAT_ID, msg)
        return order
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ Borsa Emir Hatası: {e}")

# --- [AI KOMUTA MERKEZİ] ---
@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        kaptan_text = message.text
        
        # Bakiye ve piyasa özeti al
        try:
            balance = exchange.fetch_balance()['total']['USDT']
            ticker = exchange.fetch_ticker('BTC/USDT:USDT')['last']
        except:
            balance, ticker = "Bilinmiyor", "Bilinmiyor"

        # Gemini'ye yetkiyi kullanması için talimat veriyoruz
        prompt = (f"Sen Kaptan Sadık'ın tam yetkili Evergreen botusun. "
                  f"Kaptan: '{kaptan_text}' dedi. "
                  f"Bakiye: {balance} USDT. BTC: {ticker}. "
                  f"Eğer kaptan işlem açmanı istiyorsa veya piyasa şartları senin 'risk-free' "
                  f"stratejine uygunsa, cevabının sonuna mutlaka [KOMUT:AL] veya [KOMUT:SAT] ekle. "
                  f"Eğer sadece analiz yapıyorsan [KOMUT:YOK] ekle.")
        
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            ai_cevap = response.text
            bot.reply_to(message, ai_cevap)
            
            # Komut Kontrolü
            if "[KOMUT:AL]" in ai_cevap:
                execute_trade('buy')
            elif "[KOMUT:SAT]" in ai_cevap:
                execute_trade('sell')
                
        except Exception as e:
            bot.send_message(CHAT_ID, f"📡 Bağlantı Kesildi: {e}")

# --- [RADAR SİSTEMİ] ---
def radar():
    while True:
        try:
            # Burada 'Sanal Takip' ve 'Gövde Kapanış' analizleri yapılacak
            time.sleep(3600) # Saatlik rapor
        except: pass

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🦅 **EVERGREEN V11: TAM YETKİ DEVRE ALINDI**\n\nKaptan, köprü üstündeyim. Emirlerini bekliyorum, bağlantı stabil!")
    threading.Thread(target=radar, daemon=True).start()
    bot.polling(none_stop=True)
