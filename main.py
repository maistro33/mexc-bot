import os, time, telebot, ccxt, threading
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
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [AKILLI ANALİZ - KOTA DOSTU] ---
def gemini_ask(prompt):
    """Kotaya takılmamak için akıllı bekleme yapar."""
    try:
        res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return res.text
    except Exception as e:
        if "429" in str(e):
            print("Kota doldu, 10 dk uyku...")
            time.sleep(600)
        return "BEKLE"

# --- [TAKİP VE KARAR] ---
def monitor_trade(symbol, side, contracts):
    exch = get_exchange()
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == symbol and float(p.get('contracts', 0)) > 0]
            if not pos: break
            pnl = float(pos[0]['unrealizedPnl'])
            
            # 3 dakikada bir kontrol (Kota için)
            decision = gemini_ask(f"Evergreen V11, {symbol} {side} işlemindesin. PNL: {pnl}. Kapatmalı mıyım? [KAPAT] veya [DEVAM]")
            if "[KAPAT]" in decision:
                exch.create_market_order(symbol, ('sell' if side == 'long' else 'buy'), contracts)
                bot.send_message(CHAT_ID, f"💰 Karar Verildi: Pozisyon kapatıldı. PNL: {pnl}")
                break
            time.sleep(180)
        except: time.sleep(30)

# --- [RADAR BEYNİ] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            # Önce yolu temizle (409 Hatası Koruması)
            bot.remove_webhook()
            
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], key=lambda x: abs(x.get('percentage', 0)), reverse=True)[:5]
            
            market_data = "\n".join([f"{d['symbol']}: %{d['percentage']}" for d in movers])
            prompt = f"Bakiyen: {balance}. Piyasa:\n{market_data}\nBir işlem seç: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR] veya [PAS]"
            
            decision = gemini_ask(prompt)
            if "[ISLEM:" in decision:
                # ... (İşlem açma mantığı)
                bot.send_message(CHAT_ID, f"🦅 Hedef Belirlendi: {decision}")
                # monitor_trade(...) fonksiyonunu burada çağırır
                
            time.sleep(600) # 10 dakikada bir analiz (Kesin kota çözümü)
        except: time.sleep(60)

if __name__ == "__main__":
    # Çift bot çalışmasını engellemek için zorunlu temizlik
    bot.remove_webhook()
    time.sleep(5)
    threading.Thread(target=lambda: bot.infinity_polling(timeout=90), daemon=True).start()
    bot.send_message(CHAT_ID, "🛡️ **Evergreen V11: Hatalar Giderildi.**\nKaptan, çakışmaları ve kota sorunlarını çözdüm. Av başlıyor.")
    evergreen_brain()
