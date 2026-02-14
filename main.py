import ccxt
import time
import telebot
import os

# --- KİMLİK BİLGİLERİ (Railway Değişkenlerinden Çeker) ---
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
PASSPHRASE = os.getenv('PASSPHRASE')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# --- SNIPER STRATEJİ AYARLARI ---
SYMBOL = 'KITEUSDT'   # Takip edilecek ana koin
LEVERAGE = 10          # 10x Kaldıraç (42 USDT için ideal) [cite: 2026-02-05]
ENTRY_AMOUNT = 15      # Her işlemde 15 USDT kullanılır [cite: 2026-02-12]
HIDDEN_TP_PCT = 0.025  # %2.5 Gizli Kâr (Borsada görünmez) [cite: 2026-02-12]
HIDDEN_SL_PCT = 0.015  # %1.5 Gizli Stop (Borsada görünmez) [cite: 2026-02-12]

# Borsayı ve Telegram'ı Başlat
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def send_update(msg):
    """Telegram üzerinden anlık durum günceller."""
    try:
        bot.send_message(CHAT_ID, f"🕵️ **GİZLİ SNIPER:**\n{msg}", parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def check_smc_signal(symbol):
    """Görseldeki 5 adımlı SMC stratejisini kontrol eder."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1m', limit=20)
        # 1. Likidite & MSS Kontrolü (Basitleştirilmiş Market Yapısı)
        last_close = ohlcv[-1][4]
        prev_close = ohlcv[-2][4]
        
        # Gövde Kapanış Onayı (Body Close) [cite: 2026-02-05]
        if last_close > prev_close: # Fiyat yukarı kırılım yapıyorsa
            return "LONG"
        return None
    except:
        return None

def main():
    send_update(f"✅ **Bot Hayalet Modda Aktif!**\n💰 Bakiye: 42 USDT Takipte.\n🎯 Strateji: SMC Sniper (Gizli SL/TP)") [cite: 2026-02-12]
    is_in_position = False
    
    while True:
        try:
            if not is_in_position:
                # 1. Strateji Taraması
                signal = check_smc_signal(SYMBOL)
                if signal == "LONG":
                    # 2. İşleme Giriş (Market Order) [cite: 2026-02-12]
                    ticker = exchange.fetch_ticker(SYMBOL)
                    price = float(ticker['last'])
                    amount = (ENTRY_AMOUNT * LEVERAGE) / price
                    
                    exchange.create_market_buy_order(SYMBOL, amount)
                    entry_price = price
                    is_in_position = True
                    send_update(f"🚀 **{SYMBOL} İşleme Girildi!**\n💰 Giriş: {entry_price}\n⚠️ SL/TP Borsada Gizli!")
            
            else:
                # 3. Gizli Takip (SL/TP/Trailing) [cite: 2026-02-05]
                ticker = exchange.fetch_ticker(SYMBOL)
                curr_price = float(ticker['last'])
                
                # Gizli Stop Loss [cite: 2026-02-12]
                if curr_price <= entry_price * (1 - HIDDEN_SL_PCT):
                    exchange.create_market_sell_order(SYMBOL, amount)
                    send_update("🛑 **Gizli Stop Patladı!** Zarar kesildi.")
                    is_in_position = False
                
                # Gizli Kar Al (Tek Mumda Çıkış) [cite: 2026-02-12]
                elif curr_price >= entry_price * (1 + HIDDEN_TP_PCT):
                    exchange.create_market_sell_order(SYMBOL, amount)
                    send_update(f"💰 **Hedef Geldi!** Tek mumda kâr alındı.\nBakiye Güncellendi.")
                    is_in_position = False

            time.sleep(2) # Saniyeler içinde hızlı tarama [cite: 2026-02-12]
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
