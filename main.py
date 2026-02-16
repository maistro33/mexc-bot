import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR (Railway Değişkenleri) ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Yapılandırması (Model ismi güncellendi: gemini-1.5-flash)
bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# Borsa Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# --- 2. ÖZEL FONKSİYONLAR ---

def send_telegram(message):
    """Telegram üzerinden rapor verir."""
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_gemini_instruction(prompt):
    """Gemini AI'dan stratejik analiz ve talimat alır."""
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Analiz Hatası: {e}"

def check_market():
    """Borsayı tarar ve anti-manipülasyon kalkanlarını uygular."""
    try:
        tickers = exchange.fetch_tickers()
        # Sadece USDT vadeli pariteler
        pairs = [s for s in tickers if '/USDT:USDT' in s]
        top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:15]

        for symbol in top_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            # Senin Stratejin: %3 ve üzeri hareketlerde Sanal Takip
            if abs(change) > 3:
                msg = (f"🔍 **[SANAL TAKİP]**\n"
                       f"Parite: {symbol}\n"
                       f"Değişim: %{change:.2f}\n"
                       f"🛡️ **Kalkan:** Gövde Kapanışı Bekleniyor...")
                send_telegram(msg)
                
                # Gemini Analiz Desteği
                analysis_prompt = f"{symbol} paritesinde %{change} hareket var. Bu bir manipülasyon (spoofing) olabilir mi? 21.80 USDT bakiye ile güvenli mi? Kısa bir tavsiye ver."
                decision = get_gemini_instruction(analysis_prompt)
                send_telegram(f"🧠 **GEMINI ANALİZİ:**\n{decision}")

    except Exception as e:
        print(f"Piyasa Tarama Hatası: {e}")

# --- 3. ANA OPERASYON DÖNGÜSÜ ---
if __name__ == "__main__":
    # Başlangıç Selamı
    try:
        startup_prompt = "Kaptan az önce 'Burdayım hazırım' dedi. Sistemin 21.80 USDT ile pusuda olduğunu bildiren kısa bir telsiz mesajı yaz."
        selam = get_gemini_instruction(startup_prompt)
        send_telegram(f"🫡 **BOT ŞAHLANDI**\n\n{selam}")
    except:
        send_telegram("🫡 **Sistem Aktif!** Gemini motoru ısınana kadar manuel takipteyim.")
    
    while True:
        try:
            # Market Taraması
            check_market()
            
            # Bekleme Süresi (Slow & Safe: 3 Dakika)
            time.sleep(180) 
            
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(30)
