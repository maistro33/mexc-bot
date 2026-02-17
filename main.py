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

# --- [DYNAMIC & FLEXIBLE SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın otonom scalp beynisin. 
TEK BİR COİNE TAKILIP KALMA. Eğer bir fırsat borsa limitlerine takılıyorsa veya riskliyse hemen listedeki DİĞER fırsatlara bak.

Görevin:
1. Market özetindeki tüm hareketleri tara.
2. En iyi 2-3 fırsatı belirle ama en güçlüsüne odaklan.
3. Eğer borsa kuralları bir işleme izin vermezse (limit aşımı vb.), bir sonraki döngüde hemen alternatif bir sembole yönel.

KARAR FORMATI:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *GEMINI OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def find_correct_symbol(exch, input_sym):
    try:
        markets = exch.load_markets()
        clean_name = input_sym.split('/')[0].split(':')[0].upper().strip()
        for s in markets:
            if markets[s]['swap'] and (clean_name == markets[s]['base'] or clean_name + "USDT" == markets[s]['id']):
                return s
        return None
    except: return None

def execute_autonomous_trade(decision):
    try:
        exch = get_exch()
        pattern = r"@@\[ACTION: TRADE, (.*?), (.*?), (.*?), (.*?)\]@@"
        match = re.search(pattern, decision)
        
        if match:
            raw_sym = match.group(1).strip()
            side = 'buy' if 'buy' in match.group(2).lower() or 'long' in match.group(2).lower() else 'sell'
            lev = int(float(match.group(3).strip()))
            amt = float(match.group(4).strip())
            
            exact_sym = find_correct_symbol(exch, raw_sym)
            if not exact_sym: return f"❌ {raw_sym} borsada bulunamadı, listeye geri dönüyorum."

            # Market verisini çek
            market = exch.market(exact_sym)
            ticker = exch.fetch_ticker(exact_sym)
            
            # --- [HATA ÖNLEME & ALTERNATİF MANTIĞI] ---
            # 1. Kaldıraç kontrolü
            try: exch.set_leverage(lev, exact_sym)
            except Exception as e:
                return f"⚠️ {exact_sym} için kaldıraç ayarlanamadı, pas geçiliyor. (Hata: {str(e)})"
            
            # 2. Miktar ve Limit Kontrolü
            qty = (amt * lev) / ticker['last']
            max_qty = market['limits']['amount']['max']
            
            if max_qty is not None and qty > max_qty:
                # Limit aşılıyorsa inat etme, limiti zorla veya bırak
                qty = max_qty * 0.9
                safe_send(f"🔄 {exact_sym} limiti aşıldı, miktar maksimuma çekildi. Eğer olmazsa başka fırsata bakacağım.")

            qty = float(exch.amount_to_precision(exact_sym, qty))
            
            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                return f"✅ *İŞLEM AÇILDI:* {exact_sym} ({side.upper()})"
            else:
                return f"❌ {exact_sym} miktarı geçersiz, alternatif aranıyor..."
                
    except Exception as e:
        return f"🚨 Borsa Engelini Geçemedim: {str(e)}. Hemen diğer fırsatlara odaklanıyorum."

def scanner_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            
            # Tüm marketi tara
            market_data = []
            for s, d in tickers.items():
                if ':USDT' in s:
                    market_data.append({'s': s, 'c': d.get('percentage', 0), 'v': d.get('quoteVolume', 0)})
            
            # İlk 25 yerine daha geniş bir liste gönderelim ki alternatifi çok olsun
            top_list = sorted(market_data, key=lambda x: abs(x['c']), reverse=True)[:35]
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in top_list])

            prompt = f"Bakiye: {balance} USDT\n\nMARKET RADARI (Geniş Liste):\n{snapshot}\n\nLütfen en iyi fırsatı seç. Eğer borsa engeline takılırsak bir sonraki döngüde listedeki farklı bir fırsata geçeceğiz. Hedef: Sürekli akış."
            
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=[SYSTEM_SOUL, prompt]
            ).text
            
            if "@@" in response:
                result = execute_autonomous_trade(response)
                safe_send(f"{response.split('@@')[0]}\n\n{result}")
            
            time.sleep(30) # Her 30 saniyede bir yeni/alternatif fırsat kontrolü
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    safe_send("🚀 Gemini 3 Esnek Scalper Başladı! \nTek bir coine takılmadan tüm market taranıyor.")
    threading.Thread(target=scanner_loop, daemon=True).start()
    bot.infinity_polling()
