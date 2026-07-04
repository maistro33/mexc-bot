#!/usr/bin/env python3
"""
SADIK SCALP FAST — FADE TEST SÜRÜMÜ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strateji: Gir → Kâr Al → Çık (hızlı scalp), aynı sinyal kaynakları korunuyor:
  1. CoinSonar V2 — Telegram kanalı (Telethon)
  2. FuturesKripto — Telegram kanalı (Telethon)
  3. Manuel — Sen bota yazarsın
  4. Bağımsız tarayıcı — ani pump/dump tespiti (BU SÜRÜMDE: FADE / TERS MANTIK)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEĞİŞİKLİK NOTLARI (bu sürümde neler farklı):
  1) Pozisyon küçültüldü: Margin 15$→10$ | Kaldıraç 5x (aynı) | Pozisyon 75$→50$
  2) TP/SL dolar hedefleri yeni pozisyon büyüklüğüne ORANTILI küçültüldü
     (risk/ödül oranı eskisiyle birebir aynı kaldı, sadece mutlak tutar küçüldü):
       Eski: SL≈-$1.59 | TP: 0.80/1.60/2.40/3.20 | Trail geri: 0.40
       Yeni: SL≈-$1.06 | TP: 0.53/1.07/1.60/2.13 | Trail geri: 0.27
  3) Günlük zarar limiti -15$ → -10$ (aynı orana çekildi)
  4) SADECE SCANNER (bağımsız tarayıcı) kaynağı için yön mantığı TERSİNE çevrildi:
       - Eskiden: "pump" tespit + pullback onayı → LONG (trend takibi)
       - Yeni:    "pump" tespit + pullback onayı → SHORT (fade/ters)
       - Eskiden: "dump" tespit + bounce onayı   → SHORT (trend takibi)
       - Yeni:    "dump" tespit + bounce onayı   → LONG (fade/ters)
     RSI ve "uzama filtresi" (UZAMA_LIMIT_PCT) bilinçli olarak DOKUNULMADAN
     bırakıldı — böylece tek değişkeni (yön) test edip fade hipotezinin
     gerçekten işe yarayıp yaramadığını net görebiliriz. Bu filtreler hâlâ
     eski (trend-takip) mantığıyla çalıştığı için ileride ayrıca gözden
     geçirilmesi gerekebilir (örn. RSI>75'te pump'ı ELEMEK yerine fade için
     bir AVANTAJ sayılabilir — bu değişiklik bilinçli olarak YAPILMADI).
  5) CoinSonar / FuturesKripto / Manuel komutlar (long aç / short aç) HİÇBİR
     ŞEKİLDE değiştirilmedi — sadece scanner'ın otomatik yönü değişti.
  6) [GÜNCELLEME] Pullback onay eşiği %0.15 → %0.35 büyütüldü. İlk canlı
     testte (EPICUSDT, 2dk'da SL) çok küçük bir geri çekilmenin gerçek bir
     dönüş sinyali olmadan da tetiklendiği görüldü — eşik büyütülerek
     gürültüden kaynaklı erken girişler azaltılmaya çalışılıyor.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pozisyon:
  Margin: 10$ | Kaldıraç: 5x | Pozisyon büyüklüğü: 50$

Çıkış mantığı (TEK TP + TEK SL + KÂR FLOORU İLE TRAILING):
  - SL: -%2.0 (net kayıp ≈ -$1.06, komisyonlar dahil)
  - Net kâr $0.53'e ulaşılınca pozisyon KAPANMAZ — trailing moduna geçer.
    Fiyat lehte gitmeye devam ettiği sürece pozisyon açık kalır.
    Fiyat geri dönüp net kârı tekrar $0.53 seviyesine indirirse,
    o anda LİMİT emirle kapatılıp $0.53 net kâr kasaya konur.
  - Trigger'a ulaşılmadan SL'e çarparsa normal SL ile kapanır.

Emir tipi:
  - GİRİŞ: sadece LİMİT emir (birkaç deneme, fiyat güncellenerek)
  - ÇIKIŞ: sadece LİMİT emir (SL/floor tetiklenince agresif fiyatlanan
    limit emirlerle hızlı doldurulur — market emir KULLANILMAZ)
"""

import os, time, threading, logging, re, asyncio
import ccxt
import pandas as pd
import telebot
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_FAST")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN    = os.getenv("TELE_TOKEN", "")
CHAT_ID       = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API    = os.getenv("BITGET_API", "")
BITGET_SEC    = os.getenv("BITGET_SEC", "")
BITGET_PASS   = os.getenv("BITGET_PASS", "")
SUPA_URL      = os.getenv("SUPABASE_URL", "")
SUPA_KEY      = os.getenv("SUPABASE_KEY", "")
TG_API_ID     = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH   = os.getenv("TG_API_HASH", "")
TG_SESSION    = os.getenv("TG_SESSION", "")

COINSONAR_KANAL     = "CoinSonarV2"
FUTURESKRIPTO_KANAL = "FuturesKripto"

# ── Sinyal kaynağı anahtarları ──
# False yaparsan o kanaldan gelen sinyaller görmezden gelinir, hiç işlem açılmaz.
# Sadece kendi tarayıcın (scanner) ve manuel komutların çalışır.
COINSONAR_AKTIF     = False
FUTURESKRIPTO_AKTIF = False

# ── Pozisyon (KÜÇÜK TEST BOYUTU) ──
MARGIN          = 10.0
LEVERAGE        = 5
POS_SIZE        = MARGIN * LEVERAGE     # 50$
COMMISSION      = 0.0006                # taker, tek yön
ROUNDTRIP_FEE   = POS_SIZE * COMMISSION * 2   # ≈ 0.06$ (giriş+çıkış)

MAX_OPEN_AUTO   = 2
MAX_OPEN_MANUEL = 3
MAX_DAILY_LOSS  = -10.0
MAX_SURE        = 240    # dk — süre dolunca limitle kapat

# ── Çıkış parametreleri ──
SL_PCT        = 2.00     # sabit -%2.0 SL (tüm kaynaklarda aynı)
# ── 4 kademeli TP (dolar bazlı, ana para hiç çekilmez — sadece floor/stop güncellenir) ──
# Yeni pozisyon büyüklüğüne (50$) orantılı küçültüldü — risk/ödül oranı eskisiyle aynı.
TP_LEVELS_NET   = [0.53, 1.07, 1.60, 2.13]   # $ net kâr seviyeleri
TRAIL_BACK_NET  = 0.27                        # zirveden bu kadar $ geri çekilirse kapat

RECENTLY_TTL  = 1800     # coin kapandıktan sonra 30dk tekrar açılmasın

# ── Limit emir parametreleri (SADECE LİMİT — market emir yok) ──
GIRIS_DENEME       = 5     # limit giriş: kaç kez fiyat güncellenip denenir
GIRIS_BEKLE_SN     = 3     # her denemede bekleme süresi
GIRIS_OFFSET_PCT   = 0.05  # ilk giriş limiti mid'den ne kadar içeride denensin
MAX_KOVALAMA_PCT   = 1.0   # fiyat sinyal seviyesinden bu kadar uzaklaşırsa kovalama bırakılır

KAPAT_DENEME       = 8     # limit kapatma: kaç kez agresifleştirilerek denenir
KAPAT_BEKLE_SN     = 1     # her denemede bekleme süresi (hızlı tepki için kısaltıldı)
KAPAT_ILK_AGRESIFLIK = 0.45  # İLK denemeden itibaren spread'i ciddi geçen fiyat (neredeyse market hızı)
KAPAT_ADIM_PCT     = 0.18  # her başarısız sonraki denemede fiyat bu kadar daha agresifleşir

# ── 15m Filtre (CoinSonar için) ──
RSI_MIN = 30
RSI_MAX = 55
MIN_PRICE    = 0.0001
MAX_PRICE    = 100.0
MIN_TURNOVER = 200_000

# ── Bağımsız tarayıcı (pump/dump) — FADE (TERS) MANTIK ──
SCAN_INTERVAL     = 30
SCAN_MAX_ADAY     = 20
ANI_VOL_SPIKE_MIN = 2.0
ANI_PCT_MIN       = 1.5
UZAMA_LIMIT_PCT   = 8.0   # coin son ~1 saatte bu yüzdenin üzerinde hareket ettiyse sinyal elenir
                          # (NOT: bu filtre hâlâ ESKİ trend-takip mantığıyla çalışıyor,
                          #  fade için tersine çevrilmesi ayrı bir test konusu — bilinçli
                          #  olarak bu sürümde DOKUNULMADI, sadece yön değişti)

# ════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()

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
# SUPABASE
# ════════════════════════════════════════════
supa = None  # Supabase tamamen kapatıldı — kayıt/istatistik özelliği kullanılmıyor

def save_trade(data):
    if not supa: return
    try:
        supa.table("gpt_trades").insert(data).execute()
    except Exception as e:
        log.error(f"[SAVE] {e}")

# ════════════════════════════════════════════
# EXCHANGE
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
def günlük_limit_asıldı():
    with daily_pnl_lock:
        return daily_pnl <= MAX_DAILY_LOSS

def pnl_ekle(miktar):
    global daily_pnl
    with daily_pnl_lock:
        daily_pnl += miktar
        return daily_pnl

def net_pnl_hesapla(pos, price):
    """Round-trip komisyon dahil NET pnl döner (giriş+çıkış masrafı düşülmüş)."""
    entry  = pos["entry"]
    amount = pos["amount"]
    side   = pos.get("side", "long")
    if side == "short":
        gross = (entry - price) * amount
    else:
        gross = (price - entry) * amount
    net = gross - ROUNDTRIP_FEE
    pct = (gross / (entry * amount)) * 100 if entry and amount else 0.0
    return net, pct

def fiyat_for_net(entry, amount, side, net_hedef):
    """Verilen net $ kâr/zarar hedefine denk gelen fiyatı hesaplar."""
    gross_hedef = net_hedef + ROUNDTRIP_FEE
    if side == "short":
        return entry - gross_hedef / amount
    return entry + gross_hedef / amount

# ════════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════════
def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def filtre_15m(symbol):
    try:
        r = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=25)
        if not r or len(r) < 20:
            return False, {"red": "Veri yetersiz"}
        df = pd.DataFrame(r, columns=["t","o","h","l","c","v"])
        ma5  = float(df["c"].rolling(5).mean().iloc[-1])
        ma10 = float(df["c"].rolling(10).mean().iloc[-1])
        ma20 = float(df["c"].rolling(20).mean().iloc[-1])
        vol_ma5  = float(df["v"].rolling(5).mean().iloc[-1])
        vol_ma10 = float(df["v"].rolling(10).mean().iloc[-1])
        rsi = calc_rsi(df["c"])
        ma_ok  = ma5 > ma10 > ma20
        vol_ok = vol_ma5 > vol_ma10
        rsi_ok = RSI_MIN <= rsi <= RSI_MAX
        gecti = ma_ok and vol_ok and rsi_ok
        detay = {"ma5": round(ma5,8), "ma10": round(ma10,8), "ma20": round(ma20,8),
                  "vol_ma5": round(vol_ma5,0), "vol_ma10": round(vol_ma10,0),
                  "rsi": round(rsi,1), "ma_ok": ma_ok, "vol_ok": vol_ok, "rsi_ok": rsi_ok}
        return gecti, detay
    except Exception as e:
        log.warning(f"[FİLTRE] {symbol}: {e}")
        return False, {"red": str(e)}

# ════════════════════════════════════════════
# BORSA YARDIMCILARI
# ════════════════════════════════════════════
def borsa_hazirla(symbol):
    try: exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
    except: pass
    try: exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
    except: pass

def _pozisyon_var_mi(symbol, side):
    """Geriye uyumluluk için: pozisyon varsa entry price, yoksa/hata varsa None döner."""
    basarili, acik, entry = _pozisyon_kontrol(symbol, side)
    return entry if (basarili and acik) else None

def _pozisyon_kontrol(symbol, side):
    """
    Borsadan KESİN doğrulama yapar. Dönüş: (basarili, acik_mi, entry_price)
    """
    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list is None:
            return False, None, None
        for p in pos_list:
            if float(p.get("contracts") or 0) > 0 and p.get("side") == side:
                return True, True, float(p.get("entryPrice") or 0)
        return True, False, None
    except Exception as e:
        log.warning(f"[POS_CHECK] {symbol}: {e}")
        return False, None, None

def limit_giris(symbol, side, amount, ilk_fiyat):
    """SADECE LİMİT emirle giriş. GIRIS_DENEME kez, her seferinde güncel fiyata
    göre limiti yeniden konumlandırır. Doldurulamazsa None döner (market YOK)."""
    yon = "buy" if side == "long" else "sell"
    fiyat = ilk_fiyat
    order_id = None
    fiyat_p = None
    sinyal_fiyat = ilk_fiyat

    for deneme in range(GIRIS_DENEME):
        if order_id is None:
            try:
                fiyat_p = float(exchange.price_to_precision(symbol, fiyat))
                order = safe_api(
                    exchange.create_order, symbol, "limit", yon, amount, fiyat_p,
                    {"marginMode": "isolated", "marginCoin": "USDT", "timeInForce": "GTC"}
                )
            except Exception as e:
                log.warning(f"[GİRİŞ_LİMİT] {symbol}: {e}")
                order = None
            if not order:
                time.sleep(1)
                continue
            order_id = order.get("id")

        kesin_dolmadi = False
        for _ in range(GIRIS_BEKLE_SN):
            time.sleep(1)
            durum = safe_api(exchange.fetch_order, order_id, symbol)
            if durum and durum.get("status") == "closed":
                avg = durum.get("average") or fiyat_p
                return float(avg)
            basarili, acik, entry = _pozisyon_kontrol(symbol, side)
            if basarili and acik:
                return entry
            if basarili and not acik:
                kesin_dolmadi = True
                break

        if not kesin_dolmadi:
            basarili, acik, entry = _pozisyon_kontrol(symbol, side)
            if basarili and acik:
                return entry
            if not basarili:
                log.warning(f"[GİRİŞ] {symbol} durum doğrulanamadı, emir korunuyor, tekrar kontrol edilecek")
                time.sleep(2)
                continue

        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass
        order_id = None

        t = safe_api(exchange.fetch_ticker, symbol)
        if not t: continue
        guncel = float(t["last"])

        sapma_pct = abs(guncel - sinyal_fiyat) / sinyal_fiyat * 100
        if sapma_pct >= MAX_KOVALAMA_PCT:
            log.warning(f"[GİRİŞ] {symbol} fiyat sinyalden %{sapma_pct:.2f} uzaklaştı, kovalama bırakılıyor")
            return None

        if side == "long":
            fiyat = round(guncel * (1 - GIRIS_OFFSET_PCT / 100), 8)
        else:
            fiyat = round(guncel * (1 + GIRIS_OFFSET_PCT / 100), 8)

    basarili, acik, entry = _pozisyon_kontrol(symbol, side)
    if basarili and acik:
        return entry

    if order_id is not None:
        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass

    return None

def limit_kapat(symbol, side, amount, reason=""):
    """SADECE LİMİT emirle kapama."""
    kapat_yonu = "sell" if side == "long" else "buy"
    kalan_miktar = amount

    for deneme in range(KAPAT_DENEME):
        basarili, acik, _ = _pozisyon_kontrol(symbol, side)
        if basarili and not acik:
            return None
        if basarili and acik:
            try:
                pos_list = safe_api(exchange.fetch_positions, [symbol])
                if pos_list:
                    for p in pos_list:
                        c = float(p.get("contracts") or 0)
                        if c > 0 and p.get("side") == side:
                            kalan_miktar = c
                            break
            except: pass

        t = safe_api(exchange.fetch_ticker, symbol)
        if not t:
            time.sleep(1); continue
        piyasa = float(t["last"])

        agresiflik = KAPAT_ILK_AGRESIFLIK + (KAPAT_ADIM_PCT * deneme)
        if kapat_yonu == "sell":
            limit_fiyat = round(piyasa * (1 - agresiflik / 100), 8)
        else:
            limit_fiyat = round(piyasa * (1 + agresiflik / 100), 8)

        try:
            order = safe_api(
                exchange.create_order, symbol, "limit", kapat_yonu, kalan_miktar, limit_fiyat,
                {"reduceOnly": True, "marginCoin": "USDT", "timeInForce": "GTC"}
            )
        except Exception as e:
            order = None
            if "22002" not in str(e) and "No position" not in str(e) and "40804" not in str(e):
                log.warning(f"[KAPAT_LİMİT] {symbol}: {e}")

        if not order:
            time.sleep(1); continue

        order_id = order.get("id")
        for _ in range(KAPAT_BEKLE_SN):
            time.sleep(1)
            durum = safe_api(exchange.fetch_order, order_id, symbol)
            if durum and durum.get("status") == "closed":
                avg = durum.get("average") or durum.get("price") or limit_fiyat
                return float(avg)
            gercek = _pozisyon_var_mi(symbol, side)
            if not gercek:
                return limit_fiyat

        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass

    basarili, acik, _ = _pozisyon_kontrol(symbol, side)
    if basarili and acik:
        try:
            pos_list = safe_api(exchange.fetch_positions, [symbol])
            if pos_list:
                for p in pos_list:
                    c = float(p.get("contracts") or 0)
                    if c > 0 and p.get("side") == side:
                        kalan_miktar = c
                        break
        except: pass
    t = safe_api(exchange.fetch_ticker, symbol)
    if t:
        piyasa = float(t["last"])
        son_agresiflik = KAPAT_ADIM_PCT * (KAPAT_DENEME + 3)
        if kapat_yonu == "sell":
            son_fiyat = round(piyasa * (1 - son_agresiflik / 100), 8)
        else:
            son_fiyat = round(piyasa * (1 + son_agresiflik / 100), 8)
        try:
            safe_api(exchange.create_order, symbol, "limit", kapat_yonu, kalan_miktar, son_fiyat,
                     {"reduceOnly": True, "marginCoin": "USDT", "timeInForce": "GTC"})
            time.sleep(2)
        except: pass
        if not _pozisyon_var_mi(symbol, side):
            return son_fiyat
    return None

# ════════════════════════════════════════════
# SLOT
# ════════════════════════════════════════════
def pozisyon_slot_al(symbol, entry, sl, kaynak, mod="auto", side="long"):
    sym_base = symbol.split("/")[0].upper()
    max_open = MAX_OPEN_AUTO if mod == "auto" else MAX_OPEN_MANUEL

    with pos_lock:
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < RECENTLY_TTL:
                    return False
        if len(positions) >= max_open: return False
        if günlük_limit_asıldı(): return False

        positions[symbol] = {
            "entry": entry, "sl": sl,
            "tetiklendi": False, "last_tp_idx": -1, "peak_net": 0.0,
            "max_price": entry, "min_price": entry,
            "open_time": time.time(), "amount": 0,
            "kaynak": kaynak, "mod": mod, "side": side, "pending": True,
        }
        return True

# ════════════════════════════════════════════
# İŞLEM AÇ — LONG (CoinSonar / Manuel / Tarayıcı-fade)
# ════════════════════════════════════════════
def open_pos_auto(symbol, kaynak="coinsonar"):
    sym = symbol.split("/")[0]
    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False, "Fiyat alınamadı"
    price = float(t0["last"])
    sl = round(price * (1 - SL_PCT / 100), 8)

    if not pozisyon_slot_al(symbol, price, sl, kaynak, "auto" if kaynak != "manuel" else "manuel", "long"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / price, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📡 {sym} [{kaynak}] LİMİT giriş deneniyor @ ~{price:.8f}")
            giris_fiyat = round(price * (1 - GIRIS_OFFSET_PCT / 100), 8)
            gercek = limit_giris(symbol, "long", amount, giris_fiyat)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, işlem iptal.")
                return

            sl_g = round(gercek * (1 - SL_PCT / 100), 8)
            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({"entry": gercek, "sl": sl_g, "amount": amount, "pending": False})

            tg(
                f"⚡ #{sym}USDT.P LONG\n"
                f"📡 Kaynak: {kaynak.upper()}\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (-%{SL_PCT})\n"
                f"🎯 TP seviyeleri: " + " / ".join(f"${x:.2f}" for x in TP_LEVELS_NET) + f" | ${TRAIL_BACK_NET:.2f} geri çekilince kilitlenir\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK] {sym} @ {gercek:.8f} [{kaynak}]")
        except Exception as e:
            log.error(f"[OPEN_AUTO] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM AÇ — SHORT (Manuel / Tarayıcı-fade)
# ════════════════════════════════════════════
def open_pos_short_manuel(symbol, kaynak="manuel"):
    sym = symbol.split("/")[0]
    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False, "Fiyat alınamadı"
    price = float(t0["last"])
    sl = round(price * (1 + SL_PCT / 100), 8)

    if not pozisyon_slot_al(symbol, price, sl, kaynak, "manuel", "short"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / price, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📉 {sym} [{kaynak}] LİMİT short giriş deneniyor @ ~{price:.8f}")
            giris_fiyat = round(price * (1 + GIRIS_OFFSET_PCT / 100), 8)
            gercek = limit_giris(symbol, "short", amount, giris_fiyat)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, işlem iptal.")
                return

            sl_g = round(gercek * (1 + SL_PCT / 100), 8)
            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({"entry": gercek, "sl": sl_g, "amount": amount,
                                               "min_price": gercek, "pending": False})

            tg(
                f"🔻 #{sym}USDT.P SHORT\n"
                f"📡 Kaynak: {kaynak.upper()}\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (+%{SL_PCT})\n"
                f"🎯 TP seviyeleri: " + " / ".join(f"${x:.2f}" for x in TP_LEVELS_NET) + f" | ${TRAIL_BACK_NET:.2f} geri çekilince kilitlenir\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK-SHORT] {sym} @ {gercek:.8f}")
        except Exception as e:
            log.error(f"[OPEN_SHORT] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM AÇ — FuturesKripto
# ════════════════════════════════════════════
def open_pos_futureskripto(symbol, giris_sinyal):
    sym = symbol.split("/")[0]
    sl = round(giris_sinyal * (1 - SL_PCT / 100), 8)

    if not pozisyon_slot_al(symbol, giris_sinyal, sl, "futureskripto", "manuel", "long"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / giris_sinyal, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📡 {sym} [FuturesKripto] LİMİT giriş deneniyor @ {giris_sinyal:.8f}")
            gercek = limit_giris(symbol, "long", amount, giris_sinyal)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, işlem iptal.")
                return

            sl_g = round(gercek * (1 - SL_PCT / 100), 8)
            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({"entry": gercek, "sl": sl_g, "amount": amount, "pending": False})

            tg(
                f"✅ #{sym}USDT.P LONG\n"
                f"📡 Kaynak: FUTURESKRIPTO\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (-%{SL_PCT})\n"
                f"🎯 TP seviyeleri: " + " / ".join(f"${x:.2f}" for x in TP_LEVELS_NET) + f" | ${TRAIL_BACK_NET:.2f} geri çekilince kilitlenir\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK] {sym} @ {gercek:.8f} [futureskripto]")
        except Exception as e:
            log.error(f"[FK_OPEN] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM KAPAT
# ════════════════════════════════════════════
def close_pos(symbol, reason):
    with pos_lock:
        pos = positions.get(symbol)
    if not pos: return

    sym    = symbol.split("/")[0]
    side   = pos.get("side", "long")
    amount = pos.get("amount", 0)
    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                c = float(p.get("contracts") or 0)
                if c > 0 and p.get("side") == side:
                    amount = c; break
    except: pass

    exit_price = limit_kapat(symbol, side, amount, reason)

    basarili, acik, _ = _pozisyon_kontrol(symbol, side)

    if not basarili:
        deneme = pos.get("kapanma_deneme", 0) + 1
        with pos_lock:
            if symbol in positions:
                positions[symbol]["kapanma_deneme"] = deneme
        if deneme == 1 or deneme % 5 == 0:
            tg(f"⚠️ {sym} kapatma durumu DOĞRULANAMADI (API hatası) — pozisyon takipte kalıyor, tekrar denenecek (deneme {deneme})")
        return

    if acik:
        deneme = pos.get("kapanma_deneme", 0) + 1
        with pos_lock:
            if symbol in positions:
                positions[symbol]["kapanma_deneme"] = deneme
        if deneme == 1 or deneme % 5 == 0:
            tg(f"⚠️ {sym} hâlâ açık, kapatma tekrar denenecek (deneme {deneme})")
        return

    with pos_lock:
        positions.pop(symbol, None)

    if not exit_price:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = float(t["last"]) if t else pos["entry"]

    net, pct = net_pnl_hesapla({**pos, "amount": amount}, exit_price)
    sure   = int((time.time() - pos["open_time"]) / 60)
    toplam = pnl_ekle(net)
    kaynak = pos.get("kaynak", "?")

    sym_base = sym.upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    if toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {toplam:+.2f}$")

    icon = "🟢" if net >= 0 else "🔴"
    tg(
        f"{icon} {sym.upper()} KAPANDI\n"
        f"{reason}\n"
        f"Net PnL: {net:+.2f}$ ({pct:+.2f}%) | {sure}dk\n"
        f"📡 {kaynak.upper()} | Günlük: {toplam:+.2f}$"
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
                if not pos or pos.get("pending"): continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = float(t["last"])

                entry  = pos["entry"]
                amount = pos.get("amount") or (POS_SIZE / entry)
                side   = pos.get("side", "long")
                sl     = pos["sl"]
                sym    = symbol.split("/")[0]

                net, pct = net_pnl_hesapla({**pos, "amount": amount}, price)
                sure = int((time.time() - pos["open_time"]) / 60)

                if not pos.get("tetiklendi"):
                    sl_tetiklendi = (price <= sl) if side == "long" else (price >= sl)
                    if sl_tetiklendi:
                        close_pos(symbol, f"🚫 SL ({sl:.8f})")
                        continue

                    if net >= TP_LEVELS_NET[0]:
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tetiklendi"] = True
                                positions[symbol]["last_tp_idx"] = 0
                                positions[symbol]["peak_net"] = net
                        tg(
                            f"🎯 {sym} TP1 (${TP_LEVELS_NET[0]:.2f}) net kâra ulaştı\n"
                            f"Garanti: ${TP_LEVELS_NET[0]:.2f} | Zirveden ${TRAIL_BACK_NET:.2f} geri çekilirse kapanır"
                        )
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
                        while yeni_idx + 1 < len(TP_LEVELS_NET) and peak_net >= TP_LEVELS_NET[yeni_idx + 1]:
                            yeni_idx += 1
                        if yeni_idx > last_tp_idx:
                            with pos_lock:
                                if symbol in positions:
                                    positions[symbol]["last_tp_idx"] = yeni_idx
                            last_tp_idx = yeni_idx
                            tg(f"🎯 {sym} TP{yeni_idx+1} (${TP_LEVELS_NET[yeni_idx]:.2f}) net kâra ulaştı — garanti yükseldi")

                    floor_net = TP_LEVELS_NET[last_tp_idx]

                    if (peak_net - net) >= TRAIL_BACK_NET or net <= floor_net - 0.01:
                        close_pos(symbol, f"🎯 TP{last_tp_idx+1} garantisi kilitlendi (zirve ${peak_net:.2f} → ${net:.2f})")
                        continue

                if sure >= MAX_SURE:
                    close_pos(symbol, f"⏰ Süre doldu ({MAX_SURE}dk)")
                    continue

                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit")
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════════
# SİNYAL PARSE
# ════════════════════════════════════════════
def sinyal_parse(text):
    text_up = text.upper()
    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match: match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match: match = re.search(r'\b([A-Z]{2,10})USDT\b', text_up)
    if not match: return None
    coin_adi = match.group(1)

    giris = None
    for pattern in [r'Giri[şs]\s*Fiyat[ıi]\s*[:\s]+([0-9.]+)', r'LONG\s*\|\s*([0-9.]+)', r'Price[:\s]+([0-9.]+)']:
        m = re.search(pattern, text, re.IGNORECASE)
        if m: giris = float(m.group(1)); break

    return coin_adi, giris

# ════════════════════════════════════════════
# BAĞIMSIZ TARAYICI — ani pump/dump (FADE / TERS MANTIK)
# ════════════════════════════════════════════
def ani_hareket_tespit(symbol):
    """
    "pump"/"dump" etiketleri hâlâ ham piyasa hareketinin yönünü tanımlıyor.
    FADE kararı scanner_loop içinde veriliyor — bu fonksiyon değişmedi.
    """
    try:
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=25)
        if not r1m or len(r1m) < 15: return None, {}
        df = pd.DataFrame(r1m, columns=["t","o","h","l","c","v"])
        price = float(df["c"].iloc[-1])
        son_hacim = float(df["v"].iloc[-1])
        ort_hacim = float(df["v"].iloc[:-1].tail(20).mean())
        vol_oran  = son_hacim / max(ort_hacim, 0.0001)
        if vol_oran < ANI_VOL_SPIKE_MIN: return None, {"vol": round(vol_oran,1)}
        pct_3m = (price - float(df["c"].iloc[-4])) / float(df["c"].iloc[-4]) * 100

        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=20)
        if not r15m or len(r15m) < 15: return None, {}
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])
        rsi = calc_rsi(df15m["c"])

        fiyat_1s_once = float(df15m["c"].iloc[-5]) if len(df15m) >= 5 else float(df15m["c"].iloc[0])
        pct_1s = (price - fiyat_1s_once) / fiyat_1s_once * 100

        detay = {"vol": round(vol_oran,1), "pct": round(pct_3m,2), "price": price,
                  "rsi": round(rsi,1), "pct_1s": round(pct_1s,1)}

        # NOT: eşikler hâlâ ESKİ (trend-takip) mantığından kalma — bilinçli DOKUNULMADI.
        if pct_3m >= ANI_PCT_MIN:
            if rsi > 75: return None, detay
            if pct_1s >= UZAMA_LIMIT_PCT:
                return None, detay
            return "pump", detay
        elif pct_3m <= -ANI_PCT_MIN:
            if rsi > 50: return None, detay
            if pct_1s <= -UZAMA_LIMIT_PCT:
                return None, detay
            return "dump", detay
        return None, detay
    except Exception as e:
        log.warning(f"[ANİ] {symbol}: {e}")
        return None, {}

# ── Fitil/Ret mumu + hacim klimaksı tespiti (hızlı dönüş onayı) ──
WICK_BODY_ORANI = 1.5    # üst/alt fitil, gövdenin en az bu katı olmalı
MIN_WICK_PCT    = 0.15   # fitil, fiyatın en az bu yüzdesi kadar olmalı (gürültüyü ele)

def tepe_dip_reddi_var_mi(symbol, yon):
    """
    Son KAPANMIŞ 1m mumda fitil/ret + azalan hacim ile hızlı bir dönüş
    sinyali arar. Bulunursa giris_onayi_bekle'nin pullback beklemesine
    gerek kalmadan hemen giriş onayı verilir (hızlı yol). Bulunamazsa
    scanner_loop eski pullback bekleme yöntemine düşer (yedek yol).

    yon="pump" → tepe reddi arar (üst fitil + kırmızı mum → SHORT için hızlı onay)
    yon="dump" → dip reddi arar (alt fitil + yeşil mum → LONG için hızlı onay)

    Döner: (bulundu: bool, fiyat: float|None)
    """
    try:
        r = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=5)
        if not r or len(r) < 3:
            return False, None
        df = pd.DataFrame(r, columns=["t","o","h","l","c","v"])
        son     = df.iloc[-2]   # son KAPANMIŞ mum (son satır hâlâ açık olabilir)
        onceki  = df.iloc[-3]

        o, h, l, c, v = float(son["o"]), float(son["h"]), float(son["l"]), float(son["c"]), float(son["v"])
        v_onceki = float(onceki["v"])
        govde = max(abs(c - o), (h - l) * 0.01, 1e-12)  # sıfıra bölünmeyi engelle

        if yon == "pump":
            ust_fitil = h - max(o, c)
            fitil_pct = (ust_fitil / h) * 100 if h else 0
            ret_var = (ust_fitil >= WICK_BODY_ORANI * govde) and (fitil_pct >= MIN_WICK_PCT)
            hacim_azaliyor = v < v_onceki
            kirmizi = c < o
            if ret_var and hacim_azaliyor and kirmizi:
                return True, c
            return False, None
        else:  # dump
            alt_fitil = min(o, c) - l
            fitil_pct = (alt_fitil / l) * 100 if l else 0
            ret_var = (alt_fitil >= WICK_BODY_ORANI * govde) and (fitil_pct >= MIN_WICK_PCT)
            hacim_azaliyor = v < v_onceki
            yesil = c > o
            if ret_var and hacim_azaliyor and yesil:
                return True, c
            return False, None
    except Exception as e:
        log.warning(f"[TEPE_DIP] {symbol}: {e}")
        return False, None

def giris_onayi_bekle(symbol, yon, bekle_sn=15, pullback_pct=0.35):
    """
    FADE mantığında bu geri çekilme artık "olası dönüşün ilk işareti" olarak
    yorumlanıyor — scanner_loop bu onayı aldıktan sonra hareketin TERSİ
    yönünde pozisyon açıyor.
    """
    ekstrem = None
    for _ in range(bekle_sn):
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t:
            time.sleep(1); continue
        price = float(t["last"])

        if ekstrem is None:
            ekstrem = price
        elif yon == "pump":
            ekstrem = max(ekstrem, price)
        else:
            ekstrem = min(ekstrem, price)

        if yon == "pump":
            geri_cekilme = (ekstrem - price) / ekstrem * 100
            if geri_cekilme >= pullback_pct:
                return True, price
        else:
            geri_cekilme = (price - ekstrem) / ekstrem * 100
            if geri_cekilme >= pullback_pct:
                return True, price

        time.sleep(1)

    return False, None

def scanner_loop():
    log.info("[SCANNER] Bağımsız pump/dump tarama başladı (FADE / TERS MOD)")
    while True:
        time.sleep(SCAN_INTERVAL)
        try:
            if günlük_limit_asıldı(): continue
            with pos_lock:
                if len(positions) >= MAX_OPEN_AUTO: continue

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
                    if len(positions) >= MAX_OPEN_AUTO: break
                yon, detay = ani_hareket_tespit(sym)
                if yon is None: continue
                sym_kisa = sym.split("/")[0]

                # ══ FADE MANTIK: pump tespit edilirse SHORT, dump tespit edilirse LONG ══
                if yon == "pump":
                    tg(f"🚀 Ani PUMP: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}%\n[FADE] Ters (SHORT) için onay aranıyor...")

                    # ── HIZLI YOL: fitil/ret + azalan hacim zaten oluştu mu? ──
                    hizli_bulundu, hizli_fiyat = tepe_dip_reddi_var_mi(sym, "pump")
                    if hizli_bulundu:
                        tg(f"⚡ {sym_kisa} fitil+hacim reddi tespit edildi @ {hizli_fiyat:.8f} — [FADE] SHORT açılıyor (hızlı onay)...")
                        open_pos_short_manuel(sym, "scanner_fade")
                        break

                    # ── YEDEK YOL: hızlı onay yoksa eski pullback beklemesi ──
                    onaylandi, giris_fiyat = giris_onayi_bekle(sym, "pump")
                    if onaylandi:
                        tg(f"✅ {sym_kisa} dönüş sinyali onaylandı @ {giris_fiyat:.8f} — [FADE] SHORT açılıyor (pullback onayı)...")
                        open_pos_short_manuel(sym, "scanner_fade")
                        break
                    else:
                        log.info(f"[SCANNER] {sym_kisa} dönüş onayı gelmedi, atlandı")
                        continue

                elif yon == "dump":
                    tg(f"📉 Ani DUMP: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}%\n[FADE] Ters (LONG) için onay aranıyor...")

                    # ── HIZLI YOL: fitil/ret + azalan hacim zaten oluştu mu? ──
                    hizli_bulundu, hizli_fiyat = tepe_dip_reddi_var_mi(sym, "dump")
                    if hizli_bulundu:
                        tg(f"⚡ {sym_kisa} fitil+hacim reddi tespit edildi @ {hizli_fiyat:.8f} — [FADE] LONG açılıyor (hızlı onay)...")
                        open_pos_auto(sym, "scanner_fade")
                        break

                    # ── YEDEK YOL: hızlı onay yoksa eski pullback beklemesi ──
                    onaylandi, giris_fiyat = giris_onayi_bekle(sym, "dump")
                    if onaylandi:
                        tg(f"✅ {sym_kisa} dönüş sinyali onaylandı @ {giris_fiyat:.8f} — [FADE] LONG açılıyor (pullback onayı)...")
                        open_pos_auto(sym, "scanner_fade")
                        break
                    else:
                        log.info(f"[SCANNER] {sym_kisa} dönüş onayı gelmedi, atlandı")
                        continue
        except Exception as e:
            log.error(f"[SCANNER] {e}")

# ════════════════════════════════════════════
# COINSONAR SİNYALİ İŞLE
# ════════════════════════════════════════════
def coinsonar_isle(text):
    text_up = text.upper()
    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match: match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match: return
    coin_adi = match.group(1)
    symbol = f"{coin_adi}/USDT:USDT"

    try:
        tickers = safe_api(exchange.fetch_tickers)
        if tickers and symbol not in tickers: return
    except: pass

    if günlük_limit_asıldı(): return
    with pos_lock:
        if len(positions) >= MAX_OPEN_AUTO: return
        if symbol in positions: return

    gecti, detay = filtre_15m(symbol)
    if gecti:
        tg(f"📡 CoinSonar: {coin_adi} ✅ filtre geçti, LİMİT giriş deneniyor...")
        open_pos_auto(symbol, "coinsonar")
    else:
        log.info(f"[COINSONAR] {coin_adi} ❌ PAS")

# ════════════════════════════════════════════
# TELETHON
# ════════════════════════════════════════════
async def telethon_loop():
    try:
        if not COINSONAR_AKTIF and not FUTURESKRIPTO_AKTIF:
            log.info("[TELETHON] Her iki kanal da pasif — Telethon başlatılmadı, sadece scanner/manuel çalışıyor")
            tg("📡 Kanal sinyalleri kapalı — sadece kendi tarayıcın (scanner, FADE modda) ve manuel komutlar aktif")
            return

        if TG_SESSION:
            client = TelegramClient(StringSession(TG_SESSION), TG_API_ID, TG_API_HASH)
        else:
            client = TelegramClient("sadik_session", TG_API_ID, TG_API_HASH)

        await client.start()
        log.info("[TELETHON] Bağlandı!")
        aktif_kanallar = []
        if COINSONAR_AKTIF: aktif_kanallar.append("CoinSonar")
        if FUTURESKRIPTO_AKTIF: aktif_kanallar.append("FuturesKripto")
        tg(f"📡 Telethon aktif — {' + '.join(aktif_kanallar)} dinleniyor")

        dinlenecek = []
        if COINSONAR_AKTIF: dinlenecek.append(COINSONAR_KANAL)
        if FUTURESKRIPTO_AKTIF: dinlenecek.append(FUTURESKRIPTO_KANAL)

        @client.on(events.NewMessage(chats=dinlenecek))
        async def handler(event):
            text = event.message.text or ""
            chat = await event.get_chat()
            kanal = getattr(chat, "username", "") or ""

            if COINSONAR_AKTIF and COINSONAR_KANAL.lower() in kanal.lower():
                threading.Thread(target=coinsonar_isle, args=(text,), daemon=True).start()
            elif FUTURESKRIPTO_AKTIF and FUTURESKRIPTO_KANAL.lower() in kanal.lower():
                sonuc = sinyal_parse(text)
                if sonuc:
                    coin_adi, giris = sonuc
                    if not giris: return
                    symbol = f"{coin_adi}/USDT:USDT"
                    try:
                        tickers = safe_api(exchange.fetch_tickers)
                        if tickers and symbol not in tickers: return
                    except: pass
                    if not günlük_limit_asıldı():
                        tg(f"📊 FuturesKripto: {coin_adi} | Giriş: {giris}")
                        threading.Thread(target=open_pos_futureskripto, args=(symbol, giris), daemon=True).start()

        await client.run_until_disconnected()
    except Exception as e:
        log.error(f"[TELETHON] {e}")
        tg(f"⚠️ Telethon bağlantı hatası: {e}")

def telethon_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telethon_loop())

# ════════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════════
def load_open_positions():
    try:
        raw = safe_api(exchange.fetch_positions)
        if not raw: return
        yuklenen = 0
        lines = ["♻️ Pozisyonlar yüklendi:\n"]
        for p in raw:
            try:
                contracts = float(p.get("contracts") or 0)
                symbol = p.get("symbol", "")
                p_side = p.get("side", "")
                entry = float(p.get("entryPrice") or 0)
                if contracts == 0 or not symbol or p_side not in ("long","short") or entry == 0: continue
                sl = round(entry * (1 + SL_PCT/100), 8) if p_side == "short" else round(entry * (1 - SL_PCT/100), 8)
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry": entry, "sl": sl, "tetiklendi": False, "last_tp_idx": -1, "peak_net": 0.0,
                            "max_price": entry, "min_price": entry, "open_time": time.time(),
                            "amount": contracts, "kaynak": "yukle", "mod": "manuel",
                            "side": p_side, "pending": False,
                        }
                        yuklenen += 1
                        t = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        net, _ = net_pnl_hesapla(positions[symbol], now)
                        lines.append(f"{'🟢' if net>=0 else '🔴'} {symbol.split('/')[0]} [{p_side}] @ {entry:.8f} | {net:+.2f}$")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")
        if yuklenen > 0: tg("\n".join(lines))
        else: log.info("[YUKLE] Açık pozisyon yok")
    except Exception as e:
        log.error(f"[YUKLE] {e}")

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
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ════════════════════════════════════════════
# HEALTH SERVER
# ════════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            with pos_lock: ps = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock: pnl = daily_pnl
            self.wfile.write(f"OK|pos:{len(positions)}({ps})|pnl:{pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════════
# TELEGRAM HANDLER (manuel komutlar)
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
        coin_adi = coin.split("/")[0]
        if günlük_limit_asıldı():
            bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı."); return
        with pos_lock:
            if len(positions) >= MAX_OPEN_MANUEL:
                bot.send_message(msg.chat.id, "❌ Max pozisyon dolu."); return
            if coin in positions:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} zaten açık."); return
        bot.send_message(msg.chat.id, f"📉 {coin_adi} SHORT — LİMİT giriş deneniyor...")
        open_pos_short_manuel(coin, "manuel")
        return

    if "long ac" in lower or "long aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı."); return
        coin_adi = coin.split("/")[0]
        if günlük_limit_asıldı():
            bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı."); return
        with pos_lock:
            if len(positions) >= MAX_OPEN_MANUEL:
                bot.send_message(msg.chat.id, "❌ Max pozisyon dolu."); return
            if coin in positions:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} zaten açık."); return
        bot.send_message(msg.chat.id, f"⚡ {coin_adi} LONG — LİMİT giriş deneniyor...")
        open_pos_auto(coin, "manuel")
        return

    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok."); return
            lines = ["📋 POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = float(t["last"])
                amount = pos.get("amount") or (POS_SIZE / pos["entry"])
                net, pct = net_pnl_hesapla({**pos, "amount": amount}, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                durum_str = (f"TP{pos.get('last_tp_idx',0)+1} garantili 🎯" if pos.get("tetiklendi") else f"SL:{pos['sl']:.8f}")
                lines.append(
                    f"{'🟢' if net>=0 else '🔴'} {sym.split('/')[0]} [{pos.get('side','long').upper()}/{pos.get('kaynak','?')}]\n"
                    f"   {pos['entry']:.8f}→{price:.8f}\n"
                    f"   Net:{net:+.2f}$ ({pct:+.2f}%) | {sure}dk | {durum_str}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,kaynak").execute()
            data = r.data or []
            if not data:
                bot.send_message(msg.chat.id, "Kayıt yok."); return
            toplam = len(data)
            kazan = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net = sum(float(d.get("pnl") or 0) for d in data)
            with daily_pnl_lock: gunluk = daily_pnl
            bot.send_message(msg.chat.id,
                f"📊 İSTATİSTİK\nToplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$ | Günlük: {gunluk:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
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

    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        gecti, detay = filtre_15m(coin)
        bot.send_message(msg.chat.id,
            f"📊 {sym} 15m ANALİZ\nMA Sırası: {'✅' if detay.get('ma_ok') else '❌'}\n"
            f"Hacim: {'✅' if detay.get('vol_ok') else '❌'}\n"
            f"RSI(14): {detay.get('rsi',0):.1f} {'✅' if detay.get('rsi_ok') else '❌'}\n\n"
            f"{'✅ GİRİLİR' if gecti else '❌ PAS'}")
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n/durum — Açık pozisyonlar\n/istatistik — Geçmiş işlemler\n"
        "COIN long aç — Manuel LONG\nCOIN short aç — Manuel SHORT\n"
        "COIN kapat / hepsi kapat")

# ════════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms: tg(f"⏸ Yeniden başlıyor...\n{len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK SCALP FAST (FADE TEST) BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telethon_thread, daemon=True).start()

    tg(
        "🚀 SADIK SCALP FAST — FADE TEST\n"
        "🔖 Versiyon: 2026-07-04-v9 (küçük sermaye + scanner FADE modu)\n\n"
        f"📡 Kaynaklar: {'CoinSonar V2 ✅' if COINSONAR_AKTIF else 'CoinSonar V2 ❌'} | "
        f"{'FuturesKripto ✅' if FUTURESKRIPTO_AKTIF else 'FuturesKripto ❌'} | Manuel ✅ | Tarayıcı ✅ (FADE)\n\n"
        f"💰 Pozisyon: {MARGIN}$ margin × {LEVERAGE}x = {POS_SIZE}$\n"
        f"🚫 SL: -%{SL_PCT} (net ≈ -${ROUNDTRIP_FEE + POS_SIZE*SL_PCT/100:.2f})\n"
        f"🎯 TP seviyeleri: " + " / ".join(f"${x:.2f}" for x in TP_LEVELS_NET) + f" | ${TRAIL_BACK_NET:.2f} geri çekilince kilitlenir\n"
        f"📐 Giriş/Çıkış: SADECE LİMİT emir (ilk kapatma denemesi %{KAPAT_ILK_AGRESIFLIK} agresif)\n"
        f"🔀 Scanner: pump→SHORT / dump→LONG (FADE) | RSI+uzama filtreleri eski haliyle korundu\n\n"
        "Komutlar:\n/durum | /istatistik\nCOIN long aç | COIN short aç | COIN kapat"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
