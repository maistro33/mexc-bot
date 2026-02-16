import os
import time
import telebot
import ccxt
import google.genai as genai

# Railway Variables kısmındaki bilgiler
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

def send_telegram(message):
    try: bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except: pass

if __name__ == "__main__":
    send_telegram("✅ **İSVEÇ HATTI AKTİF!**\nKaptan, 2600 SEK kredi ile operasyon başlıyor. Artık durmak yok!")

    while True:
        try:
            # Bakiyeni kontrol et
            balance = exchange.fetch_balance()
            usdt = balance.get('USDT', {}).get('free', 0)
            
            # En hareketli coinleri tara
            tickers = exchange.fetch_tickers()
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:10]

            market_info = []
            for symbol in top_pairs:
                d = tickers[symbol]
                market_info.append(f"{symbol}: %{d['percentage']:.2f}")

            # ÜCRETLİ HAT ANALİZİ (Kesintisiz)
            prompt = f"Bakiye: {usdt} USDT. Market: {market_info}. Sadece ciddi fırsat varsa 'GİR' de, yoksa 'İzliyorum' de."
            
            # Artık saniyeler içinde cevap alacağız
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if response.text:
                send_telegram(f"📡 **CANLI RADAR:**\n{response.text}\n💰 Bakiye: {usdt:.2f} USDT")

            time.sleep(60) # Her dakikada bir kontrol (Hızlı Mod)

        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(10)
