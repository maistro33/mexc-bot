import os
import time
import telebot
import ccxt
import google.genai as genai

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

def send_telegram(message):
    try: bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except: pass

if __name__ == "__main__":
    send_telegram("🦅 **KAPTAN, KONTROL TAMAMEN GEMINI'DE**\nCanlı piyasa takibi ve yapay zeka karar mekanizması başlatıldı.")

    while True:
        try:
            # 1. Piyasayı Tara (En Hacimli 5 Parite)
            tickers = exchange.fetch_tickers()
            market_summary = []
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:5]

            for symbol in top_pairs:
                data = tickers[symbol]
                market_summary.append(f"{symbol}: Fiyat:{data['last']}, Değişim:%{data['percentage']:.2f}, Hacim:{data['quoteVolume']:.0f}")

            # 2. Gemini'ye Sor: "İşlem Açalım mı?"
            prompt = f"""
            Sen profesyonel bir tradersın. Aşağıdaki piyasa verilerini incele:
            {market_summary}
            Bakiyemiz: 21.57 USDT. 
            Eğer çok güçlü bir yükseliş (Pump) veya güvenli bir giriş sinyali görüyorsan, 
            kaptana parite ismini ve nedenini söyle. İşlem açma kararı SENDEDİR.
            Eğer fırsat yoksa 'Piyasa izleniyor, fırsat bekleniyor' de.
            """

            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            ai_decision = response.text

            if ai_decision:
                send_telegram(f"📡 **GEMINI KARARI:**\n\n{ai_decision}")

            # 3. Kota ve Strateji Dinlenmesi
            # 120 saniye, pump yakalamak için altın orta yoldur.
            time.sleep(120)

        except Exception as e:
            if "429" in str(e):
                print("Kota molası...")
                time.sleep(60)
            else:
                print(f"Hata: {e}")
                time.sleep(20)
