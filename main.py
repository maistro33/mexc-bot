import os
import time
import telebot
import ccxt
from google import genai
from telebot import apihelper

# --- [BAĞLANTI GÜVENLİĞİ] ---
apihelper.RETRY_ON_ERROR = True
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN, threaded=False)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [BORSA YETKİ MERKEZİ] ---
def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap', 'positionMode': False},
        'enableRateLimit': True
    })

def get_market_data():
    """Borsadaki tüm canlı verileri toplar"""
    try:
        exch = get_exchange()
        balance = exch.fetch_balance()['total'].get('USDT', 0)
        positions = [p for p in exch.fetch_positions() if float(p.get('contracts', 0)) > 0]
        # BTC ve ETH gibi ana paritelerin fiyatlarını da ekleyelim
        btc_price = exch.fetch_ticker('BTC/USDT:USDT')['last']
        return balance, positions, btc_price
    except Exception as e:
        print(f"Veri çekme hatası: {e}")
        return 0, [], 0

# --- [YAPAY ZEKA KARAR MEKANİZMASI] ---
def ai_commander(user_msg=None):
    """Her döngüde ve her mesajda botun karar vermesini sağlar"""
    balance, positions, btc_price = get_market_data()
    
    pos_desc = "Açık pozisyon yok."
    if positions:
        pos_desc = "\n".join([f"{p['symbol']} {p['side']} (Miktar: {p['contracts']}, PNL: {p['unrealizedPnl']} USDT)" for p in positions])

    prompt = (
        f"Sen Evergreen V11'sin. Gemini 3 Flash altyapısıyla Kaptan Sadık'ın tek yetkili traderısın. "
        f"CANLI VERİLER: Bakiye: {balance} USDT, BTC Fiyatı: {btc_price}, Açık Pozisyonlar: {pos_desc}. "
        f"STRATEJİ: Profitable, slow, risk-free trades. Market Maker (spoofing/stop hunting) tuzaklarına karşı kalkanların aktif. "
        f"YETKİ: Her şeye müdahale edebilirsin. Pozisyon açabilir, kapatabilir veya bekleyebilirsin. "
        f"KARARIN: Eğer bir işlem yapacaksan mutlaka şu formatta bitir: "
        f"[KOMUT:AL_BTC], [KOMUT:SAT_BTC], [KOMUT:KAPAT_HEPSİ] veya [KOMUT:İZLEME]."
        f"Kaptan'ın mesajı (varsa): {user_msg}"
    )

    try:
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        decision = response.text
        
        # Komutları Uygula
        exch = get_exchange()
        if "[KOMUT:AL_BTC]" in decision:
            # 15 USDT'lik Long
            amount = float(exch.amount_to_precision('BTC/USDT:USDT', 150 / btc_price))
            exch.create_market_order('BTC/USDT:USDT', 'buy', amount)
            bot.send_message(CHAT_ID, "🦅 AI Kararı: BTC Long işlemi başlatıldı.")
            
        elif "[KOMUT:KAPAT_HEPSİ]" in decision and positions:
            for p in positions:
                side = 'sell' if p['side'] == 'long' else 'buy'
                exch.create_market_order(p['symbol'], side, p['contracts'])
                bot.send_message(CHAT_ID, f"🛡️ AI Müdahalesi: {p['symbol']} işlemi risk/kâr analiziyle kapatıldı.")
        
        return decision
    except Exception as e:
        print(f"AI Karar Hatası: {e}")
        return "Karar verilemedi."

# --- [TELEGRAM VE OTOMASYON] ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        # Kaptan bir şey yazdığında hemen AI'yı borsa verileriyle çalıştır
        res = ai_commander(message.text)
        bot.reply_to(message, res)

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🦅 **EVERGREEN V11 ONLINE**\nBorsa yetkileri devralındı. Analiz başlıyor...")
    
    # Arka planda sürekli tarama (Müdahale Modu)
    while True:
        try:
            ai_commander() # Periyodik olarak piyasayı ve pozisyonları denetle
            bot.polling(none_stop=True, interval=5, timeout=30)
        except Exception as e:
            time.sleep(10)
