#!/usr/bin/env python3
"""
SADIK TRADING BOT v2
- Otomatik tarama YOK
- Bot coin onerir, sen onaylarsın
- GPT pozisyon takip eder
- Sen de kapat diyebilirsin
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

LEVERAGE       = 5
MARGIN         = 10.0
MAX_OPEN       = 5
MIN_QUOTE_VOL  = 2_000_000
MAX_PRICE      = 30
COMMISSION     = 0.0006
MAX_DAILY_LOSS = -15.0
ONERI_INTERVAL = 300  # Her 5 dakikada bir öneri

# STATE
positions     = {}
pos_lock      = threading.Lock()
pos_messages  = {}
msg_lock      = threading.Lock()
daily_pnl     = 0.0
gpt_calls     = 0
bekleyen_oneri = {}  # Onay bekleyen öneriler

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

def load_history(limit=6):
    if not supa: return "Gecmis yok."
    try:
        r = supa.table("gpt_trades").select("symbol,signal,pnl,neden,reason").order("created_at", desc=True).limit(limit).execute()
        data = r.data or []
        if not data: return "Henuz islem yok."
        lines = []
        for d in data:
            icon = "+" if float(d.get("pnl") or 0) > 0 else "-"
            lines.append(f"[{icon}] {d.get('symbol','').split('/')[0]} {d.get('signal','')} {float(d.get('pnl') or 0):+.2f}$ | {d.get('neden','')[:30]}")
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
        raw15 = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=20)

        c1 = df1["c"]; v1 = df1["v"]
        price = float(c1.iloc[-1])
        d = c1.diff()
        g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        rsi = float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])
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

        # 15m grafik
        chart_str = ""
        if raw15:
            df15 = pd.DataFrame(raw15, columns=["t","o","h","l","c","v"])
            highs = df15["h"].values; lows = df15["l"].values
            closes = df15["c"].values; opens = df15["o"].values
            support = float(min(lows[-10:]))
            resistance = float(max(highs[-10:]))
            up_count = sum(1 for i in range(len(closes)) if closes[i] > opens[i])
            chart_lines = []
            for i in range(-8, 0):
                o = float(opens[i]); c = float(closes[i])
                h = float(highs[i]); l = float(lows[i])
                direction = "+" if c > o else "-"
                change = (c-o)/o*100
                chart_lines.append(f"  {direction}{change:+.2f}%")
            chart_str = (
                f"15m Son 8 Mum: {''.join(chart_lines)}\n"
                f"Yukari:{up_count}/20 Asagi:{20-up_count}/20\n"
                f"Destek:{support:.6f} Direnc:{resistance:.6f}"
            )

        return {
            "symbol": symbol, "price": price, "rsi": rsi,
            "ema_1m": "YUKARI" if ema9>ema20 else "ASAGI",
            "ema_5m": "YUKARI" if ema9_5>ema20_5 else "ASAGI",
            "ema_1h": "USTUNDE" if price>ema20_1h else "ALTINDA",
            "macd": "POZ" if macd_hist>0 else "NEG",
            "bb_pct": bb_pct, "vol_ratio": vol_ratio,
            "move_1": move_1, "move_5": move_5, "move_1h": move_1h,
            "candles": candles, "chart_str": chart_str,
        }
    except Exception as e:
        log.warning(f"[COIN] {symbol}: {e}")
        return None

# GPT - TIMEOUT ILE
def gpt(messages, model="gpt-4o", max_tokens=400):
    global gpt_calls
    if not OPENAI_KEY: return None
    gpt_calls += 1
    if gpt_calls > 500: return None

    result = [None]
    def call():
        try:
            r = req.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json={"model": model, "max_tokens": max_tokens, "temperature": 0.3, "messages": messages},
                timeout=12)
            if r.status_code == 200:
                result[0] = r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"[GPT] {e}")

    t = threading.Thread(target=call, daemon=True)
    t.start()
    t.join(timeout=15)
    if t.is_alive():
        log.warning("[GPT] Timeout")
        return None
    return result[0]

# SYSTEM PROMPT
SYSTEM = """Sen SADIK, kripto futures paper trading asistanisin.
Kullanici ile BIRLIKTE karar veriyorsun - sen oneri yapiyorsun, kullanici onayi veriyor.

TRADING KURALLARI:
- Komisyon: %0.12 | Kaldirac: 5x | Margin: 10 USDT
- BTC UP = LONG icin ideal | BTC DOWN = SHORT icin ideal
- Min kar %1.2 olmadan kapatma
- 15 dakika dolmadan kapatma
- Zarar %2 gecince kapat

KONUSMA TARZI:
- Kisa ve net konusuyorsun
- Grafik verilerini yorumluyorsun
- "Acalim mi?" diye soruyorsun, kullanici karar veriyor
- Pozisyon takibinde "Trend devam ediyor, bekle" veya "Kar iyi, kapatalim mi?" diyorsun"""

# POZİSYON BİLGİSİ
def pos_info():
    if not positions: return "Acik pozisyon yok."
    lines = []
    for sym, pos in positions.items():
        t = safe_api(exchange.fetch_ticker, sym)
        if t:
            price = t["last"]; entry = pos["entry"]; signal = pos["signal"]
            pnl = (price-entry)/entry*MARGIN*LEVERAGE if signal=="LONG" else (entry-price)/entry*MARGIN*LEVERAGE
            pnl_pct = (price-entry)/entry*100 if signal=="LONG" else (entry-price)/entry*100
            sure = int((time.time()-pos["open_time"])/60)
            icon = "+" if pnl >= 0 else "-"
            lines.append(f"[{icon}] {sym.split('/')[0]} {signal} {pnl:+.2f}$ ({pnl_pct:+.2f}%) {sure}dk")
    return "\n".join(lines)

# COİN BUL
def find_coin(text):
    text_upper = text.upper()
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        best = None; best_len = 0
        for symbol in tickers.keys():
            if not symbol.endswith("/USDT:USDT"): continue
            sym = symbol.split("/")[0].upper()
            if sym in BLACKLIST: continue
            if len(sym) >= 2 and sym in text_upper and len(sym) > best_len:
                best = symbol; best_len = len(sym)
        return best
    except: return None

# ISLEM AC
def open_pos(symbol, yon, neden, btc_trend):
    global daily_pnl
    with pos_lock:
        if symbol in positions:
            tg(f"{symbol.split('/')[0]} zaten acik!"); return False
        if len(positions) >= MAX_OPEN:
            tg(f"Max {MAX_OPEN} pozisyon dolu."); return False
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t: return False
        price = t["last"]
        positions[symbol] = {
            "signal": yon, "entry": price,
            "max_pnl": 0.0, "neden": neden,
            "btc_trend": btc_trend, "open_time": time.time(),
        }
    sym = symbol.split("/")[0]
    icon = "\U0001f4c8" if yon=="LONG" else "\U0001f4c9"
    tg(f"\U0001f4cb {icon} {sym} {yon}\nGiris: {price:.6f}\nBTC: {btc_trend}\n\U0001f4ac {neden}")
    return True

# ISLEM KAPAT
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl
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
    save_trade({
        "symbol": symbol, "signal": sig, "pnl": round(pnl,4),
        "tp_pct": 0, "sl_pct": 0, "guven": 0,
        "btc_trend": pos.get("btc_trend",""),
        "sure_dk": sure, "reason": reason, "neden": pos.get("neden",""),
    })
    icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# YÖNETİCİ - GPT takip eder
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
                max_pnl = pos.get("max_pnl", 0)

                # Zaman asimi
                if sure > 120:
                    close_pos(symbol, "ZAMAN ASIMI 2 saat", price)
                    continue

                # Ilk 15 dakika sadece izle
                if sure < 15:
                    continue

                # GPT takip
                with msg_lock:
                    msgs = list(pos_messages.get(symbol, []))
                if not msgs:
                    msgs = [{"role": "system", "content": SYSTEM}]

                sym = symbol.split("/")[0]
                update = (
                    f"{sym} {sig} - {sure}. dakika\n"
                    f"Giris: {entry:.6f} | Simdi: {price:.6f}\n"
                    f"PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%)\n"
                    f"En yuksek kar: %{max_pnl:.2f}\n\n"
                    f"Trend devam mi? Kapat mi?\n"
                    f"JSON: {{\"devam\": true}} veya {{\"kapat\": true, \"mesaj\": \"kullaniciya bildir\"}}"
                )

                new_msgs = msgs + [{"role": "user", "content": update}]
                yanit = gpt(new_msgs, model="gpt-4o-mini", max_tokens=150)
                if not yanit: continue

                try:
                    j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                    if j:
                        karar = json.loads(j.group())
                        if karar.get("kapat"):
                            # Kurallar
                            if sure < 15: continue
                            if pnl_pct > 0 and pnl_pct < 1.2: continue
                            if pnl_pct > -1.5 and pnl_pct < 0: continue
                            mesaj = karar.get("mesaj", "GPT kapat")
                            close_pos(symbol, mesaj, price)
                        else:
                            # Kullaniciye bilgi ver
                            temiz = re.sub(r'\{[^{}]+\}', '', yanit).strip()
                            if temiz and sure % 10 == 0:  # Her 10 dakikada bilgi ver
                                tg(f"\U0001f916 {sym}: {temiz[:200]}")
                            new_msgs.append({"role": "assistant", "content": yanit})
                            if len(new_msgs) > 16:
                                new_msgs = [new_msgs[0]] + new_msgs[-8:]
                            with msg_lock:
                                pos_messages[symbol] = new_msgs
                except Exception as e:
                    log.warning(f"[YON] {e}")

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ÖNERİ LOOP - Her 5 dakikada en iyi fırsatı öner
def oneri_loop():
    time.sleep(60)  # Başlangıçta bekle
    while True:
        try:
            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(ONERI_INTERVAL); continue

            btc_trend, btc_price, btc_change = get_btc()
            if btc_trend == "NEUTRAL":
                time.sleep(ONERI_INTERVAL); continue

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(ONERI_INTERVAL); continue

            with pos_lock: open_syms = set(positions.keys())

            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                if symbol.split("/")[0] in BLACKLIST: continue
                if symbol in open_syms: continue
                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_QUOTE_VOL: continue
                price = ticker.get("last") or 0
                if not price or price > MAX_PRICE: continue
                if abs(ticker.get("percentage") or 0) < 0.8: continue
                candidates.append({"symbol": symbol, "volume": qv, "pct": abs(ticker.get("percentage") or 0)})

            candidates.sort(key=lambda x: x["volume"], reverse=True)
            candidates = candidates[:8]

            if not candidates:
                time.sleep(ONERI_INTERVAL); continue

            # Veri topla
            coins_data = []
            for c in candidates[:5]:
                d = get_coin(c["symbol"])
                if d: coins_data.append(d)
                time.sleep(0.3)

            if not coins_data:
                time.sleep(ONERI_INTERVAL); continue

            history = load_history(4)
            summary = ""
            for d in coins_data:
                sym = d["symbol"].split("/")[0]
                summary += f"\n{sym}: RSI={d['rsi']:.0f} EMA1m={d['ema_1m']} EMA5m={d['ema_5m']} MACD={d['macd']} Hacim={d['vol_ratio']:.1f}x 5dk={d['move_5']:+.2f}%\n{d.get('chart_str','')}"

            msgs = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": (
                    f"BTC: {btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)\n"
                    f"Gecmis: {history}\n\n"
                    f"Bu coinleri analiz et:\n{summary}\n\n"
                    f"En iyi 1 firsat var mi? Varsa kullaniciya sor.\n"
                    f"Yoksa sessiz kal.\n"
                    f"JSON: {{\"oneri\": true, \"symbol\": \"COIN/USDT:USDT\", \"yon\": \"LONG\", \"mesaj\": \"neden iyi\"}}\n"
                    f"Yoksa: {{\"oneri\": false}}"
                )}
            ]

            yanit = gpt(msgs, model="gpt-4o", max_tokens=300)
            if not yanit:
                time.sleep(ONERI_INTERVAL); continue

            try:
                j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                if j:
                    karar = json.loads(j.group())
                    if karar.get("oneri") and karar.get("symbol"):
                        symbol = karar["symbol"]
                        yon = karar.get("yon", "LONG")
                        mesaj = karar.get("mesaj", "")
                        sym = symbol.split("/")[0]
                        # Kullaniciya sor
                        bekleyen_oneri[sym] = {
                            "symbol": symbol, "yon": yon,
                            "neden": mesaj, "btc_trend": btc_trend,
                            "zaman": time.time()
                        }
                        icon = "\U0001f4c8" if yon=="LONG" else "\U0001f4c9"
                        tg(
                            f"\U0001f4a1 ONERİ: {icon} {sym} {yon}\n\n"
                            f"{mesaj}\n\n"
                            f"BTC: {btc_trend}\n\n"
                            f"Açalım mı? \U0001f449 'evet {sym}' veya 'pas {sym}'"
                        )
            except Exception as e:
                log.warning(f"[ONERI] {e}")

            time.sleep(ONERI_INTERVAL)

        except Exception as e:
            log.error(f"[ONERI] {e}")
            time.sleep(30)

# HEALTH
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(f"OK|pos:{len(positions)}|pnl:{daily_pnl:+.2f}|gpt:{gpt_calls}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# MESAJ HANDLER
@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    if not msg.text: return
    text = msg.text.strip()
    text_lower = text.lower()

    # /durum
    if "/durum" in text_lower or "/status" in text_lower:
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

    # /istatistik
    if "/istatistik" in text_lower or "/stats" in text_lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,signal").execute()
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
                f"Gunluk: {daily_pnl:+.2f}$\n"
                f"GPT cagri: {gpt_calls}"
            )
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    # KAPAT - aninda, GPT beklemeden
    if "kapat" in text_lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Acik pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            sym_name = symbol.split("/")[0].upper()
            if sym_name in text.upper() or "hepsi" in text_lower or "hepsini" in text_lower:
                close_pos(symbol, "Kullanici istegi")
                kapatildi = True
        if not kapatildi:
            isimler = [s.split("/")[0] for s in syms]
            bot.send_message(msg.chat.id, f"Hangisini kapatayim? {', '.join(isimler)}")
        return

    # EVET - oneri onayi
    if text_lower.startswith("evet"):
        parts = text.split()
        coin_adi = parts[1].upper() if len(parts) > 1 else ""
        if coin_adi in bekleyen_oneri:
            oneri = bekleyen_oneri.pop(coin_adi)
            # 5 dakikadan eski oneri gecersiz
            if time.time() - oneri["zaman"] > 300:
                bot.send_message(msg.chat.id, f"Oneri suresi gecti, yeniden analiz lazim.")
                return
            open_pos(oneri["symbol"], oneri["yon"], oneri["neden"], oneri["btc_trend"])
        else:
            bot.send_message(msg.chat.id, f"Hangi oneri? Bekleyen: {list(bekleyen_oneri.keys())}")
        return

    # PAS - oneri reddi
    if text_lower.startswith("pas"):
        parts = text.split()
        coin_adi = parts[1].upper() if len(parts) > 1 else ""
        if coin_adi in bekleyen_oneri:
            bekleyen_oneri.pop(coin_adi)
            bot.send_message(msg.chat.id, f"\U0001f44d {coin_adi} pas gecildi.")
        return

    # DIREKT AC - "X long ac" veya "X short ac"
    ac_keywords = ["long ac", "short ac", "long aç", "short aç"]
    if any(kw in text_lower for kw in ac_keywords):
        coin_symbol = find_coin(text)
        if coin_symbol:
            yon = "LONG" if "long" in text_lower else "SHORT"
            btc_trend, _, _ = get_btc()
            with msg_lock:
                pos_messages[coin_symbol] = [{"role": "system", "content": SYSTEM}]
            open_pos(coin_symbol, yon, "Kullanici istegi", btc_trend)
        else:
            bot.send_message(msg.chat.id, "Coin bulunamadi. Ornek: 'AVAX long ac'")
        return

    # DOGAL DIL - GPT'ye sor
    bot.send_message(msg.chat.id, "\U0001f914 Bakiyorum...")
    try:
        btc_trend, btc_price, btc_change = get_btc()
        history = load_history(5)
        current_pos = pos_info()

        # Coin var mi?
        coin_str = ""
        coin_symbol = find_coin(text)
        if coin_symbol:
            data = get_coin(coin_symbol)
            if data:
                sym = coin_symbol.split("/")[0]
                coin_str = (
                    f"\n{sym} VERILER:\n"
                    f"Fiyat:{data['price']:.6f} RSI:{data['rsi']:.1f}\n"
                    f"EMA(1m):{data['ema_1m']} EMA(5m):{data['ema_5m']} EMA(1h):{data['ema_1h']}\n"
                    f"MACD:{data['macd']} BB:%{data['bb_pct']:.0f} Hacim:{data['vol_ratio']:.1f}x\n"
                    f"Hareket: 1dk={data['move_1']:+.2f}% 5dk={data['move_5']:+.2f}% 1s={data['move_1h']:+.2f}%\n"
                    f"{data.get('chart_str','')}"
                )

        user_content = (
            f"BTC: {btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)\n"
            f"Pozisyonlar: {current_pos}\n"
            f"Gecmis: {history}\n"
            f"{coin_str}\n\n"
            f"Kullanici: {text}"
        )

        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content}
        ]

        yanit = gpt(msgs, model="gpt-4o", max_tokens=350)
        if not yanit:
            bot.send_message(msg.chat.id, "GPT cevap vermedi."); return

        bot.send_message(msg.chat.id, f"\U0001f916 {yanit[:800]}")

    except Exception as e:
        log.error(f"[HANDLE] {e}")
        bot.send_message(msg.chat.id, f"\u274c {type(e).__name__}")

# MAIN
import signal as signal_module, sys

def shutdown(signum, frame):
    log.info("[SHUTDOWN] Pozisyonlar kaydediliyor...")
    with pos_lock: syms = list(positions.keys())
    for symbol in syms:
        try:
            t = safe_api(exchange.fetch_ticker, symbol)
            close_pos(symbol, "BOT RESTART", t["last"] if t else None)
        except: pass
    sys.exit(0)

signal_module.signal(signal_module.SIGTERM, shutdown)
signal_module.signal(signal_module.SIGINT, shutdown)

if __name__ == "__main__":
    print("SADIK v2 BASLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=oneri_loop,    daemon=True).start()
    tg(
        "\U0001f916 SADIK TRADING BOT v2\n\n"
        "Birlikte karar veriyoruz!\n\n"
        "Ben coin oneriyorum \u2192 sen onayliyorsun\n\n"
        "Komutlar:\n"
        "- 'AVAX analiz et'\n"
        "- 'evet AVAX' (oneri onayla)\n"
        "- 'pas AVAX' (oneri reddet)\n"
        "- 'AVAX long ac' (direkt ac)\n"
        "- 'AVAX kapat'\n"
        "- 'hepsini kapat'\n"
        "- /durum /istatistik"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
