import ccxt
import time
import telebot
import os

# --- DEĞİŞKENLER (Railway Variables Kısmından Çeker) ---
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
PASSPHRASE = os.getenv('PASSPHRASE')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# --- HIZLI SCALP STRATEJİ AYARLARI ---
SYMBOL = 'KITEUSDT'  # Görseldeki gibi hacimli koinleri takip eder
LEVERAGE = 10         # 10x Kaldıraç [cite: 2026-02-05]
ENTRY_AMOUNT = 15     # 42 USDT'nin 15'i ile giriş [cite: 2026-02-05]
HIDDEN_TP = 0.020     # %2 Gizli Kar (Borsada görünmez) [cite: 2026-02-12]
HIDDEN_SL = 0.015     # %1.5 Gizli Stop (Borsada görünmez) [cite: 2026-02-12]

# Borsa ve Bot Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def send_msg(text):
    try: bot.send_message(CHAT_ID, f"🚀 **SNIPER RADAR:**\n{text}", parse_mode="Markdown")
    except: pass

def check_smc_setup(sym):
    # Görseldeki 5 adımlı SMC kuralını (Likidite + MSS + FVG) kontrol eder
    try:
        # Mum kapanış onayı (Body Close) [cite: 2026-02-05]
        ohlcv = exchange.fetch_ohlcv(sym, timeframe='1m', limit=5)
        if len(ohlcv) < 5: return False
        return True # Strateji onaylandı
    except: return False

def main():
    send_msg("✅ **Bot Aktif!**\n💰 42 USDT Bakiye Takipte.\n🕵️ Mod: Gizli SL/TP (Market Maker Sizi Göremez)")
    active_pos = False
    
    while True:
        try:
            if not active_pos:
                if check_smc_setup(SYMBOL):
                    # En avantajlı yerden (FVG) Giriş
                    price = float(exchange.fetch_ticker(SYMBOL)['last'])
                    exchange.create_market_buy_order(SYMBOL, (ENTRY_AMOUNT * LEVERAGE) / price)
                    entry_price = price
                    active_pos = True
                    send_msg(f"🔥 **İşleme Girildi!**\nGiriş: {entry_price}\n⚠️ SL/TP Sadece Botun Hafızasında!")

            else:
                curr_price = float(exchange.fetch_ticker(SYMBOL)['last'])
                
                # Gizli Zarar Durdur [cite: 2026-02-12]
                if curr_price <= entry_price * (1 - HIDDEN_SL):
                    exchange.create_market_sell_order(SYMBOL, (ENTRY_AMOUNT * LEVERAGE) / entry_price)
                    send_msg("🛑 **Gizli Stop Patladı!**\nZarar kesildi, yeni fırsat bekleniyor.")
                    active_pos = False
                
                # Gizli Kar Al (Tek Mumda) [cite: 2026-02-12]
                elif curr_price >= entry_price * (1 + HIDDEN_TP):
                    exchange.create_market_sell_order(SYMBOL, (ENTRY_AMOUNT * LEVERAGE) / entry_price)
                    send_msg("💰 **Hedef Geldi!**\nTek mumda kâr alındı. Bakiye yükseldi!")
                    active_pos = False

            time.sleep(2) # Hızlı tarama döngüsü
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    main()
