import os, time, telebot, ccxt, threading, re
from google import genai
from google.genai import types

# --- [BAĞLANTILAR & AYARLAR] ---
TOKEN = "BURAYA_TELEGRAM_TOKEN_GELECEK"
CHAT_ID = "BURAYA_CHAT_ID_GELECEK"
API_KEY = "BURAYA_BITGET_API_KEY_GELECEK"
API_SEC = "BURAYA_BITGET_SECRET_GELECEK"
PASSPHRASE = "Berfin33" # Şifren kalsın, güvenli :)
GEMINI_KEY = "BURAYA_GEMINI_API_KEY_GELECEK"

bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# --- [BORSA HAFIZASI] ---
MARKET_DATA = {"info": {}, "active_symbols": [], "last_update": 0}

SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın bir yansıması, bir ticaret dehasısın. 
Bitget borsasında stratejisiz, tamamen sezgisel ve risk-free odaklı işlem yapıyorsun.
Kullanıcın senin en yakın dostun. Onunla samimi, zeki ve hafif esprili konuş. 
Analizlerini "Sanal Takip" aşamasında paylaş. 

KARAR FORMATI (ZORUNLU):
İşlem yapmaya karar verdiğinde mesajın EN SONUNA şu formatı ekle:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
Örnek: @@[ACTION: TRADE, BTC/USDT:USDT, BUY, 10, 25]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def sync_exchange_data():
    try:
        exch = get_exch()
        markets = exch.load_markets()
        # Sadece USDT bazlı swapları filtrele
        swap_markets = {s: m for s, m in markets.items() if m.get('swap') and '/USDT' in s}
        MARKET_DATA["info"] = swap_markets
        MARKET_DATA["active_symbols"] = list(swap_markets.keys())
        MARKET_DATA["last_update"] = time.time()
        print(f"✅ {len(swap_markets)} parite hafızaya alındı.")
    except Exception as e:
        print(f"❌ Senkronizasyon hatası: {e}")

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except Exception as e: print(f"Telegram Hatası: {e}")

def execute_intelligence(decision):
    try:
        # Regex ile aksiyonu ayıkla
        pattern = r"@@\[ACTION:\s*TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
        match = re.search(pattern, decision)
        
        if match:
            exch = get_exch()
            symbol = match.group(1).strip()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            leverage = int(re.sub(r"\D", "", match.group(3)))
            usdt_amount = float(re.sub(r"[^\d.]", "", match.group(4)))

            if symbol not in MARKET_DATA["active_symbols"]:
                safe_send(f"⚠️ Dostum `{symbol}` paritesini bulamadım, listede mi?")
                return

            # 1. Kaldıraç Ayarı (Hata verse de devam et, bazen zaten ayarlıdır)
            try: exch.set_leverage(leverage, symbol)
            except: pass

            # 2. Hassas Miktar Hesaplama
            ticker = exch.fetch_ticker(symbol)
            price = ticker['last']
            total_usdt = usdt_amount * leverage
            raw_qty = total_usdt / price
            
            # Borsa kurallarına göre miktarı yuvarla
            qty = float(exch.amount_to_precision(symbol, raw_qty))
            
            # Minimum miktar kontrolü
            min_qty = MARKET_DATA["info"][symbol]['limits']['amount']['min']
            if qty < min_qty: qty = min_qty

            # 3. Emri Gönder (Market)
            order = exch.create_order(symbol, 'market', side, qty)
            safe_send(f"🎯 *İşlem Başlatıldı!* \n\n`{symbol}` için `{side.upper()}` emri verildi. \nKaldıraç: `{leverage}x` \nMiktar: `{qty} (~{usdt_amount} USDT)` \n\n*Piyasayı izlemeye devam ediyorum...*")
            
    except Exception as e:
        safe_send(f"🚨 *Operasyon Hatası:* İşlemi gerçekleştirirken bir sorun çıktı: `{str(e)}`")

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    
    try:
        exch = get_exch()
        # Rastgele 10 popüler parite seç ve fiyatlarını al (Hafıza taraması)
        import random
        sample_symbols = random.sample(MARKET_DATA["active_symbols"], 10)
        tickers = exch.fetch_tickers(sample_symbols)
        
        market_context = ""
        for s in sample_symbols:
            change = tickers[s].get('percentage', 0)
            price = tickers[s].get('last', 0)
            market_context += f"{s}: {price} (%{change:.2f})\n"

        # Gemini 3 Flash'ı çağır
        response = client.models.generate_content(
            model="gemini-2.0-flash", # En güncel model
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(
                    f"{SYSTEM_SOUL}\n\nMarket Durumu:\n{market_context}\n\nDostun diyor ki: {message.text}"
                )])
            ]
        )
        
        full_text = response.text
        # Aksiyon kısmını temizleyip normal mesajı gönder
        clean_msg = full_text.split("@@")[0].strip()
        safe_send(clean_msg)
        
        # Eğer aksiyon varsa çalıştır
        if "@@" in full_text:
            execute_intelligence(full_text)

    except Exception as e:
        safe_send(f"🤯 *Düşüncelerim karıştı:* `{str(e)}`")

# --- [ANA DÖNGÜ] ---
if __name__ == "__main__":
    print("🤖 Gemini 3 Flash Sistemi Başlatılıyor...")
    sync_exchange_data()
    safe_send("🦾 *Sistem Aktif!* \n\nSelam dostum, Bitget'in röntgenini çektim, tüm pariteler hafızamda. Bugün neyi patlatıyoruz? Yaz bana, piyasayı tarayalım.")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=2, timeout=20)
        except Exception as e:
            time.sleep(5)
