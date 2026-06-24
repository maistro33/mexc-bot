#!/usr/bin/env python3
"""
SADIK TRADER v3 - Multi-Timeframe + Kademeli Kar Koruma
- BTC UP = LONG | BTC DOWN = SHORT | NEUTRAL = her iki yon
- 1m + 5m + 15m + 1h uyumu = erken giris
- Her $1 karda SL yukar cek - sermaye icerde kalsin
- Hacim once artar, fiyat sonra hareket eder mantigi
"""

import os, time, threading, logging, re
import ccxt
import pandas as pd
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK")

# CONFIG
TELE_TOKEN  = os.getenv("TELE_TOKEN", "")
CHAT_ID     = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API  = os.getenv("BITGET_API", "")
BITGET_SEC  = os.getenv("BITGET_SEC", "")
BITGET_PASS = os.getenv("BITGET_PASS", "")
SUPA_URL    = os.getenv("SUPABASE_URL", "")
SUPA_KEY    = os.getenv("SUPABASE_KEY", "")

LEVERAGE       = 5
MARGIN         = 10.0
POS_SIZE       = MARGIN * LEVERAGE   # 50$
COMMISSION     = 0.0006
MAX_OPEN       = 3
MIN_VOL_USDT   = 1_000_000   # Min 1M
MAX_VOL_USDT   = 5_000_000   # Max 5M - buyuk hantaller disari
MAX_DAILY_LOSS = -10.0
SCAN_INTERVAL  = 60

# Kademeli kar koruma seviyeleri
# Her $1 karda SL'i bir kademe yukari cek
KAR_KADEMELERI = [
    (1.0, 0.30),   # $1 kar gorulunce SL'i $0.30 kara cek
    (2.0, 0.80),   # $2 kar gorulunce SL'i $0.80 kara cek
    (3.0, 1.50),   # $3 kar gorulunce SL'i $1.50 kara cek
    (4.0, 2.50),   # $4 kar gorulunce SL'i $2.50 kara cek
    (5.0, 3.50),   # $5 kar gorulunce SL'i $3.50 kara cek
]

# Geri cekilme limiti - bu kadar geri donerse kapat
GERI_CEKILME = 0.30   # $0.30 geri donerse kapat

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME","CLOSED",
}

# Fiyat filtresi - hantal buyuk coinleri atla
# Fiyat filtresi yok - hacim filtresi yeterli

# STATE
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
recently_closed = {}
closed_lock     = threading.Lock()
son_bakilan     = set()

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

def load_recently_closed():
    if not supa: return
    try:
        import datetime
        ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()
        r = supa.table("gpt_trades").select("symbol,created_at").eq(
            "signal","CLOSED").gte("created_at", ago).execute()
        for d in (r.data or []):
            sym = d["symbol"].replace("_CLOSED","")
            with closed_lock:
                recently_closed[sym] = time.time() - 3600
        log.info(f"[CLOSED] {len(r.data or [])} coin yuklendi")
    except Exception as e:
        log.warning(f"[CLOSED] {e}")

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

# BTC TREND
def get_btc_trend():
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=50)
        if not raw: return "NEUTRAL", 0, 0
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price = float(df["c"].iloc[-1])
        e20   = float(df["c"].ewm(span=20).mean().iloc[-1])
        e50   = float(df["c"].ewm(span=50).mean().iloc[-1])
        chg   = (price - float(df["c"].iloc[-24])) / float(df["c"].iloc[-24]) * 100
        if price > e20 * 1.005 and price > e50 and chg > 1:
            return "UP", price, chg
        elif price < e20 * 0.995 and price < e50 and chg < -1:
            return "DOWN", price, chg
        return "NEUTRAL", price, chg
    except:
        return "NEUTRAL", 0, 0

# TEKNIK ANALIZ
def ema_yonu(df):
    e9  = df["c"].ewm(span=9).mean()
    e20 = df["c"].ewm(span=20).mean()
    son_yukari = float(e9.iloc[-1]) > float(e20.iloc[-1])
    # Son 5 mumda kesti mi?
    kesiyor_yukari = float(e9.iloc[-5]) < float(e20.iloc[-5]) and son_yukari
    kesiyor_asagi  = float(e9.iloc[-5]) > float(e20.iloc[-5]) and not son_yukari
    return son_yukari, kesiyor_yukari, kesiyor_asagi

def rsi(df):
    delta = df["c"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1+rs)).iloc[-1])

def hacim(df, n=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(n).mean())
    return son / max(avg, 0.001)

def analyze_coin(symbol):
    """1m + 5m + 15m + 1h multi-timeframe analiz"""
    try:
        r1m  = safe_api(exchange.fetch_ohlcv, symbol, "1m",  limit=30)
        r5m  = safe_api(exchange.fetch_ohlcv, symbol, "5m",  limit=30)
        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=30)
        r1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=30)

        if not r15m or len(r15m) < 20: return None

        df1m  = pd.DataFrame(r1m,  columns=["t","o","h","l","c","v"]) if r1m  else None
        df5m  = pd.DataFrame(r5m,  columns=["t","o","h","l","c","v"]) if r5m  else None
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])
        df1h  = pd.DataFrame(r1h,  columns=["t","o","h","l","c","v"]) if r1h  else None

        price = float(df15m["c"].iloc[-1])

        # Her timeframe EMA yonu
        def trend(df):
            if df is None: return None
            yukari, _, _ = ema_yonu(df)
            return "YUKARI" if yukari else "ASAGI"

        t1m  = trend(df1m)
        t5m  = trend(df5m)
        t15m = trend(df15m)
        t1h  = trend(df1h)

        # Timeframe uyumu
        trendler = [t for t in [t1m, t5m, t15m, t1h] if t]
        uyum_yukari = trendler.count("YUKARI")
        uyum_asagi  = trendler.count("ASAGI")

        # EMA kesiyor mu? (erken giris sinyali)
        _, k1m_yukari,  k1m_asagi  = ema_yonu(df1m)  if df1m  is not None else (None, False, False)
        _, k5m_yukari,  k5m_asagi  = ema_yonu(df5m)  if df5m  is not None else (None, False, False)
        _, k15m_yukari, k15m_asagi = ema_yonu(df15m)

        # Hacim
        v1m  = hacim(df1m,  3) if df1m  is not None else 1.0
        v5m  = hacim(df5m,  3) if df5m  is not None else 1.0
        v15m = hacim(df15m, 3)

        # RSI 15m
        rsi_val = rsi(df15m)

        # Fiyat degisimi - 15m'de son 10 mum
        pct = (price - float(df15m["c"].iloc[-10])) / float(df15m["c"].iloc[-10]) * 100

        return {
            "price": price, "rsi": rsi_val,
            "uyum_yukari": uyum_yukari, "uyum_asagi": uyum_asagi,
            "k1m_yukari": k1m_yukari, "k1m_asagi": k1m_asagi,
            "k5m_yukari": k5m_yukari, "k5m_asagi": k5m_asagi,
            "k15m_yukari": k15m_yukari, "k15m_asagi": k15m_asagi,
            "v1m": v1m, "v5m": v5m, "v15m": v15m,
            "pct": pct,
        }
    except Exception as e:
        log.warning(f"[ANALYZE] {symbol}: {e}")
        return None

def karar_ver(data, btc_trend):
    """
    Multi-timeframe uyum + hacim + erken giris
    """
    if not data: return None, ""

    rsi_val = data["rsi"]
    uy      = data["uyum_yukari"]
    ua      = data["uyum_asagi"]
    v1m     = data["v1m"]
    v5m     = data["v5m"]
    pct     = data["pct"]

    # Hacim en az bir timeframe'de guclu olmali
    vol_ok = v1m >= 1.5 or v5m >= 1.5

    # Cok gec kalindiysa girme
    if abs(pct) > 20:
        return None, f"Gec kalindi ({pct:.1f}%)"

    # GEC KALMA KONTROLU - en onemli filtre
    # Hareket zaten cok olmussa girme
    if pct > 5:   # 5%+ yukseldi, LONG icin gec
        return None, f"LONG gec kalindi ({pct:.1f}% hareket)"
    if pct < -5:  # 5%+ dustu, SHORT icin gec
        return None, f"SHORT gec kalindi ({pct:.1f}% hareket)"

    # LONG - sadece hareket YENI BASLAMISSA
    if btc_trend in ["UP", "NEUTRAL"]:
        vol_long = v1m >= 1.5 or v5m >= 1.5
        if not vol_long: pass
        # En erken: 1m EMA yeni kesti, hareket az
        elif data["k1m_yukari"] and uy >= 2 and 0 < pct < 3:
            return "LONG", f"1m EMA kesti, {uy}/4 yukari, +{pct:.1f}%"
        # 5m EMA kesti, hareket az
        elif data["k5m_yukari"] and uy >= 3 and 0 < pct < 4:
            return "LONG", f"5m EMA kesti, {uy}/4 yukari, +{pct:.1f}%"
        # Hacim patlamasi - fiyat henuz hareket etmemis
        elif v1m >= 2.5 and uy >= 2 and 0 < pct < 2 and rsi_val < 65:
            return "LONG", f"Hacim patlamasi {v1m:.1f}x, henuz +{pct:.1f}%"

    # SHORT - sadece hareket YENI BASLAMISSA
    if btc_trend in ["DOWN", "NEUTRAL"]:
        vol_short = v1m >= 1.5 or v5m >= 1.5
        if not vol_short: pass
        # En erken: 1m EMA yeni kesti, hareket az
        elif data["k1m_asagi"] and ua >= 2 and -3 < pct < 0:
            return "SHORT", f"1m EMA kesti, {ua}/4 asagi, {pct:.1f}%"
        # 5m EMA kesti, hareket az
        elif data["k5m_asagi"] and ua >= 3 and -4 < pct < 0:
            return "SHORT", f"5m EMA kesti, {ua}/4 asagi, {pct:.1f}%"
        # Hacim patlamasi - fiyat henuz hareket etmemis
        elif v1m >= 2.5 and ua >= 2 and -2 < pct < 0 and rsi_val > 35:
            return "SHORT", f"Hacim patlamasi {v1m:.1f}x, henuz {pct:.1f}%"

    return None, f"Kosul saglanamadi (pct:{pct:.1f}% Y:{uy} A:{ua})"

# PNL HESAP
def hesap_pnl(pos, price):
    entry = pos["entry"]
    sig   = pos["signal"]
    if sig == "LONG":
        pnl_pct = (price - entry) / entry * 100
        pnl     = (price - entry) / entry * POS_SIZE - POS_SIZE * COMMISSION
    else:
        pnl_pct = (entry - price) / entry * 100
        pnl     = (entry - price) / entry * POS_SIZE - POS_SIZE * COMMISSION
    return pnl, pnl_pct

# ISLEM AC
def open_pos(symbol, yon, neden, btc_trend):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS: return False
    if btc_trend == "DOWN" and yon == "LONG": return False
    if btc_trend == "UP"   and yon == "SHORT": return False

    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price    = t["last"]
    sl_price = price * (1 - 0.02) if yon == "LONG" else price * (1 + 0.02)

    with pos_lock:
        sym_base = symbol.split("/")[0].upper()
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 7200: return False
        if len(positions) >= MAX_OPEN: return False

        positions[symbol] = {
            "signal": yon, "entry": price,
            "sl_price": sl_price,
            "sl_garantili": 0.0,   # Garantilenen min kar ($)
            "max_pnl": 0.0,
            "max_kar": 0.0,        # En yuksek gordugu kar ($)
            "neden": neden, "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    sym  = symbol.split("/")[0]
    icon = "\U0001f4c8" if yon == "LONG" else "\U0001f4c9"
    tg(f"\U0001f4cb {icon} {sym} {yon}\nGiris: {price:.6f}\nSL: {sl_price:.6f} (-%2.0)\nBTC: {btc_trend}\n\U0001f4ac {neden}")
    log.info(f"[OPEN] {sym} {yon}")
    return True

# ISLEM KAPAT
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    pnl, _ = hesap_pnl(pos, exit_price)
    sure    = int((time.time() - pos["open_time"]) / 60)
    daily_pnl += pnl

    sym_base = symbol.split("/")[0].upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    try:
        save_trade({
            "symbol": symbol, "signal": pos["signal"],
            "pnl": round(pnl, 4), "tp_pct": pos.get("max_pnl", 0),
            "sl_pct": 2.0, "btc_trend": pos.get("btc_trend", ""),
            "sure_dk": sure, "reason": reason, "neden": pos.get("neden", ""),
        })
        save_trade({
            "symbol": sym_base + "_CLOSED", "signal": "CLOSED",
            "pnl": 0, "reason": "recently_closed", "sure_dk": 0,
        })
    except Exception as e:
        log.error(f"[SAVE] {e}")

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"\u26d4 GUNLUK LIMIT! {daily_pnl:+.2f}$")

    icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# YÖNETİM — Kademeli kar koruma
def manage_loop():
    while True:
        time.sleep(30)
        try:
            with pos_lock: syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price   = t["last"]
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure    = int((time.time() - pos["open_time"]) / 60)

                # Max kar guncelle
                with pos_lock:
                    if symbol in positions:
                        if pnl > positions[symbol]["max_kar"]:
                            positions[symbol]["max_kar"] = pnl
                        if pnl_pct > positions[symbol]["max_pnl"]:
                            positions[symbol]["max_pnl"] = pnl_pct

                max_kar = pos["max_kar"]

                # SL kontrolu
                if pnl_pct <= -2.0:
                    close_pos(symbol, "Stop Loss -%2.0", price)
                    continue

                # Garantili kar SL'e gore kapat
                sl_garantili = pos.get("sl_garantili", 0.0)
                if sl_garantili > 0 and pnl < sl_garantili:
                    close_pos(symbol, f"Kar garantisi ({sl_garantili:.2f}$)", price)
                    continue

                # Geri cekilme kontrolu - kar varsa
                if max_kar > 0 and (max_kar - pnl) >= GERI_CEKILME:
                    if pnl > 0:  # Hala karda ise
                        close_pos(symbol, f"Geri cekilme ${max_kar-pnl:.2f}", price)
                        continue

                # Zaman asimi 2 saat
                if sure >= 120:
                    close_pos(symbol, "Zaman asimi 2 saat", price)
                    continue

                # Kademeli kar koruma - SL yukari cek
                yeni_garantili = pos.get("sl_garantili", 0.0)
                for kar_seviyesi, garantili in KAR_KADEMELERI:
                    if max_kar >= kar_seviyesi and garantili > yeni_garantili:
                        yeni_garantili = garantili

                if yeni_garantili > pos.get("sl_garantili", 0.0):
                    with pos_lock:
                        if symbol in positions:
                            eski = positions[symbol].get("sl_garantili", 0.0)
                            positions[symbol]["sl_garantili"] = yeni_garantili
                            sym = symbol.split("/")[0]
                            tg(f"\U0001f512 {sym} SL guncellendi: ${yeni_garantili:.2f} kar garantilendi (max kar: ${max_kar:.2f})")

                # BTC trend degisti, kar varsa cik
                btc_now, _, _ = get_btc_trend()
                if pos["signal"] == "LONG" and btc_now == "DOWN" and pnl > 0:
                    close_pos(symbol, "BTC DOWN - kar al", price)
                    continue
                if pos["signal"] == "SHORT" and btc_now == "UP" and pnl > 0:
                    close_pos(symbol, "BTC UP - kar al", price)
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# TARAYICI
def scanner_loop():
    global son_bakilan
    time.sleep(60)
    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(SCAN_INTERVAL); continue

            btc_trend, btc_price, btc_chg = get_btc_trend()
            log.info(f"[SCAN] BTC:{btc_trend} ${btc_price:,.0f} ({btc_chg:+.1f}%)")

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(30); continue
                open_syms = set(positions.keys())

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            # Aday coinleri topla
            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue
                if sym in son_bakilan: continue

                qv    = ticker.get("quoteVolume") or 0
                pct   = ticker.get("percentage")  or 0
                price = float(ticker.get("last") or 0)
                if qv < MIN_VOL_USDT: continue
                if qv > MAX_VOL_USDT: continue
                if price <= 0: continue
                if price > 5.0: continue  # $5 ustu hantal - kesin filtre
                

                # Yöne gore on filtre
                if btc_trend == "UP"      and pct < 2: continue
                if btc_trend == "DOWN"    and pct > -2: continue
                if btc_trend == "NEUTRAL" and abs(pct) < 3: continue
                if abs(pct) > 50: continue  # Gec kalma filtresi

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 7200:
                            continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # Rotasyon - son 30 coini atla
            yeni = [c for c in candidates if c["symbol"].split("/")[0] not in son_bakilan]
            if len(yeni) < 3:
                son_bakilan = set()  # Sifirla
                yeni = candidates

            # Karisik sirala - her turda farkli coinler
            import random
            random.shuffle(yeni)
            candidates = yeni[:6]

            # Bakilan coinleri kaydet (max 30 tane)
            for c in candidates:
                son_bakilan.add(c["symbol"].split("/")[0])
            if len(son_bakilan) > 30:
                son_bakilan = set(list(son_bakilan)[-15:])

            if not candidates:
                time.sleep(SCAN_INTERVAL); continue

            log.info(f"[SCAN] {len(candidates)} aday")

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]

                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                data = analyze_coin(symbol)
                if not data: continue

                yon, neden = karar_ver(data, btc_trend)
                if yon:
                    open_pos(symbol, yon, neden, btc_trend)
                    with pos_lock: open_syms = set(positions.keys())
                else:
                    log.info(f"[PAS] {sym}: {neden}")

                time.sleep(1)

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
            self.wfile.write(f"OK|pos:{len(positions)}|pnl:{daily_pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# COIN BUL
def find_coin(text):
    words = re.findall(r'[A-Z0-9]+', text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for word in words:
            if len(word) < 3: continue
            sym = f"{word}/USDT:USDT"
            if sym in tickers and word not in BLACKLIST:
                return sym
    except: pass
    return None

# TELEGRAM HANDLER
@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text  = msg.text.strip()
    lower = text.lower()

    # /durum
    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "\U0001f4cb Acik pozisyon yok."); return
            lines = ["\U0001f4cb POZISYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = t["last"]
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure  = int((time.time() - pos["open_time"]) / 60)
                garantili = pos.get("sl_garantili", 0.0)
                max_kar   = pos.get("max_kar", 0.0)
                icon  = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                sicon = "\U0001f4c8" if pos["signal"] == "LONG" else "\U0001f4c9"
                lines.append(
                    f"{icon} {sicon} {sym.split('/')[0]} {pos['signal']}\n"
                    f"   {pos['entry']:.6f} \u2192 {price:.6f}\n"
                    f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk\n"
                    f"   Max kar: ${max_kar:.2f} | Garantili: ${garantili:.2f}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    # /istatistik
    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r    = supa.table("gpt_trades").select("pnl,signal").execute()
            data = [d for d in (r.data or []) if d.get("signal") not in ["CLOSED"]]
            if not data: bot.send_message(msg.chat.id, "Kayit yok."); return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            bot.send_message(msg.chat.id,
                f"\U0001f4ca ISTATISTIK\n\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$\nGunluk: {daily_pnl:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    # /btc
    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        bot.send_message(msg.chat.id, f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)")
        return

    # KAPAT
    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Acik pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            sname = symbol.split("/")[0].upper()
            if sname in text.upper() or "hepsi" in lower or "hepsini" in lower:
                close_pos(symbol, "Kullanici istegi")
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    # DIREKT AC
    if any(k in lower for k in ["long ac", "short ac", "long aç", "short aç"]):
        coin = find_coin(text)
        if coin:
            yon   = "LONG" if "long" in lower else "SHORT"
            trend, _, _ = get_btc_trend()
            if not open_pos(coin, yon, "Kullanici istegi", trend):
                bot.send_message(msg.chat.id, f"{coin.split('/')[0]} acilamadi.")
        else:
            bot.send_message(msg.chat.id, "Coin bulunamadi.")
        return

    # ANALİZ
    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        bot.send_message(msg.chat.id, f"{sym} analiz ediliyor...")
        data = analyze_coin(coin)
        if data:
            trend, _, _ = get_btc_trend()
            yon, neden  = karar_ver(data, trend)
            bot.send_message(msg.chat.id,
                f"\U0001f4ca {sym}\n"
                f"BTC: {trend}\n"
                f"Uyum: {data['uyum_yukari']}/4 yukari | {data['uyum_asagi']}/4 asagi\n"
                f"Hacim 1m: {data['v1m']:.1f}x | 5m: {data['v5m']:.1f}x\n"
                f"RSI: {data['rsi']:.0f} | Hareket: {data['pct']:+.1f}%\n\n"
                f"Karar: {yon or 'PAS'}\n{neden}")
        else:
            bot.send_message(msg.chat.id, f"{sym} veri alinamadi.")
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n"
        "/durum - Acik pozisyonlar\n"
        "/istatistik - Istatistik\n"
        "/btc - BTC trend\n"
        "COIN - Analiz\n"
        "COIN long/short ac - Manuel ac\n"
        "hepsini kapat")

# MAIN
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    for symbol in syms:
        try:
            t = safe_api(exchange.fetch_ticker, symbol)
            close_pos(symbol, "Restart", t["last"] if t else None)
        except: pass
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT,  shutdown)

if __name__ == "__main__":
    print("SADIK TRADER v3 BASLIYOR...")
    load_recently_closed()
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    tg(
        "\U0001f916 SADIK TRADER v3\n\n"
        "Multi-Timeframe + Kademeli Kar\n\n"
        "\u2705 1m+5m+15m+1h uyumu = erken giris\n"
        "\u2705 BTC UP=LONG | DOWN=SHORT | NEUTRAL=her yon\n"
        "\u2705 Her $1 karda SL yukari cekiliyor\n"
        "\u2705 $0.30 geri cekilirse kapat\n"
        "\u2705 Gec kalma filtresi (%30+)\n"
        "\u2705 2 saat sonra kapat\n\n"
        "/durum /istatistik /btc"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
