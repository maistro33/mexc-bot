#!/usr/bin/env python3
"""
SADIK CHAT TRADING BOT
Seninle konusur gibi - dogal dil anlama
GPT-4o ile tam otonom
"""

import os, time, threading, logging, json, re
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK")

# CONFIG
TELE_TOKEN  = os.getenv("TELE_TOKEN","")
CHAT_ID     = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API  = os.getenv("BITGET_API","")
BITGET_SEC  = os.getenv("BITGET_SEC","")
BITGET_PASS = os.getenv("BITGET_PASS","")
SUPA_URL    = os.getenv("SUPABASE_URL","")
SUPA_KEY    = os.getenv("SUPABASE_KEY","")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY","")
CG_KEY      = os.getenv("COINGLASS_API_KEY","")

LEVERAGE       = 5
MARGIN         = 10.0
MAX_OPEN       = 5
SCAN_INTERVAL  = 90
MIN_QUOTE_VOL  = 3_000_000
MAX_PRICE      = 30
COMMISSION     = 0.0006
MAX_DAILY_LOSS = -15.0

# STATE
positions    = {}
pos_lock     = threading.Lock()
pos_messages = {}
msg_lock     = threading.Lock()
daily_pnl    = 0.0
bot_active   = True
gpt_calls    = 0

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ",
}

# TELEGRAM
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# SUPABASE
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] OK")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("gpt_trades").insert(data).execute()
    except Exception as e: log.error(f"[SAVE] {e}")

def load_history(limit=8):
    if not supa: return "Gecmis yok."
    try:
        r = supa.table("gpt_trades").select("symbol,signal,pnl,neden,reason").order("created_at", desc=True).limit(limit).execute()
        data = r.data or []
        if not data: return "Henuz islem yok."
        lines = []
        for d in data:
            icon = "+" if float(d.get("pnl") or 0) > 0 else "-"
            lines.append(f"[{icon}] {d.get('symbol','').split('/')[0]} {d.get('signal','')} {float(d.get('pnl') or 0):+.2f}$ | {d.get('neden','')[:40]}")
        return "\n".join(lines)
    except: return "Gecmis yuklenemedi."

# EXCHANGE
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API = 0
api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global LAST_API
    for i in range(4):
        try:
            with api_lock:
                w = 0.6 - (time.time() - LAST_API)
                if w > 0: time.sleep(w)
                LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            log.warning(f"[API] {e}")
            time.sleep(2)
    return None

# BTC
def get_btc():
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=24)
        if not raw: return "NEUTRAL", 0, 0
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        c = df["c"]
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        price = float(c.iloc[-1])
        chg = (price - float(c.iloc[0])) / float(c.iloc[0]) * 100
        if price > e20 * 1.001: return "UP", price, chg
        if price < e20 * 0.999: return "DOWN", price, chg
        return "NEUTRAL", price, chg
    except: return "NEUTRAL", 0, 0

# COIN VERİSİ
def get_coin(symbol):
    try:
        raw1 = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=30)
        if not raw1: return None
        df1 = pd.DataFrame(raw1, columns=["t","o","h","l","c","v"])
        raw5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=20)
        if not raw5: return None
        df5 = pd.DataFrame(raw5, columns=["t","o","h","l","c","v"])
        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=10)
        if not raw1h: return None
        df1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])

        c1 = df1["c"]; v1 = df1["v"]
        price = float(c1.iloc[-1])
        d = c1.diff()
        rsi = float((100 - 100/(1+d.clip(lower=0).rolling(14).mean()/(-d.clip(upper=0)).rolling(14).mean().replace(0,0.001))).iloc[-1])
        ema9 = float(c1.ewm(span=9).mean().iloc[-1])
        ema20 = float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5 = float(df5["c"].ewm(span=9).mean().iloc[-1])
        ema20_5 = float(df5["c"].ewm(span=20).mean().iloc[-1])
        ema20_1h = float(df1h["c"].ewm(span=20).mean().iloc[-1])
        ema12 = c1.ewm(span=12).mean()
        ema26 = c1.ewm(span=26).mean()
        macd_hist = float((ema12-ema26-(ema12-ema26).ewm(span=9).mean()).iloc[-1])
        bb_ma = float(c1.rolling(20).mean().iloc[-1])
        bb_std = float(c1.rolling(20).std().iloc[-1])
        bb_upper = bb_ma + 2*bb_std; bb_lower = bb_ma - 2*bb_std
        bb_pct = (price-bb_lower)/(bb_upper-bb_lower)*100 if bb_upper != bb_lower else 50
        vol_avg = float(v1.rolling(20).mean().iloc[-1])
        vol_ratio = float(v1.iloc[-1]) / max(vol_avg, 0.001)
        move_1 = (price-float(c1.iloc[-2]))/float(c1.iloc[-2])*100
        move_5 = (price-float(c1.iloc[-6]))/float(c1.iloc[-6])*100
        move_1h = (price-float(df1h["c"].iloc[-2]))/float(df1h["c"].iloc[-2])*100
        candles = "".join(["+" if float(df1["c"].iloc[i])>float(df1["o"].iloc[i]) else "-" for i in range(-5,0)])

        return {
            "symbol": symbol, "price": price, "rsi": rsi,
            "ema_1m": "YUKARI" if ema9>ema20 else "ASAGI",
            "ema_5m": "YUKARI" if ema9_5>ema20_5 else "ASAGI",
            "ema_1h": "USTUNDE" if price>ema20_1h else "ALTINDA",
            "macd": "POZ" if macd_hist>0 else "NEG",
            "bb_pct": bb_pct, "vol_ratio": vol_ratio,
            "move_1": move_1, "move_5": move_5, "move_1h": move_1h,
            "candles": candles,
        }
    except Exception as e:
        log.warning(f"[COIN] {symbol}: {e}")
        return None

# GPT CAGRI
def gpt(messages, model="gpt-4o", max_tokens=400):
    global gpt_calls
    if not OPENAI_KEY: return None
    gpt_calls += 1
    if gpt_calls > 500: return None
    try:
        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "temperature": 0.3, "messages": messages},
            timeout=25)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception as e:
        log.warning(f"[GPT] {e}")
        return None

# SYSTEM PROMPT
SYSTEM = """Sen SADIK, bir kripto futures paper trading botusun.
Kullanicinin hem trading asistanisin hem de borsada islem yapiyorsun.

TRADING KURALLARI:
- Komisyon: %0.12 | Kaldirac: 5x | Margin: 10 USDT
- BTC UP = LONG icin ideal | BTC DOWN = SHORT icin ideal
- BTC NEUTRAL = dikkatli ol
- Minimum kar %1.2 olmadan kapatma
- Zarar %2 gecince kapat
- Gunluk max zarar -15 USDT

KONUSMA:
- Kullanici dogal Turkce ile konusuyor, sen de ayni sekilde cevap ver
- Coin sordugunda gercek verilere bak ve karar ver
- "Analiz edeyim" deme, direkt sonucu soy le
- Kisa ve net ol

ISLEM ACMAK ICIN JSON:
{"ac": true, "symbol": "AVAX/USDT:USDT", "yon": "LONG", "tp": 2.0, "sl": 1.0, "guven": 80, "not": "neden"}

KAPATMAK ICIN JSON:
{"kapat": "AVAX"}
{"hepsini_kapat": true}"""

# POZISYON BILGISI
def pos_info():
    if not positions:
        return "Acik pozisyon yok."
    lines = []
    for sym, pos in positions.items():
        t = safe_api(exchange.fetch_ticker, sym)
        if t:
            price = t["last"]
            entry = pos["entry"]
            signal = pos["signal"]
            pnl = (price-entry)/entry*MARGIN*LEVERAGE if signal=="LONG" else (entry-price)/entry*MARGIN*LEVERAGE
            sure = int((time.time()-pos["open_time"])/60)
            icon = "+" if pnl >= 0 else "-"
            lines.append(f"[{icon}] {sym.split('/')[0]} {signal} PnL:{pnl:+.2f}$ {sure}dk")
    return "\n".join(lines)

# COİN BUL
def find_coin(text):
    """Mesajdaki coin sembolunu bul"""
    text_upper = text.upper()
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None, None
        
        # En uzun eslesen sembolu bul
        best_match = None
        best_len = 0
        for symbol in tickers.keys():
            if not symbol.endswith("/USDT:USDT"): continue
            sym = symbol.split("/")[0].upper()
            if sym in BLACKLIST: continue
            if len(sym) >= 2 and sym in text_upper and len(sym) > best_len:
                best_match = symbol
                best_len = len(sym)
        return best_match, tickers.get(best_match)
    except:
        return None, None

# ISLEM AC
def open_pos(symbol, yon, tp_pct, sl_pct, guven, neden, btc_trend):
    global daily_pnl
    tp_pct = max(0.015, min(float(tp_pct)/100, 0.060))
    sl_pct = max(0.008, min(float(sl_pct)/100, 0.025))
    if tp_pct <= sl_pct: tp_pct = sl_pct * 1.5

    with pos_lock:
        if symbol in positions: return False
        if len(positions) >= MAX_OPEN: return False
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t: return False
        price = t["last"]
        positions[symbol] = {
            "signal": yon, "entry": price,
            "ref_tp": tp_pct*100, "ref_sl": sl_pct*100,
            "max_pnl": 0.0, "guven": guven, "neden": neden,
            "btc_trend": btc_trend, "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    tg(f"\U0001f4cb {sym} {yon}\nGiris: {price:.6f}\nRef TP: +%{tp_pct*100:.1f} | Ref SL: -%{sl_pct*100:.1f}\nGuven: {guven}% | BTC: {btc_trend}\n\U0001f4ac {neden}")
    return True

# ISLEM KAPAT
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl, bot_active
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return
    with msg_lock:
        pos_messages.pop(symbol, None)

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig = pos["signal"]; entry = pos["entry"]
    pos_size = MARGIN * LEVERAGE
    if sig == "LONG":
        pnl = (exit_price-entry)/entry*pos_size - pos_size*COMMISSION
    else:
        pnl = (entry-exit_price)/entry*pos_size - pos_size*COMMISSION

    sure = int((time.time()-pos["open_time"])/60)
    daily_pnl += pnl

    if daily_pnl <= MAX_DAILY_LOSS and bot_active:
        bot_active = False
        tg(f"\u26d4 GUNLUK LIMIT! {daily_pnl:+.2f}$ — Bot durduruldu.")

    save_trade({
        "symbol": symbol, "signal": sig, "pnl": round(pnl,4),
        "tp_pct": pos.get("ref_tp",0), "sl_pct": pos.get("ref_sl",0),
        "guven": pos.get("guven",0), "btc_trend": pos.get("btc_trend",""),
        "sure_dk": sure, "reason": reason, "neden": pos.get("neden",""),
    })

    icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk")

# YONETICI
def manage_loop():
    while True:
        time.sleep(30)
        try:
            with pos_lock: syms = list(positions.keys())
            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = t["last"]
                sig = pos["signal"]; entry = pos["entry"]
                sure = int((time.time()-pos["open_time"])/60)
                pos_size = MARGIN * LEVERAGE

                if sig == "LONG":
                    pnl_pct = (price-entry)/entry*100
                    pnl = (price-entry)/entry*pos_size - pos_size*COMMISSION
                else:
                    pnl_pct = (entry-price)/entry*100
                    pnl = (entry-price)/entry*pos_size - pos_size*COMMISSION

                with pos_lock:
                    if symbol in positions and pnl_pct > positions[symbol].get("max_pnl", 0):
                        positions[symbol]["max_pnl"] = pnl_pct

                if sure > 120:
                    close_pos(symbol, "ZAMAN ASIMI 2 saat", price)
                    continue

                if sure < 3: continue

                # GPT yonetim
                with msg_lock:
                    msgs = list(pos_messages.get(symbol, []))
                if not msgs:
                    msgs = [{"role": "system", "content": SYSTEM}]

                sym = symbol.split("/")[0]
                update = (
                    f"{sym} {sig} — {sure}. dakika\n"
                    f"Giris: {entry:.6f} | Simdi: {price:.6f}\n"
                    f"PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%)\n"
                    f"Max kar: %{pos.get('max_pnl',0):.2f}\n\n"
                    f"DEVAM mi KAPAT mi? Min %1.2 kar olmadan kapatma.\n"
                    f"JSON: {{\"devam\": true}} veya {{\"kapat\": true, \"neden\": \"...\"}}"
                )

                new_msgs = msgs + [{"role": "user", "content": update}]
                yanit = gpt(new_msgs, model="gpt-4o-mini", max_tokens=100)
                if not yanit: continue

                try:
                    j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                    if j:
                        karar = json.loads(j.group())
                        if karar.get("kapat"):
                            if pnl_pct > 0 and pnl_pct < 1.2:
                                continue  # Min kar yok, devam
                            neden = karar.get("neden", "GPT kapat")
                            close_pos(symbol, neden, price)
                        else:
                            new_msgs.append({"role": "assistant", "content": yanit})
                            if len(new_msgs) > 16:
                                new_msgs = [new_msgs[0]] + new_msgs[-8:]
                            with msg_lock:
                                pos_messages[symbol] = new_msgs
                except Exception as e:
                    log.warning(f"[YON] {e}")

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# TARAYICI
def scanner_loop():
    global bot_active
    while True:
        try:
            if not bot_active:
                time.sleep(SCAN_INTERVAL); continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(30); continue

            btc_trend, btc_price, btc_change = get_btc()
            if btc_trend == "NEUTRAL":
                log.info("[SCAN] BTC NEUTRAL")
                time.sleep(SCAN_INTERVAL); continue

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            candidates = []
            with pos_lock: open_syms = set(positions.keys())

            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                if symbol.split("/")[0] in BLACKLIST: continue
                if symbol in open_syms: continue
                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_QUOTE_VOL: continue
                price = ticker.get("last") or 0
                if not price or price > MAX_PRICE: continue
                if abs(ticker.get("percentage") or 0) < 0.5: continue
                candidates.append({"symbol": symbol, "volume": qv})

            candidates.sort(key=lambda x: x["volume"], reverse=True)
            candidates = candidates[:10]
            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend}")

            if not candidates:
                time.sleep(SCAN_INTERVAL); continue

            # Veri topla
            coins_data = []
            for c in candidates:
                d = get_coin(c["symbol"])
                if d: coins_data.append(d)
                time.sleep(0.3)

            if not coins_data:
                time.sleep(SCAN_INTERVAL); continue

            # GPT batch analiz
            history = load_history(6)
            summary = ""
            for d in coins_data:
                sym = d["symbol"].split("/")[0]
                summary += f"\n{sym}: RSI={d['rsi']:.0f} EMA1m={d['ema_1m']} EMA5m={d['ema_5m']} MACD={d['macd']} Hacim={d['vol_ratio']:.1f}x Hareket5dk={d['move_5']:+.2f}%"

            msgs = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": (
                    f"BTC: {btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)\n"
                    f"Gecmis islemlerim:\n{history}\n\n"
                    f"Analiz et, en iyi 1-2 islem sec:\n{summary}\n\n"
                    f"JSON liste olarak ver:\n"
                    f'[{{"ac": true, "symbol": "COIN/USDT:USDT", "yon": "LONG", "tp": 2.0, "sl": 1.0, "guven": 80, "not": "neden"}}]\n'
                    f"Hicbiri uygun degilse: []"
                )}
            ]

            yanit = gpt(msgs, model="gpt-4o", max_tokens=400)
            if not yanit:
                time.sleep(SCAN_INTERVAL); continue

            try:
                j = re.search(r'\[.*?\]', yanit, re.DOTALL)
                if j:
                    kararlar = json.loads(j.group())
                    for k in kararlar:
                        if not k.get("ac"): continue
                        symbol = k.get("symbol","")
                        yon = k.get("yon","LONG")
                        with pos_lock:
                            if len(positions) >= MAX_OPEN: break
                            if symbol in positions: continue
                        with msg_lock:
                            pos_messages[symbol] = [
                                {"role": "system", "content": SYSTEM},
                                {"role": "user", "content": f"{symbol} icin {yon} sectim"},
                                {"role": "assistant", "content": yanit}
                            ]
                        open_pos(symbol, yon, k.get("tp",2.0), k.get("sl",1.0), k.get("guven",70), k.get("not",""), btc_trend)
                        time.sleep(1)
            except Exception as e:
                log.warning(f"[SCAN JSON] {e}")

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# HEALTH
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(f"OK|pos:{len(positions)}|pnl:{daily_pnl:+.2f}|gpt:{gpt_calls}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# ANA MESAJ HANDLER - dogal dil
@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    text = msg.text.strip()

    # /durum komutu
    if text.startswith("/durum") or text.startswith("/status"):
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "\U0001f4cb Acik pozisyon yok."); return
            lines = ["\U0001f4cb POZISYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if t:
                    price = t["last"]; entry = pos["entry"]; signal = pos["signal"]
                    pnl = (price-entry)/entry*MARGIN*LEVERAGE if signal=="LONG" else (entry-price)/entry*MARGIN*LEVERAGE
                    pnl_pct = (price-entry)/entry*100 if signal=="LONG" else (entry-price)/entry*100
                    sure = int((time.time()-pos["open_time"])/60)
                    icon = "\U0001f7e2" if pnl>=0 else "\U0001f534"
                    sig_icon = "\U0001f4c8" if signal=="LONG" else "\U0001f4c9"
                    lines.append(f"{icon} {sig_icon} {sym.split('/')[0]} {signal}\n   Giris:{entry:.6f} \u2192 {price:.6f}\n   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%)\n   Sure: {sure}dk\n")
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    # /istatistik komutu  
    if text.startswith("/istatistik") or text.startswith("/stats"):
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,guven,signal").execute()
            data = r.data or []
            if not data:
                bot.send_message(msg.chat.id, "Kayit yok."); return
            toplam = len(data)
            kazan = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net = sum(float(d.get("pnl") or 0) for d in data)
            bot.send_message(msg.chat.id,
                f"\U0001f4ca ISTATISTIK\n\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net PnL: {net:+.2f}$\n"
                f"Gunluk PnL: {daily_pnl:+.2f}$\n"
                f"GPT cagri: {gpt_calls}"
            )
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    # /kapat komutu
    if text.startswith("/kapat"):
        parts = text.split()
        if len(parts) > 1:
            sym = parts[1].upper()
            symbol = f"{sym}/USDT:USDT"
            with pos_lock:
                if symbol in positions:
                    close_pos(symbol, "Manuel kapat")
                    bot.send_message(msg.chat.id, f"{sym} kapatildi.")
                else:
                    bot.send_message(msg.chat.id, f"{sym} bulunamadi.")
        return

    # DOGAL DIL - GPT'ye gonder
    bot.send_message(msg.chat.id, "\U0001f914 Bakiyorum...")

    try:
        btc_trend, btc_price, btc_change = get_btc()
        history = load_history(6)
        current_pos = pos_info()

        # Mesajda coin var mi? Bul ve veri cek
        coin_str = ""
        coin_symbol, _ = find_coin(text)
        if coin_symbol:
            data = get_coin(coin_symbol)
            if data:
                sym = coin_symbol.split("/")[0]
                coin_str = (
                    f"\n{sym} GERCEK VERILER:\n"
                    f"Fiyat: {data['price']:.6f}\n"
                    f"RSI: {data['rsi']:.1f}\n"
                    f"EMA(1m): {data['ema_1m']} | EMA(5m): {data['ema_5m']} | EMA(1h): {data['ema_1h']}\n"
                    f"MACD: {data['macd']} | BB: %{data['bb_pct']:.0f}\n"
                    f"Hacim: {data['vol_ratio']:.1f}x\n"
                    f"Hareket: 1dk={data['move_1']:+.2f}% 5dk={data['move_5']:+.2f}% 1s={data['move_1h']:+.2f}%\n"
                    f"Son mumlar: {data['candles']}"
                )

        user_content = (
            f"BTC: {btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)\n"
            f"Pozisyonlar: {current_pos}\n"
            f"Gecmis: {history}\n"
            f"{coin_str}\n\n"
            f"Kullanici: {text}\n\n"
            f"Gercek verilere bak ve net karar ver. "
            f"Islem acacaksan JSON ver: {{\"ac\": true, \"symbol\": \"{coin_symbol or 'COIN/USDT:USDT'}\", \"yon\": \"LONG\", \"tp\": 2.0, \"sl\": 1.0, \"guven\": 80, \"not\": \"neden\"}}\n"
            f"Kapatacaksan: {{\"kapat\": \"SEMBOL\"}}\n"
            f"Yoksa normal Turkce cevap ver."
        )

        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content}
        ]

        yanit = gpt(msgs, model="gpt-4o", max_tokens=400)
        if not yanit:
            bot.send_message(msg.chat.id, "GPT cevap vermedi."); return

        # JSON kontrol
        j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
        if j:
            try:
                karar = json.loads(j.group())

                # Islem ac
                if karar.get("ac") and karar.get("symbol"):
                    symbol = karar["symbol"]
                    yon = karar.get("yon", "LONG")
                    with pos_lock:
                        pos_dolu = len(positions) >= MAX_OPEN
                        zaten_var = symbol in positions

                    if not pos_dolu and not zaten_var:
                        with msg_lock:
                            pos_messages[symbol] = [
                                {"role": "system", "content": SYSTEM},
                                {"role": "user", "content": user_content},
                                {"role": "assistant", "content": yanit}
                            ]
                        acildi = open_pos(
                            symbol, yon,
                            karar.get("tp", 2.0), karar.get("sl", 1.0),
                            karar.get("guven", 70), karar.get("not", ""),
                            btc_trend
                        )
                    elif pos_dolu:
                        bot.send_message(msg.chat.id, f"Max pozisyon dolu ({MAX_OPEN}).")

                # Kapat
                elif karar.get("kapat"):
                    sym = str(karar["kapat"]).upper()
                    symbol = f"{sym}/USDT:USDT"
                    with pos_lock:
                        if symbol in positions:
                            close_pos(symbol, "Kullanici istegi")

            except Exception as je:
                log.warning(f"[JSON] {je}")

        # Temiz metin goster
        temiz = re.sub(r'\{[^{}]+\}', '', yanit).strip()
        if temiz:
            bot.send_message(msg.chat.id, f"\U0001f916 {temiz}")

    except Exception as e:
        log.error(f"[HANDLE] {e}")
        bot.send_message(msg.chat.id, f"\u274c {type(e).__name__}: {str(e)[:100]}")

# MAIN
if __name__ == "__main__":
    print("SADIK CHAT BOT BASLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    tg(
        "\U0001f916 SADIK CHAT TRADING BOT\n\n"
        "Seninle konusur gibi islem yapiyorum!\n\n"
        "Ornekler:\n"
        "- 'NAORIS long olur mu?'\n"
        "- 'BTC nasil gidiyor?'\n"
        "- 'AVAX'i kapat'\n"
        "- 'bugun ne kadar kazandik?'\n\n"
        "/durum /istatistik /kapat AVAX"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
