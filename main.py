import ccxt
import telebot
import time

# ===== AYARLAR =====
API_KEY = "BITGET_API_KEY"
API_SECRET = "BITGET_SECRET"
PASSWORD = "BITGET_PASSWORD"
TELEGRAM_TOKEN = "TELEGRAM_BOT_TOKEN"

SYMBOL = "BTC/USDT:USDT"
GRID_LEVELS = 5
GRID_SPREAD = 0.003   # %0.3 aralık
ORDER_SIZE = 5        # USDT

# ===== BORSAYA BAGLAN =====
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'password': PASSWORD,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

bot = telebot.TeleBot(TELEGRAM_TOKEN)

running = False

# ===== GRID KUR =====
def create_grid():
    ticker = exchange.fetch_ticker(SYMBOL)
    price = ticker['last']

    print("Grid kuruluyor:", price)

    for i in range(1, GRID_LEVELS + 1):

        buy_price = price * (1 - GRID_SPREAD * i)
        sell_price = price * (1 + GRID_SPREAD * i)

        exchange.create_limit_buy_order(SYMBOL, ORDER_SIZE/price, buy_price)
        exchange.create_limit_sell_order(SYMBOL, ORDER_SIZE/price, sell_price)

    print("Grid kuruldu")

# ===== SNIPER (Dip Long — Tepe Short) =====
def sniper_trade():
    ticker = exchange.fetch_ticker(SYMBOL)
    price = ticker['last']
    change = ticker['percentage']

    # Dip LONG
    if change < -3:
        print("Dip LONG açılıyor")
        exchange.create_market_buy_order(SYMBOL, ORDER_SIZE/price)

    # Tepe SHORT
    elif change > 3:
        print("Tepe SHORT açılıyor")
        exchange.create_market_sell_order(SYMBOL, ORDER_SIZE/price)

# ===== TELEGRAM KOMUTLARI =====

@bot.message_handler(commands=['startbot'])
def start_bot(message):
    global running
    running = True
    bot.reply_to(message, "Bot başladı 🚀")

@bot.message_handler(commands=['stopbot'])
def stop_bot(message):
    global running
    running = False
    bot.reply_to(message, "Bot durdu 🛑")

@bot.message_handler(commands=['grid'])
def grid_cmd(message):
    create_grid()
    bot.reply_to(message, "Grid kuruldu ⚡")

@bot.message_handler(commands=['ara'])
def search_trade(message):
    sniper_trade()
    bot.reply_to(message, "Fırsat arandı 🔎")

# ===== ANA LOOP =====
def main_loop():
    global running
    while True:
        if running:
            sniper_trade()
        time.sleep(20)

# ===== BASLAT =====
import threading
threading.Thread(target=main_loop).start()

bot.polling()
