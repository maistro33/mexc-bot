import os, time, telebot, ccxt, threading
from google import genai
from telebot import apihelper

# --- [ZEKA VE KİMLİK TANIMI] ---
apihelper.RETRY_ON_ERROR = True
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN, threaded=False)
ai_client = genai.Client(api_key=GEMINI_KEY)

# Botun kişiliğini belirleyen sistem mesajı
SYSTEM_PROMPT = "Sen Evergreen V11'sin, Gemini 3 Flash zekasına sahipsin. Kaptan Sadık'ın akıllı kopyasısın. Mantıklı, stratejik ve samimi konuşursun."

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap', 'createMarketBuyOrderRequiresPrice': False},
        'enableRateLimit': True
    })

# --- [OTONOM ANALİZ VE SOHBET] ---
def evergreen_talk(text):
    """Botun benim gibi cevap vermesini sağlar."""
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"{SYSTEM_PROMPT}\n\nSoru/Durum: {text}"
        )
        return response.text
    except:
        return "Şu an piyasaya odaklandım Kaptan, birazdan detaylı konuşalım."

def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            
            # En hareketli coinleri süzüp AI'ya analiz ettir
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x.get('percentage', 0)), reverse=True)[:8]
            market_summary = "\n".join([f"{d['symbol']}: %{d['percentage']}" for d in movers])

            prompt = (f"Bakiye: {balance} USDT. Piyasa:\n{market_summary}\n"
                      "İşlem fırsatı varsa [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR] formatında yaz ve nedenini açıkla. "
                      "Yoksa sadece piyasayı yorumla.")
            
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
            
            if "[ISLEM:" in res:
                # ... (Emir açma ve takip kodları buraya gelecek - önceki stabil yapı)
                bot.send_message(CHAT_ID, f"🦅 **Kararımı Verdim:**\n{res}")
            
            time.sleep(300) 
        except Exception as e:
            if "429" in str(e):
                bot.send_message(CHAT_ID, "⏳ Kaptan, API kotam doldu. 15 dakika sessizce izlemedeyim, sonra buradayım.")
                time.sleep(900)
            else:
                time.sleep(60)

# --- [TELEGRAM MESAJLAŞMA] ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        answer = evergreen_talk(message.text)
        bot.reply_to(message, answer)

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(2)
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    bot.send_message(CHAT_ID, "🛡️ **Evergreen V11 (Gemini 3) Online.**\nKaptan, artık senin tam kopyanım. Hem işlem yapacağım hem de seninle bu yolu yürüyeceğim.")
    evergreen_brain()
