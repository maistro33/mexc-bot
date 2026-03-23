import os
import ccxt
import telebot

print("START OK")

print("TELE_TOKEN:", bool(os.getenv("TELE_TOKEN")))
print("CHAT_ID:", bool(os.getenv("MY_CHAT_ID")))
print("API:", bool(os.getenv("BITGET_API")))
print("SECRET:", bool(os.getenv("BITGET_SEC")))

# TELEGRAM TEST
try:
    bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
    bot.send_message(os.getenv("MY_CHAT_ID"), "✅ TELEGRAM OK")
    print("TELEGRAM OK")
except Exception as e:
    print("TELEGRAM ERROR:", e)

# EXCHANGE TEST
try:
    exchange = ccxt.bitget({
        "apiKey": os.getenv("BITGET_API"),
        "secret": os.getenv("BITGET_SEC"),
        "options": {"defaultType": "swap"},
        "enableRateLimit": True
    })

    balance = exchange.fetch_balance()
    print("EXCHANGE OK")
except Exception as e:
    print("EXCHANGE ERROR:", e)
