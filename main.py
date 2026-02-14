import ccxt
import time
import telebot
import os

# --- AYARLAR ---
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
PASSPHRASE = os.getenv('PASSPHRASE')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

exchange = ccxt.bitget({'apiKey': API_KEY, 'secret': SECRET_KEY, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}})
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- GİZLİ STRATEJİ AYARLARI ---
SYMBOL = 'SPACEUSDT'
LEVERAGE = 10
AMOUNT_USDT = 15      # 42 USDT kasadan 15 USDT giriş [cite: 2026-02-05]
HIDDEN_TP = 0.020     # %2 Kar (Gizli) [cite: 2026-02-12]
HIDDEN_SL = 0.015     # %1.5 Zarar (Gizli) [cite: 2026-02-12]
TRAILING_ACTIVATE = 0.010 # %1 kara geçince Trailing Stop başlasın [cite: 2026-02-05]

def send_msg(text):
    try: bot.send_message(CHAT_ID, f"🕵️ **GİZLİ MOD AKTİF:**\n{text}")
    except: pass

def manage_hidden_position():
    entry_price = None
    max_price = 0
    is_in_position = False

    while True:
        try:
            # Pozisyon Kontrolü
            pos = exchange.fetch_positions(symbols=[SYMBOL])
            if pos and float(pos[0]['contracts']) > 0:
                if not is_in_position:
                    entry_price = float(pos[0]['entryPrice'])
                    is_in_position = True
                    send_msg(f"🚀 İşleme Girildi!\nGiriş: {entry_price}\nStop/TP Borsada Gizli!")

                curr_price = float(exchange.fetch_ticker(SYMBOL)['last'])
                
                # 1. GİZLİ STOP LOSS [cite: 2026-02-12]
                if curr_price <= entry_price * (1 - HIDDEN_SL):
                    exchange.create_market_sell_order(SYMBOL, pos[0]['contracts'])
                    send_msg(f"🛑 Gizli Stop Patladı. Zarar Kesildi.\nBakiye: {exchange.fetch_balance()['total']['USDT']} USDT")
                    is_in_position = False

                # 2. GİZLİ TAKE PROFIT [cite: 2026-02-12]
                elif curr_price >= entry_price * (1 + HIDDEN_TP):
                    exchange.create_market_sell_order(SYMBOL, pos[0]['contracts'])
                    send_msg(f"💰 Gizli TP Alındı! Tek Mumda Kar.\nBakiye: {exchange.fetch_balance()['total']['USDT']} USDT")
                    is_in_position = False

                # 3. GİZLİ TRAILING STOP [cite: 2026-02-05]
                if curr_price > max_price: max_price = curr_price
                if curr_price >= entry_price * (1 + TRAILING_ACTIVATE):
                    if curr_price < max_price * 0.995: # %0.5 geri çekilirse karı al çık
                        exchange.create_market_sell_order(SYMBOL, pos[0]['contracts'])
                        send_msg("📉 Trailing Stop Karı Aldı ve Çıktı!")
                        is_in_position = False

            time.sleep(1) # Saniyede 1 kontrol (Hızlı Scalp için)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(5)

if __name__ == "__main__":
    manage_hidden_position()
