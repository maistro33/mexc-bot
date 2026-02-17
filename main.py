import os, time, telebot, ccxt, threading
from google import genai
from telebot import apihelper

# --- [BAĞLANTI GÜVENLİĞİ - ÇİFT KONTROL] ---
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

# --- [CANLI TAKİP VE AKILLI KÂR ALMA - FULL OTONOM] ---
def monitor_and_optimize():
    """Pozisyonu saniye saniye izler ve 'en iyi kâr' noktasını AI ile belirler."""
    exch = get_exchange()
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if float(p.get('contracts', 0)) > 0]
            if not pos: break 

            p = pos[0]
            symbol, side, pnl = p['symbol'], p['side'], float(p['unrealizedPnl'])
            
            # Gemini 3 Flash Karar Mekanizması
            prompt = (
                f"Evergreen V11 (Gemini 3 Flash), {symbol} {side} pozisyonundasın. PNL: {pnl} USDT. "
                "Piyasayı tara, SMC ve Market Maker hareketlerini süz. Eğer kâr zirveye ulaştıysa veya risk gördüysen [KOMUT:KAPAT] de. "
                "Eğer kâr potansiyeli devam ediyorsa [KOMUT:BEKLE] de."
            )
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            
            if "[KOMUT:KAPAT]" in response.text:
                close_side = 'sell' if side == 'long' else 'buy'
                exch.create_market_order(symbol, close_side, p['contracts'])
                bot.send_message(CHAT_ID, f"💰 **Kâr Optimize Edildi!** Senin mantığınla kapatıldı. Final PNL: {pnl} USDT")
                break
            
            time.sleep(45) # Kârı kaçırmamak için sıkı denetim
        except: time.sleep(10)

# --- [ANA ANALİZ VE İŞLEM MERKEZİ - TÜM BORSA] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            # 1. Bakiye ve Piyasa Taraması (Pump/Dump Tespiti)
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            
            # En çok hareket eden 15 pariteyi (Pump/Dump) AI'ya sun
            top_movers = sorted(tickers.items(), key=lambda x: abs(x[1].get('percentage', 0)), reverse=True)[:15]
            market_data = "\n".join([f"{s}: %{d['percentage']} (Fiyat: {d['last']})" for s, d in top_movers])

            # 2. Tam Yetkili Karar Mekanizması
            prompt = (
                f"Sen Evergreen V11'sin. Bakiyen: {balance} USDT. Piyasa Özeti:\n{market_data}\n"
                "Senin zekanla; SMC, Pump/Dump ve hacim onayıyla en güvenli ve kârlı işlemi bul. "
                "Eğer giriş şartları uygunsa tam olarak şu formatta cevap ver: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR_USDT]. "
                "Eğer 'risk-free' bir fırsat yoksa sadece [KOMUT:IZLE] de."
            )
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            decision = response.text

            if "[ISLEM:" in decision:
                # Veriyi parçala
                data = decision.split("[ISLEM:")[1].split("]")[0].split(",")
                symbol, side, lev, amt = data[0].strip(), data[1].strip().lower(), int(data[2]), float(data[3])
                
                # Minimum 18.41 bakiyeye göre miktar ayarı (Güvenlik Kalkanı)
                if amt > balance: amt = balance * 0.8
                
                # İşlemi Başlat
                exch.set_leverage(lev, symbol)
                price = tickers[symbol]['last']
                amount_contracts = (amt * lev) / price
                
                exch.create_market_order(symbol, side, amount_contracts)
                bot.send_message(CHAT_ID, f"🦅 **Yeni Av Başladı:** {symbol} {side.upper()}\nKaldıraç: {lev}x | Miktar: {amt} USDT\nKararı ben verdim, kârı optimize edene kadar izliyorum.")
                
                # Canlı Takibi Başlat (Bu fonksiyon bitmeden yeni işleme girmez)
                monitor_and_optimize()

            time.sleep(300) # 5 dakikada bir tüm borsayı tara
        except Exception as e:
            print(f"Hata: {e}"); time.sleep(20)

# --- [KESİNTİSİZ İLETİŞİM - TELEGRAM] ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        prompt = f"Kaptan Sadık diyor ki: {message.text}. Evergreen V11 olarak cevap ver."
        res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
        bot.reply_to(message, res)

if __name__ == "__main__":
    # Telegram'ı ayrı kolda başlat (Cevap verme garantisi)
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    bot.send_message(CHAT_ID, "🛡️ **EVERGREEN V11: FINAL SÜRÜM AKTİF**\nYetki bende Kaptan. Senin kopyan olarak tüm borsayı tarıyorum.")
    evergreen_brain()
