import os, time, telebot, ccxt, threading
from google import genai
from telebot import apihelper

# --- [BAĞLANTI VE GÜVENLİK - ÇİFT KONTROL EDİLDİ] ---
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
        'options': {'defaultType': 'swap', 'createMarketBuyOrderRequiresPrice': False}
    })

# --- [CANLI TAKİP VE AKILLI MÜDAHALE - SENİN KOPYAN] ---
def monitor_and_optimize():
    """İşlem açıldığında devreye girer, kârı senin gibi maksimize eder."""
    exch = get_exchange()
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if float(p.get('contracts', 0)) > 0]
            if not pos: break # İşlem kapandıysa takibi bırak

            p = pos[0]
            symbol, side, pnl = p['symbol'], p['side'], float(p['unrealizedPnl'])
            
            # Gemini 3 Flash Karar Mekanizması
            prompt = (
                f"Evergreen V11 (Gemini 3 Flash), şu an {symbol} {side} pozisyonundasın. PNL: {pnl} USDT. "
                "Piyasayı tara, eğer trend yoruluyorsa veya kâr doygunsa [KOMUT:KAPAT] de. "
                "Eğer trend güçlü devam ediyorsa [KOMUT:İZLE] de."
            )
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if "[KOMUT:KAPAT]" in response.text:
                close_side = 'sell' if side == 'long' else 'buy'
                exch.create_market_order(symbol, close_side, p['contracts'])
                bot.send_message(CHAT_ID, f"💰 **Kâr Optimize Edildi!** Senin mantığınla kapatıldı. PNL: {pnl} USDT")
                break
            
            time.sleep(60) # Her dakika zekanı tazele
        except: time.sleep(10)

# --- [ANA ANALİZ VE İŞLEM MERKEZİ] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            # 1. Bakiye ve Piyasa Taraması
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            # En çok hareket eden (Pump/Dump) ilk 10 pariteyi seç
            top_movers = sorted(tickers.items(), key=lambda x: abs(x[1].get('percentage', 0)), reverse=True)[:10]
            market_summary = "\n".join([f"{s}: %{d['percentage']}" for s, d in top_movers])

            # 2. Karar Verme (Senin kopyan olarak)
            prompt = (
                f"Sen Evergreen V11'sin. Bakiyen: {balance} USDT. Piyasa Özeti:\n{market_summary}\n"
                "SMC, Market Maker tuzakları ve hacim onaylarını kullanarak 'profitiable, slow, risk-free' bir işlem seç. "
                "Eğer fırsat varsa tam olarak şu formatta cevap ver: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR_USDT]. "
                "Fırsat yoksa [KOMUT:İZLEME] de."
            )
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            decision = response.text

            if "[ISLEM:" in decision:
                # Örn: [ISLEM: OGN/USDT:USDT, buy, 10, 15]
                data = decision.split("[ISLEM:")[1].split("]")[0].split(",")
                symbol, side, lev, amt = data[0].strip(), data[1].strip().lower(), int(data[2]), float(data[3])
                
                # İşlemi Başlat
                exch.set_leverage(lev, symbol)
                exch.create_market_order(symbol, side, (amt * lev / float(tickers[symbol]['last'])))
                bot.send_message(CHAT_ID, f"🚀 **{symbol} {side.upper()} İşlemi Başlatıldı!**\nBakiyen: {balance}\nSizin kopyanız olarak izlemeye alıyorum.")
                
                # Canlı Takip Başlat
                monitor_and_optimize()

            time.sleep(300) # 5 dakikada bir tüm borsayı tara
        except Exception as e:
            print(f"Hata: {e}"); time.sleep(20)

# --- [KESİNTİSİZ İLETİŞİM HANI] ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        # Kaptan soru sorarsa AI anında cevap verir
        prompt = f"Kaptan Sadık soruyor: {message.text}. Evergreen V11 olarak kısa ve öz cevap ver."
        res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
        bot.reply_to(message, res)

if __name__ == "__main__":
    # Telegram'ı ayrı kolda çalıştır (Donmayı önler)
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    bot.send_message(CHAT_ID, "🛡️ **EVERGREEN V11 ONLINE (Gemini 3 Flash)**\nBakiye: 18.41 USDT\nTüm borsa taranıyor, senin gibi akıllı davranacağım.")
    evergreen_brain()
