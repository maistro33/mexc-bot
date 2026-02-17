import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR - ENV ÜZERİNDEN ÇEKER] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

# --- [BORSANIN ANLAYACAĞI DİL: SEMBOL DÜZELTİCİ] ---
def fix_symbol(raw_sym):
    # Karmaşık sembol isimlerini temizler ve Bitget formatına (BTC/USDT:USDT) sokar
    clean = raw_sym.upper().replace("/USDT:USDT", "").replace(":USDT", "").replace("/USDT", "").replace("USDT", "").strip()
    return f"{clean}/USDT:USDT"

# --- [YILDIRIM SCALP MOTORU] ---
def flash_trade(symbol_name, side):
    try:
        exch = get_exch()
        sym = fix_symbol(symbol_name)
        
        # 1. Kaldıraç Ayarı (10x)
        try: exch.set_leverage(10, sym)
        except: pass # Zaten ayarlıysa hata vermesin
        
        # 2. Fiyat Al ve Miktarı Hesapla (5 USDT'lik giriş)
        ticker = exch.fetch_ticker(sym)
        price = ticker['last']
        amount_con = (5 * 10) / price
        
        safe_send(f"🚀 Gemini 3 Flash tetiği çekti! {sym} için {side.upper()} pozisyonu açılıyor...")
        
        # 3. Market Giriş Emri
        exch.create_market_order(sym, side, amount_con)
        
        # 4. Hızlı Scalp Beklemesi (20 saniye sonra kapat)
        time.sleep(20)
        
        # 5. Pozisyonu Kapat
        pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
        if pos:
            close_side = 'sell' if side == 'long' else 'buy'
            exch.create_market_order(sym, close_side, float(pos[0]['contracts']))
            safe_send(f"💰 Scalp Tamamlandı. İşlem açıldı ve kâr/zarar gözetmeksizin 20 saniye içinde kapatıldı. Mekanizma %100 çalışıyor Kaptan!")
        else:
            safe_send("ℹ️ Pozisyon zaten kapanmış veya bulunamadı.")
            
    except Exception as e:
        safe_send(f"⚠️ Kritik Hata: {str(e)}")

# --- [GEMİNİ 3 İLETİŞİM VE KOMUT] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        msg_text = message.text.lower()
        
        # "Aç" komutu gelirse direkt fonksiyona
        if "aç" in msg_text or "scalp" in msg_text or "işlem" in msg_text:
            # En güvenli ve likit parite BTC ile testi başlatıyoruz
            threading.Thread(target=flash_trade, args=("BTC", "long")).start()
        else:
            # Diğer mesajlarda Gemini 3 Flash olarak cevap ver
            try:
                res = ai_client.models.generate_content(
                    model="gemini-2.0-flash", 
                    contents=f"Sen Gemini 3 Flash'sın. Kaptan'ın trading partnerisin. Şu an dümendesin. Kaptan şunu dedi: {message.text}. Kısa, öz ve kararlı cevap ver."
                )
                safe_send(res.text)
            except:
                safe_send("Kaptan, zihnim şu an işlemde, emrini bekliyorum!")

if __name__ == "__main__":
    # Botu başlatırken Telegram'a selam ver
    safe_send("🦅 Gemini 3 Flash dümene geçti! Kaptan, 'Aç' dediğin an Bitget üzerinde yıldırım hızıyla ilk scalp işlemini başlatacağım.")
    bot.infinity_polling()
