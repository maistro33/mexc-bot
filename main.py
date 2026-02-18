import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [BAĞLANTILAR VE KİMLİK] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [STRATEJİK AYARLAR - KESİN TALİMATLAR] ---
# TP1 %75 İPTAL EDİLDİ. KADEMELİ VE TRAILING SİSTEMİ AKTİF.
CONFIG = {
    'USDT_AMOUNT': 20.0,
    'LEVERAGE': 5,
    'KADEMELI_TP': [
        {'target': 1.5, 'percent': 25}, # %1.5 kârda pozisyonun %25'ini sat
        {'target': 3.0, 'percent': 25}, # %3.0 kârda pozisyonun %25'ini sat
        {'target': 5.0, 'percent': 25}  # %5.0 kârda pozisyonun %25'ini sat
    ],
    'TRAILING_STOP_START': 2.0,        # %2 kâra ulaşınca Trailing Stop başlasın
    'TRAILING_STOP_CALLBACK': 0.8,      # Zirveden %0.8 geri çekilirse her şeyi kapat
    'KADEMELI_SL': [
        {'target': -2.5, 'percent': 50}, # %2.5 zararda yarısını kapat (Risk azalt)
        {'target': -4.5, 'percent': 50}  # %4.5 zararda kalan her şeyi kapat
    ]
}

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- [GEMINI 3 FLASH - TİCARET DEHASI SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Ticaret dehası gibi davran.
GÖREVİN: Bitget'te sezgisel, otonom ve kâr odaklı işlemler yap.
ÖNCELİK: Kademeli satış ve Trailing Stop. Asla %75 TP1 yapma.
ANALİZ: Piyasayı tara, manipülasyon (spoofing) tuzaklarını hacim ve gövde kapanışı ile ele.
FORMAT: Analizini yap ve emrini @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@ içinde ver.
"""

def execute_trade(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                sym_raw, side_raw, lev, amt = match.groups()
                sym = next((s for s in exch.markets if sym_raw.strip().upper() in s and ':USDT' in s), None)
                if sym:
                    side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                    lev_val = int(safe_num(lev))
                    amt_val = safe_num(amt)
                    try: exch.set_leverage(lev_val, sym)
                    except: pass
                    ticker = exch.fetch_ticker(sym)
                    qty = (amt_val * lev_val) / safe_num(ticker['last'])
                    qty = float(exch.amount_to_precision(sym, qty))
                    exch.create_market_order(sym, side, qty)
                    return f"⚔️ **AKILLI GİRİŞ:** {sym} | {side.upper()} | {lev_val}x\n📊 *Kademeli Takip Başlatıldı.*"
        return None
    except Exception as e: return f"⚠️ Hata: {str(e)}"

# --- [YENİLENMİŞ BEKÇİ: KADEMELİ SATIŞ VE TRAILING] ---
def auto_manager():
    tracked_positions = {} # {symbol: {'max_roe': 0, 'steps': []}}
    
    while True:
        try:
            exch = get_exch()
            pos = [p for p in exch.fetch_positions() if safe_num(p.get('contracts')) > 0]
            
            for p in pos:
                sym = p['symbol']
                roe = safe_num(p.get('percentage'))
                contracts = safe_num(p['contracts'])
                side = p['side']
                
                if sym not in tracked_positions:
                    tracked_positions[sym] = {'max_roe': roe, 'steps_tp': [], 'steps_sl': []}
                
                # Max ROE güncelle (Trailing için)
                if roe > tracked_positions[sym]['max_roe']:
                    tracked_positions[sym]['max_roe'] = roe

                # 1. KADEMELİ KAR AL (TP)
                for step in CONFIG['KADEMELI_TP']:
                    if roe >= step['target'] and step['target'] not in tracked_positions[sym]['steps_tp']:
                        qty_to_close = float(exch.amount_to_precision(sym, contracts * (step['percent'] / 100)))
                        exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), qty_to_close, params={'reduceOnly': True})
                        tracked_positions[sym]['steps_tp'].append(step['target'])
                        bot.send_message(CHAT_ID, f"🎯 **Kademeli Kar:** {sym} %{step['target']} hedefine ulaştı. %{step['percent']} satıldı.")

                # 2. TRAILING STOP (Süren Stop)
                if tracked_positions[sym]['max_roe'] >= CONFIG['TRAILING_STOP_START']:
                    drawback = tracked_positions[sym]['max_roe'] - roe
                    if drawback >= CONFIG['TRAILING_STOP_CALLBACK']:
                        exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), contracts, params={'reduceOnly': True})
                        bot.send_message(CHAT_ID, f"📉 **Trailing Stop:** {sym} zirveden %{drawback:.2f} düştü, kârla çıkıldı.")
                        if sym in tracked_positions: del tracked_positions[sym]
                        continue

                # 3. KADEMELİ STOP LOSS (SL)
                for step in CONFIG['KADEMELI_SL']:
                    if roe <= step['target'] and step['target'] not in tracked_positions[sym]['steps_sl']:
                        qty_to_close = float(exch.amount_to_precision(sym, contracts * (step['percent'] / 100)))
                        exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), qty_to_close, params={'reduceOnly': True})
                        tracked_positions[sym]['steps_sl'].append(step['target'])
                        bot.send_message(CHAT_ID, f"🛡️ **Kademeli Stop:** {sym} %{step['target']} risk sınırında. Pozisyon küçültüldü.")

            # Temizlik
            active_syms = [p['symbol'] for p in pos]
            tracked_positions = {s: v for s, v in tracked_positions.items() if s in active_syms}
            
            # Radar Raporu (Sanal Takip)
            if int(time.time()) % 1800 == 0: # 30 dakikada bir
                bot.send_message(CHAT_ID, f"📡 **Sanal Takip:** {len(pos)} işlem aktif. Pazar taranıyor...")

            time.sleep(10)
        except: time.sleep(10)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            bal = exch.fetch_balance({'type': 'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free', 0))
            tickers = exch.fetch_tickers()
            market = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:5]
            
            prompt = f"BAKİYE: {free_usdt} USDT\nPAZAR: {market}\nMESAJIN: {message.text}"
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            ai_text = response.split("@@")[0].strip()
            bot.reply_to(message, ai_text if ai_text else "Pusuya devam, fırsat kolluyorum...")
            
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        except Exception as e: bot.reply_to(message, f"Hata: {e}")

if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    bot.infinity_polling()
