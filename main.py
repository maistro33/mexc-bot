#!/usr/bin/env python3
"""
SADIK GPT TRADING BOT v3
Tam Otonom — GPT-4o Her Karara Karar Verir
TP/SL/Yön/Büyüklük hepsini GPT belirler
"""

import os, time, threading, logging, json
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK_GPT")

# ─── CONFIG ───
TELE_TOKEN  = os.getenv("TELE_TOKEN","")
CHAT_ID     = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API  = os.getenv("BITGET_API","")
BITGET_SEC  = os.getenv("BITGET_SEC","")
BITGET_PASS = os.getenv("BITGET_PASS","")
SUPA_URL    = os.getenv("SUPABASE_URL","")
SUPA_KEY    = os.getenv("SUPABASE_KEY","")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY","")
CG_KEY      = os.getenv("COINGLASS_API_KEY", os.getenv("COINGL_API_KEY",""))

# ─── SABİT PARAMETRELER ───
LEVERAGE      = 5
MARGIN        = 10.0
MAX_OPEN      = 5       # Az ama kaliteli
SCAN_INTERVAL = 60      # GPT çağrısı pahalı, sık tarama yapma
MIN_QUOTE_VOL = 3_000_000
MAX_PRICE     = 30
COMMISSION    = 0.0006  # %0.12 toplam

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ",
}

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# ─── SUPABASE ───
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

def load_gpt_history(limit=20):
    """GPT'ye geçmiş işlemleri göster — öğrensin"""
    if not supa: return ""
    try:
        r = supa.table("gpt_trades").select("symbol,signal,pnl,tp_pct,sl_pct,reason").order("created_at", desc=True).limit(limit).execute()
        data = r.data or []
        if not data: return "Henüz geçmiş işlem yok."
        lines = []
        for d in data:
            icon = "✅" if float(d.get("pnl") or 0) > 0 else "❌"
            lines.append(f"{icon} {d.get('symbol','').split('/')[0]} {d.get('signal','')} PnL:{float(d.get('pnl') or 0):+.2f} TP:{d.get('tp_pct','')}% SL:{d.get('sl_pct','')}%")
        return "\n".join(lines)
    except Exception as e:
        log.warning(f"[HISTORY] {e}")
        return ""

# ─── EXCHANGE ───
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
            log.warning(f"[API {i}] {e}")
            time.sleep(2)
    return None

# ─── STATE ───
positions = {}
pos_lock  = threading.Lock()
gpt_calls_today = 0
gpt_call_lock = threading.Lock()
recently_closed = {}  # Son 1 saatte kapanan coinler
closed_lock = threading.Lock()
daily_pnl = 0.0
bot_active = True
MAX_DAILY_LOSS = -15.0

# ─── BTC TREND ───
def get_btc_data():
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=24)
        if not raw: return "NEUTRAL", 0, 0
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        c = df["c"]
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        price = float(c.iloc[-1])
        change_24h = (price - float(c.iloc[0])) / float(c.iloc[0]) * 100
        if price > e20 * 1.001: trend = "UP"
        elif price < e20 * 0.999: trend = "DOWN"
        else: trend = "NEUTRAL"
        return trend, price, change_24h
    except Exception as e:
        log.warning(f"[BTC] {e}")
        return "NEUTRAL", 0, 0

# ─── VERİ HAZIRLA ───
def get_market_data(symbol):
    """GPT için kapsamlı piyasa verisi hazırla"""
    try:
        # 1m mumlar
        raw1 = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=30)
        if not raw1: return None
        df1 = pd.DataFrame(raw1, columns=["t","o","h","l","c","v"])

        # 5m mumlar
        raw5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=20)
        if not raw5: return None
        df5 = pd.DataFrame(raw5, columns=["t","o","h","l","c","v"])

        # 1h mumlar
        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=10)
        if not raw1h: return None
        df1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])

        c1 = df1["c"]; v1 = df1["v"]
        price = float(c1.iloc[-1])

        # RSI
        d = c1.diff()
        g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        rsi = float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

        # EMA
        ema9  = float(c1.ewm(span=9).mean().iloc[-1])
        ema20 = float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5  = float(df5["c"].ewm(span=9).mean().iloc[-1])
        ema20_5 = float(df5["c"].ewm(span=20).mean().iloc[-1])
        ema20_1h = float(df1h["c"].ewm(span=20).mean().iloc[-1])

        # Hacim
        vol_avg = float(v1.rolling(20).mean().iloc[-1])
        vol_ratio = float(v1.iloc[-1]) / max(vol_avg, 0.001)

        # Fiyat değişimi
        move_1 = (price - float(c1.iloc[-2])) / float(c1.iloc[-2]) * 100
        move_5 = (price - float(c1.iloc[-6])) / float(c1.iloc[-6]) * 100
        move_1h = (price - float(df1h["c"].iloc[-2])) / float(df1h["c"].iloc[-2]) * 100

        # Son 5 mum yönleri
        candles = []
        for i in range(-5, 0):
            o = float(df1["o"].iloc[i])
            c = float(df1["c"].iloc[i])
            h = float(df1["h"].iloc[i])
            l = float(df1["l"].iloc[i])
            direction = "🟢" if c > o else "🔴"
            change = (c - o) / o * 100
            candles.append(f"{direction}{change:+.2f}% (H:{h:.6f} L:{l:.6f})")

        # Funding rate
        funding = 0.0
        if CG_KEY:
            try:
                sym = symbol.split("/")[0]
                r = req.get("https://open-api-v3.coinglass.com/api/futures/fundingRate/current",
                    headers={"CG-API-KEY": CG_KEY}, params={"symbol": sym}, timeout=5)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    if data:
                        d = next((x for x in data if "bitget" in x.get("exchangeName","").lower()), data[0])
                        funding = float(d.get("fundingRate", 0) or 0)
            except: pass

        # MACD
        ema12 = c1.ewm(span=12).mean()
        ema26 = c1.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_hist = float((macd_line - signal_line).iloc[-1])
        macd_status = "YUKARI" if macd_hist > 0 else "ASAGI"

        # Bollinger Bands
        bb_ma = float(c1.rolling(20).mean().iloc[-1])
        bb_std = float(c1.rolling(20).std().iloc[-1])
        bb_upper = bb_ma + 2 * bb_std
        bb_lower = bb_ma - 2 * bb_std
        bb_pct = (price - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper != bb_lower else 50
        if bb_pct > 80: bb_pos = "ÜST BANT"
        elif bb_pct < 20: bb_pos = "ALT BANT"
        else: bb_pos = "ORTA"

        return {
            "symbol": symbol,
            "price": price,
            "rsi": rsi,
            "ema9": ema9, "ema20": ema20,
            "ema9_5": ema9_5, "ema20_5": ema20_5,
            "ema20_1h": ema20_1h,
            "vol_ratio": vol_ratio,
            "move_1": move_1, "move_5": move_5, "move_1h": move_1h,
            "candles": candles,
            "funding": funding,
            "macd_hist": macd_hist,
            "macd_status": macd_status,
            "bb_pos": bb_pos,
            "bb_pct": bb_pct,
        }
    except Exception as e:
        log.warning(f"[DATA] {symbol}: {e}")
        return None

# ─── GPT ANA KARAR ───
def gpt_analyze(symbol, data, btc_trend, btc_price, btc_change):
    """GPT tüm analizi yapar ve karar verir"""
    if not OPENAI_KEY:
        return None

    global gpt_calls_today
    with gpt_call_lock:
        gpt_calls_today += 1
        if gpt_calls_today > 200:  # Günlük limit
            log.warning("[GPT] Günlük limit aşıldı")
            return None

    try:
        sym = symbol.split("/")[0]
        history = load_gpt_history(10)

        candle_str = "\n".join([f"  {i+1}. {c}" for i, c in enumerate(data["candles"])])

        prompt = f"""Sen bir kripto futures paper trading botusun. Piyasayı analiz edip kendi kararını veriyorsun.
Geçmiş işlemlerinden öğreniyorsun ve her seferinde daha iyi karar vermeye çalışıyorsun.

═══ PİYASA DURUMU ═══
BTC: {btc_trend} | Fiyat: ${btc_price:,.0f} | 24s: {btc_change:+.2f}%

═══ {sym}/USDT ANALİZ ═══
Fiyat: {data['price']:.6f}
RSI: {data['rsi']:.1f}
EMA9/20 (1m): {data['ema9']:.6f} / {data['ema20']:.6f} → {'YUKARI' if data['ema9'] > data['ema20'] else 'AŞAĞI'}
EMA9/20 (5m): {data['ema9_5']:.6f} / {data['ema20_5']:.6f} → {'YUKARI' if data['ema9_5'] > data['ema20_5'] else 'AŞAĞI'}
EMA20 (1h): {data['ema20_1h']:.6f} → Fiyat {'üstünde' if data['price'] > data['ema20_1h'] else 'altında'}
Hacim: {data['vol_ratio']:.1f}x ortalama
Hareket: 1dk={data['move_1']:+.2f}% 5dk={data['move_5']:+.2f}% 1s={data['move_1h']:+.2f}%
MACD: {data['macd_status']} (histogram: {data['macd_hist']:+.6f})
Bollinger: {data['bb_pos']} (%{data['bb_pct']:.0f})
Funding: {data['funding']*100:.4f}%

Son 5 mum:
{candle_str}

═══ GEÇMİŞ İŞLEMLERİM ═══
{history}

═══ KARAR VER ═══
Yukarıdaki verileri analiz et. Geçmiş işlemlerinden öğren.
Komisyon: %0.12 (açış + kapanış)
Kaldıraç: 5x | Margin: 10 USDT

SADECE JSON formatında cevap ver, başka hiçbir şey yazma:
{{
  "karar": "LONG" veya "SHORT" veya "PAS",
  "tp_pct": 1.5,
  "sl_pct": 1.0,
  "guven": 75,
  "neden": "kısa analiz"
}}

Notlar:
- PAS ver: RSI aşırı, trend belirsiz, hacim düşükse
- TP ve SL'i piyasa koşuluna göre belirle (TP her zaman SL'den büyük olsun)
- BTC NEUTRAL ise çok dikkatli ol
- Geçmiş kayıplarından öğren"""

        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "max_tokens": 200, "temperature": 0.3,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=15)

        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            # JSON parse
            yanit_clean = yanit.replace("```json","").replace("```","").strip()
            karar = json.loads(yanit_clean)
            log.info(f"[GPT] {sym} → {karar.get('karar')} güven:{karar.get('guven')} | {karar.get('neden')}")
            return karar
        else:
            log.warning(f"[GPT] HTTP {r.status_code}")
            return None

    except json.JSONDecodeError as e:
        log.warning(f"[GPT] JSON parse hatası: {e} | {yanit}")
        return None
    except Exception as e:
        log.warning(f"[GPT] {e}")
        return None

# ─── PAPER AÇ ───
def open_paper(symbol, karar, data, btc_trend):
    signal  = karar["karar"]
    tp_pct  = float(karar.get("tp_pct", 1.5)) / 100
    sl_pct  = float(karar.get("sl_pct", 1.0)) / 100
    guven   = int(karar.get("guven", 60))
    neden   = karar.get("neden", "")

    # Güven skoru düşükse açma
    if guven < 60:
        log.info(f"[SKIP] {symbol.split('/')[0]} güven düşük: {guven}")
        return

    # TP/SL makul aralıkta olmalı
    tp_pct = max(0.010, min(tp_pct, 0.050))  # %1 - %5 arası
    sl_pct = max(0.005, min(sl_pct, 0.020))  # %0.5 - %2 arası
    # TP her zaman SL'den büyük olmalı
    if tp_pct <= sl_pct:
        tp_pct = sl_pct * 1.5
        log.info(f"[FIX] TP düzeltildi: {tp_pct*100:.1f}%")

    with pos_lock:
        if symbol in positions: return
        if len(positions) >= MAX_OPEN: return
        price = data["price"]
        if signal == "LONG":
            tp = price * (1 + tp_pct)
            sl = price * (1 - sl_pct)
        else:
            tp = price * (1 - tp_pct)
            sl = price * (1 + sl_pct)

        positions[symbol] = {
            "signal": signal, "entry": price,
            "tp": tp, "sl": sl,
            "tp_pct": tp_pct * 100, "sl_pct": sl_pct * 100,
            "guven": guven, "neden": neden,
            "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    tg(
        f"📋 [GPT BOT] {sym} {signal}\n"
        f"Giriş: {price:.6f}\n"
        f"TP: {tp:.6f} (+%{tp_pct*100:.1f})\n"
        f"SL: {sl:.6f} (-%{sl_pct*100:.1f})\n"
        f"Güven: {guven}% | BTC:{btc_trend}\n"
        f"💬 {neden}"
    )

# ─── PAPER KAPAT ───
def close_paper(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig   = pos["signal"]; entry = pos["entry"]
    pos_size = MARGIN * LEVERAGE
    commission = pos_size * COMMISSION

    if sig == "LONG":
        pnl = (exit_price - entry) / entry * pos_size - commission
    else:
        pnl = (entry - exit_price) / entry * pos_size - commission

    sure = int((time.time() - pos["open_time"]) / 60)

    save_trade({
        "symbol":    symbol,
        "signal":    sig,
        "pnl":       round(pnl, 4),
        "tp_pct":    pos.get("tp_pct", 0),
        "sl_pct":    pos.get("sl_pct", 0),
        "guven":     pos.get("guven", 0),
        "btc_trend": pos.get("btc_trend", "NEUTRAL"),
        "sure_dk":   sure,
        "reason":    reason,
        "neden":     pos.get("neden", ""),
    })

    sym  = symbol.split("/")[0]
    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} [GPT BOT] {sym} KAPANDI\n{reason}\nPnL: {pnl:+.2f} USDT | {sure}dk")
    log.info(f"[KAPAT] {sym} {reason} pnl={pnl:+.2f}")
    with closed_lock:
        recently_closed[symbol] = time.time()
    # Günlük PnL güncelle
    global daily_pnl, bot_active
    daily_pnl += pnl
    if daily_pnl <= MAX_DAILY_LOSS and bot_active:
        bot_active = False
        tg(f"⛔ GÜNLÜK ZARAR LİMİTİ AŞILDI!\nGünlük PnL: {daily_pnl:+.2f} USDT\nBot durduruldu. Yarın devam eder.")
        log.warning(f"[LIMIT] Günlük zarar limiti: {daily_pnl:+.2f}")

# ─── GPT POZİSYON YÖNETİMİ ───
def gpt_manage_position(symbol, pos, current_price):
    """GPT açık pozisyonu yönetir — kapat/devam et/TP yükselt/SL ayarla"""
    if not OPENAI_KEY:
        return None

    try:
        sig    = pos["signal"]
        entry  = pos["entry"]
        tp     = pos["tp"]
        sl     = pos["sl"]
        sure   = int((time.time() - pos["open_time"]) / 60)
        pos_size = MARGIN * LEVERAGE

        if sig == "LONG":
            pnl_pct = (current_price - entry) / entry * 100
            pnl     = (current_price - entry) / entry * pos_size
        else:
            pnl_pct = (entry - current_price) / entry * 100
            pnl     = (entry - current_price) / entry * pos_size

        sym = symbol.split("/")[0]
        btc_trend, btc_price, _ = get_btc_data()

        prompt = f"""Sen bir kripto futures trading botusun. Açık pozisyonu yönetiyorsun.
Komisyon: %0.12 | Kaldıraç: 5x | Margin: 10 USDT

═══ AÇIK POZİSYON ═══
Coin: {sym} {sig}
Giriş: {entry:.6f}
Şu an: {current_price:.6f}
PnL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)
Süre: {sure} dakika
Mevcut TP: {tp:.6f} ({pos['tp_pct']:.1f}%)
Mevcut SL: {sl:.6f} ({pos['sl_pct']:.1f}%)

BTC: {btc_trend} ${btc_price:,.0f}

═══ KARAR VER ═══
SADECE JSON formatında cevap ver:
{{
  "karar": "DEVAM" veya "KAPAT" veya "TP_YUKSEL" veya "SL_AYARLA",
  "yeni_tp_pct": 2.0,
  "yeni_sl_pct": 0.5,
  "neden": "kısa açıklama"
}}

Kurallar:
- Zarar %1.5'i geçtiyse → MUTLAKA KAPAT, bekletme
- Zarar %1'i geçti VE trend aleyhine döndüyse → KAPAT
- Zarar var ama trend hâlâ lehimize → DEVAM veya SL_AYARLA
- Kazanç var ve trend güçlü → TP_YUKSEL
- Kazanç var ama trend zayıflıyor → KAPAT, karı koru
- DEVAM: trend güçlü, zarar küçük, bekle
- Komisyon %0.12 — küçük kazançta bile kapatmaya değebilir
- 60 dakikadan fazla açık → KAPAT"""

        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "max_tokens": 150, "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=10)

        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            yanit_clean = yanit.replace("```json","").replace("```","").strip()
            return json.loads(yanit_clean)
        return None

    except Exception as e:
        log.warning(f"[MANAGE_GPT] {symbol}: {e}")
        return None

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(30)  # Her 30 saniyede kontrol et
        try:
            with pos_lock: syms = list(positions.keys())

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price  = t["last"]
                sig    = pos["signal"]
                entry  = pos["entry"]
                sure   = int((time.time() - pos["open_time"]) / 60)

                # Zaman aşımı — 1 saat
                if sure > 60:
                    close_paper(symbol, "ZAMAN AŞIMI 2 saat", price)
                    continue

                # GPT pozisyon yönetimi
                karar = gpt_manage_position(symbol, pos, price)
                if not karar:
                    continue

                action = karar.get("karar", "DEVAM")
                neden  = karar.get("neden", "")
                sym    = symbol.split("/")[0]

                log.info(f"[MANAGE] {sym} → {action} | {neden}")

                if action == "KAPAT":
                    close_paper(symbol, f"GPT KAPAT: {neden}", price)

                elif action == "TP_YUKSEL":
                    yeni_tp_pct = float(karar.get("yeni_tp_pct", pos["tp_pct"])) / 100
                    yeni_tp_pct = max(0.010, min(yeni_tp_pct, 0.080))  # %1-%8 arası
                    if sig == "LONG":
                        yeni_tp = entry * (1 + yeni_tp_pct)
                    else:
                        yeni_tp = entry * (1 - yeni_tp_pct)
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["tp"] = yeni_tp
                            positions[symbol]["tp_pct"] = yeni_tp_pct * 100
                    tg(f"📈 [GPT] {sym} TP yükseltildi → %{yeni_tp_pct*100:.1f}\n{neden}")

                elif action == "SL_AYARLA":
                    yeni_sl_pct = float(karar.get("yeni_sl_pct", pos["sl_pct"])) / 100
                    yeni_sl_pct = max(0.003, min(yeni_sl_pct, 0.020))  # %0.3-%2 arası
                    if sig == "LONG":
                        yeni_sl = entry * (1 - yeni_sl_pct)
                    else:
                        yeni_sl = entry * (1 + yeni_sl_pct)
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["sl"] = yeni_sl
                            positions[symbol]["sl_pct"] = yeni_sl_pct * 100
                    tg(f"🛡 [GPT] {sym} SL ayarlandı → %{yeni_sl_pct*100:.1f}\n{neden}")

                # DEVAM — hiçbir şey yapma, bekle

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    global bot_active, daily_pnl
    while True:
        try:
            with pos_lock:
                open_count = len(positions)
                open_syms  = set(positions.keys())

            if open_count >= MAX_OPEN:
                time.sleep(30); continue

            # Günlük zarar limiti kontrolü
            if not bot_active:
                log.info(f"[LIMIT] Bot durduruldu. Günlük PnL: {daily_pnl:+.2f}")
                time.sleep(SCAN_INTERVAL); continue

            btc_trend, btc_price, btc_change = get_btc_data()

            # BTC NEUTRAL'da çok dikkatli ol
            if btc_trend == "NEUTRAL":
                log.info("[SCAN] BTC NEUTRAL — bekleniyor")
                time.sleep(SCAN_INTERVAL); continue

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            # En hareketli coinleri seç
            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                if symbol.split("/")[0] in BLACKLIST: continue
                if symbol in open_syms: continue
                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_QUOTE_VOL: continue
                price = ticker.get("last") or 0
                if not price or price > MAX_PRICE: continue
                pct = abs(ticker.get("percentage") or 0)
                if pct < 0.5: continue  # En az %0.5 hareket
                candidates.append({"symbol": symbol, "volume": qv, "pct": pct})

            # Hacme göre sırala, ilk 10'u analiz et
            candidates.sort(key=lambda x: x["volume"], reverse=True)
            candidates = candidates[:10]

            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend}")

            for coin in candidates:
                symbol = coin["symbol"]
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in positions: continue

                # Son 1 saatte kapandıysa atla
                with closed_lock:
                    if symbol in recently_closed:
                        if time.time() - recently_closed[symbol] < 3600:
                            continue
                        else:
                            del recently_closed[symbol]

                # Veri hazırla
                data = get_market_data(symbol)
                if not data: continue

                # GPT analiz et
                karar = gpt_analyze(symbol, data, btc_trend, btc_price, btc_change)
                if not karar: continue
                if karar.get("karar") == "PAS":
                    log.info(f"[PAS] {symbol.split('/')[0]}: {karar.get('neden')}")
                    continue

                # Aç
                open_paper(symbol, karar, data, btc_trend)
                time.sleep(2)  # GPT rate limit

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(f"OK|pos:{len(positions)}|gpt:{gpt_calls_today}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id, "📋 Pozisyon yok."); return
        lines = ["📋 GPT BOT POZİSYONLAR\n"]
        for sym, pos in positions.items():
            t = safe_api(exchange.fetch_ticker, sym)
            if t:
                price = t["last"]
                entry = pos["entry"]
                signal = pos["signal"]
                pos_size = MARGIN * LEVERAGE
                if signal == "LONG":
                    pnl = (price - entry) / entry * pos_size
                else:
                    pnl = (entry - price) / entry * pos_size
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} {signal}\n"
                    f"Giriş:{entry:.6f} → {price:.6f}\n"
                    f"PnL:{pnl:+.2f} USDT\n"
                    f"Güven:{pos['guven']}% | {pos['neden'][:50]}\n"
                )
        bot.send_message(msg.chat.id, "\n".join(lines))

@bot.message_handler(commands=["istatistik","stats"])
def cmd_stats(msg):
    if not supa:
        bot.send_message(msg.chat.id, "Supabase yok."); return
    try:
        r = supa.table("gpt_trades").select("pnl,signal,btc_trend,guven").execute()
        data = r.data or []
        if not data:
            bot.send_message(msg.chat.id, "Henüz kayıt yok."); return

        toplam = len(data)
        kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
        net    = sum(float(d.get("pnl") or 0) for d in data)

        # Güven skoruna göre analiz
        yuksek_guven = [d for d in data if int(d.get("guven") or 0) >= 75]
        yuksek_win   = [d for d in yuksek_guven if float(d.get("pnl") or 0) > 0]

        bot.send_message(msg.chat.id,
            f"📊 GPT BOT İSTATİSTİK\n\n"
            f"Toplam: {toplam} işlem\n"
            f"Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
            f"Net PnL: {net:+.2f} USDT\n\n"
            f"🎯 Güven ≥75:\n"
            f"  {len(yuksek_guven)} işlem → %{len(yuksek_win)/max(len(yuksek_guven),1)*100:.0f} kazanç\n\n"
            f"📞 GPT çağrısı bugün: {gpt_calls_today}\n"
            f"💰 Günlük PnL: {daily_pnl:+.2f} USDT (limit: {MAX_DAILY_LOSS})"
        )
    except Exception as e:
        bot.send_message(msg.chat.id, f"Hata: {e}")

@bot.message_handler(commands=["sor","ask","ai"])
def cmd_sor(msg):
    if not OPENAI_KEY:
        bot.send_message(msg.chat.id, "❌ OpenAI API key yok."); return
    soru = msg.text.replace("/sor","").replace("/ask","").replace("/ai","").strip()
    if not soru:
        bot.send_message(msg.chat.id, "Kullanım: /sor BTC bugün ne yapar?"); return
    bot.send_message(msg.chat.id, "🤔 Düşünüyorum...")
    try:
        btc_trend, btc_price, btc_change = get_btc_data()
        history = load_gpt_history(5)
        with pos_lock: pos_info = f"{len(positions)} açık pozisyon"
        prompt = f"""Sen SADIK GPT trading botunun AI asistanısın.
Şu an: {pos_info} | BTC: {btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)
Son işlemler: {history}
Soru: {soru}
Kısa ve net cevap ver, Türkçe."""
        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "max_tokens": 300, "temperature": 0.7,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=15)
        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            bot.send_message(msg.chat.id, f"🤖 {yanit}")
        else:
            bot.send_message(msg.chat.id, f"❌ GPT hata: {r.status_code}")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ {e}")

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text = msg.text.replace("/kapat","").strip().upper()
    if not text:
        bot.send_message(msg.chat.id, "Kullanım: /kapat SOL"); return
    symbol = f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions:
            bot.send_message(msg.chat.id, f"❌ {text} yok."); return
    close_paper(symbol, "MANUEL")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms = list(positions.keys())
    for s in syms: close_paper(s, "MANUEL HEPSI")

# ─── MAIN ───
if __name__ == "__main__":
    print("🤖 SADIK GPT TRADING BOT v3 BAŞLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    print("[OK] Health | Manage | Scanner")
    tg(
        "🤖 SADIK GPT TRADING BOT v3\n\n"
        "TAM OTONOM — GPT Her Karara Karar Verir!\n\n"
        "✅ GPT-4o-mini piyasayı analiz eder\n"
        "✅ Yön, TP, SL hepsini GPT belirler\n"
        "✅ Geçmiş işlemlerden öğrenir\n"
        "✅ Komisyon dahil PnL hesabı\n"
        "✅ BTC NEUTRAL'da bekler\n"
        "✅ Güven < 60 ise açmaz\n\n"
        f"Max {MAX_OPEN} pozisyon | Günlük maks 200 GPT çağrısı\n\n"
        "/durum /istatistik /sor [soru] /kapat SOL /hepsikapat"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
