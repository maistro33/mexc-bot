import ccxt
import time
import telebot
import os
import threading

# --- [BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [ÇÖKME KORUMALI MESAJ] ---
def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode="Markdown")
    except: print("Mesaj gönderilemedi, bot meşgul olabilir.")

# --- [V21 ANALİZ VE MOTOR] ---
# (Buradaki is_perfect_setup ve monitor fonksiyonlarını V21'den olduğu gibi kopyala)
# ... [cite: 2026-02-14]

if __name__ == "__main__":
    try:
        ex.load_markets()
        threading.Thread(target=main_loop, daemon=True).start()
        # ÇÖKMEYİ ENGELLEYEN POLLING AYARI
        bot.infinity_polling(timeout=20, long_polling_timeout=10)
    except Exception as e:
        print(f"Kritik Hata: {e}")
        time.sleep(10)
