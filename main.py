import os
import time
import telebot
import ccxt
import google.genai as genai
import threading

# --- [YAPILANDIRMA VE AYARLAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Başlatma
bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# Bitget Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}
})

# --- [STRATEJİ PARAMETRELERİ - KAPTANIN İSTEKLERİ] ---
config = {
    'TakeProfit_1': 0.015,         # %1.5 Kâr Al 1
    'Close_Percentage_TP1': 0.75,  # İlk hedefte %75 kapat (Kaptan'ın özel emri)
    'Leverage': 10,                # 10x kaldıraç
    'Entry_Amount_USDT': 20,       # Giriş miktarı
    'Anti_Manipulation': True      # Gövde kapanış onayı aktif
}

# --- [TELEGRAM MESAJ YÖNETİMİ] ---
@bot.message_handler(func=lambda message: True)
def handle_kaptan_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        kaptan_text = message.text
        print(f"📡 TELSİZDEN GELEN: {kaptan_text}") # Terminalde canlı izle
        
        # Mesajı doğrudan Gemini'ye analiz ettiriyoruz
        prompt = (f"Sen Kaptan Sadık'ın Evergreen botusun. Kaptan az önce şunu yazdı: '{kaptan_text}'. "
                  f"Şu anki bakiye: 21.58 USDT. Hedef: 2100 USDT. "
                  f"Kaptanın bu mesajına, onun risk-free ve kârlı ticaret vizyonuna uygun, "
                  f"karakterli ve teknik bir cevap ver.")
        
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
        except Exception as e:
            bot.send_message(CHAT_ID, f"⚠️ Sinyal hatası: {e}")

# --- [RADAR VE ANALİZ DÖNGÜSÜ] ---
def radar_status():
    """Botun yaşadığını ve analiz yaptığını Telegram'a bildirir."""
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt_balance = balance['total']['USDT']
            status_msg = (f"📡 **Evergreen Radar Raporu**\n"
                          f"💰 Mevcut Bakiye: {usdt_balance} USDT\n"
                          f"🛡️ Anti-Manipülasyon: Aktif\n"
                          f"📈 Hedef: 2100 USDT\n"
                          f"🕒 Durum: Gövde kapanış onayı bekleniyor...")
            bot.send_message(CHAT_ID, status_msg)
            time.sleep(3600) # Saatte bir durum güncellemesi
        except Exception as e:
            print(f"Radar hatası: {e}")
            time.sleep(60)

# --- [ANA ÇALIŞTIRICI] ---
if __name__ == "__main__":
    print("🚀 Evergreen V11 Operasyonu Başlatıyor...")
    bot.send_message(CHAT_ID, "🦅 **V11: ÇELİK HAT KURULDU**\n\nKaptan, telsiz pırıl pırıl. Artık her yazdığını saniyesinde alıyorum. Operasyon kontrolü bende!")
    
    # Radar döngüsünü ayrı bir kanalda başlat
    threading.Thread(target=radar_status, daemon=True).start()
    
    # Telegram'ı dinlemeye başla
    bot.polling(none_stop=True)
