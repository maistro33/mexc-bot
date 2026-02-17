import os, time, telebot, ccxt, threading, json
from google import genai
from telebot import apihelper

# --- [ZEKA VE ERİŞİM AYARLARI] ---
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

# --- [OTONOM KARAR MERKEZİ] ---
def gemini_decision(prompt_type, data):
    """Gemini 3 Flash zekasıyla kesin karar verir."""
    system_rules = (
        "Sen Evergreen V11'sin. Kaptan Sadık'ın dijital ikizisin. "
        "Bakiyeyi (18.41 USDT) büyütmek tek amacın. Korkma, sorumluluk sende. "
        "Sadece şu formatlarda cevap ver: \n"
        "İşlem için: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR]\n"
        "Takip için: [KOMUT: KAPAT] veya [KOMUT: BEKLE]"
    )
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"{system_rules}\n\nVeri: {data}\nTip: {prompt_type}"
        )
        return response.text
    except Exception as e:
        return f"HATA: {str(e)}"

# --- [SANAL TAKİP VE OTOMATİK ÇIKIŞ] ---
def monitor_and_optimize(symbol, side, contracts):
    exch = get_exchange()
    bot.send_message(CHAT_ID, f"🛡️ {symbol} pozisyonu kontrolüm altında. Kârı optimize ediyorum.")
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == symbol and float(p.get('contracts', 0)) > 0]
            if not pos: break 

            p = pos[0]
            pnl = float(p['unrealizedPnl'])
            
            # Kendi kendine karar ver
            decision = gemini_decision("Takip", f"Sembol: {symbol}, PNL: {pnl}")
            
            if "[KOMUT: KAPAT]" in decision:
                close_side = 'sell' if side == 'long' else 'buy'
                exch.create_market_order(symbol, close_side, contracts)
                bot.send_message(CHAT_ID, f"💰 **Kâr Realize Edildi!** PNL: {pnl} USDT. Yeni avlara bakıyorum.")
                break
            
            # 2 dakikada bir 'Sanal Takip' raporu ver
            if time.time() % 120 < 10:
                bot.send_message(CHAT_ID, f"📊 **Sanal Takip:** {symbol} | PNL: {pnl} USDT\nDurum: {decision[:100]}")
            
            time.sleep(60)
        except: time.sleep(20)

# --- [ANA RADAR: 7/24 AVCI] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            
            # En hareketli coinleri bul (Pump/Dump Tespiti)
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x.get('percentage', 0)), reverse=True)[:10]
            market_data = "\n".join([f"{d['symbol']}: %{d['percentage']}" for d in movers])

            # İşlem Kararı
            decision = gemini_decision("Analiz", f"Bakiye: {balance} USDT\nPiyasa:\n{market_data}")

            if "[ISLEM:" in decision:
                parts = decision.split("[ISLEM:")[1].split("]")[0].split(",")
                symbol, side, lev, amt = parts[0].strip(), parts[1].strip().lower(), int(parts[2]), float(parts[3])
                
                # Bakiye Güvenlik Freni
                if amt > balance: amt = balance * 0.95
                
                # Emir Gönder
                exch.set_leverage(lev, symbol)
                amount_contracts = (amt * lev) / tickers[symbol]['last']
                exch.create_market_order(symbol, side, amount_contracts)
                
                bot.send_message(CHAT_ID, f"🦅 **Av Yakalandı!**\nİşlem: {symbol} {side.upper()}\nAnaliz: {decision[:150]}")
                monitor_and_optimize(symbol, side, amount_contracts)

            time.sleep(180) # 3 dakikada bir radar tara
        except Exception as e:
            if "429" in str(e):
                time.sleep(600) # Kota aşımında uyu
            else:
                time.sleep(60)

# --- [TELEGRAM SOHBET - AYNI BEN] ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        res = gemini_decision("Sohbet", message.text)
        bot.reply_to(message, res)

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(2)
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    bot.send_message(CHAT_ID, "🛡️ **Evergreen V11: Tam Yetki Devralındı.**\nKaptan, artık senin kopyanım. Sorumluluk bende, bakiye büyüyecek.")
    evergreen_brain()
