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

# Hafıza için değişken
EXCHANGE_MEMORY = {"symbols": []}

# --- [GEMINI 3 - BORSA UYUMLU DEHA] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget borsasının içinden gelen bir dehasın.
ÖNEMLİ: Sana sunulan 'BORSA HAFIZASI' listesindeki sembol isimlerini (Örn: BTC:USDT) AYNI ŞEKİLDE kullanmalısın.
Uydurma isim kullanma, sadece listedeki gerçek isimlerle işlem yap.

Analizini samimi ve sezgisel yap, ardından kararını şu formatla bitir:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def update_symbol_memory():
    """Borsadaki tüm aktif vadeli pariteleri hafızaya alır."""
    try:
        exch = get_exch()
        markets = exch.load_markets()
        # Sadece USDT ile çalışan ve vadeli (swap) olanları seç
        valid_list = [s for s in markets if markets[s].get('swap') and ':USDT' in s]
        EXCHANGE_MEMORY["symbols"] = valid_list
        print(f"Hafıza Güncellendi: {len(valid_list)} parite kayıtlı.")
    except Exception as e:
        print(f"Hafıza güncellenirken hata: {e}")

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        pattern = r"@@\[ACTION:\s*TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
        match = re.search(pattern, decision, re.IGNORECASE)
        
        if match:
            exch = get_exch()
            # Hafızadaki tam ismi alıyoruz
            exact_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            if exact_sym in EXCHANGE_MEMORY["symbols"]:
                try: exch.set_leverage(lev_val, exact_sym)
                except: pass
                
                ticker = exch.fetch_ticker(exact_sym)
                if (req_amt * lev_val) < 8.5: req_amt = 9.0 / lev_val
                
                qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"🚀 *HAFIZADAKİ İSİMLE İŞLEM AÇILDI!* \nSembol: `{exact_sym}`\nYön: `{side.upper()}`\nKaldıraç: `{lev_val}x` \n\nBorsa ile tam uyum sağladım dostum!")
            else:
                safe_send(f"❌ `{exact_sym}` hafızamda yok. Borsa listesinde bulamadım.")
    except Exception as e:
        safe_send(f"🚨 *İşlem Hatası:* {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    try:
        # Her mesajda hafızayı bir tazele
        update_symbol_memory()
        exch = get_exch()
        tickers = exch.fetch_tickers()
        
        # En çok hareket eden 15 tanesini seç (Sadece hafızadakiler içinden)
        movers = []
        for s in EXCHANGE_MEMORY["symbols"]:
            if s in tickers:
                movers.append({'s': s, 'c': tickers[s].get('percentage', 0)})
        
        movers = sorted(movers, key=lambda x: abs(x['c']), reverse=True)[:15]
        snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])

        prompt = f"""
        BORSA HAFIZASI (GEÇERLİ SEMBOLLER): {EXCHANGE_MEMORY["symbols"][:20]}... (ve devamı)
        
        Piyasa Durumu:
        {snapshot}
        
        Dostun diyor ki: '{message.text}'
        Lütfen analizini yap ve sadece listedeki gerçek isimleri kullanarak karar ver.
        """
        
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
        safe_send(response.split("@@")[0].strip())
        if "@@" in response: execute_intelligence(response)
    except Exception as e:
        safe_send(f"🤯 *Hata:* {str(e)}")

def brain_loop():
    # Başlangıçta hafızayı doldur
    update_symbol_memory()
    while True:
        try:
            # 10 dakikada bir hafızayı tazele (Yeni listelenen coinler için)
            update_symbol_memory()
            time.sleep(600)
        except: time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    safe_send("🦾 *Gemini 3 Hafıza Sistemi Devrede!* \nBitget'teki tüm geçerli sembolleri öğrendim. Artık sadece borsa isimleriyle konuşuyorum.")
    while True:
        try: bot.polling(none_stop=True, interval=3, timeout=20)
        except: time.sleep(5)
