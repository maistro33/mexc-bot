import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR VE KİMLİK (Railway Değişkenleri) ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Yapılandırması
bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

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
        return f"Analiz Hatası: {e}"

def check_market():
    """Borsayı tarar ve anti-manipülasyon kalkanlarını uygular."""
    try:
        tickers = exchange.fetch_tickers()
        # Sadece USDT vadeli işlemler
        pairs = [s for s in tickers if '/USDT:USDT' in s]
        # Hacme göre ilk 20'yi tara
        top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:20]

        for symbol in top_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            # Senin Stratejin: %3 ve üzeri hareketlerde Sanal Takip
            if abs(change) > 3:
                msg = (f"🔍 **[SANAL TAKİP]**\n"
                       f"Parite: {symbol}\n"
                       f"Değişim: %{change:.2f}\n"
                       f"🛡️ **Kalkanlar:** Gövde Kapanışı ve Hacim Onayı Bekleniyor...")
                send_telegram(msg)
                
                # Gemini Analiz Desteği
                analysis_prompt = f"{symbol} paritesindeki %{change} hareketi analiz et. Bu bir stop hunting (tuzak) olabilir mi? 21.80 USDT bakiye ve 10x kaldıraç için riskli mi? Kısa bir cevap ver."
                decision = get_gemini_instruction(analysis_prompt)
                send_telegram(f"🧠 **GEMINI ANALİZİ:**\n{decision}")

    except Exception as e:
        print(f"Piyasa Tarama Hatası: {e}")

# --- 3. ANA OPERASYON DÖNGÜSÜ ---
if __name__ == "__main__":
    # Başlangıç Selamı ve Kontrol Teyidi
    startup_prompt = "Kaptan az önce 'Burdayım hazırım' dedi. Ona sistemin senin kontrolünde açıldığını ve pusuda olduğunu bildiren çok kısa bir tekmil mesajı yaz."
    selam = get_gemini_instruction(startup_prompt)
    send_telegram(f"🫡 **SİSTEM AKTİF**\n\n{selam}")
    
    while True:
        try:
            # 1. Market Taraması ve Kalkan Kontrolü
            check_market()
            
            # 2. Bakiye Raporu (Her döngüde kontrol)
            balance = exchange.fetch_balance()
            free_usdt = balance.get('USDT', {}).get('free', 0)
            print(f"Güncel Bakiye: {free_usdt} USDT")

            # 3. Bekleme Süresi (Slow & Safe: 2 Dakika)
            # Test aşamasında olduğumuz için 120 saniye idealdir.
            time.sleep(120) 
            
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(30)
