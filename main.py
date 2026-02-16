import os
import time
import telebot
import ccxt
import google.genai as genai
import threading

# --- AYARLAR ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

exchange = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})

# --- CANLI MESAJ DİNLEME (Kaptan Yazınca Gemini Cevap Verir) ---
@bot.message_handler(func=lambda message: True)
def handle_kaptan_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        kaptan_sorusu = message.text
        try:
            # Senin mesajını alıp Gemini'ye soruyorum
            response = client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=f"Kaptan Sadık soruyor: {kaptan_sorusu}. Samimi, kısa ve bir profesyonel trader gibi cevap ver."
            )
            bot.reply_to(message, response.text)
        except Exception as e:
            bot.reply_to(message, "Bağlantıda bir parazit var kaptan, tekrar dene.")

# --- OTOMATİK RADAR DÖNGÜSÜ ---
def radar_loop():
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt = balance.get('USDT', {}).get('free', 0)
            
            tickers = exchange.fetch_tickers()
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:10]
            market_summary = [f"{s}: %{tickers[s]['percentage']:.2f}" for s in top_pairs]

            prompt = (
                f"Bakiye: {usdt} USDT. Market: {market_summary}. "
                "Ciddi bir fırsat (Gövde kapanış onaylı) varsa GİR de, yoksa izle."
            )
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if response.text:
                bot.send_message(CHAT_ID, f"📡 **OTOMATİK RADAR:**\n\n{response.text}\n\n💰 Bakiye: {usdt:.2f} USDT")
            
            time.sleep(120) # 2 dakikada bir analiz
        except:
            time.sleep(30)

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🚀 **EVERGREEN V8 AKTİF!**\n\nKaptan, artık telsiz hattı iki yönlü açıldı. Bana Telegram'dan istediğini sorabilirsin, buradayım!")
    
    # Radarı arka planda çalıştır
    t = threading.Thread(target=radar_loop)
    t.start()
    
    # Mesaj dinlemeyi başlat
    bot.polling(none_stop=True)
