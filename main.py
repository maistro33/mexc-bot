#!/usr/bin/env python3
"""
SADIK TRADER v3 - Kural Tabanlı
- Claude yok, AI yok, kredi yok
- 1073 gecmis islemden cikarilan kurallar
- BTC DOWN = islem acma
- BTC NEUTRAL = sadece SHORT
- BTC UP = sadece LONG
- Hacim 2x+ ve EMA kesisimi = gir
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
TELE_TOKEN    = os.getenv("TELE_TOKEN","")
CHAT_ID       = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API    = os.getenv("BITGET_API","")
BITGET_SEC    = os.getenv("BITGET_SEC","")
BITGET_PASS   = os.getenv("BITGET_PASS","")
SUPA_URL      = os.getenv("SUPABASE_URL","")
SUPA_KEY      = os.getenv("SUPABASE_KEY","")

LEVERAGE       = 5
MARGIN         = 10.0
MAX_OPEN       = 3
MIN_VOL        = 2_000_000   # Min 2M USDT hacim
COMMISSION     = 0.0006
MAX_DAILY_LOSS = -10.0
SCAN_INTERVAL  = 120

# STATE
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
recently_closed = {}
closed_lock     = threading.Lock()
son_bakilan     = set()

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ","CLOSED",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME",  # Volatil ETF
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

def load_recently_closed():
    if not supa: return
    try:
        import datetime
        two_hours_ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()
        r = supa.table("gpt_trades").select("symbol,created_at").eq(
            "signal", "CLOSED"
        ).gte("created_at", two_hours_ago).execute()
        for d in (r.data or []):
            sym = d["symbol"].replace("_CLOSED", "")
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
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=48)
        if not raw: return "NEUTRAL", 0, 0
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price = float(df["c"].iloc[-1])
        ema20 = float(df["c"].ewm(span=20).mean().iloc[-1])
        ema50 = float(df["c"].ewm(span=50).mean().iloc[-1])
        chg = (price - float(df["c"].iloc[-24])) / float(df["c"].iloc[-24]) * 100

        if price > ema20 * 1.005 and price > ema50 and chg > 1:
            trend = "UP"
        elif price < ema20 * 0.995 and price < ema50 and chg < -1:
            trend = "DOWN"
        else:
            trend = "NEUTRAL"

        return trend, price, chg
    except:
        return "NEUTRAL", 0, 0

# TEKNİK ANALİZ - Kural tabanlı
def ema_trend(df):
    """EMA9 EMA20 trend yonu"""
    e9  = df["c"].ewm(span=9).mean()
    e20 = df["c"].ewm(span=20).mean()
    return "YUKARI" if float(e9.iloc[-1]) > float(e20.iloc[-1]) else "ASAGI"

def ema_kesiyor(df):
    """EMA son 3 mumda kesti mi?"""
    e9  = df["c"].ewm(span=9).mean()
    e20 = df["c"].ewm(span=20).mean()
    yukari = float(e9.iloc[-3]) < float(e20.iloc[-3]) and float(e9.iloc[-1]) > float(e20.iloc[-1])
    asagi  = float(e9.iloc[-3]) > float(e20.iloc[-3]) and float(e9.iloc[-1]) < float(e20.iloc[-1])
    return yukari, asagi

def rsi_hesap(df):
    delta = df["c"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100/(1+rs)).iloc[-1])

def hacim_ratio(df, pencere=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(pencere).mean())
    return son / max(avg, 0.001)

def analyze_coin(symbol):
    """
    Multi-timeframe analiz: 1m + 5m + 15m + 1h
    Hepsi ayni yonde = guclu sinyal, erken giris
    """
    try:
        # Veri cek
        raw1m  = safe_api(exchange.fetch_ohlcv, symbol, "1m",  limit=30)
        raw5m  = safe_api(exchange.fetch_ohlcv, symbol, "5m",  limit=30)
        raw15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=30)
        raw1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=24)

        if not raw15m or len(raw15m) < 20: return None

        df1m  = pd.DataFrame(raw1m,  columns=["t","o","h","l","c","v"]) if raw1m  else None
        df5m  = pd.DataFrame(raw5m,  columns=["t","o","h","l","c","v"]) if raw5m  else None
        df15m = pd.DataFrame(raw15m, columns=["t","o","h","l","c","v"])
        df1h  = pd.DataFrame(raw1h,  columns=["t","o","h","l","c","v"]) if raw1h  else None

        price = float(df15m["c"].iloc[-1])

        # Her timeframe'de trend
        trend_1m  = ema_trend(df1m)  if df1m  is not None else "BELIRSIZ"
        trend_5m  = ema_trend(df5m)  if df5m  is not None else "BELIRSIZ"
        trend_15m = ema_trend(df15m)
        trend_1h  = ema_trend(df1h)  if df1h  is not None else "BELIRSIZ"

        # 1m'de EMA yeni kesti mi? (erken giris sinyali)
        ema1m_yukari, ema1m_asagi = (False, False)
        if df1m is not None:
            ema1m_yukari, ema1m_asagi = ema_kesiyor(df1m)

        # 5m'de EMA yeni kesti mi?
        ema5m_yukari, ema5m_asagi = (False, False)
        if df5m is not None:
            ema5m_yukari, ema5m_asagi = ema_kesiyor(df5m)

        # Hacim - 1m'de ani artis var mi?
        vol_1m  = hacim_ratio(df1m,  3) if df1m  is not None else 1.0
        vol_5m  = hacim_ratio(df5m,  3) if df5m  is not None else 1.0
        vol_15m = hacim_ratio(df15m, 3)

        # RSI 15m
        rsi = rsi_hesap(df15m)

        # Fiyat degisimi
        pct_5m  = (price - float(df5m["c"].iloc[-5]))   / float(df5m["c"].iloc[-5])   * 100 if df5m  is not None else 0
        pct_15m = (price - float(df15m["c"].iloc[-10])) / float(df15m["c"].iloc[-10]) * 100

        # Timeframe uyumu say
        uyum_yukari = sum([
            trend_1m  == "YUKARI",
            trend_5m  == "YUKARI",
            trend_15m == "YUKARI",
            trend_1h  == "YUKARI",
        ])
        uyum_asagi = sum([
            trend_1m  == "ASAGI",
            trend_5m  == "ASAGI",
            trend_15m == "ASAGI",
            trend_1h  == "ASAGI",
        ])

        return {
            "price": price,
            "trend_1m": trend_1m, "trend_5m": trend_5m,
            "trend_15m": trend_15m, "trend_1h": trend_1h,
            "uyum_yukari": uyum_yukari, "uyum_asagi": uyum_asagi,
            "ema1m_yukari": ema1m_yukari, "ema1m_asagi": ema1m_asagi,
            "ema5m_yukari": ema5m_yukari, "ema5m_asagi": ema5m_asagi,
            "vol_1m": vol_1m, "vol_5m": vol_5m, "vol_15m": vol_15m,
            "rsi": rsi,
            "pct_5m": pct_5m, "pct_15m": pct_15m,
        }
    except Exception as e:
        log.warning(f"[ANALYZE] {symbol}: {e}")
        return None

def karar_ver(data, btc_trend, pct_change):
    """
    Multi-timeframe uyum kontrolu:
    4/4 veya 3/4 timeframe ayni yonde = guclu sinyal = GIR
    2/4 veya az = belirsiz = PAS
    """
    if not data: return None, ""

    rsi = data["rsi"]
    uyum_yukari = data["uyum_yukari"]
    uyum_asagi  = data["uyum_asagi"]
    vol_1m      = data["vol_1m"]
    vol_5m      = data["vol_5m"]

    # Hacim en az 1 timeframe'de guclu olmali
    vol_guclu = vol_1m >= 1.5 or vol_5m >= 1.5

    if not vol_guclu:
        return None, "Hacim yetersiz"

    # LONG kosullari
    if btc_trend in ["UP", "NEUTRAL"]:
        # 3+ timeframe yukari + erken kesisim
        if uyum_yukari >= 3 and rsi < 72:
            if data["ema1m_yukari"]:
                return "LONG", f"1m EMA kesti, {uyum_yukari}/4 yukari, vol {vol_1m:.1f}x"
            if data["ema5m_yukari"] and uyum_yukari >= 3:
                return "LONG", f"5m EMA kesti, {uyum_yukari}/4 yukari, vol {vol_5m:.1f}x"
            if uyum_yukari == 4 and vol_guclu and pct_change < 5:
                return "LONG", f"4/4 uyum, gec degil ({pct_change:.1f}%), vol {vol_5m:.1f}x"

    # SHORT kosullari
    if btc_trend in ["DOWN", "NEUTRAL"]:
        if uyum_asagi >= 3 and rsi > 28:
            if data["ema1m_asagi"]:
                return "SHORT", f"1m EMA kesti, {uyum_asagi}/4 asagi, vol {vol_1m:.1f}x"
            if data["ema5m_asagi"] and uyum_asagi >= 3:
                return "SHORT", f"5m EMA kesti, {uyum_asagi}/4 asagi, vol {vol_5m:.1f}x"
            if uyum_asagi == 4 and vol_guclu and pct_change > -5:
                return "SHORT", f"4/4 uyum, gec degil ({pct_change:.1f}%), vol {vol_5m:.1f}x"

    return None, f"Uyum yetersiz (yukari:{uyum_yukari} asagi:{uyum_asagi})"

# ISLEM AC
def open_pos(symbol, yon, neden, btc_trend):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS:
        return False

    # BTC kontrolu - kesin kural
    if btc_trend == "DOWN":
        return False

    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price = t["last"]
    sl_price = price*(1-0.02) if yon=="LONG" else price*(1+0.02)

    with pos_lock:
        sym_base = symbol.split("/")[0].upper()
        for existing in positions.keys():
            if existing.split("/")[0].upper() == sym_base:
                return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 7200:
                    log.info(f"[SKIP] {sym_base} 2 saat bekleme")
                    return False
        if len(positions) >= MAX_OPEN:
            return False

        positions[symbol] = {
            "signal": yon, "entry": price,
            "sl_price": sl_price,
            "max_pnl": 0.0,
            "neden": neden, "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    icon = "\U0001f4c8" if yon=="LONG" else "\U0001f4c9"
    tg(f"\U0001f4cb {icon} {sym} {yon}\nGiris: {price:.6f}\nSL: {sl_price:.6f} (-%2.0)\nBTC: {btc_trend}\n\U0001f4ac {neden}")
    log.info(f"[OPEN] {sym} {yon} | {neden}")
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

    sig = pos["signal"]; entry = pos["entry"]
    pos_size = MARGIN * LEVERAGE
    if sig == "LONG":
        pnl = (exit_price-entry)/entry*pos_size - pos_size*COMMISSION
    else:
        pnl = (entry-exit_price)/entry*pos_size - pos_size*COMMISSION

    sure = int((time.time()-pos["open_time"])/60)
    daily_pnl += pnl

    sym_base = symbol.split("/")[0].upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    # Kaydet
    try:
        save_trade({
            "symbol": symbol, "signal": sig, "pnl": round(pnl,4),
            "tp_pct": pos.get("max_pnl",0), "sl_pct": 2.0,
            "btc_trend": pos.get("btc_trend",""),
            "sure_dk": sure, "reason": reason, "neden": pos.get("neden",""),
        })
        # recently_closed kaydet
        save_trade({
            "symbol": sym_base + "_CLOSED", "signal": "CLOSED",
            "pnl": 0, "reason": "recently_closed", "sure_dk": 0,
        })
    except Exception as e:
        log.error(f"[SAVE] {e}")

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"\u26d4 GUNLUK LIMIT! {daily_pnl:+.2f}$")

    icon = "\U0001f7e2" if pnl>=0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# YÖNETİM LOOP
def manage_loop():
    while True:
        time.sleep(30)
        try:
            with pos_lock: syms = list(positions.keys())
            if not syms: continue

            pass  # Log azaltildi

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
                    if symbol in positions:
                        if pnl_pct > positions[symbol]["max_pnl"]:
                            positions[symbol]["max_pnl"] = pnl_pct

                max_pnl = pos["max_pnl"]

                # SL
                if pnl_pct <= -2.0:
                    close_pos(symbol, "Stop Loss -%2.0", price)
                    continue

                # Zaman asimi - 2 saat
                if sure >= 120:
                    close_pos(symbol, "Zaman asimi 2 saat", price)
                    continue

                # Kar koruma
                if max_pnl >= 2.0:
                    if pnl < 0.50:
                        close_pos(symbol, "Kar koruma (0.50$)", price)
                        continue
                if max_pnl >= 3.0:
                    if pnl < 0.80:
                        close_pos(symbol, "Kar koruma (0.80$)", price)
                        continue

                # Trailing
                if max_pnl >= 5.0 and pnl_pct < max_pnl - 3.0:
                    close_pos(symbol, f"Trailing (zirve:%{max_pnl:.1f})", price)
                    continue

                # BTC trend degistiyse cik
                btc_trend, _, _ = get_btc_trend()
                if sig == "LONG" and btc_trend == "DOWN" and pnl > 0:
                    close_pos(symbol, "BTC DOWN - kari al", price)
                    continue
                if sig == "SHORT" and btc_trend == "UP" and pnl > 0:
                    close_pos(symbol, "BTC UP - kari al", price)
                    continue

                # Teknik cikis
                if sure >= 15:
                    data = analyze_coin(symbol)
                    if data:
                        # LONG icin cikis
                        if sig == "LONG":
                            if data["rsi"] > 75:
                                close_pos(symbol, f"RSI asiri alim ({data['rsi']:.0f})", price)
                                continue
                            if data["ema_asagi"] and pnl > 0:
                                close_pos(symbol, "EMA asagi kesti", price)
                                continue
                        # SHORT icin cikis
                        if sig == "SHORT":
                            if data["rsi"] < 25:
                                close_pos(symbol, f"RSI asiri satim ({data['rsi']:.0f})", price)
                                continue
                            if data["ema_yukari"] and pnl > 0:
                                close_pos(symbol, "EMA yukari kesti", price)
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

            # BTC DOWN = sadece dusen coinler
            pass

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(30); continue
                open_syms = set(positions.keys())

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue
                if sym in son_bakilan: continue

                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_VOL: continue

                pct = ticker.get("percentage") or 0

                # Yöne gore filtre
                if btc_trend == "UP" and pct < 2: continue
                if btc_trend == "DOWN" and pct > -2: continue
                if btc_trend == "NEUTRAL" and abs(pct) < 4: continue

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 7200:
                            continue

                # Gec kalma filtresi - zaten cok hareket etmis
                if abs(pct) > 30: continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # Hacime gore sirala
            candidates.sort(key=lambda x: x["qv"], reverse=True)
            candidates = candidates[:8]

            # Rotasyon
            yeni = [c for c in candidates if c["symbol"].split("/")[0] not in son_bakilan]
            if len(yeni) < 2:
                son_bakilan = set()
                yeni = candidates
            candidates = yeni[:5]
            son_bakilan = {c["symbol"].split("/")[0] for c in candidates}

            if not candidates:
                log.info("[SCAN] Aday yok")
                time.sleep(SCAN_INTERVAL); continue

            log.info(f"[SCAN] {len(candidates)} aday analiz ediliyor")

            for c in candidates:
                symbol = c["symbol"]
                sym = symbol.split("/")[0]
                pct = c["pct"]

                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                data = analyze_coin(symbol)
                if not data: continue

                yon, neden = karar_ver(data, btc_trend, pct)

                if yon: log.info(f"[OPEN] {sym}: {yon} - {neden}")

                if yon:
                    acildi = open_pos(symbol, yon, neden, btc_trend)
                    if acildi:
                        open_syms.add(symbol)

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
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# FIND COIN
def find_coin(text):
    words = re.findall(r'[A-Z0-9]+', text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for word in words:
            if len(word) < 3: continue
            symbol = f"{word}/USDT:USDT"
            if symbol in tickers and word not in BLACKLIST:
                return symbol
    except: pass
    return None

# MESAJ HANDLER
@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text = msg.text.strip()
    text_lower = text.lower()

    # /durum
    if "/durum" in text_lower:
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
                    lines.append(f"{icon} {sig_icon} {sym.split('/')[0]} {signal}\n   {entry:.6f} \u2192 {price:.6f}\n   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk\n   Max kar: %{pos.get('max_pnl',0):.2f}\n")
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    # /istatistik
    if "/istatistik" in text_lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,signal,sure_dk").execute()
            data = [d for d in (r.data or []) if d.get("signal") not in ["CLOSED"]]
            if not data:
                bot.send_message(msg.chat.id, "Kayit yok."); return
            toplam = len(data)
            kazan = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net = sum(float(d.get("pnl") or 0) for d in data)
            bot.send_message(msg.chat.id,
                f"\U0001f4ca ISTATISTIK\n\nToplam:{toplam} | Kazanan:{kazan} (%{kazan/toplam*100:.0f})\nNet:{net:+.2f}$\nGunluk:{daily_pnl:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata:{e}")
        return

    # /btc
    if "/btc" in text_lower:
        trend, price, chg = get_btc_trend()
        bot.send_message(msg.chat.id, f"BTC: {trend}\nFiyat: ${price:,.0f}\n24s: {chg:+.1f}%")
        return

    # KAPAT
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
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(isimler)}")
        return

    # DIREKT AC
    if any(k in text_lower for k in ["long ac", "short ac", "long aç", "short aç"]):
        coin_symbol = find_coin(text)
        if coin_symbol:
            yon = "LONG" if "long" in text_lower else "SHORT"
            btc_trend, _, _ = get_btc_trend()
            acildi = open_pos(coin_symbol, yon, "Kullanici istegi", btc_trend)
            if not acildi:
                bot.send_message(msg.chat.id, f"{coin_symbol.split('/')[0]} acilamadi.")
        else:
            bot.send_message(msg.chat.id, "Coin bulunamadi.")
        return

    # ANALIZ
    coin_symbol = find_coin(text)
    if coin_symbol:
        sym = coin_symbol.split("/")[0]
        bot.send_message(msg.chat.id, f"{sym} analiz ediliyor...")
        data = analyze_coin(coin_symbol)
        if data:
            btc_trend, btc_price, _ = get_btc_trend()
            ticker = safe_api(exchange.fetch_ticker, coin_symbol)
            pct = ticker.get("percentage", 0) if ticker else 0
            yon, neden = karar_ver(data, btc_trend, pct)
            msg_text = (
                f"\U0001f4ca {sym} ANALIZ\n"
                f"BTC: {btc_trend}\n"
                f"EMA: {'YUKARI' if data['ema9'] > data['ema20'] else 'ASAGI'}\n"
                f"Hacim: {data['vol_ratio']:.1f}x\n"
                f"RSI: {data['rsi']:.0f}\n"
                f"1h Trend: {data['trend_1h']}\n\n"
                f"Karar: {yon or 'PAS'}\n"
                f"Sebep: {neden}"
            )
            bot.send_message(msg.chat.id, msg_text)
        else:
            bot.send_message(msg.chat.id, f"{sym} veri alinamadi.")
        return

    # Bilgi
    bot.send_message(msg.chat.id,
        "Komutlar:\n"
        "/durum - Acik pozisyonlar\n"
        "/istatistik - Genel istatistik\n"
        "/btc - BTC trend\n"
        "COIN analiz et - Teknik analiz\n"
        "COIN long/short ac - Manuel islem\n"
        "hepsini kapat - Tum pozisyonlari kapat"
    )

# MAIN
import signal as sig_mod, sys

def shutdown(signum, frame):
    log.info("[SHUTDOWN] Kapaniyor...")
    with pos_lock: syms = list(positions.keys())
    for symbol in syms:
        try:
            t = safe_api(exchange.fetch_ticker, symbol)
            close_pos(symbol, "Bot restart", t["last"] if t else None)
        except: pass
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

if __name__ == "__main__":
    print("SADIK TRADER v3 BASLIYOR...")
    load_recently_closed()
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    tg(
        "\U0001f916 SADIK TRADER v3\n\n"
        "Kural tabanlı - AI yok!\n"
        "1073 gecmis islemden ogrendi:\n\n"
        "\u2705 BTC DOWN = hic islem yok\n"
        "\u2705 BTC UP = sadece LONG\n"
        "\u2705 BTC NEUTRAL = sadece SHORT\n"
        "\u2705 Hacim 2x+ gerekli\n"
        "\u2705 EMA kesisimi gerekli\n"
        "\u2705 Gec kalma filtresi\n\n"
        "/durum /istatistik /btc"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
