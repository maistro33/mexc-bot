#!/usr/bin/env python3
"""
SADIK SCALP — KAĞIT (PAPER) TRADING SÜRÜMÜ — v8
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÖNEMLİ: Bu sürümde GERÇEK PARA KULLANILMAZ. Borsada hiçbir gerçek emir
açılmaz/kapatılmaz. Tüm sinyaller, kararlar ve pozisyon takibi GERÇEK
piyasa fiyatlarıyla ama SİMÜLE edilerek yapılır. Panel ve Telegram
raporları gerçek işlem yapılıyormuş gibi çalışır — sonuçlar "eğer gerçek
para ile yapılsaydı ne olurdu" sorusuna cevap verir.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEDEN BU TASARIM? (önceki canlı testten çıkan dersler)

  1) FADE (ters bahis) stratejisi trend takibi kadar güvenilir çıkmadı
     (EPIC örneklerinde fade yanıldı, trend teyidi doğru sonuç verdi).
     → Bu sürümde FADE tamamen KALDIRILDI. Tek ve tutarlı mantık var:
       ADX ile GERÇEK TREND teyit edilirse hareketin YÖNÜNDE gir.
       Teyit edilmezse (zayıf/yatay piyasa) sinyali ATLA — ne fade
       ne zorla trend, sadece "emin değilsem işlem açma".

  2) Sabit -%2.0 SL, her coin'in kendi oynaklığına uymuyordu — bazı
     coinlerde çok dar (gürültüden sürekli SL yeniyordu), bazılarında
     gereksiz geniş kalıyordu.
     → Bu sürümde SL, her coin'in kendi ATR'ine (Average True Range,
       gerçek oynaklık ölçüsü) göre HESAPLANIYOR. TP hedefleri de sabit
       dolar değil, riskin KATLARI (1R/2R/3R/4R) olarak tanımlanıyor —
       risk/ödül oranı her zaman tutarlı kalıyor.

  3) Uzun süren işlemlerin çoğu zararla kapanıyordu (canlı veri).
     → Zaman stopu korunuyor: TP1 (1R) seviyesine 5 dakikada ulaşmayan
       VE o an zararda olan işlem, SL'e kadar beklemeden kapatılır.
       Kâr yolundaki işlemlere dokunulmaz.

  4) Kademeli TP + yüzdesel trailing (zirvenin %30'u geri çekilirse
     kapat) canlı testte makul çalıştı → aynen korunuyor, sadece
     dolar yerine R birimiyle ifade ediliyor.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POZİSYON: 10$ margin × 5x kaldıraç = 50$ (simüle)
GİRİŞ: Sinyal + ADX teyidi anında, güncel piyasa fiyatından (simüle dolum)
ÇIKIŞ: SL (ATR bazlı) | 1R/2R/3R/4R kademeli taban + yüzdesel trailing |
       5dk zaman stopu (zarardaysa) | 240dk mutlak süre limiti
"""

import os, time, threading, logging, re
import ccxt
import pandas as pd
import telebot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_PAPER")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN    = os.getenv("TELE_TOKEN", "")
CHAT_ID       = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API    = os.getenv("BITGET_API", "")
BITGET_SEC    = os.getenv("BITGET_SEC", "")
BITGET_PASS   = os.getenv("BITGET_PASS", "")

# ── KAĞIT (PAPER) MODU — HER ZAMAN True olmalı, gerçek para riski yok ──
PAPER_TRADING   = True

# ── Pozisyon (simüle) ──
MARGIN          = 10.0
LEVERAGE        = 5
POS_SIZE        = MARGIN * LEVERAGE     # 50$ (referans/varsayılan — gerçek boyut ATR'e göre değişir)
COMMISSION      = 0.0006                # taker, tek yön (simüle komisyon, gerçekçilik için düşülür)

# ── RİSK BAZLI POZİSYON BOYUTLANDIRMA ──
# ATR bazlı SL kullanınca, sabit $ pozisyon boyutu her coin için FARKLI dolar
# riski demek (oynak coinde çok büyük risk, sakin coinde çok küçük risk).
# Bunu düzeltmek için: her işlemde HEDEF DOLAR RİSKİNİ sabit tutuyoruz
# (marjinin %10'u), pozisyon boyutunu buna göre HESAPLIYORUZ — oynak
# coinde otomatik küçük, sakin coinde otomatik büyük pozisyon.
RISK_PER_TRADE_PCT = 0.10                        # marjinin %10'u kadar dolar risk hedefi
HEDEF_RISK_DOLAR    = MARGIN * RISK_PER_TRADE_PCT  # örn. 10$ × %10 = 1.00$
MAX_POS_SIZE        = MARGIN * LEVERAGE * 3        # üst sınır (aşırı düşük ATR'de bile çok büyümesin)
MIN_POS_SIZE        = MARGIN * LEVERAGE * 0.3      # alt sınır (aşırı yüksek ATR'de bile çok küçülmesin)

MAX_OPEN        = 3
MAX_DAILY_LOSS  = -10.0    # simüle günlük zarar limiti (gerçek para değil, ama disiplin için korunuyor)
MAX_SURE_DK     = 240      # dk — mutlak süre limiti (herkes için, kâr/zarar fark etmez)

# ── ZAMAN STOPU (scalp mantığı) ──
ZAMAN_STOPU_DK    = 5      # 1R'a ulaşmadan bu süre geçip hâlâ zarardaysa erken kapat
ZAMAN_STOPU_AKTIF = True

# ── REJİM FİLTRESİ (ADX) — TEK mantık: teyit yoksa işlem YOK ──
ADX_PERIOD  = 14
ADX_ESIK    = 20    # bu değerin altında ADX = "zayıf/yatay piyasa" → sinyal ATLANIR

# ── Soluklanma bekleme (v9'da eklendi) — ŞİMDİLİK KAPALI ──
# v8'in kazanma oranı toparlanmakta (13%→26%→37.5%) — bu özelliği hemen
# açarsak, "chasing" (anında giriş) mantığının gerçekten iyi mi kötü mü
# olduğunu hiç net göremeyiz. 40-50 işlemlik temiz bir v8 verisi
# toplandıktan sonra bu bayrak True yapılıp karşılaştırma yapılacak.
SOLUKLANMA_BEKLE_AKTIF = False

# ── ATR bazlı risk yönetimi ──
ATR_PERIOD    = 14
ATR_SL_MULT   = 1.5     # SL mesafesi = 1.5 × ATR (coinin kendi oynaklığına göre)
R_KADEMELERI  = [1.0, 2.0, 3.0, 4.0]   # TP hedefleri: risk'in katları (1R/2R/3R/4R)
TRAIL_GIVEBACK_PCT = 0.30   # zirve net kârın bu yüzdesi kadar geri çekilirse kapat

# ── Bağımsız tarayıcı (ani hareket tespiti) ──
SCAN_INTERVAL     = 30
SCAN_MAX_ADAY     = 20
ANI_VOL_SPIKE_MIN = 2.0
ANI_PCT_MIN       = 1.5
MIN_PRICE    = 0.0001
MAX_PRICE    = 100.0
MIN_TURNOVER = 200_000
RECENTLY_TTL = 1800     # coin kapandıktan sonra 30dk tekrar açılmasın

# ════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()

trade_log       = []
trade_log_lock  = threading.Lock()
MAX_TRADE_LOG   = 500

# ── KALICI DEPOLAMA (Railway Volume) ──
# /data yolu, Railway'de eklenecek bir Volume'a bağlanmalı — böylece kod
# güncellemelerinde (yeniden deploy) bile işlem geçmişi KAYBOLMAZ.
# Volume yoksa (yol yazılabilir değilse) bot yine de çalışır, sadece
# kalıcılık olmadan (eski davranış) devam eder — hata vermez.
import json
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/trade_log.json")

def trade_log_yukle():
    global trade_log
    try:
        if os.path.exists(TRADE_LOG_PATH):
            with open(TRADE_LOG_PATH, "r", encoding="utf-8") as f:
                yuklenen = json.load(f)
            with trade_log_lock:
                trade_log = yuklenen
            log.info(f"[KALICI] {len(yuklenen)} işlem diskten yüklendi ({TRADE_LOG_PATH})")
        else:
            log.info(f"[KALICI] {TRADE_LOG_PATH} bulunamadı — muhtemelen Volume bağlı değil, sıfırdan başlanıyor")
    except Exception as e:
        log.warning(f"[KALICI] Yükleme başarısız (kalıcılık olmadan devam ediliyor): {e}")

def trade_log_kaydet_diske():
    try:
        os.makedirs(os.path.dirname(TRADE_LOG_PATH), exist_ok=True)
        with trade_log_lock:
            veriler = list(trade_log)
        with open(TRADE_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(veriler, f)
    except Exception as e:
        log.warning(f"[KALICI] Diske yazma başarısız (Volume bağlı olmayabilir): {e}")

def kaydet_islem(sembol, yon, net, sure_dk, kaynak, sonuc_metni):
    with trade_log_lock:
        trade_log.append({
            "zaman": time.strftime("%H:%M:%S"),
            "sembol": sembol, "yon": yon, "net": net,
            "sure": sure_dk, "kaynak": kaynak, "sonuc": sonuc_metni,
        })
        if len(trade_log) > MAX_TRADE_LOG:
            del trade_log[0]
    trade_log_kaydet_diske()

# ════════════════════════════════════════════
# TELEGRAM BOT
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")

# ════════════════════════════════════════════
# EXCHANGE (SADECE PİYASA VERİSİ İÇİN — emir açılmaz)
# ════════════════════════════════════════════
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})

_last_api = 0
_api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global _last_api
    for attempt in range(4):
        try:
            with _api_lock:
                wait = 0.5 - (time.time() - _last_api)
                if wait > 0: time.sleep(wait)
                _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except ccxt.NetworkError as e:
            log.warning(f"[API] Network: {e}"); time.sleep(3)
        except Exception as e:
            log.warning(f"[API] {attempt+1}: {e}"); time.sleep(2)
    return None

# ════════════════════════════════════════════
# PNL
# ════════════════════════════════════════════
def gunluk_limit_asildi():
    with daily_pnl_lock:
        return daily_pnl <= MAX_DAILY_LOSS

def pnl_ekle(miktar):
    global daily_pnl
    with daily_pnl_lock:
        daily_pnl += miktar
        return daily_pnl

def net_pnl_hesapla(pos, price):
    """Round-trip komisyon dahil NET pnl (simüle) — pozisyonun GERÇEK
    boyutuna göre hesaplanır, sabit bir varsayıma dayanmaz."""
    entry  = pos["entry"]
    amount = pos["amount"]
    side   = pos.get("side", "long")
    if side == "short":
        gross = (entry - price) * amount
    else:
        gross = (price - entry) * amount
    notional = entry * amount
    fee = notional * COMMISSION * 2
    net = gross - fee
    pct = (gross / notional) * 100 if notional else 0.0
    return net, pct

# ════════════════════════════════════════════
# İNDİKATÖRLER (ADX + ATR)
# ════════════════════════════════════════════
def calc_adx(df, period=14):
    """Trend GÜCÜNÜ ölçer (yönü değil). Yüksek ADX = güçlü/kararlı trend."""
    high, low, close = df["h"], df["l"], df["c"]
    up_move   = high.diff()
    down_move = -low.diff()

    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 0.0001)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 0.0001)

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 0.0001)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return float(adx.iloc[-1])

def calc_atr(df, period=14):
    """Average True Range — coinin GERÇEK oynaklığını ölçer (mutlak fiyat birimi)."""
    high, low, close = df["h"], df["l"], df["c"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return float(atr.iloc[-1])

def piyasa_verisi_al(symbol, period=14):
    """15m mumlardan ADX ve ATR'i TEK seferde hesaplar (gereksiz tekrar
    API çağrısı yapmamak için). Veri yetersizse (None, None) döner."""
    try:
        r = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=period * 3)
        if not r or len(r) < period * 2:
            return None, None
        df = pd.DataFrame(r, columns=["t", "o", "h", "l", "c", "v"])
        return calc_adx(df, period), calc_atr(df, period)
    except Exception as e:
        log.warning(f"[PIYASA_VERI] {symbol}: {e}")
        return None, None

# ════════════════════════════════════════════
# ANİ HAREKET TESPİTİ (1m hacim/fiyat spike)
# ════════════════════════════════════════════
def ani_hareket_tespit(symbol):
    try:
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=25)
        if not r1m or len(r1m) < 15: return None, {}
        df = pd.DataFrame(r1m, columns=["t", "o", "h", "l", "c", "v"])
        price = float(df["c"].iloc[-1])
        son_hacim = float(df["v"].iloc[-1])
        ort_hacim = float(df["v"].iloc[:-1].tail(20).mean())
        vol_oran  = son_hacim / max(ort_hacim, 0.0001)
        if vol_oran < ANI_VOL_SPIKE_MIN: return None, {"vol": round(vol_oran, 1)}
        pct_3m = (price - float(df["c"].iloc[-4])) / float(df["c"].iloc[-4]) * 100

        detay = {"vol": round(vol_oran, 1), "pct": round(pct_3m, 2), "price": price}

        if pct_3m >= ANI_PCT_MIN:
            return "pump", detay
        elif pct_3m <= -ANI_PCT_MIN:
            return "dump", detay
        return None, detay
    except Exception as e:
        log.warning(f"[ANİ] {symbol}: {e}")
        return None, {}

# ════════════════════════════════════════════
# POZİSYON SLOTU
# ════════════════════════════════════════════
def pozisyon_slot_al(symbol, entry, sl, kaynak, side, tp_levels, r_dollar, amount):
    sym_base = symbol.split("/")[0].upper()
    with pos_lock:
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < RECENTLY_TTL:
                    return False
        if len(positions) >= MAX_OPEN: return False
        if gunluk_limit_asildi(): return False

        positions[symbol] = {
            "entry": entry, "sl": sl, "side": side, "amount": amount,
            "tetiklendi": False, "last_tp_idx": -1, "peak_net": 0.0,
            "open_time": time.time(), "kaynak": kaynak,
            "tp_levels": tp_levels, "r_dollar": r_dollar,
        }
        return True

# ════════════════════════════════════════════
# GİRİŞ (SİMÜLE — gerçek emir YOK)
# ════════════════════════════════════════════
def pozisyon_boyutu_hesapla(risk_mesafe, price):
    """
    Hedef dolar riskine (HEDEF_RISK_DOLAR) göre pozisyon miktarını hesaplar.
    Oynak coin (büyük risk_mesafe) → küçük miktar. Sakin coin (küçük
    risk_mesafe) → büyük miktar. MIN/MAX_POS_SIZE ile sınırlanır.
    Döner: (amount, pos_size_dolar, gercek_r_dolar)
    """
    if risk_mesafe <= 0 or price <= 0:
        return None, None, None

    amount = HEDEF_RISK_DOLAR / risk_mesafe
    pos_size = amount * price

    if pos_size > MAX_POS_SIZE:
        pos_size = MAX_POS_SIZE
        amount = pos_size / price
    elif pos_size < MIN_POS_SIZE:
        pos_size = MIN_POS_SIZE
        amount = pos_size / price

    gercek_r_dolar = risk_mesafe * amount
    return amount, pos_size, gercek_r_dolar

def trend_giris_onayi_bekle(symbol, yon_pump_dump, atr, bekle_sn=12):
    """
    Ani hareket + ADX teyidi geldiğinde, tam sıçramanın UCUNDAN girmek
    yerine kısa bir soluklanma/geri çekilme bekler. Bu, "doğru yöndeyiz
    ama tam yanlış anda giriyoruz" sorununu (canlı veride %13 kazanma
    oranıyla kanıtlanmış) çözmeye çalışır — trend teyitli olsa bile,
    mikro-giriş noktası hâlâ önemli.

    ATR'e göre ölçekli bir geri çekilme eşiği kullanır (her coinin kendi
    oynaklığına göre orantılı, sabit yüzde değil).

    pump → zirveyi takip et, zirveden (0.3×ATR) kadar geri çekilirse onay.
    dump → dibi takip et, dipten (0.3×ATR) kadar yukarı gelirse onay.

    Döner: (onaylandi: bool, fiyat: float|None)
    """
    pullback_mesafe = 0.3 * atr
    if pullback_mesafe <= 0:
        return False, None

    ekstrem = None
    for _ in range(bekle_sn):
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t:
            time.sleep(1); continue
        price = float(t["last"])

        if ekstrem is None:
            ekstrem = price
        elif yon_pump_dump == "pump":
            ekstrem = max(ekstrem, price)
        else:
            ekstrem = min(ekstrem, price)

        if yon_pump_dump == "pump":
            if (ekstrem - price) >= pullback_mesafe:
                return True, price
        else:
            if (price - ekstrem) >= pullback_mesafe:
                return True, price

        time.sleep(1)

    return False, None

def paper_giris_dene(symbol, yon_pump_dump, adx, atr):
    """
    ADX teyitli sinyal geldiğinde ÇAĞRILIR. Güncel piyasa fiyatından
    ANINDA simüle giriş yapar (gerçek emir yok, gerçek para riski yok).
    SL'i ATR'e göre, pozisyon boyutunu RİSK BAZLI (HEDEF_RISK_DOLAR sabit
    kalacak şekilde), TP kademelerini R katlarına göre hesaplar.
    """
    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price = float(t["last"])
    sym = symbol.split("/")[0]

    side = "long" if yon_pump_dump == "pump" else "short"

    risk_mesafe = ATR_SL_MULT * atr
    if risk_mesafe <= 0: return False

    if side == "long":
        sl = price - risk_mesafe
    else:
        sl = price + risk_mesafe

    amount, pos_size, r_dollar = pozisyon_boyutu_hesapla(risk_mesafe, price)
    if amount is None or r_dollar <= 0: return False

    tp_levels = [round(r_dollar * k, 4) for k in R_KADEMELERI]

    if not pozisyon_slot_al(symbol, price, sl, "scanner_trend", side, tp_levels, r_dollar, amount):
        return False

    yon_metni = "LONG" if side == "long" else "SHORT"
    tg(
        f"⚡ #{sym}USDT.P {yon_metni} [KAĞIT]\n"
        f"📡 Kaynak: SCANNER_TREND | ADX:{adx:.1f}\n"
        f"🏁 Giriş: {price:.8f}\n"
        f"🚫 SL: {sl:.8f} (ATR bazlı, {ATR_SL_MULT}×ATR)\n"
        f"🎯 TP (R bazlı): " + " / ".join(f"${x:.2f}" for x in tp_levels) + f" | R=${r_dollar:.2f} (hedef risk: ${HEDEF_RISK_DOLAR:.2f})\n"
        f"💰 Pozisyon: ${pos_size:.2f} | Kaldıraç: {LEVERAGE}x (SİMÜLE, risk bazlı boyutlandırıldı)"
    )
    log.info(f"[AÇIK-KAĞIT] {sym} {yon_metni} @ {price:.8f} ADX:{adx:.1f}")
    return True

# ════════════════════════════════════════════
# ÇIKIŞ (SİMÜLE — gerçek emir YOK)
# ════════════════════════════════════════════
def close_pos(symbol, reason):
    with pos_lock:
        pos = positions.get(symbol)
    if not pos: return

    sym  = symbol.split("/")[0]
    side = pos["side"]

    t = safe_api(exchange.fetch_ticker, symbol)
    exit_price = float(t["last"]) if t else pos["entry"]

    net, pct = net_pnl_hesapla(pos, exit_price)
    sure = int((time.time() - pos["open_time"]) / 60)
    toplam = pnl_ekle(net)
    kaynak = pos.get("kaynak", "?")

    kaydet_islem(sym.upper(), side, net, sure, kaynak, reason)

    with pos_lock:
        positions.pop(symbol, None)
    with closed_lock:
        recently_closed[sym.upper()] = time.time()

    if toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! (simüle) {toplam:+.2f}$")

    icon = "🟢" if net >= 0 else "🔴"
    tg(
        f"{icon} {sym.upper()} KAPANDI [KAĞIT]\n"
        f"{reason}\n"
        f"Net PnL: {net:+.2f}$ ({pct:+.2f}%) | {sure}dk\n"
        f"📡 {kaynak.upper()} | Günlük (simüle): {toplam:+.2f}$"
    )

# ════════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ
# ════════════════════════════════════════════
def manage_loop():
    while True:
        time.sleep(1)
        try:
            with pos_lock:
                syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = float(t["last"])

                side       = pos["side"]
                sl         = pos["sl"]
                tp_levels  = pos["tp_levels"]
                sym        = symbol.split("/")[0]

                net, pct = net_pnl_hesapla(pos, price)
                sure = int((time.time() - pos["open_time"]) / 60)

                if not pos.get("tetiklendi"):
                    sl_tetiklendi = (price <= sl) if side == "long" else (price >= sl)
                    if sl_tetiklendi:
                        close_pos(symbol, f"🚫 SL ({sl:.8f})")
                        continue

                    # ── ZAMAN STOPU ──
                    if ZAMAN_STOPU_AKTIF and sure >= ZAMAN_STOPU_DK and net < 0:
                        close_pos(symbol, f"⏱️ Zaman stopu ({ZAMAN_STOPU_DK}dk'da 1R'a ulaşmadı, zarar büyümeden kapatıldı)")
                        continue

                    if net >= tp_levels[0]:
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tetiklendi"] = True
                                positions[symbol]["last_tp_idx"] = 0
                                positions[symbol]["peak_net"] = net
                        tg(f"🎯 {sym} 1R (${tp_levels[0]:.2f}) net kâra ulaştı — trailing moduna geçildi")
                        continue

                else:
                    peak_net    = pos.get("peak_net", net)
                    last_tp_idx = pos.get("last_tp_idx", 0)

                    if net > peak_net:
                        peak_net = net
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["peak_net"] = peak_net

                        yeni_idx = last_tp_idx
                        while yeni_idx + 1 < len(tp_levels) and peak_net >= tp_levels[yeni_idx + 1]:
                            yeni_idx += 1
                        if yeni_idx > last_tp_idx:
                            with pos_lock:
                                if symbol in positions:
                                    positions[symbol]["last_tp_idx"] = yeni_idx
                            last_tp_idx = yeni_idx
                            tg(f"🎯 {sym} {yeni_idx+1}R (${tp_levels[yeni_idx]:.2f}) net kâra ulaştı — garanti yükseldi")

                    floor_net = tp_levels[last_tp_idx]
                    dinamik_trail = max(tp_levels[0] * 0.5, peak_net * TRAIL_GIVEBACK_PCT)

                    if (peak_net - net) >= dinamik_trail or net <= floor_net - 0.01:
                        close_pos(symbol, f"🎯 {last_tp_idx+1}R garantisi kilitlendi (zirve ${peak_net:.2f} → ${net:.2f})")
                        continue

                if sure >= MAX_SURE_DK:
                    close_pos(symbol, f"⏰ Süre doldu ({MAX_SURE_DK}dk)")
                    continue

                if gunluk_limit_asildi():
                    close_pos(symbol, "Günlük limit (simüle)")
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════════
# BAĞIMSIZ TARAYICI — tek mantık: ADX teyitliyse yönünde gir, değilse atla
# ════════════════════════════════════════════
def scanner_loop():
    log.info("[SCANNER] Kağıt (paper) mod tarama başladı — ADX teyitli momentum")
    while True:
        time.sleep(SCAN_INTERVAL)
        try:
            if gunluk_limit_asildi(): continue
            with pos_lock:
                if len(positions) >= MAX_OPEN: continue

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers: continue

            adaylar = []
            for sym, t in tickers.items():
                if not sym.endswith("/USDT:USDT"): continue
                sym_base = sym.split("/")[0].upper()
                with pos_lock:
                    if sym in positions: continue
                    if any(ex.split("/")[0].upper() == sym_base for ex in positions): continue
                with closed_lock:
                    if sym_base in recently_closed and time.time() - recently_closed[sym_base] < RECENTLY_TTL:
                        continue
                last = t.get("last"); vol = t.get("quoteVolume") or 0; chg = abs(t.get("percentage") or 0)
                if not last or last < MIN_PRICE or last > MAX_PRICE: continue
                if vol < MIN_TURNOVER: continue
                adaylar.append((sym, chg))

            adaylar.sort(key=lambda x: x[1], reverse=True)
            adaylar = adaylar[:SCAN_MAX_ADAY]

            for sym, _ in adaylar:
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break

                yon, detay = ani_hareket_tespit(sym)
                if yon is None: continue
                sym_kisa = sym.split("/")[0]

                adx, atr = piyasa_verisi_al(sym, ADX_PERIOD)
                if adx is None or atr is None:
                    log.info(f"[SCANNER] {sym_kisa} veri yetersiz, atlandı")
                    continue

                if adx < ADX_ESIK:
                    log.info(f"[SCANNER] {sym_kisa} ADX:{adx:.1f} < {ADX_ESIK} (zayıf piyasa), sinyal ATLANDI")
                    continue

                yon_metni = "LONG" if yon == "pump" else "SHORT"
                emoji = "🚀" if yon == "pump" else "📉"

                if SOLUKLANMA_BEKLE_AKTIF:
                    tg(f"{emoji} Ani {yon.upper()}: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}% | ADX:{adx:.1f} ✅ teyit\n[KAĞIT] Soluklanma bekleniyor, sonra {yon_metni}...")
                    onaylandi, giris_fiyat = trend_giris_onayi_bekle(sym, yon, atr)
                    if not onaylandi:
                        log.info(f"[SCANNER] {sym_kisa} soluklanma onayı gelmedi, atlandı")
                        continue
                else:
                    tg(f"{emoji} Ani {yon.upper()}: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}% | ADX:{adx:.1f} ✅ teyit\n[KAĞIT] {yon_metni} deneniyor (anında giriş)...")

                acildi = paper_giris_dene(sym, yon, adx, atr)
                if acildi:
                    break
        except Exception as e:
            log.error(f"[SCANNER] {e}")

# ════════════════════════════════════════════
# GÜNLÜK SIFIRLAMA
# ════════════════════════════════════════════
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with daily_pnl_lock:
                eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gün! (simüle) Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ════════════════════════════════════════════
# PANEL (HTML) — botun kendi işlem geçmişinden üretilir
# ════════════════════════════════════════════
def panel_html():
    with trade_log_lock:
        kayitlar = list(trade_log)

    n = len(kayitlar)
    kazananlar = [t for t in kayitlar if t["net"] > 0]
    kaybedenler = [t for t in kayitlar if t["net"] <= 0]
    net_toplam = sum(t["net"] for t in kayitlar)
    avg_win = (sum(t["net"] for t in kazananlar) / len(kazananlar)) if kazananlar else 0.0
    avg_loss = (abs(sum(t["net"] for t in kaybedenler) / len(kaybedenler))) if kaybedenler else 0.0
    win_rate = (len(kazananlar) / n * 100) if n else 0.0
    breakeven = (avg_loss / (avg_win + avg_loss) * 100) if (avg_win + avg_loss) > 0 else 0.0

    kumulatif = []
    running = 0.0
    for t in kayitlar:
        running += t["net"]
        kumulatif.append(running)

    svg_polyline = ""
    if len(kumulatif) >= 2:
        vmin, vmax = min(kumulatif + [0]), max(kumulatif + [0])
        span = (vmax - vmin) or 1.0
        w, h = 600, 160
        pts = []
        for i, v in enumerate(kumulatif):
            x = (i / (len(kumulatif) - 1)) * w
            y = h - ((v - vmin) / span) * h
            pts.append(f"{x:.1f},{y:.1f}")
        svg_polyline = " ".join(pts)
        sifir_y = h - ((0 - vmin) / span) * h
    else:
        sifir_y = 80

    renk = "#00C6AE" if net_toplam >= 0 else "#FF5C77"
    be_renk = "#00C6AE" if win_rate > breakeven else "#FF5C77"

    satirlar = ""
    for t in reversed(kayitlar[-100:]):
        r = "#00C6AE" if t["net"] >= 0 else "#FF5C77"
        satirlar += f"""
        <div class="row">
          <div>
            <div class="sym">{t['sembol']} <span class="tag {t['yon']}">{t['yon']}</span></div>
            <div class="meta">{t['zaman']} · {t['sure']}dk · {t['kaynak']}</div>
          </div>
          <div class="pnl" style="color:{r}">{t['net']:+.2f}$</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sadık Scalp — Kağıt Mod Performans Paneli</title>
<style>
  body {{ background:#0B0E11; color:#E8ECEF; font-family:-apple-system,Segoe UI,sans-serif; margin:0; padding:20px 16px 60px; }}
  .mono {{ font-family: 'JetBrains Mono', monospace; }}
  .eyebrow {{ font-size:12px; letter-spacing:1.5px; color:#6B7684; text-transform:uppercase; font-weight:600; }}
  h1 {{ margin:2px 0 18px; font-size:22px; }}
  .badge {{ display:inline-block; background:#FFB02E1A; color:#FFB02E; font-size:11px; font-weight:700;
            padding:3px 8px; border-radius:6px; margin-bottom:10px; letter-spacing:.5px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }}
  .card {{ background:#12161C; border:1px solid #1E242C; border-radius:10px; padding:14px; }}
  .label {{ font-size:11px; color:#6B7684; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }}
  .big {{ font-size:26px; font-weight:700; }}
  .row {{ display:flex; justify-content:space-between; align-items:center; background:#12161C; border:1px solid #1E242C; border-radius:10px; padding:10px 12px; margin-bottom:6px; }}
  .sym {{ font-weight:600; font-size:13.5px; }}
  .meta {{ font-size:11px; color:#5B6572; margin-top:2px; }}
  .pnl {{ font-weight:700; font-size:14px; font-family:monospace; }}
  .tag {{ font-size:10px; padding:1px 6px; border-radius:4px; text-transform:uppercase; font-weight:600; margin-left:4px; }}
  .tag.long {{ background:#00C6AE1A; color:#00C6AE; }}
  .tag.short {{ background:#FF5C771A; color:#FF5C77; }}
  .sectionlabel {{ font-size:11.5px; color:#6B7684; text-transform:uppercase; letter-spacing:.5px; margin:16px 2px 8px; }}
</style></head>
<body>
  <div class="eyebrow">Sadık Scalp</div>
  <h1>Performans Paneli</h1>
  <div class="badge">📝 KAĞIT MOD — gerçek para kullanılmıyor</div>
  <div style="font-size:12px;color:#4A5361;margin-bottom:18px">{n} işlem (simüle) · sayfa her yenilendiğinde güncellenir</div>

  <div class="grid2">
    <div class="card"><div class="label">Net Toplam</div><div class="big mono" style="color:{renk}">{net_toplam:+.2f}$</div></div>
    <div class="card"><div class="label">Kazanma Oranı</div><div class="big mono">%{win_rate:.1f}</div></div>
  </div>
  <div class="grid2">
    <div class="card"><div class="label">Kazanan ({len(kazananlar)})</div><div class="mono" style="font-size:17px;font-weight:600;color:#00C6AE">ort +{avg_win:.2f}$</div></div>
    <div class="card"><div class="label">Kaybeden ({len(kaybedenler)})</div><div class="mono" style="font-size:17px;font-weight:600;color:#FF5C77">ort -{avg_loss:.2f}$</div></div>
  </div>
  <div class="card" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
    <span style="font-size:11.5px;color:#8B95A1">Başa baş için gereken kazanma oranı</span>
    <span class="mono" style="font-size:15px;font-weight:700;color:{be_renk}">%{breakeven:.1f}</span>
  </div>

  <div class="card" style="padding:16px 8px 8px;margin-bottom:16px">
    <div style="font-size:11.5px;color:#8B95A1;text-transform:uppercase;letter-spacing:.5px;padding:0 8px 10px">Kümülatif Net PnL (simüle)</div>
    <svg viewBox="0 0 600 160" width="100%" height="160" preserveAspectRatio="none">
      <line x1="0" y1="{sifir_y:.1f}" x2="600" y2="{sifir_y:.1f}" stroke="#2A323C" stroke-width="1"/>
      <polyline points="{svg_polyline}" fill="none" stroke="#1E90FF" stroke-width="2.5"/>
    </svg>
  </div>

  <div class="sectionlabel">İşlem Geçmişi (yeniden eskiye, son 100)</div>
  {satirlar if satirlar else '<div style="text-align:center;color:#4A5361;font-size:13px;padding:30px 0">Henüz kapanan işlem yok</div>'}
</body></html>"""

# ════════════════════════════════════════════
# HEALTH SERVER + PANEL
# ════════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/panel"):
                try:
                    html = panel_html()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                except Exception as e:
                    self.send_response(500); self.end_headers()
                    self.wfile.write(f"Panel hatası: {e}".encode())
                return
            self.send_response(200); self.end_headers()
            with pos_lock: ps = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock: pnl = daily_pnl
            self.wfile.write(f"OK|PAPER|pos:{len(positions)}({ps})|pnl:{pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════════
# TELEGRAM HANDLER (manuel komutlar — hepsi simüle)
# ════════════════════════════════════════════
def find_coin(text):
    words = re.findall(r"\b[A-Z]{2,10}\b", text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for w in words:
            sym = f"{w}/USDT:USDT"
            if sym in tickers: return sym
    except: pass
    return None

def manuel_giris(symbol, side, kaynak="manuel"):
    adx, atr = piyasa_verisi_al(symbol, ADX_PERIOD)
    if atr is None:
        return False, "Piyasa verisi alınamadı"
    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False, "Fiyat alınamadı"
    price = float(t["last"])

    risk_mesafe = ATR_SL_MULT * atr
    sl = price - risk_mesafe if side == "long" else price + risk_mesafe
    amount, pos_size, r_dollar = pozisyon_boyutu_hesapla(risk_mesafe, price)
    if amount is None:
        return False, "Risk mesafesi hesaplanamadı"
    tp_levels = [round(r_dollar * k, 4) for k in R_KADEMELERI]

    if not pozisyon_slot_al(symbol, price, sl, kaynak, side, tp_levels, r_dollar, amount):
        return False, "Slot alınamadı (zaten açık / limit dolu)"

    sym = symbol.split("/")[0]
    yon_metni = "LONG" if side == "long" else "SHORT"
    tg(
        f"⚡ #{sym}USDT.P {yon_metni} [KAĞIT/MANUEL]\n"
        f"🏁 Giriş: {price:.8f}\n"
        f"🚫 SL: {sl:.8f} (ATR bazlı)\n"
        f"🎯 TP (R bazlı): " + " / ".join(f"${x:.2f}" for x in tp_levels) + f" | R=${r_dollar:.2f}\n"
        f"💰 Pozisyon: ${pos_size:.2f} (SİMÜLE, risk bazlı boyutlandırıldı)"
    )
    return True, "OK"

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text = msg.text.strip()
    lower = text.lower()

    if "short ac" in lower or "short aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı."); return
        bot.send_message(msg.chat.id, f"📉 {coin.split('/')[0]} SHORT deneniyor (kağıt)...")
        threading.Thread(target=manuel_giris, args=(coin, "short"), daemon=True).start()
        return

    if "long ac" in lower or "long aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı."); return
        bot.send_message(msg.chat.id, f"⚡ {coin.split('/')[0]} LONG deneniyor (kağıt)...")
        threading.Thread(target=manuel_giris, args=(coin, "long"), daemon=True).start()
        return

    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok (kağıt mod)."); return
            lines = ["📋 POZİSYONLAR (KAĞIT)\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = float(t["last"])
                net, pct = net_pnl_hesapla(pos, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                durum_str = (f"{pos.get('last_tp_idx',0)+1}R garantili 🎯" if pos.get("tetiklendi") else f"SL:{pos['sl']:.8f}")
                lines.append(
                    f"{'🟢' if net>=0 else '🔴'} {sym.split('/')[0]} [{pos.get('side','long').upper()}/{pos.get('kaynak','?')}]\n"
                    f"   {pos['entry']:.8f}→{price:.8f}\n"
                    f"   Net:{net:+.2f}$ ({pct:+.2f}%) | {sure}dk | {durum_str}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Açık pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            if symbol.split("/")[0].upper() in text.upper() or "hepsi" in lower:
                threading.Thread(target=close_pos, args=(symbol, "Kullanıcı isteği"), daemon=True).start()
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    bot.send_message(msg.chat.id,
        "📝 KAĞIT MOD — gerçek para kullanılmıyor\n\n"
        "Komutlar:\n/durum — Açık pozisyonlar\n"
        "COIN long aç — Manuel LONG (simüle)\nCOIN short aç — Manuel SHORT (simüle)\n"
        "COIN kapat / hepsi kapat\n\nPanel: /panel yolunu tarayıcıda aç")

# ════════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms: tg(f"⏸ Yeniden başlıyor... (kağıt) {len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK SCALP — KAĞIT (PAPER) MOD BAŞLIYOR...")
    trade_log_yukle()
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    tg(
        "📝 SADIK SCALP — KAĞIT (PAPER) MOD\n"
        "🔖 Versiyon: v9 (kalıcı işlem geçmişi/Volume AKTİF | soluklanma bekleme hazır ama KAPALI — v8 verisi bozulmasın diye)\n\n"
        "🧠 Strateji: ADX ile trend teyidi olmadan işlem AÇILMAZ (fade kaldırıldı).\n"
        f"   ADX ≥ {ADX_ESIK} → hareketin YÖNÜNDE gir. ADX < {ADX_ESIK} → sinyal atlanır.\n\n"
        f"💰 Pozisyon: RİSK BAZLI boyutlandırma (hedef risk: ${HEDEF_RISK_DOLAR:.2f} = marjinin %{int(RISK_PER_TRADE_PCT*100)}'si, {MIN_POS_SIZE:.0f}$-{MAX_POS_SIZE:.0f}$ arası)\n"
        f"🚫 SL: {ATR_SL_MULT}×ATR (coinin kendi oynaklığına göre otomatik)\n"
        f"🎯 TP: 1R/2R/3R/4R kademeli + %{int(TRAIL_GIVEBACK_PCT*100)} yüzdesel trailing\n"
        f"⏱️ Zaman stopu: {ZAMAN_STOPU_DK}dk'da 1R'a ulaşmayan zarardaki işlem erken kapanır\n\n"
        "Komutlar:\n/durum\nCOIN long aç | COIN short aç | COIN kapat\n"
        "Panel: (public domain)/panel"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
