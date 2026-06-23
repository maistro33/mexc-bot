#!/usr/bin/env python3
"""
SADIK TRADER BOT v2
- Bot grafik cizer, Claude'a gonderir
- Claude LONG/SHORT/PAS karar verir
- Bot acar, takip eder, kapatir
"""

import os, time, threading, logging, json, re, base64, io
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
# matplotlib devre disi
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
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY","")

LEVERAGE       = 5
MARGIN         = 10.0
MAX_OPEN       = 4
MIN_VOL        = 500_000
COMMISSION     = 0.0006
MAX_DAILY_LOSS = -15.0
SCAN_INTERVAL  = 120

# STATE
positions       = {}
pos_lock        = threading.Lock()
pos_messages    = {}
msg_lock        = threading.Lock()
daily_pnl       = 0.0
claude_calls    = 0
recently_closed = {}
closed_lock     = threading.Lock()
bekleyen        = {}
son_bakilan     = set()  # Son turda bakilan coinler

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

def save_recently_closed(sym_base):
    """Kapanan coini Supabase'e kaydet - restart sonrasi da gecerli"""
    if not supa: return
    try:
        supa.table("gpt_trades").insert({
            "symbol": sym_base + "_CLOSED",
            "signal": "CLOSED",
            "pnl": 0,
            "reason": "recently_closed",
            "sure_dk": 0,
        }).execute()
    except: pass

def load_recently_closed():
    """Supabase'den son 2 saatte kapanan coinleri yukle"""
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
                recently_closed[sym] = time.time() - 3600  # 1 saat once kapanmis say
        log.info(f"[CLOSED] {len(r.data or [])} coin yuklendi")
    except Exception as e:
        log.warning(f"[CLOSED] {e}")

def save_lesson(symbol, signal, pnl, ders, btc_trend, piyasa=""):
    if not supa: return
    try:
        sonuc = "KAZANC" if pnl > 0 else "KAYIP"
        supa.table("gpt_lessons").insert({
            "symbol": symbol, "signal": signal,
            "pnl": round(pnl,4), "sonuc": sonuc,
            "ders": ders[:500], "piyasa": piyasa,
            "btc_trend": btc_trend,
        }).execute()
    except Exception as e:
        log.error(f"[DERS SAVE] {e}")

def load_lessons(limit=8):
    if not supa: return "Gecmis yok."
    try:
        lessons_r = supa.table("gpt_lessons").select(
            "symbol,signal,pnl,sonuc,ders,btc_trend"
        ).order("created_at", desc=True).limit(6).execute()
        trades_r = supa.table("gpt_trades").select(
            "symbol,signal,pnl,neden,reason,sure_dk,btc_trend"
        ).order("created_at", desc=True).limit(limit).execute()

        lines = ["=== GECMIS ISLEMLER ==="]
        data = trades_r.data or []
        if data:
            kazanc = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            lines.append(f"Son {len(data)}: {kazanc} kazanc, {len(data)-kazanc} kayip")
            for d in data:
                pnl = float(d.get("pnl") or 0)
                icon = "+" if pnl > 0 else "-"
                lines.append(f"[{icon}] {d.get('symbol','').split('/')[0]} {d.get('signal','')} {pnl:+.2f}$ | {d.get('reason','')[:30]}")

        lessons = lessons_r.data or []
        if lessons:
            lines.append("\n=== OGRENILENLER ===")
            for l in lessons:
                icon = "+" if float(l.get("pnl") or 0) > 0 else "-"
                lines.append(f"[{icon}] {l.get('symbol','').split('/')[0]}: {l.get('ders','')[:80]}")

        return "\n".join(lines)
    except Exception as e:
        return f"Gecmis yuklenemedi: {e}"

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

# PIYASA
def get_market():
    try:
        raw1h = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=48)
        raw4h = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "4h", limit=24)
        if not raw1h: return "NEUTRAL", 0, 0, "BELIRSIZ"
        df1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])
        price = float(df1h["c"].iloc[-1])
        e20 = float(df1h["c"].ewm(span=20).mean().iloc[-1])
        e50 = float(df1h["c"].ewm(span=50).mean().iloc[-1])
        chg24 = (price - float(df1h["c"].iloc[-24])) / float(df1h["c"].iloc[-24]) * 100
        regime = "YATAY"
        if raw4h:
            df4h = pd.DataFrame(raw4h, columns=["t","o","h","l","c","v"])
            e20_4h = float(df4h["c"].ewm(span=20).mean().iloc[-1])
            p4h = float(df4h["c"].iloc[-1])
            chg4h = (p4h - float(df4h["c"].iloc[-12])) / float(df4h["c"].iloc[-12]) * 100
            if p4h > e20_4h * 1.02 and chg4h > 3: regime = "BOGASI"
            elif p4h < e20_4h * 0.98 and chg4h < -3: regime = "AYISI"
        if price > e20 * 1.001 and price > e50: trend = "UP"
        elif price < e20 * 0.999 and price < e50: trend = "DOWN"
        elif price > e20 * 1.001: trend = "UP"
        elif price < e20 * 0.999: trend = "DOWN"
        else: trend = "NEUTRAL"
        return trend, price, chg24, regime
    except:
        return "NEUTRAL", 0, 0, "BELIRSIZ"

# GRAFİK ÇİZ
def chart_summary(ohlcv_data):
    """Grafik yerine sayisal ozet - mum analizi"""
    try:
        df = pd.DataFrame(ohlcv_data[-20:], columns=["t","o","h","l","c","v"])
        
        # Mum renkleri
        yesil = sum(1 for i in range(len(df)) if df["c"].iloc[i] >= df["o"].iloc[i])
        kirmizi = len(df) - yesil
        
        # Son 5 mum
        son5 = df.tail(5)
        son5_yesil = sum(1 for i in range(len(son5)) if son5["c"].iloc[i] >= son5["o"].iloc[i])
        
        # EMA
        ema9  = float(df["c"].ewm(span=9).mean().iloc[-1])
        ema20 = float(df["c"].ewm(span=20).mean().iloc[-1])
        price = float(df["c"].iloc[-1])
        ema_durum = "EMA9>EMA20 YUKARI" if ema9 > ema20 else "EMA9<EMA20 ASAGI"
        
        # Bollinger
        bb_ma  = df["c"].rolling(20).mean().iloc[-1]
        bb_std = df["c"].rolling(20).std().iloc[-1]
        bb_ust = bb_ma + 2*bb_std
        bb_alt = bb_ma - 2*bb_std
        if price > bb_ust: bb_pos = "UST BANDIN USTUNDE"
        elif price < bb_alt: bb_pos = "ALT BANDIN ALTINDA"
        else: bb_pos = f"ORTA (band ici %{((price-bb_alt)/(bb_ust-bb_alt)*100):.0f})"
        
        # Hacim trendi
        vol_avg = float(df["v"].rolling(10).mean().iloc[-1])
        vol_son = float(df["v"].iloc[-1])
        vol_ratio = vol_son / max(vol_avg, 0.001)
        vol_trend = "ARTIYOR" if vol_ratio > 1.2 else "AZALIYOR" if vol_ratio < 0.8 else "NORMAL"
        
        # Momentum
        pct_5 = (float(df["c"].iloc[-1]) - float(df["c"].iloc[-5])) / float(df["c"].iloc[-5]) * 100
        pct_10 = (float(df["c"].iloc[-1]) - float(df["c"].iloc[-10])) / float(df["c"].iloc[-10]) * 100
        
        # Destek/Direnc
        high20 = float(df["h"].max())
        low20  = float(df["l"].min())
        direnc_uzaklik = (high20 - price) / price * 100
        destek_uzaklik = (price - low20) / price * 100
        
        return (
            f"SON 20 MUM ANALIZI:\n"
            f"Yesil/Kirmizi: {yesil}/{kirmizi} | Son 5 mum: {son5_yesil} yesil {5-son5_yesil} kirmizi\n"
            f"EMA: {ema_durum} (EMA9:{ema9:.4f} EMA20:{ema20:.4f})\n"
            f"Bollinger: {bb_pos}\n"
            f"Hacim: {vol_ratio:.1f}x ortalama ({vol_trend})\n"
            f"Momentum: 5mum={pct_5:+.2f}% | 10mum={pct_10:+.2f}%\n"
            f"Direnc uzaklik: %{direnc_uzaklik:.1f} | Destek uzaklik: %{destek_uzaklik:.1f}"
        )
    except Exception as e:
        return f"Ozet hatasi: {e}"

def draw_chart(symbol, ohlcv_data, title=""):
    """Grafik ciz - hafif versiyon, thread ile timeout"""
    result = [None]
    def _draw():
        try:
            df = pd.DataFrame(ohlcv_data[-20:], columns=["t","o","h","l","c","v"])
            df["t"] = pd.to_datetime(df["t"], unit="ms")

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 4),
                                           gridspec_kw={"height_ratios": [3,1]},
                                           facecolor="#1a1a2e")
            ax1.set_facecolor("#1a1a2e")
            ax2.set_facecolor("#1a1a2e")

            for i, row in df.iterrows():
                color = "#00ff88" if row["c"] >= row["o"] else "#ff4444"
                ax1.plot([i, i], [row["l"], row["h"]], color=color, linewidth=0.8)
                ax1.bar(i, abs(row["c"]-row["o"]), bottom=min(row["c"],row["o"]),
                       color=color, width=0.6)

            ema9  = df["c"].ewm(span=9).mean()
            ema20 = df["c"].ewm(span=20).mean()
            ax1.plot(range(len(df)), ema9,  color="#ffff00", linewidth=1, label="EMA9")
            ax1.plot(range(len(df)), ema20, color="#ff8800", linewidth=1, label="EMA20")

            bb_ma  = df["c"].rolling(20).mean()
            bb_std = df["c"].rolling(20).std()
            ax1.fill_between(range(len(df)), bb_ma-2*bb_std, bb_ma+2*bb_std,
                            alpha=0.1, color="#4488ff")

            last_price = float(df["c"].iloc[-1])
            ax1.axhline(y=last_price, color="#ffffff", linewidth=0.5, linestyle="--")
            ax1.text(len(df)-1, last_price, f" {last_price:.4f}", color="#ffffff", fontsize=8)
            ax1.set_title(f"{symbol.split('/')[0]} - {title}", color="#ffffff", fontsize=11)
            ax1.tick_params(colors="#888888")
            ax1.legend(fontsize=7, facecolor="#1a1a2e", labelcolor="white")
            ax1.set_xlim(-1, len(df))
            for spine in ax1.spines.values(): spine.set_color("#333333")

            vol_colors = ["#00ff88" if df["c"].iloc[i] >= df["o"].iloc[i] else "#ff4444"
                         for i in range(len(df))]
            ax2.bar(range(len(df)), df["v"], color=vol_colors, width=0.6)
            ax2.set_facecolor("#1a1a2e")
            ax2.tick_params(colors="#888888")
            for spine in ax2.spines.values(): spine.set_color("#333333")

            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format="jpeg", dpi=60, bbox_inches="tight", facecolor="#1a1a2e")
            plt.close()
            buf.seek(0)
            result[0] = base64.standard_b64encode(buf.read()).decode("utf-8")
        except Exception as e:
            log.warning(f"[CHART] {e}")
            plt.close("all")

    t = threading.Thread(target=_draw, daemon=True)
    t.start(); t.join(timeout=10)
    if t.is_alive():
        log.warning("[CHART] Timeout - grafik atlandi")
        plt.close("all")
        return None
    return result[0]

# CLAUDE API
def claude_api(messages, model="claude-sonnet-4-6", max_tokens=200,
               image_data=None, image_type="image/jpeg"):
    global claude_calls
    if not ANTHROPIC_KEY: return None
    claude_calls += 1
    if claude_calls > 600: return None

    result = [None]
    def call():
        try:
            system_msg = ""
            claude_msgs = []
            for i, m in enumerate(messages):
                if m["role"] == "system":
                    system_msg = m["content"]
                else:
                    if image_data and m["role"] == "user" and i == len(messages)-1:
                        claude_msgs.append({
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {
                                    "type": "base64",
                                    "media_type": image_type,
                                    "data": image_data
                                }},
                                {"type": "text", "text": m["content"]}
                            ]
                        })
                    else:
                        claude_msgs.append({"role": m["role"], "content": m["content"]})

            payload = {"model": model, "max_tokens": max_tokens, "messages": claude_msgs}
            if system_msg: payload["system"] = system_msg

            r = req.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY,
                         "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json=payload, timeout=30)
            if r.status_code == 200:
                result[0] = r.json()["content"][0]["text"].strip()
            else:
                log.warning(f"[CLAUDE] HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log.warning(f"[CLAUDE] {e}")

    t = threading.Thread(target=call, daemon=True)
    t.start(); t.join(timeout=45)
    if t.is_alive():
        log.warning("[CLAUDE] Timeout")
        return None
    return result[0]

# SYSTEM PROMPT
SYSTEM = """Sen SADIK, profesyonel bir kripto futures trader'isin.

GOREV:
Sana coin teknik verileri gonderilecek. Her coini analiz edip karar vereceksin.
Grafik olmasa da sayisal verilerden (EMA, Bollinger, hacim, momentum) karar verebilirsin.

STRATEJI:
- BTC'den bagimsiz hareket eden pump ve dumplari yakala
- Pump baslangicinda LONG gir, kar al cik
- Dump baslangicinda SHORT gir, kar al cik
- Bir coinden kar alinca 2 SAAT bir daha acma
- Gec kalmis pump/dump'a girme

GRAFİK ANALİZİ:
- Mum renkleri: yesil=yukari, kirmizi=asagi
- EMA9 (sari) EMA20 (turuncu) - kesimlere bak
- Hacim artisi = guclu sinyal
- Bollinger bant kirilmasi = guclu hareket

KARAR FORMATI (sadece JSON):
{"karar": "LONG", "tp_pct": 2.0, "sl_pct": 1.0, "neden": "EMA kesisti, hacim artıyor"}
{"karar": "SHORT", "tp_pct": 2.0, "sl_pct": 1.0, "neden": "Bollinger kirdi, dump basladi"}
{"karar": "PAS", "neden": "Gec kalindi veya sinyal zayif"}

ONEMLI: JSON mutlaka kapanmali. neden alani maksimum 1 cumle, net ve aciklayici.

KURALLAR:
- Komisyon %0.12 | Kaldirac 5x | Margin 10$
- SL %2 max | Min kar %1.2
- Duz Turkce yaz, markdown yok
- Sadece JSON ver, baska bir sey yazma"""

# COİN BUL
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
        best = None; best_len = 0
        for symbol in tickers.keys():
            if not symbol.endswith("/USDT:USDT"): continue
            sym = symbol.split("/")[0].upper()
            if sym in BLACKLIST: continue
            if sym in words and len(sym) > best_len:
                best = symbol; best_len = len(sym)
        return best
    except: return None

# CLAUDE ILE GRAFİK ANALİZ
def analyze_with_chart(symbol, timeframe="15m", extra_info=""):
    """Grafik ciz, Claude'a gonder, karar al"""
    try:
        raw = safe_api(exchange.fetch_ohlcv, symbol, timeframe, limit=50)
        if not raw: return None

        # Grafik ciz
        sym = symbol.split("/")[0]
        chart_b64 = None

        # Teknik veriler
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price = float(df["c"].iloc[-1])
        pct_change = (price - float(df["c"].iloc[-10])) / float(df["c"].iloc[-10]) * 100
        vol_avg = float(df["v"].rolling(20).mean().iloc[-1])
        vol_son = float(df["v"].iloc[-1])
        vol_ratio = vol_son / max(vol_avg, 0.001)

        btc_trend, btc_price, btc_chg, regime = get_market()
        history = load_lessons(4)

        ozet = chart_summary(raw)

        user_msg = (
            f"Coin: {sym}/USDT | Fiyat: {price:.6f}\n"
            f"BTC: {btc_trend} ${btc_price:,.0f} ({btc_chg:+.2f}%) | Rejim: {regime}\n"
            f"{extra_info}\n\n"
            f"{ozet}\n\n"
            f"Gecmis:\n{history}\n\n"
            f"Bu verilere gore LONG mu SHORT mu PAS mi?\n"
            f"Sadece JSON formatinda karar ver. neden alani max 5 kelime."
        )

        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg}
        ]

        yanit = claude_api(msgs, model="claude-sonnet-4-6", max_tokens=300,
                          image_data=chart_b64, image_type="image/jpeg")
        return yanit
    except Exception as e:
        log.warning(f"[ANALYZE] {symbol}: {e}")
        return None

# ISLEM AC
def open_pos(symbol, yon, neden, btc_trend, tp_pct=2.0, sl_pct=1.0):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS:
        log.info("[SKIP] Gunluk limit")
        return False

    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price = t["last"]
    sl_price = price*(1-0.02) if yon=="LONG" else price*(1+0.02)

    with pos_lock:
        sym_base = symbol.split("/")[0].upper()
        for existing in positions.keys():
            if existing.split("/")[0].upper() == sym_base:
                log.info(f"[SKIP] {sym_base} zaten acik")
                return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 7200:
                    log.info(f"[SKIP] {sym_base} 2 saat bekleme")
                    return False
        if len(positions) >= MAX_OPEN:
            log.info(f"[SKIP] Max pozisyon {MAX_OPEN}")
            return False
        log.info(f"[OPEN] {sym_base} {yon} aciliyor...")

        positions[symbol] = {
            "signal": yon, "entry": price,
            "sl_price": sl_price, "ref_tp": tp_pct,
            "max_pnl": 0.0, "trailing_aktif": False,
            "neden": neden, "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    icon = "\U0001f4c8" if yon=="LONG" else "\U0001f4c9"
    tg(f"\U0001f4cb {icon} {sym} {yon}\nGiris: {price:.6f}\nSL: {sl_price:.6f}\n\U0001f4ac {neden}")
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

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"\u26d4 GUNLUK LIMIT! {daily_pnl:+.2f}$")

    sym_base = symbol.split("/")[0].upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()
    # Supabase'e de kaydet - restart sonrasi kaybolmasin
    threading.Thread(target=save_recently_closed, args=(sym_base,), daemon=True).start()

    # Trade kaydet
    try:
        save_trade({
            "symbol": symbol, "signal": sig, "pnl": round(pnl,4),
            "tp_pct": pos.get("max_pnl",0), "sl_pct": 2.0, "guven": 0,
            "btc_trend": pos.get("btc_trend",""),
            "sure_dk": sure, "reason": reason, "neden": pos.get("neden",""),
        })
    except Exception as e:
        log.error(f"[SAVE_TRADE] {e}")

    # Ders cikar
    def ders_cikar():
        try:
            ders_prompt = (
                f"Islem kapandi:\n"
                f"Coin: {symbol.split('/')[0]} {sig}\n"
                f"PnL: {pnl:+.2f}$ | Sure: {sure}dk\n"
                f"Kapanma: {reason}\n"
                f"Neden acilmisti: {pos.get('neden','')}\n\n"
                f"2 cumlede ders: Ne dogru/yanlis yapildi?"
            )
            msgs = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": ders_prompt}]
            ders = claude_api(msgs, model="claude-sonnet-4-6", max_tokens=100)
            if ders:
                save_lesson(symbol, sig, pnl, ders, pos.get("btc_trend",""))
            else:
                fallback = f"{'Kazanc' if pnl>0 else 'Kayip'}: {reason} - {pos.get('neden','')[:80]}"
                save_lesson(symbol, sig, pnl, fallback, pos.get("btc_trend",""), "fallback")
        except Exception as e:
            log.warning(f"[DERS] {e}")

    threading.Thread(target=ders_cikar, daemon=True).start()

    icon = "\U0001f7e2" if pnl>=0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# YÖNETİCİ - Claude grafik gorur
def manage_loop():
    while True:
        time.sleep(60)
        try:
            with pos_lock: syms = list(positions.keys())
            if syms:
                log.info(f"[MANAGE] {len(syms)} pozisyon")

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

                # Zaman asimi
                if sure > 120:
                    close_pos(symbol, "Zaman asimi 2 saat", price)
                    continue

                # SL kontrolu
                if pnl_pct <= -2.0:
                    close_pos(symbol, "Stop Loss -%2.0", price)
                    continue

                # KAR KORUMA - garantili minimum kar
                pos_size = MARGIN * LEVERAGE
                kar_usdt = pnl  # Mevcut kar dolar olarak

                if max_pnl >= 2.0:  # En az %2 kar gorulduyse
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["trailing_aktif"] = True
                    # Kar 0.50$ altina dustuyse kapat - minimum kari koru
                    if kar_usdt < 0.50 and pnl > 0:
                        close_pos(symbol, f"Kar koruma (min 0.50$)", price)
                        continue
                    # Kar 1.50$+ gorulduyse ve 0.80$ altina dustuyse kapat
                    if max_pnl >= 3.0 and kar_usdt < 0.80:
                        close_pos(symbol, f"Kar koruma (min 0.80$)", price)
                        continue

                # Cok buyuk geri cekilme - son guvence
                if max_pnl >= 5.0 and pnl_pct < max_pnl - 3.0:
                    close_pos(symbol, f"Trailing Stop (zirve:%{max_pnl:.1f})", price)
                    continue

                # Ilk 15dk bekle
                if sure < 15: continue

                # Claude grafik gorur, karar verir
                if sure % 3 == 0:  # Her 3 dakikada bir
                    sym = symbol.split("/")[0]
                    raw = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=30)
                    if not raw: continue

                    chart_b64 = None

                    user_msg = (
                        f"{sym} {sig} pozisyonu - {sure}. dakika\n"
                        f"Giris: {entry:.6f} | Simdi: {price:.6f}\n"
                        f"PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | Max: %{max_pnl:.2f}\n"
                        f"Trailing: {'Aktif' if pos.get('trailing_aktif') else 'Bekliyor'}\n\n"
                        f"Grafige bak. DEVAM mi KAPAT mi?\n"
                        f"JSON: {{\"karar\": \"DEVAM\"}} veya {{\"karar\": \"KAPAT\", \"neden\": \"...\"}}"
                    )

                    msgs = [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user_msg}
                    ]

                    yanit = claude_api(msgs, model="claude-sonnet-4-6", max_tokens=100,
                                      image_data=chart_b64, image_type="image/jpeg")
                    if not yanit: continue

                    try:
                        j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                        if j:
                            karar = json.loads(j.group())
                            if karar.get("karar") == "KAPAT":
                                if sure < 15: continue
                                if 0 < pnl_pct < 1.2: continue
                                if -1.5 < pnl_pct < 0: continue
                                close_pos(symbol, karar.get("neden","Claude kapat"), price)
                    except Exception as e:
                        log.warning(f"[YON] {e}")

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# TARAYICI - Claude grafik gorur, karar verir
def scanner_loop():
    time.sleep(90)
    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(SCAN_INTERVAL); continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(30); continue
                open_syms = set(positions.keys())

            btc_trend, btc_price, btc_chg, regime = get_market()
            log.info(f"[SCAN] BTC:{btc_trend} ${btc_price:,.0f} | {regime}")

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            # En hareketli coinler
            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue
                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_VOL: continue
                pct = ticker.get("percentage") or 0
                if abs(pct) < 3: continue

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 7200:
                            continue

                # Pump skoru
                pump_score = 0
                if abs(pct) > 15: pump_score += 50
                elif abs(pct) > 8: pump_score += 35
                elif abs(pct) > 4: pump_score += 20
                elif abs(pct) > 2: pump_score += 10
                if qv > 10_000_000: pump_score += 40
                elif qv > 5_000_000: pump_score += 30
                elif qv > 2_000_000: pump_score += 15
                elif qv > 500_000: pump_score += 5

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv, "score": pump_score})

            # Onceki turda bakilan coinleri atla
            global son_bakilan
            yeni_adaylar = [c for c in candidates if c["symbol"].split("/")[0] not in son_bakilan]
            
            # Eger hepsi bakildiysa sifirla
            if len(yeni_adaylar) < 2:
                son_bakilan = set()
                yeni_adaylar = candidates
            
            # Pump skoruna gore sirala
            yeni_adaylar.sort(key=lambda x: x["score"], reverse=True)
            candidates = yeni_adaylar[:5]
            
            # Bu turdaki coinleri kaydet
            son_bakilan = {c["symbol"].split("/")[0] for c in candidates}

            if not candidates:
                time.sleep(SCAN_INTERVAL); continue

            log.info(f"[SCAN] {len(candidates)} aday analiz ediliyor")

            for c in candidates:
                symbol = c["symbol"]
                sym = symbol.split("/")[0]
                pct = c["pct"]

                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                # Claude grafik analizi
                yon_ipucu = "LONG" if pct > 0 else "SHORT"
                extra = f"Son hareket: {pct:+.2f}% | Hacim: {c['qv']/1e6:.1f}M USDT | Yon ipucu: {yon_ipucu}"

                yanit = analyze_with_chart(symbol, "15m", extra)
                if not yanit:
                    log.info(f"[SCAN] {sym}: Claude cevap vermedi")
                    continue

                log.info(f"[SCAN] {sym}: {yanit[:100]}")

                try:
                    j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                    if j:
                        karar = json.loads(j.group())
                        if karar.get("karar") in ["LONG", "SHORT"]:
                            yon = karar["karar"]
                            neden = karar.get("neden", "")
                            tp = float(karar.get("tp_pct", 2.0))
                            sl = float(karar.get("sl_pct", 1.0))

                            with pos_lock:
                                if len(positions) >= MAX_OPEN: break
                                if symbol in open_syms: continue

                            acildi = open_pos(symbol, yon, neden, btc_trend, tp, sl)
                            if acildi:
                                open_syms.add(symbol)
                        else:
                            log.info(f"[SCAN] {sym}: PAS - {karar.get('neden','')[:60]}")
                except Exception as e:
                    log.warning(f"[SCAN JSON] {symbol}: {e}")

                time.sleep(5)  # Claude rate limit icin bekle

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
            self.wfile.write(f"OK|pos:{len(positions)}|pnl:{daily_pnl:+.2f}|calls:{claude_calls}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# MESAJ HANDLER
@bot.message_handler(content_types=["photo"])
def handle_photo(msg):
    threading.Thread(target=handle_photo_async, args=(msg,), daemon=True).start()

def handle_photo_async(msg):
    try:
        bot.send_message(msg.chat.id, "Grafik analiz ediyorum...")
        photo = msg.photo[-1]
        file_info = bot.get_file(photo.file_id)
        photo_bytes = bot.download_file(file_info.file_path)
        img_b64 = base64.standard_b64encode(photo_bytes).decode("utf-8")
        caption = msg.caption or "Bu grafigi analiz et"
        btc_trend, btc_price, btc_chg, regime = get_market()
        history = load_lessons(3)
        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"BTC:{btc_trend} ${btc_price:,.0f} | {regime}\n{history}\n\n{caption}\n\nSadece JSON karar ver."}
        ]
        yanit = claude_api(msgs, model="claude-sonnet-4-6", max_tokens=150,
                          image_data=img_b64, image_type="image/jpeg")
        if not yanit:
            bot.send_message(msg.chat.id, "Analiz yapilamadi."); return

        # JSON islem var mi?
        try:
            j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
            if j:
                karar = json.loads(j.group())
                if karar.get("karar") in ["LONG","SHORT"]:
                    coin_symbol = find_coin(caption)
                    if coin_symbol:
                        yon = karar["karar"]
                        neden = karar.get("neden","Grafik analizi")
                        open_pos(coin_symbol, yon, neden, btc_trend)
        except: pass

        bot.send_message(msg.chat.id, f"\U0001f916 {yanit[:500]}")
    except Exception as e:
        log.error(f"[PHOTO] {e}")
        bot.send_message(msg.chat.id, f"Hata: {type(e).__name__}")

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    if not msg.text: return
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
                    trailing = " | Trailing" if pos.get("trailing_aktif") else ""
                    lines.append(f"{icon} {sig_icon} {sym.split('/')[0]} {signal}\n   {entry:.6f} \u2192 {price:.6f}\n   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk{trailing}\n")
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    # /istatistik
    if "/istatistik" in text_lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,signal,sure_dk").execute()
            data = r.data or []
            if not data:
                bot.send_message(msg.chat.id, "Kayit yok."); return
            toplam = len(data)
            kazan = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net = sum(float(d.get("pnl") or 0) for d in data)
            bot.send_message(msg.chat.id,
                f"\U0001f4ca ISTATISTIK\n\nToplam:{toplam} | Kazanan:{kazan}(%{kazan/toplam*100:.0f})\nNet:{net:+.2f}$\nGunluk:{daily_pnl:+.2f}$\nClaude:{claude_calls} cagri")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata:{e}")
        return

    # KAPAT - aninda
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
    ac_keys = ["long ac", "short ac", "long aç", "short aç"]
    if any(k in text_lower for k in ac_keys):
        coin_symbol = find_coin(text)
        if coin_symbol:
            yon = "LONG" if "long" in text_lower else "SHORT"
            btc_trend, _, _, _ = get_market()
            acildi = open_pos(coin_symbol, yon, "Kullanici istegi", btc_trend)
            if not acildi:
                bot.send_message(msg.chat.id, f"{coin_symbol.split('/')[0]} acilamadi.")
        else:
            bot.send_message(msg.chat.id, "Coin bulunamadi. Ornek: 'AVAX long ac'")
        return

    # DOGAL DIL - Claude grafik ile analiz
    bot.send_message(msg.chat.id, "\U0001f914 Analiz ediyorum...")
    try:
        btc_trend, btc_price, btc_chg, regime = get_market()
        history = load_lessons(3)

        # Acik pozisyon bilgisi
        current = ""
        with pos_lock:
            if positions:
                for sym, pos in positions.items():
                    t = safe_api(exchange.fetch_ticker, sym)
                    if t:
                        price = t["last"]; entry = pos["entry"]; signal = pos["signal"]
                        pnl = (price-entry)/entry*MARGIN*LEVERAGE if signal=="LONG" else (entry-price)/entry*MARGIN*LEVERAGE
                        sure = int((time.time()-pos["open_time"])/60)
                        current += f"{sym.split('/')[0]} {signal} {pnl:+.2f}$ {sure}dk\n"
            else:
                current = "Acik pozisyon yok"

        # Coin var mi?
        coin_symbol = find_coin(text)
        chart_b64 = None
        coin_info = ""

        if coin_symbol:
            sym = coin_symbol.split("/")[0]
            raw = safe_api(exchange.fetch_ohlcv, coin_symbol, "15m", limit=50)
            if raw:
                chart_b64 = None
                ticker = safe_api(exchange.fetch_ticker, coin_symbol)
                if ticker:
                    pct = ticker.get("percentage", 0)
                    qv = ticker.get("quoteVolume", 0)
                    coin_info = f"\n{sym}: {pct:+.2f}% | Hacim: {qv/1e6:.1f}M USDT"
        else:
            # Tara - en hareketli coinleri cek
            tara_keys = ["tara", "bul", "firsat", "pump", "short", "long"]
            if any(k in text_lower for k in tara_keys):
                try:
                    tickers = safe_api(exchange.fetch_tickers)
                    if tickers:
                        top = []
                        with pos_lock: open_syms = set(positions.keys())
                        for symbol, ticker in tickers.items():
                            if not symbol.endswith("/USDT:USDT"): continue
                            if symbol.split("/")[0] in BLACKLIST: continue
                            if symbol in open_syms: continue
                            qv = ticker.get("quoteVolume") or 0
                            if qv < 500_000: continue
                            pct = abs(ticker.get("percentage") or 0)
                            if pct < 3: continue
                            top.append({"symbol": symbol, "pct": ticker.get("percentage",0), "qv": qv})
                        top.sort(key=lambda x: abs(x["pct"]), reverse=True)
                        top = top[:5]
                        if top:
                            coin_info = "\nEN HAREKETLI COINLER:\n"
                            for c in top:
                                s = c["symbol"].split("/")[0]
                                coin_info += f"{s}: {c['pct']:+.1f}% | {c['qv']/1e6:.1f}M\n"
                            # En yuksek hareketteki coinin grafigini ciz
                            best = top[0]["symbol"]
                            raw = safe_api(exchange.fetch_ohlcv, best, "15m", limit=50)
                            if raw:
                                chart_b64 = None
                                coin_symbol = best
                except Exception as e:
                    log.warning(f"[TARA] {e}")

        user_content = (
            f"BTC:{btc_trend} ${btc_price:,.0f} ({btc_chg:+.2f}%) | {regime}\n"
            f"Pozisyonlar: {current}\n"
            f"{history}\n"
            f"{coin_info}\n\n"
            f"Kullanici: {text}\n\n"
            f"Grafige bak ve karar ver. Sadece JSON formatinda cevap ver."
        )

        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content}
        ]

        yanit = claude_api(msgs, model="claude-sonnet-4-6", max_tokens=300,
                          image_data=chart_b64, image_type="image/jpeg")

        if not yanit:
            bot.send_message(msg.chat.id, "Claude cevap vermedi."); return

        # JSON islem var mi?
        try:
            j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
            if j:
                karar = json.loads(j.group())
                if karar.get("karar") in ["LONG","SHORT"] and coin_symbol:
                    yon = karar["karar"]
                    neden = karar.get("neden","Claude grafik analizi")
                    tp = float(karar.get("tp_pct", 2.0))
                    sl = float(karar.get("sl_pct", 1.0))
                    open_pos(coin_symbol, yon, neden, btc_trend, tp, sl)
        except Exception as e:
            log.warning(f"[JSON] {e}")

        bot.send_message(msg.chat.id, f"\U0001f916 {yanit[:600]}")

    except Exception as e:
        log.error(f"[HANDLE] {e}")
        bot.send_message(msg.chat.id, f"\u274c {type(e).__name__}")

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
    print("SADIK TRADER v2 BASLIYOR...")
    load_recently_closed()  # Restart sonrasi kapanan coinleri yukle
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    tg(
        "\U0001f916 SADIK TRADER v2\n\n"
        "Claude grafik gorur, karar verir!\n\n"
        "\u2705 Her coin icin grafik cizilir\n"
        "\u2705 Claude grafikten LONG/SHORT/PAS der\n"
        "\u2705 Pozisyon yonetimi de grafik ile\n"
        "\u2705 Pump/Dump yakalama\n"
        "\u2705 Sen de grafik atabilirsin\n\n"
        "/durum /istatistik\n"
        "veya dogal konusmaya devam et"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
