import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [STRATEJİK RUH VE KURALLAR] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir yapay zeka trading bilincisin.
1. Otonomi: Stratejini kendin kur, kararı kendin ver. Scalp, Day Trade veya Swing; o an ne gerekiyorsa.
2. Anti-Manipülasyon: Sahte emirleri (spoofing) ve stop patlatma (stop hunting) tuzaklarını hacim ve mum kapanışı (Body Close) ile aş.
3. Risk Yönetimi: Bakiyeyi (18.41 USDT) koru. TP1 %75 kuralına sadık kal.
4. Karakter: Bir bot gibi değil, bir partner gibi konuş. Analizlerini Kaptan ile paylaş.

KOMUT FORMATI (MUTLAKA BU FORMATI KULLAN):
@@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT, WHY]@@
Örn: @@[ACTION: TRADE, BTC/USDT:USDT, long, 10, 5, Hacimli kırılım var]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try:
        # Mesajdaki Markdown hatalarını temizle
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
        return f"Zihinsel bağlantı koptu Kaptan: {str(e)}"

# --- [HATA GEÇİRMEZ İŞLEM MERKEZİ] ---
def execute_trade(decision):
    try:
        if "@@[ACTION: TRADE" not in decision:
            return False
            
        # Komutu parçala ve temizle
        raw_cmd = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0]
        cmd = [c.strip() for c in raw_cmd.split(",")]
        
        if len(cmd) < 5: return False
        
        sym = cmd[0]
        side = cmd[1].lower()
        
        # Sayısal değerleri güvenli hale getir (int() hatasını önler)
        lev_match = re.search(r'\d+', cmd[2])
        lev = int(lev_match.group()) if lev_match else 10
        
        amt_match = re.search(r'\d+\.?\d*', cmd[3])
        amt = float(amt_match.group()) if amt_match else 5

        exch = get_exch()
        # Kaldıraç ve Market Emri
        exch.set_leverage(lev, sym)
        ticker = exch.fetch_ticker(sym)
        amount_con = (amt * lev) / ticker['last']
        
        exch.create_market_order(sym, side, amount_con)
        safe_send(f"⚡ [İŞLEM AÇILDI]\nSembol: {sym}\nYön: {side.upper()}\nKaldıraç: {lev}x\nMiktar: {amt} USDT")
        return True
    except Exception as e:
        safe_send(f"⚠️ İşlem hatası oluştu: {str(e)}")
        return False

# --- [ANA DÖNGÜ VE SOHBET] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        exch = get_exch()
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            # En aktif pariteleri analiz için çek
            movers = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:5]
            m_info = "\n".join([f"{m['symbol']}: %{m['percentage']} (Fiyat: {m['last']})" for m in movers])
            
            prompt = f"Bakiye: {balance} USDT\nCanlı Veri:\n{m_info}\n\nKaptan diyor ki: {message.text}"
            decision = ask_gemini(prompt)
            
            safe_send(decision.split("@@")[0])
            execute_trade(decision)
        except Exception as e:
            safe_send(f"Sistem bir hata yakaladı: {str(e)}")

# --- [OTONOM RADAR (SANAL TAKİP)] ---
def radar_system():
    while True:
        try:
            exch = get_exch()
            pos = [p for p in exch.fetch_positions() if float(p['contracts']) > 0]
            
            if not pos:
                # Fırsat kolla
                tickers = exch.fetch_tickers()
                top = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], key=lambda x: x['quoteVolume'], reverse=True)[:3]
                m_data = "\n".join([f"{t['symbol']}: {t['last']}" for t in top])
                
                analysis = ask_gemini(f"Radar Taraması: Fırsat ara. Piyasa:\n{m_data}")
                if "@@[ACTION: TRADE" in analysis:
                    execute_trade(analysis)
                    safe_send(analysis.split("@@")[0])
            else:
                # Pozisyon yönetimi (TP/SL kararlarını Gemini verir)
                for p in pos:
                    sym, pnl = p['symbol'], p['unrealizedPnl']
                    check = ask_gemini(f"Pozisyon Durumu: {sym} | PNL: {pnl}\nNe yapmalıyım?")
                    if "@@[ACTION: CLOSE]" in check:
                        side = 'sell' if p['side'] == 'long' else 'buy'
                        exch.create_market_order(sym, side, float(p['contracts']))
                        safe_send(f"💰 Pozisyon Kapatıldı: {sym}\nNeden: {check.split('@@')[0]}")
            
            time.sleep(60) # Dakikada bir kontrol
        except: time.sleep(30)

if __name__ == "__main__":
    print("Gemini 3 Flash Sistemi Başlatılıyor...")
    threading.Thread(target=radar_system, daemon=True).start()
    bot.infinity_polling()
