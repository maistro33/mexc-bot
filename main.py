import ccxt
import pandas as pd
import telebot

# Telegram bot token ve chat_id
TELEGRAM_TOKEN = "TELEGRAM_BOT_TOKEN"  # kendi tokenını buraya koy
CHAT_ID = "CHAT_ID"  # kendi chat id'ni buraya koy

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# CCXT borsa ayarları
exchange = ccxt.bybit({  # kullandığın borsa
    'apiKey': 'API_KEY',
    'secret': 'SECRET_KEY',
    'enableRateLimit': True  # rate limit hatalarını önler
})

def telegram_alert(message):
    """Telegram üzerinden uyarı gönderir"""
    try:
        bot.send_message(CHAT_ID, message)
    except Exception as e:
        print("Telegram hatası:", e)

def fetch_balance_safe():
    """Bakiye çekme işlemi try-except ile güvenli hale getirildi"""
    try:
        balance = exchange.fetch_balance()
        return balance
    except ccxt.NetworkError as e:
        msg = f"Ağ hatası: {e}"
        print(msg)
        telegram_alert(msg)
    except ccxt.ExchangeError as e:
        msg = f"Borsa hatası: {e}"
        print(msg)
        telegram_alert(msg)
    except Exception as e:
        msg = f"Genel hata: {e}"
        print(msg)
        telegram_alert(msg)
    return None

# Örnek kullanım
balance = fetch_balance_safe()
if balance:
    print(balance)
else:
    print("Bakiye alınamadı, hata bildirildi.")
