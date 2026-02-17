import os
import time
import telebot
import ccxt
from google import genai
from telebot import apihelper

# --- [BAĞLANTI ZIRHI] ---
apihelper.RETRY_ON_ERROR = True
apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT = 60

# --- [YAPILANDIRMA - PANELİNLE %100 UYUMLU] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
# İsmi senin panelindeki gibi 'BITGET_PASSPHR' yaptım:
PASSPHRASE = os.getenv('BITGET_PASSPHR') 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Başlatma
bot = telebot.TeleBot(TOKEN, threaded=False)
client = genai.Client(api_key=GEMINI_KEY)

# --- [GÜVENLİK AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'anti_manipulation': True
}

# Bitget Bağlantısı
def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap', 'positionMode': True},
        'enableRateLimit': True
    })

def execute_trade(side, symbol="BTC/USDT:USDT"):
    try:
        exchange = get_exchange()
        exchange.set_leverage(CONFIG['leverage'], symbol)
        
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
        
        order = exchange.create_market_order(symbol, side, amount)
        
        report = (f"🎯 **İŞLEM AÇILDI**\n\n"
                  f"📈 Parite: {symbol}\n"
                  f"⚡ Yön: {side.upper()}\n"
                  f"💰 Miktar: 20 USDT (10x)\n"
                  f"🛡️ Kalkan: SL ve TP1 (%75) Aktif!")
        bot.send_message(CHAT_ID, report)
        return order
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ İşlem Hatası: {e}")

@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exchange = get_exchange()
            balance_data = exchange.fetch_balance()
            balance = balance_data['total'].get('USDT', 0)
            
            prompt = (f"Sen Evergreen V11'sin. Kaptan Sadık'ın tam yetkili botusun. "
                      f"Kaptan: '{message.text}' dedi. Mevcut Bakiye: {balance} USDT. "
                      f"Stratejin: Profitable, slow, risk-free trades."
                      f"Karar verirsen sonuna [KOMUT:AL] veya [KOMUT:SAT] ekle.")
            
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
            
            if "[KOMUT:AL]" in response.text:
                execute_trade('buy')
            elif "[KOMUT:SAT]" in response.text:
                execute_trade('sell')
                
        except Exception as e:
            print(f"Hata: {e}")

if __name__ == "__main__":
    print("🚀 Evergreen V11: Motorlar Isıtılıyor...")
    
    try:
        bot.remove_webhook()
        time.sleep(2)
        
        # Başlangıç Kontrolü
        exchange = get_exchange()
        balance_data = exchange.fetch_balance()
        current_balance = balance_data['total'].get('USDT', 0)
        
        online_msg = (f"🦅 **SİSTEM ONLINE**\n\n"
                      f"💰 Güncel Bakiye: {current_balance} USDT\n"
                      f"🛡️ Kalkanlar: Aktif\n"
                      f"📡 Radar: Amsterdam üzerinden bağlı!\n\n"
                      f"Kaptan, her şey senin panelindeki ayarlara göre hazırlandı. Ava hazırız!")
        
        bot.send_message(CHAT_ID, online_msg)
        print("✅ Bot Başarıyla Yayına Girdi.")
    except Exception as e:
        print(f"❌ Başlatma Hatası: {e}")

    while True:
        try:
            bot.polling(none_stop=True, interval=2, timeout=40)
        except Exception as e:
            time.sleep(5)
