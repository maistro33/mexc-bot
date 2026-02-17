import os
import time
import telebot
import ccxt
from google import genai
from telebot import apihelper

# --- [BAĞLANTI VE GÜVENLİK] ---
apihelper.RETRY_ON_ERROR = True
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN, threaded=False)
client = genai.Client(api_key=GEMINI_KEY)

# --- [STRATEJİ VE MÜDAHALE AYARLARI] ---
CONFIG = {
    'entry_usdt': 15.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'close_tp1_perc': 0.75, # TP1'de %75 kapat
    'anti_manipulation': True
}

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap', 'positionMode': False},
        'enableRateLimit': True
    })

def scan_and_manage():
    """Borsadaki tüm pozisyonları tara ve stratejiyi uygula"""
    try:
        exchange = get_exchange()
        positions = exchange.fetch_positions()
        
        for pos in positions:
            contracts = float(pos.get('contracts', 0))
            if contracts > 0:
                symbol = pos['symbol']
                side = pos['side']
                unrealized_pnl = float(pos.get('unrealizedPnl', 0))
                entry_price = float(pos.get('entryPrice', 0))
                
                # Kâr Durumu ve Müdahale Mantığı
                if unrealized_pnl > 0:
                    # %75 Kademeli Kâr Al
                    # Basit bir TP mantığı: PNL bakiye bazlı %2'yi geçerse TP1 uygula
                    pnl_percentage = (unrealized_pnl / CONFIG['entry_usdt']) * 100
                    if pnl_percentage >= 5.0: # Örnek: %5 kârda %75 kapat
                        close_side = 'sell' if side == 'long' else 'buy'
                        exchange.create_market_order(symbol, close_side, contracts * CONFIG['close_tp1_perc'])
                        bot.send_message(CHAT_ID, f"🎯 **OTOMATİK MÜDAHALE: TP1 ALINDI**\nParite: {symbol}\nKâr: %{pnl_percentage:.2f}\nPozisyonun %75'i kapatıldı.")

    except Exception as e:
        print(f"Yönetim Hatası: {e}")

@bot.message_handler(func=lambda message: True)
def handle_ai(message):
    if str(message.chat.id) == str(CHAT_ID):
        exchange = get_exchange()
        # Her mesajda canlı bakiye ve pozisyon kontrolü
        balance = exchange.fetch_balance()['total'].get('USDT', 0)
        positions = [p for p in exchange.fetch_positions() if float(p.get('contracts', 0)) > 0]
        
        status = f"Bakiye: {balance} USDT. Açık İşlem: {len(positions)} adet."
        
        prompt = (f"Sen Evergreen V11'sin. Kaptan Sadık'ın tam yetkili botusun. "
                  f"Şu anki durum: {status}. Stratejin: Profitable, slow, risk-free. "
                  f"Kaptan diyor ki: '{message.text}'. Her şeye müdahale etme yetkin var.")
        
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        bot.reply_to(message, response.text)
        
        # Manuel Kapatma Komutu
        if "KAPAT" in message.text.upper() and positions:
            for p in positions:
                side = 'sell' if p['side'] == 'long' else 'buy'
                exchange.create_market_order(p['symbol'], side, p['contracts'])
                bot.send_message(CHAT_ID, f"🚫 **KOMUT ALINDI: İŞLEM KAPATILDI**\n{p['symbol']} sonlandırıldı.")

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🦅 **EVERGREEN V11: TAM MÜDAHALE MODU AKTİF**\n\nArtık sadece izlemiyorum, yönetiyorum Kaptan!")
    
    while True:
        try:
            scan_and_manage() # Her 30 saniyede bir pozisyonları kontrol et ve yönet
            bot.polling(none_stop=True, interval=2, timeout=20)
        except Exception as e:
            time.sleep(5)
