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

# --- [YAPILANDIRMA] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN, threaded=False)
client = genai.Client(api_key=GEMINI_KEY)

# --- [STRATEJİ AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'anti_manipulation': True
}

# Bitget Bağlantısı (Hedge Mode Destekli)
def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {
            'defaultType': 'swap', 
            'positionMode': True  # Hedge Modu (Çift Yönlü) Aktif
        },
        'enableRateLimit': True
    })

def execute_trade(side, symbol="BTC/USDT:USDT"):
    try:
        exchange = get_exchange()
        # Kaldıraç ayarı
        exchange.set_leverage(CONFIG['leverage'], symbol)
        
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
        
        # Hedge Modunda işlem açarken 'posSide' belirtmek zorunludur
        # buy -> Long açar, sell -> Short açar
        pos_side = 'long' if side == 'buy' else 'short'
        
        params = {'posSide': pos_side}
        order = exchange.create_market_order(symbol, side, amount, params)
        
        report = (f"🎯 **HEDGE MODU İŞLEMİ AÇILDI**\n\n"
                  f"📈 Parite: {symbol}\n"
                  f"⚡ Pozisyon: {pos_side.upper()}\n"
                  f"💰 Miktar: 20 USDT (10x)\n"
                  f"🛡️ Kalkan: Aktif!")
        bot.send_message(CHAT_ID, report)
        return order
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ İşlem Hatası (Hedge): {e}")

@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exchange = get_exchange()
            balance_data = exchange.fetch_balance()
            balance = balance_data['total'].get('USDT', 0)
            
            prompt = (f"Sen Evergreen V11'sin. Kaptan Sadık'ın botusun. "
                      f"Kullanıcı mesajı: '{message.text}'. Bakiye: {balance} USDT. "
                      f"Hedge modu aktif. Karar verirsen [KOMUT:AL] veya [KOMUT:SAT] ekle.")
            
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
            
            if "[KOMUT:AL]" in response.text:
                execute_trade('buy')
            elif "[KOMUT:SAT]" in response.text:
                execute_trade('sell')
                
        except Exception as e:
            print(f"Hata: {e}")

if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(2)
        exchange = get_exchange()
        balance = exchange.fetch_balance()['total'].get('USDT', 0)
        bot.send_message(CHAT_ID, f"🦅 **HEDGE MODU AKTİF**\n\nBakiye: {balance} USDT\nSistem tüm yönlere açık!")
    except Exception as e:
        print(f"Hata: {e}")

    while True:
        try:
            bot.polling(none_stop=True, interval=2, timeout=40)
        except Exception as e:
            time.sleep(5)
