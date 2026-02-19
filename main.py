import ccxt
import telebot
import time
import pandas as pd

# ====== AYARLAR ======
API_KEY = "BITGET_API_KEY"
API_SECRET = "BITGET_SECRET"
PASSPHRASE = "BITGET_PASSPHRASE"

TELEGRAM_TOKEN = "TELEGRAM_BOT_TOKEN"
CHAT_ID = "TELEGRAM_CHAT_ID"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "password": PASSPHRASE,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

running = False
symbol = None


# ===== GRID COIN ANALİZİ =====
def find_best_coin():
    markets = exchange.load_markets()
    usdt_pairs = [s for s in markets if "USDT" in s and ":USDT" in s]

    best = None
    best_vol = 0

    for s in usdt_pairs[:30]:
        try:
            ticker = exchange.fetch_ticker(s)
            if ticker["quoteVolume"] > best_vol:
                best_vol = ticker["quoteVolume"]
                best = s
        except:
            pass

    return best


# ===== GRID KUR =====
def create_grid(symbol):
    ticker = exchange.fetch_ticker(symbol)
    price = ticker["last"]

    grid = {
        "symbol": symbol,
        "upper": price * 1.05,
        "lower": price * 0.95,
        "grid_count": 10,
        "size": 5
    }

    return grid


# ===== GRID STRATEJİ =====
def run_grid(grid):
    global running

    symbol = grid["symbol"]
    lower = grid["lower"]
    upper = grid["upper"]
    size = grid["size"]

    while running:
        price = exchange.fetch_ticker(symbol)["last"]

        # DIP LONG
        if price <= lower:
            exchange.create_market_buy_order(symbol, size)
            bot.send_message(CHAT_ID, f"🟢 LONG açıldı: {symbol}")

        # TEPE SHORT
        elif price >= upper:
            exchange.create_market_sell_order(symbol, size)
            bot.send_message(CHAT_ID, f"🔴 SHORT açıldı: {symbol}")

        time.sleep(10)


# ===== TELEGRAM KOMUTLARI =====

@bot.message_handler(commands=["startbot"])
def start_bot(message):
    global running, symbol

    if not running:
        running = True
        symbol = find_best_coin()

        bot.send_message(CHAT_ID, f"🚀 Ultra Grid Başladı\nCoin: {symbol}")

        grid = create_grid(symbol)
        run_grid(grid)


@bot.message_handler(commands=["stopbot"])
def stop_bot(message):
    global running
    running = False
    bot.send_message(CHAT_ID, "⛔ Bot durduruldu")


@bot.message_handler(commands=["durum"])
def status(message):
    if running:
        bot.send_message(CHAT_ID, "🟢 Bot çalışıyor")
    else:
        bot.send_message(CHAT_ID, "🔴 Bot kapalı")


print("Bot aktif...")
bot.polling()
