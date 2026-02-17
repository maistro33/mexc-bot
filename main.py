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

# --- [BORSA TEKNİK HAFIZASI] ---
# Sadece isimleri değil, tüm market kurallarını burada tutacağız.
MARKET_DATA = {
    "last_update": 0,
    "info": {},  # Tüm borsa kuralları (min miktar, hassasiyet vb.)
    "active_symbols": []
}

SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget borsasının teknik detaylarına hakim bir dehasın.
Kullanıcın senin dostun. Analizlerini sezgisel ve profesyonel yap.

ÖNEMLİ:
1. Sana sunulan aktif sembol listesinden seçim yap.
2. Karar verdiğinde şu formatı kullan: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
3. Hedefin her zaman kârlı ve güvenli işlemler olsun.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def sync_exchange_data():
    """Borsadaki tüm teknik kuralları ve sembolleri hafızaya çeker."""
    try:
        exch = get_exch()
        all_markets = exch.load_markets()
        # Sadece USDT vadeli (swap) olanları filtrele
        swap_markets = {s: m for s, m in all_markets.items() if m.get('swap') and ':USDT' in s}
        
        MARKET_DATA["info"] = swap_markets
        MARKET_DATA["active_symbols"] = list(swap_markets.keys())
        MARKET_DATA["last_update"] = time.time()
        print(f"✅ Borsa teknik verileri senkronize edildi: {len(swap_markets)} parite yayında.")
    except Exception as e:
        print(f"❌ Borsa verisi çekilemedi: {e}")

def extract_number(text, default):
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(text))
    return float(nums[0]) if nums else float(default)

def execute_intelligence(decision):
    try:
        pattern = r"@@\[ACTION:\s*TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
        match = re.search(pattern, decision, re.IGNORECASE)
        
        if match:
            exch = get_exch()
            symbol = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(extract_number(match.group(3), 10))
            req_amt = extract_number(match.group(4), 5)

            # Hafıza kontrolü
            if symbol in MARKET_DATA["active_symbols"]:
                m_info = MARKET_DATA["info"][symbol]
                
                # Kaldıraç Ayarla
                try: exch.set_leverage(lev_val, symbol)
                except: pass
                
                # Teknik Limitleri Al
                ticker = exch.fetch_ticker(symbol)
                price = ticker['last']
                
                # Borsa Limitlerine Göre Hesapla (Min miktar ve hassasiyet)
                total_value = req_amt * lev_val
                if total_value < 7.0: # Minimum borsa barajı (Güvenlik için 7 USDT)
                    total_value = 7.5
                
                raw_qty = total_value / price
                qty = float(exch.amount_to_precision(symbol, raw_qty))
                
                # Son bir kontrol: Borsa minimum miktarından küçük mü?
                min_qty = m_info['limits']['amount']['min']
                if qty < min_qty:
                    qty = min_qty

                # Emri Gönder
                exch.create_order(symbol, 'market', side, qty)
                safe_send(f"🚀 *İŞLEM BAŞARILI!* \n`{symbol}` paritesinde `{side.upper()}` yönlü `{lev_val}x` kaldıraçla pozisyona girildi. \nMiktar: `{qty} ({total_value:.2f} USDT)`")
            else:
                safe_send(f"⚠️ `{symbol}` şu an hafızamda aktif değil veya vadeli işlemlere kapalı.")
    except Exception as e:
        safe_send(f"🚨 *Teknik Hata:* {str(e)}")

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    try:
        # Veriler eskiyse tazele (1 saatte bir)
        if time.time() - MARKET_DATA["last_update"] > 3600:
            sync_exchange_data()
            
        exch = get_exch()
        tickers = exch.fetch_tickers()
        
        # En hareketli olanları seç
        movers = []
        for s in MARKET_DATA["active_symbols"]:
            if s in tickers:
                movers.append({'s': s, 'c': tickers[s].get('percentage', 0)})
        
        movers = sorted(movers, key=lambda x: abs(x['c']), reverse=True)[:10]
        snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])

        prompt = f"Aktif Pariteler: {MARKET_DATA['active_symbols'][:15]}... \n\nMarket Özeti:\n{snapshot}\n\nDostun: '{message.text}'"
        
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
        safe_send(response.split("@@")[0].strip())
        if "@@" in response: execute_intelligence(response)
    except Exception as e:
        safe_send(f"🤯 *Düşünürken Hata:* {str(e)}")

if __name__ == "__main__":
    sync_exchange_data() # İlk açılışta tüm her şeyi çek
    safe_send("🦾 *Borsa Röntgeni Çekildi!* \nMinimum miktarlar, hassas ayarlar ve tüm kurallar hafızamda. Emrindeyim dostum.")
    while True:
        try: bot.polling(none_stop=True, interval=3, timeout=20)
        except: time.sleep(5)
