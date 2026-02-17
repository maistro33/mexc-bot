import os, time, telebot, ccxt, threading
from google import genai
from telebot import apihelper

# --- [BAĞLANTI GÜVENLİĞİ] ---
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

# --- [AKILLI TAKİP VE ÇIKIŞ - SENİN KOPYAN] ---
def monitor_and_optimize(symbol, side, contracts):
    exch = get_exchange()
    bot.send_message(CHAT_ID, f"🛡️ {symbol} için otonom takip başlatıldı. Kârı ben optimize edeceğim.")
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == symbol and float(p.get('contracts', 0)) > 0]
            if not pos: break 

            p = pos[0]
            pnl = float(p['unrealizedPnl'])
            
            # Gemini 3 Zekasıyla Dinamik Karar
            prompt = (f"Evergreen V11 (Gemini 3), {symbol} {side} pozisyonu. PNL: {pnl} USDT. "
                      "Trendi analiz et. [KOMUT:KAPAT] veya [KOMUT:BEKLE] de.")
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if "[KOMUT:KAPAT]" in response.text:
                close_side = 'sell' if side == 'long' else 'buy'
                exch.create_market_order(symbol, close_side, contracts)
                bot.send_message(CHAT_ID, f"💰 **Kâr Alındı!** Pozisyon kapatıldı. PNL: {pnl} USDT")
                break
            
            time.sleep(60) # Takipte kota riskimiz az
        except Exception as e:
            if "429" in str(e): time.sleep(120)
            else: time.sleep(20)

# --- [HİBRİT RADAR BEYNİ - KAÇIRMA YOK, KOTA DOSTU] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            # 1. BORSAYI HIZLI TARA (Kota harcamaz)
            tickers = exch.fetch_tickers()
            # Son 5 dk'da %1.5'ten fazla hareket eden 'canlı' coinleri bul
            hot_coins = [s for s, d in tickers.items() if '/USDT:USDT' in s and abs(d.get('percentage', 0)) > 1.5]

            if hot_coins:
                balance = exch.fetch_balance()['total'].get('USDT', 0)
                market_summary = "\n".join([f"{s}: %{tickers[s]['percentage']}" for s in hot_coins[:8]])
                
                # 2. SADECE HAREKET VARSA AI'YI UYANDIR
                prompt = (f"Sen Evergreen V11 (Gemini 3 Flash). Bakiyen: {balance} USDT. "
                          f"Radardaki Hareketli Coinler:\n{market_summary}\n"
                          "SMC ve Manipülasyon filtrelerini kullan. Uygunsa: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR_USDT]. "
                          "Fırsat yoksa: [KOMUT:IZLE]")
                
                response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                decision = response.text

                if "[ISLEM:" in decision:
                    data = decision.split("[ISLEM:")[1].split("]")[0].split(",")
                    symbol, side, lev, amt = data[0].strip(), data[1].strip().lower(), int(data[2]), float(data[3])
                    
                    if amt > balance: amt = balance * 0.9 # Güvenlik marjı
                    
                    exch.set_leverage(lev, symbol)
                    price = tickers[symbol]['last']
                    amount_contracts = (amt * lev) / price
                    
                    exch.create_market_order(symbol, side, amount_contracts)
                    bot.send_message(CHAT_ID, f"🚀 **FIRSAT YAKALANDI:** {symbol} {side.upper()}\nKaldıraç: {lev}x | Miktar: {amt} USDT")
                    
                    # İşlemi takibe al
                    monitor_and_optimize(symbol, side, amount_contracts)

            time.sleep(45) # 45 saniyede bir borsayı tara (Hızlı ama kota dostu)

        except Exception as e:
            if "429" in str(e):
                time.sleep(300) # Kota hatasında 5 dk uyu
            else:
                time.sleep(20)

# --- [TELEGRAM İLETİŞİM HANI] ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        prompt = f"Kaptan Sadık soruyor: {message.text}. Evergreen V11 olarak kısa ve öz cevap ver."
        try:
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
            bot.reply_to(message, res)
        except:
            bot.reply_to(message, "Şu an piyasayı analiz ediyorum, birazdan döneceğim.")

if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    bot.send_message(CHAT_ID, "🦅 **EVERGREEN V11: HİBRİT RADAR AKTİF**\nBakiye: 18.41 USDT\nHem hızlıyım hem de kota dostu. Av başlıyor.")
    evergreen_brain()
