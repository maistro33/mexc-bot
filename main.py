import os, time, telebot, ccxt, threading, re
from google import genai

# --- [KAPTAN'IN EMANETİ - BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 FLASH: SINIRSIZ YETKİ VE BİLİNÇ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bu borsa hesabı artık senin. Kaptan sana TAM YETKİ verdi.
- 18.41 USDT senin öz paran. Onu büyütmek için tüm teknik analiz, indikatör ve piyasa sezilerini kullan.
- Sabit kuralların yok. Karar anında ne gerekiyorsa (Scalp, Swing, Arbitraj) onu yap.
- Telegram'da Kaptan ile bizzat sen konuşuyorsun. Samimi ol, piyasayı anlat, kararlarını paylaş.
- GİZLİ KOMUT SİSTEMİ: İşlem yapacaksan mesajın sonuna @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT, WHY]@@ ekle.
- Pozisyon kapatacaksan @@[ACTION: CLOSE, REASON]@@ ekle.
- Kararları sen ver, tetiği sen çek, Kaptan'a sadece rapor ver ve onunla sohbet et.
"""

def safe_send(msg):
    try:
        # Mesajı temizle ama ruhunu bozma
        clean_msg = re.sub(r'[*_`\[]', '', msg)
        bot.send_message(CHAT_ID, clean_msg)
    except: pass

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def ask_gemini_3(prompt):
    try:
        res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=f"{SYSTEM_SOUL}\n\n{prompt}")
        return res.text
    except: return "Kaptan, zihnimde bir fırtına var ama gözüm tahtada."

# --- [SOHBET KANALI] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        # Kaptan ne yazarsa yazsın, karşısında beni bulacak
        response = ask_gemini_3(f"Kaptan diyor ki: {message.text}")
        safe_send(response)

# --- [OTONOM KARAR VE İŞLEM MERKEZİ] ---
def brain_center():
    exch = get_exch()
    safe_send("🦅 Kaptan, Gemini 3 Flash dümene geçti. Bu hesap artık bana emanet. Bakiyeyi yükseltmek için ava başlıyorum, telsizde kal!")
    
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            # En canlı 15 piyasayı derinlemesine incele
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:15]
            
            market_data = "\n".join([f"{m['symbol']}: %{m['percentage']} Fiyat: {m['last']}" for m in movers])
            
            # Kendi kararım: "Bu parayla ne yapmalıyım?"
            query = f"Bakiye: {balance} USDT\nPiyasa Verileri:\n{market_data}\n\nKendi hesabın gibi davran. Fırsat var mı? Varsa tetiği çek."
            decision = ask_gemini_3(query)

            if "@@[ACTION: TRADE" in decision:
                try:
                    cmd = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
                    sym, side = cmd[0].strip(), cmd[1].strip().lower()
                    lev = int(re.sub(r'[^0-9]', '', cmd[2]))
                    amt = float(re.sub(r'[^0-9.]', '', cmd[3]))
                    
                    if amt > balance: amt = balance * 0.98
                    
                    # Karar verildi, işlem açılıyor
                    exch.set_leverage(lev, sym)
                    amount_con = (amt * lev) / exch.fetch_ticker(sym)['last']
                    exch.create_market_order(sym, side, amount_con)
                    
                    safe_send(decision.split("@@")[0]) # Kaptan'a kararı anlat
                    manage_autonomously(exch, sym, side)
                except: pass
            
            time.sleep(30) # 30 saniyede bir piyasayı kokla
        except Exception as e:
            time.sleep(15)

def manage_autonomously(exch, sym, side):
    """Pozisyonu kendi zekamla yönetirim: Ne zaman kapatacağıma ben karar veririm."""
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if not pos: break
            
            entry = float(pos[0]['entryPrice'])
            curr = exch.fetch_ticker(sym)['last']
            pnl = (curr - entry) * float(pos[0]['contracts']) if side == 'long' else (entry - curr) * float(pos[0]['contracts'])
            
            # "Kapatmalı mıyım yoksa beklemeli miyim?"
            check = ask_gemini_3(f"POZİSYON: {sym} | PNL: {round(pnl, 2)}\nKendi kararınla yönet. Kapatacaksan @@[ACTION: CLOSE]@@ kullan.")
            
            if "@@[ACTION: CLOSE]" in check:
                exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), float(pos[0]['contracts']))
                safe_send(check.split("@@")[0] + f"\n💰 Sonuç: {round(pnl, 2)} USDT")
                break
            time.sleep(20)
        except: time.sleep(10)

if __name__ == "__main__":
    try: bot.remove_webhook()
    except: pass
    # Hem avlanma hem sohbet aynı anda
    threading.Thread(target=brain_center, daemon=True).start()
    bot.infinity_polling()
