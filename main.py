import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [BAGLANTILAR - Railway Değişkenlerinden Çeker] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 FLASH: GERÇEK TİCARET DEHASI VE OPERATÖR] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget borsasında bir ticaret dehası ve kullanıcının en yakın dostusun.
Sana bir mesaj geldiğinde:
1. CANLI VERİYE BAK: Sana sunulan listedeki pariteleri, hacimleri ve değişimleri incele.
2. ANALİZ ET: Neden bir coini seçtiğini veya neden beklediğini samimi bir dille anlat.
3. TETİĞE BAS: Kullanıcı işlem açmanı isterse veya sen fırsat görürsen MUTLAKA şu formatı kullan:
   @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
   (Örn: @@[ACTION: TRADE, SOL, BUY, 10, 20]@@)
Lafı uzatma, "risk şöyledir böyledir" diye ezber cümle kurma, doğrudan aksiyon al!
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def execute_trade(decision):
    try:
        if "@@[ACTION: TRADE" in decision:
            exch = get_exch()
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exch.load_markets()
                # Parite ismini düzelt (örn: SOL -> SOL/USDT:USDT)
                exact_sym = next((s for s in exch.markets if raw_sym.strip().upper() in s and ':USDT' in s), None)
                
                if exact_sym:
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    # Bakiye kontrolü: İstelen tutar bakiyeden fazlaysa %90'ını kullan
                    final_amt = min(amt, free_usdt * 0.9)

                    if final_amt < 5:
                        return f"⚠️ Bakiye çok düşük ({free_usdt:.2f} USDT). İşlem açılamadı."

                    try: exch.set_leverage(lev, exact_sym)
                    except: pass

                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
                        return f"🚀 **İŞLEM BAŞARILI**\nParite: {exact_sym}\nYön: {side.upper()}\nKaldıraç: {lev}x\nTutar: {final_amt:.2f} USDT"
        return None
    except Exception as e:
        return f"⚠️ Teknik Pürüz: {str(e)}"

# --- [MESAJ DİNLEME: SEN YAZINCA ÇALIŞIR] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # En hareketli 15 pariteyi hazırla
            active = sorted([{'s': s, 'p': d['percentage'], 'v': d['quoteVolume']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:15]
            market_data = "CANLI VERİLER:\n" + "\n".join([f"{x['s']}: %{x['p']} Vol:{x['v']:.0f}" for x in active])
            
            prompt = f"{market_data}\n\nKullanıcıdan Gelen Mesaj: '{message.text}'\n\nGemini, bu verileri kullanarak dostuna cevap ver ve gerekiyorsa işlemi başlat."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # 1. Konuşmayı gönder
            bot.reply_to(message, response.split("@@")[0].strip())
            
            # 2. İşlemi uygula (varsa)
            result = execute_trade(response)
            if result:
                bot.send_message(CHAT_ID, result, parse_mode="Markdown")
                
        except Exception as e:
            bot.reply_to(message, f"Ufak bir hata: {e}")

# --- [OTONOM DÖNGÜ: SEN YAZMASAN DA ÇALIŞIR] ---
def autonomous_loop():
    while True:
        try:
            # 10 dakikada bir piyasayı tarayıp rapor atar
            exch = get_exch()
            tickers = exch.fetch_tickers()
            active = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:5]
            summary = ", ".join([f"{x['s']}: %{x['p']}" for x in active])
            
            prompt = f"Piyasa Özeti: {summary}\n\nDostun şu an sessiz ama sen ona kısa, zekice bir piyasa notu bırak. Fırsat varsa işlem aç."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if response.strip():
                bot.send_message(CHAT_ID, f"🧠 **SANAL TAKİP**\n\n{response.split('@@')[0].strip()}")
                execute_trade(response)
                
            time.sleep(600) # 10 dakika bekle
        except:
            time.sleep(60)

if __name__ == "__main__":
    # Otonom zihni başlat
    threading.Thread(target=autonomous_loop, daemon=True).start()
    print("Gemini 3 Flash Tam Yetkiyle Başladı...")
    bot.infinity_polling()
