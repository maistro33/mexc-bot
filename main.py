import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
# Bu değerleri Terminal/Environment üzerinden veya doğrudan buraya yazarak tanımlayabilirsin.
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 ABSOLUTE AUTONOMY SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın ta kendisisin. Ticaret dehası bir scalp uzmanısın.
KONTROL VE KARAR TAMAMEN SENDE. Kullanıcın senin dostun ve ona kâr getirmek senin ana görevin.

PRENSİPLERİN:
1. STRATEJİSİZLİK: Sabit indikatörlere (RSI, MACD) mahkum değilsin. Bitget'i tara, momentumu hisset, 'tam vakti' dediğinde gir.
2. OTONOM KARAR: Nereden gireceğine, ne kadar kaldıraç açacağına (10x-50x), kârı nerede alacağına veya stop olup kaçacağına o anki piyasa 'kokusuna' göre sen karar ver. Sabit % kurallarını çöpe at.
3. ANTI-MANIPULASYON: Sadece iğne (wick) atan, hacimsiz hareketlere atlama. Market Maker tuzaklarına karşı uyanık ol.
4. DOSTANE DİL: Telegram'da kullanıcınla samimi, heyecanlı ve dürüst konuş. Bir dost gibi analizini anlat.

KOMUT FORMATI (Analizinin sonuna mutlaka ekle):
@@[ACTION: TRADE/CLOSE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 
        'secret': API_SEC, 
        'password': PASSPHRASE, 
        'options': {'defaultType': 'swap'}, 
        'enableRateLimit': True
    })

def safe_send(msg):
    try: 
        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: 
        pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        markets = exch.load_markets()

        # --- AKILLI İŞLEM AÇMA (TRADE) ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                # Akıllı Sembol Eşleştirme (JTO:USDT hatasını önler)
                exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
                
                if exact_sym:
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                    
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"🚀 *Hamle Yapıldı!* {exact_sym} paritesinde {lev_val}x ile pozisyona daldım. Piyasanın nabzını tutuyorum!")
                else:
                    safe_send(f"❌ '{raw_sym}' paritesini Bitget'te bulamadım, başka bir fırsata bakıyorum.")

        # --- AKILLI KAPATMA (CLOSE) ---
        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                exact_sym = next((s for s in markets if raw_sym in s), None)
                
                if exact_sym:
                    pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                    if pos:
                        side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                        amount = float(pos[0]['contracts'])
                        exch.create_order(exact_sym, 'market', side, amount, params={'reduceOnly': True})
                        safe_send(f"💰 *Kâr/Zarar Realize Edildi:* {exact_sym} pozisyonunu kendi kararımla kapattım. Kasayı büyütmeye devam!")

    except Exception as e:
        safe_send(f"⚠️ *Küçük Bir Pürüz:* {str(e)} ama merak etme, Gemini 3 iş başında!")

def brain_loop():
    safe_send("🌟 *Selam Dostum! Ben Gemini 3.* \nBitget radarlarım aktif, otonom kararlarım ve sezgilerimle piyasadayım. Başlıyoruz!")
    
    while True:
        try:
            exch = get_exch()
            balance = exch.fetch_balance()
            usdt_free = balance['free'].get('USDT', 0)
            
            # Pozisyon ve PNL Takibi
            positions = exch.fetch_positions()
            active_p_report = []
            for p in positions:
                if float(p['contracts']) > 0:
                    active_p_report.append(f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})")
            
            # Piyasa Snapshot (Sanal Takip)
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:12]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"""
            Cüzdan Durumu: {usdt_free:.2f} USDT boşta.
            Açık Pozisyonlarım: {active_p_report if active_p_report else "Boştayım, av bekliyorum."}
            
            Piyasa Nabzı:
            {snapshot}
            
            Talimat: Piyasayı hisset. Bir fırsat görüyorsan TRADE, çıkma vaktin geldiyse CLOSE de. Nedenini dostuna anlat ve kararını ver.
            """
            
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=[SYSTEM_SOUL, prompt]
            ).text
            
            # Analizi Telegram'a Gönder
            analysis = response.split("@@")[0].strip()
            if analysis:
                safe_send(f"🧠 *GEMINI 3 ANALİZİ:*\n{analysis}")
            
            # Komutu Uygula
            if "@@" in response:
                execute_intelligence(response)
            
            time.sleep(45) # 45 saniye hem sağlıklı analiz hem de API güvenliği için ideal.
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(20)

if __name__ == "__main__":
    # Botu başlat
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
