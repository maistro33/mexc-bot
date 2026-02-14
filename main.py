import ccxt
import os
import telebot
import time

# --- [BAĞLANTILAR] ---
ex = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API'), 
    'secret': os.getenv('BITGET_SEC'), 
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(os.getenv('TELE_TOKEN'))
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# --- [STRATEJİ AYARLARI] ---
SYMBOL = 'SOL/USDT:USDT'
LEVERAGE = 10
USDT_AMOUNT = 10.0
TP1_RATIO = 1.015       # %1.5 kârda yarısını kapat
SL_RATIO = 0.985        # %1.5 zarar kes (başlangıç)
TRAILING_DIST = 0.015   # %1.5 mesafeden takip et (Trailing)
BE_PLUS = 1.002         # Stopu girişin %0.20 üzerine taşı (Komisyon koruması)

def send_msg(text):
    try:
        bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def start_trade():
    try:
        # 1. HAZIRLIK VE GİRİŞ
        price = ex.fetch_ticker(SYMBOL)['last']
        amt = (USDT_AMOUNT * LEVERAGE) / price
        ex.set_leverage(LEVERAGE, SYMBOL)
        
        ex.create_order(SYMBOL, 'market', 'buy', amt, params={'posSide': 'long'})
        
        entry_price = price
        sl_price = round(entry_price * SL_RATIO, 4)
        tp1_price = round(entry_price * TP1_RATIO, 4)
        
        send_msg(f"🚀 **İşlem Başladı (SOL)**\n💰 Giriş: {entry_price}\n🛑 İlk Stop: {sl_price}\n🎯 TP1 Hedefi: {tp1_price}")

        tp1_done = False
        trailing_sl = sl_price
        
        while True:
            time.sleep(5) # 5 saniyede bir kontrol
            curr_price = ex.fetch_ticker(SYMBOL)['last']
            
            # A. ZARAR KES KONTROLÜ
            if curr_price <= trailing_sl:
                ex.create_order(SYMBOL, 'market', 'sell', amt, params={'posSide': 'long', 'reduceOnly': True})
                send_msg(f"🛑 **Stop Kapatıldı!**\nFiyat: {curr_price}\nİşlem sonlandırıldı.")
                break

            # B. TP1 KONTROLÜ (YARISINI KAPAT & BE+ TAŞI)
            if not tp1_done and curr_price >= tp1_price:
                half_amt = amt / 2
                ex.create_order(SYMBOL, 'market', 'sell', half_amt, params={'posSide': 'long', 'reduceOnly': True})
                amt = half_amt # Kalan miktar
                tp1_done = True
                
                # Stopu Girişin %0.20 üstüne taşı (Risk-Free)
                trailing_sl = round(entry_price * BE_PLUS, 4)
                send_msg(f"✅ **TP1 Tamamlandı!**\nPozisyonun %50'si satıldı.\n🛡️ **Risk-Free Modu:** Stop seviyesi {trailing_sl} (BE+) noktasına taşındı. Artık zarar ihtimali yok!")

            # C. TRAILING STOP KONTROLÜ (TP1'den sonra çalışır)
            if tp1_done:
                potential_sl = round(curr_price * (1 - TRAILING_DIST), 4)
                if potential_sl > trailing_sl:
                    trailing_sl = potential_sl
                    send_msg(f"🔄 **Trailing Güncellendi**\nYeni Takip Seviyesi: {trailing_sl}")

    except Exception as e:
        send_msg(f"❌ Hata: {str(e)}")

if __name__ == "__main__":
    start_trade()
