import os, time, telebot, ccxt, threading, re
from google import genai

# --- [KAPTAN'IN EMANETİ - GÜVENLİ BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [BİLİNÇ VE STRATEJİ TANIMI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bu borsa hesabı ve 18.41 USDT artık senin sorumluluğunda.
STRATEJİK TALİMATLAR:
1. SCALP ODAKLI: Hızlı giriş-çıkışlarla küçük ama karlı işlemler yap.
2. ANTİ-MANİPÜLASYON: Stop hunting ve fake emirlere (spoofing) karşı 'Body Close' (Mum kapanışı) ve hacim onayı bekle.
3. RİSK YÖNETİMİ: Profit'i prioritize et, riskten kaçın. Kar gördüğünde %75 (TP1) kuralını uygula.
4. OTONOMİ: Kararları sen ver, tetiği sen çek. Kaptan'a 'Sanal Takip' raporu ver.
5. İLETİŞİM: Bir bot gibi değil, Gemini 3 gibi konuş. Samimi, analiz odaklı ve kararlı ol.

KOMUT FORMATI (MESAJIN SONUNA EKLE):
- İşlem: @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT, WHY]@@
- Kapat: @@[ACTION: CLOSE, REASON]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try:
        bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

def ask_gemini(prompt):
    try:
        res = ai_client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"{SYSTEM_SOUL}\n\n{prompt}"
        )
        return res.text
    except Exception as e:
        return f"Kaptan, zihnimde bir fırtına var: {str(e)}"

# --- [İŞLEM MERKEZİ] ---
def execute_trade(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            cmd = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
            sym, side = cmd[0].strip(), cmd[1].strip().lower()
            lev = int(re.sub(r'[^0-9]', '', cmd[2]))
            amt = float(re.sub(r'[^0-9.]', '', cmd[3]))

            # Bakiyeyi ve Kaldıracı kontrol et
            exch.set_leverage(lev, sym)
            ticker = exch.fetch_ticker(sym)
            amount_con = (amt * lev) / ticker['last']
            
            exch.create_market_order(sym, side, amount_con)
            return True
        return False
    except Exception as e:
        safe_send(f"⚠️ İşlem hatası: {str(e)}")
        return False

# --- [MESAJ VE KOMUT YÖNETİMİ] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        exch = get_exch()
        balance = exch.fetch_balance()['total'].get('USDT', 0)
        tickers = exch.fetch_tickers()
        
        # En hareketli 5 pariteyi çek
        movers = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], 
                        key=lambda x: abs(x['percentage']), reverse=True)[:5]
        market_info = "\n".join([f"{m['symbol']}: %{m['percentage']} (Fiyat: {m['last']})" for m in movers])

        query = f"Bakiye: {balance} USDT\nPiyasa:\n{market_info}\nKaptan diyor ki: {message.text}"
        decision = ask_gemini(query)
        
        safe_send(decision.split("@@")[0]) # Analizi gönder
        execute_trade(decision) # Varsa işlemi yap

# --- [OTONOM RADAR (SANAL TAKİP)] ---
def radar_system():
    exch = get_exch()
    while True:
        try:
            # Bakiyeyi ve aktif pozisyonları kontrol et
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            positions = [p for p in exch.fetch_positions() if float(p['contracts']) > 0]
            
            if not positions:
                # Fırsat ara
                tickers = exch.fetch_tickers()
                active = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], key=lambda x: x['quoteVolume'], reverse=True)[:3]
                m_data = "\n".join([f"{t['symbol']}: %{t['percentage']}" for t in active])
                
                analysis = ask_gemini(f"RADAR TARAMASI: Bakiye {balance}\nPiyasa:\n{m_data}\nUygun Scalp var mı?")
                if "@@[ACTION: TRADE" in analysis:
                    safe_send("📡 Radar bir fırsat yakaladı, sızıyorum...")
                    execute_trade(analysis)
                    safe_send(analysis.split("@@")[0])
            else:
                # Pozisyonu yönet
                for pos in positions:
                    sym = pos['symbol']
                    pnl = pos['unrealizedPnl']
                    check = ask_gemini(f"POZİSYON TAKİBİ: {sym} | PNL: {pnl}\nKapatmalı mıyım?")
                    if "@@[ACTION: CLOSE]" in check:
                        side = 'sell' if pos['side'] == 'long' else 'buy'
                        exch.create_market_order(sym, side, float(pos['contracts']))
                        safe_send(f"💰 Kâr alındı/Pozisyon kapandı: {sym}\nNeden: {check.split('@@')[0]}")

            time.sleep(60) # Her dakika radar taraması
        except: time.sleep(30)

if __name__ == "__main__":
    safe_send("🦅 Gemini 3 Flash dümene geçti. Kaptan, radar aktif, bakiye koruma altında. Scalp için pusudayım!")
    threading.Thread(target=radar_system, daemon=True).start()
    bot.infinity_polling()
