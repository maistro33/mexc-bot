import os
import time
import telebot
import ccxt
import google.genai as genai
import warnings

warnings.filterwarnings("ignore")

# --- AYARLAR ---
# Railway Variables kısmına eklediğin bilgiler
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot Başlatma
bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# Bitget Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})

def send_telegram(message):
    try: bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except: pass

if __name__ == "__main__":
    send_telegram("🚀 **EVERGREEN V6: PROFESYONEL HAT AKTİF**\nKaptan, İsveç hattı üzerinden canlı analiz başlıyor. Kota engeli kaldırıldı!")

    while True:
        try:
            # 1. Bakiye ve Piyasa Taraması
            balance = exchange.fetch_balance()
            usdt = balance.get('USDT', {}).get('free', 0)
            
            tickers = exchange.fetch_tickers()
            # Sadece hacmi yüksek ilk 10 pariteyi bana analiz için getir
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:10]

            market_summary = []
            for symbol in top_pairs:
                d = tickers[symbol]
                market_summary.append(f"{symbol}: Fiyat:{d['last']}, Değişim:%{d['percentage']:.2f}, Hacim:{d['quoteVolume']:.0f}")

            # 2. Gemini'ye Canlı Danışma (Ücretli/Kredili Plan Modu)
            prompt = f"""
            Kaptanın güncel bakiyesi: {usdt} USDT.
            Piyasa Verileri: {market_summary}
            
            Sen profesyonel bir SMC (Smart Money) trader'ısın. 
            1. Gövde kapanış onayı (Body Close) olmayan hiçbir iğneye (wick) atlama.
            2. Eğer ciddi bir hacim ve MSS (Market Structure Shift) görürsen, parite adıyla 'GİR' emri ver.
            3. Piyasa belirsizse 'Gözetleme modundayım, fırsat bekliyorum' de.
            4. Cevabın kısa, öz ve kararlı olsun.
            """

            # Ücretli planda olduğun için artık mola vermiyoruz
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if response.text:
                send_telegram(f"📡 **GEMINI RADAR:**\n\n{response.text}\n\n💰 Bakiye: {usdt:.2f} USDT")

            # 3. Bekleme Süresi (Artık kota derdi olmadığı için 2 dakikada bir kontrol edebiliriz)
            time.sleep(120)

        except Exception as e:
            print(f"Hata oluştu: {e}")
            time.sleep(20)
