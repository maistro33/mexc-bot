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
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap', 'createMarketBuyOrderRequiresPrice': False},
        'enableRateLimit': True
    })

def market_scanner():
    """Hacmi patlayan ve fırsat veren coinleri tarar"""
    try:
        exch = get_exchange()
        tickers = exch.fetch_tickers()
        # %5'ten fazla hareket eden ve USDT ile işlem görenleri seç
        active_coins = [f"{s}: %{d['percentage']}" for s, d in tickers.items() if '/USDT:USDT' in s and abs(d['percentage']) > 5]
        return active_coins[:15]
    except: return "Tarama hatası."

def evergreen_final_engine():
    exch = get_exchange()
    balance = exch.fetch_balance()['total'].get('USDT', 0)
    pos = exch.fetch_positions()
    active_pos = [p for p in pos if float(p.get('contracts', 0)) > 0]
    radar = market_scanner()
    
    # AI'ya verilen tam yetki promptu
    prompt = (
        f"Sen Evergreen V11'sin. 18 USDT bakiyeyle scalp yapıyorsun. Hata lüksün yok.\n"
        f"RADAR: {radar}\nBAKİYE: {balance} USDT\nPOZİSYONLAR: {active_pos}\n\n"
        f"GÖREV: Kararları sen ver. Scalp, Pump/Dump veya Trend takibi yap.\n"
        f"KOMUT FORMATI: [ISLEM: SEMBOL, YON, KALDIRAC, TP_ORANI, SL_ORANI]\n"
        f"Örnek: [ISLEM: BTC/USDT:USDT, buy, 10, 0.02, 0.01] (%2 kâr, %1 stop)\n"
        f"Stratejin: Market Maker tuzaklarına (spoofing) karşı gövde kapanışı bekle ve hacmi onayla."
    )

    try:
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        decision = response.text
        
        if "[ISLEM:" in decision:
            # Komutu parçala
            data = decision.split("[ISLEM:")[1].split("]")[0].split(",")
            symbol, side, lev, tp_p, sl_p = data[0].strip(), data[1].strip(), int(data[2]), float(data[3]), float(data[4])
            
            # 1. Kaldıraç ve Mod Ayarla
            exch.set_leverage(lev, symbol)
            
            # 2. Giriş Emri
            price = exch.fetch_ticker(symbol)['last']
            amount = (balance * 0.8 * lev) / price # Bakiyenin %80'i ile gir (Güvenlik payı)
            precision_amount = float(exch.amount_to_precision(symbol, amount))
            
            # TP ve SL Fiyatlarını Hesapla
            tp_price = price * (1 + tp_p) if side == 'buy' else price * (1 - tp_p)
            sl_price = price * (1 - sl_p) if side == 'buy' else price * (1 + sl_p)

            # Emri gönderirken TP/SL ekle (Bitget V2 formatı)
            params = {
                'stopLoss': {'triggerPrice': sl_price},
                'takeProfit': {'triggerPrice': tp_price}
            }
            exch.create_order(symbol, 'market', side, precision_amount, params=params)
            
            bot.send_message(CHAT_ID, f"🚀 **Evergreen Karar Verdi!**\n{symbol} {side} açıldı.\nKaldıraç: {lev}x\nTP: {tp_price}\nSL: {sl_price}")
        
        return decision
    except Exception as e:
        return f"Analiz raporu: {str(e)}"

@bot.message_handler(func=lambda m: True)
def handle(m):
    if str(m.chat.id) == CHAT_ID:
        bot.reply_to(m, evergreen_final_engine())

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🦅 **Evergreen V11 Otonom Zihin Devrede.**\nAnaliz başlıyor...")
    while True:
        try:
            evergreen_final_engine()
            time.sleep(300) # 5 dakikada bir otomatik analiz
        except: time.sleep(10)
