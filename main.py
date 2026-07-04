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
       Yeni: SL≈-$1.06 | TP: 0.80/1.61/2.41/3.21 | Trail geri: 0.27
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
  - Net kâr $0.80'e ulaşılınca pozisyon KAPANMAZ — trailing moduna geçer.
    Fiyat lehte gitmeye devam ettiği sürece pozisyon açık kalır.
    Fiyat geri dönüp net kârı tekrar $0.80 seviyesine indirirse,
    o anda LİMİT emirle kapatılıp $0.80 net kâr kasaya konur.
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
TP_LEVELS_NET   = [0.80, 1.61, 2.41, 3.21]   # $ net kâr seviyeleri (taban $0.53→$0.80 yükseltildi,
                                               # SL -$1.06'ya karşı risk/ödül 1:2'den ~1:1.3'e iyileşti)
TRAIL_BACK_NET  = 0.27                        # zirveden bu kadar $ geri çekilirse kapat (KÜÇÜK kârlarda taban)
TRAIL_GIVEBACK_PCT = 0.30                     # BÜYÜK kârlarda: zirvenin bu yüzdesi kadar geri çekilme payı
                                               # (ikisinin BÜYÜĞÜ kullanılır — küçük kârda sabit, büyük kârda yüzdesel devreye girer)

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

# ── REJİM TESPİTİ (ADX) — fade mi trend-takip mi? ──
# ADX düşükse (yatay/sıkışık piyasa) → FADE (ters) mantığı uygulanır.
# ADX yüksekse (güçlü, kararlı trend — örn. EPIC gibi) → TREND TAKİBİ uygulanır
# (pump'ta LONG, dump'ta SHORT — yani hareketin yönünde girilir).
# Böylece hiçbir sinyal atlanmaz, sadece yön kararı piyasa karakterine göre verilir.
ADX_PERIOD      = 14
ADX_TREND_ESIK  = 25   # bu değerin üzerinde ADX = "gerçek trend var" kabul edilir

# ════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()

# ── Panel için işlem geçmişi (bot içi HTML panelde gösterilir) ──
trade_log       = []
trade_log_lock  = threading.Lock()
MAX_TRADE_LOG   = 500   # bellek şişmesin diye üst sınır

def kaydet_islem(sembol, yon, net, sure_dk, kaynak, sonuc_metni):
    with trade_log_lock:
        trade_log.append({
            "zaman": time.strftime("%H:%M:%S"),
            "sembol": sembol, "yon": yon, "net": net,
            "sure": sure_dk, "kaynak": kaynak, "sonuc": sonuc_metni,
        })
        if len(trade_log) > MAX_TRADE_LOG:
            del trade_log[0]

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
    """Round-trip komisyon dahil NET pnl döner (giriş+çıkış masrafı düşülmüş).
    Komisyon, POZİSYONUN GERÇEK boyutuna göre hesaplanır (sabit varsayılan
    POS_SIZE değil) — böylece double-fill veya yüklenen pozisyonlar gibi
    standarttan farklı boyuttaki işlemlerde de doğru net kâr/zarar çıkar."""
    entry  = pos["entry"]
    amount = pos["amount"]
    side   = pos.get("side", "long")
    if side == "short":
        gross = (entry - price) * amount
    else:
        gross = (price - entry) * amount
    gercek_notional = entry * amount
    gercek_fee = gercek_notional * COMMISSION * 2
    net = gross - gercek_fee
    pct = (gross / gercek_notional) * 100 if gercek_notional else 0.0
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
def calc_adx(df, period=14):
    """
    ADX (Average Directional Index) — trend gücünü ölçer (yön değil, GÜÇ).
    Yüksek ADX = güçlü/kararlı trend var. Düşük ADX = yatay/sıkışık piyasa.
    Sadece pandas ile (Wilder'ın orijinal smoothing yöntemine yakın, EMA ile
    yaklaştırılmış) hesaplanır.
    """
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

def trend_gucu_adx(symbol, period=ADX_PERIOD):
    """15m mumlardan ADX hesaplar. Veri yetersizse/hata olursa None döner
    (bu durumda çağıran taraf güvenli varsayılan olarak FADE'e düşer)."""
    try:
        r = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=period * 3)
        if not r or len(r) < period * 2:
            return None
        df = pd.DataFrame(r, columns=["t", "o", "h", "l", "c", "v"])
        return calc_adx(df, period)
    except Exception as e:
        log.warning(f"[ADX] {symbol}: {e}")
        return None

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

    kaydet_islem(sym.upper(), pos.get("side", "long"), net, sure, kaynak, reason)

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

                    # ── DİNAMİK TRAILING: küçük kârda sabit ($0.27), büyük kârda
                    # zirvenin %30'u — hangisi BÜYÜKSE o kullanılır. Böylece büyük
                    # hareketlerde (örn. güçlü trend) pozisyon daha uzun süre nefes
                    # alabilir, küçük kârlarda ise eski sıkı koruma aynen kalır.
                    # Taban (floor_net) HER ZAMAN mutlak alt sınır — dinamik trail
                    # ne olursa olsun, garanti edilen TP seviyesinin altına inilmez.
                    dinamik_trail = max(TRAIL_BACK_NET, peak_net * TRAIL_GIVEBACK_PCT)

                    if (peak_net - net) >= dinamik_trail or net <= floor_net - 0.01:
                        close_pos(symbol, f"🎯 TP{last_tp_idx+1} garantisi kilitlendi (zirve ${peak_net:.2f} → ${net:.2f}, pay:${dinamik_trail:.2f})")
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

                # ══ REJİM TESPİTİ: ADX düşükse FADE, yüksekse TREND TAKİBİ ══
                adx = trend_gucu_adx(sym)
                adx_guclu = (adx is not None) and (adx >= ADX_TREND_ESIK)
                adx_str = f"{adx:.1f}" if adx is not None else "N/A"

                if yon == "pump":
                    if adx_guclu:
                        hedef_yon, mod, kaynak_etiket = "long", "TREND", "scanner_trend"
                        aciklama = f"[TREND ADX:{adx_str}] Yönünde (LONG) onay aranıyor..."
                    else:
                        hedef_yon, mod, kaynak_etiket = "short", "FADE", "scanner_fade"
                        aciklama = f"[FADE ADX:{adx_str}] Ters (SHORT) için onay aranıyor..."

                    tg(f"🚀 Ani PUMP: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}%\n{aciklama}")

                    # Hızlı fitil/hacim reddi SADECE fade senaryosunda anlamlı
                    # (dönüş/tükenme sinyali arıyor — trend takibinde kullanılmaz)
                    if mod == "FADE":
                        hizli_bulundu, hizli_fiyat = tepe_dip_reddi_var_mi(sym, "pump")
                        if hizli_bulundu:
                            tg(f"⚡ {sym_kisa} fitil+hacim reddi tespit edildi @ {hizli_fiyat:.8f} — [{mod}] SHORT açılıyor (hızlı onay)...")
                            open_pos_short_manuel(sym, kaynak_etiket)
                            break

                    onaylandi, giris_fiyat = giris_onayi_bekle(sym, "pump")
                    if onaylandi:
                        yon_metni = "LONG" if hedef_yon == "long" else "SHORT"
                        tg(f"✅ {sym_kisa} onaylandı @ {giris_fiyat:.8f} — [{mod}] {yon_metni} açılıyor...")
                        if hedef_yon == "long":
                            open_pos_auto(sym, kaynak_etiket)
                        else:
                            open_pos_short_manuel(sym, kaynak_etiket)
                        break
                    else:
                        log.info(f"[SCANNER] {sym_kisa} onay gelmedi, atlandı")
                        continue

                elif yon == "dump":
                    if adx_guclu:
                        hedef_yon, mod, kaynak_etiket = "short", "TREND", "scanner_trend"
                        aciklama = f"[TREND ADX:{adx_str}] Yönünde (SHORT) onay aranıyor..."
                    else:
                        hedef_yon, mod, kaynak_etiket = "long", "FADE", "scanner_fade"
                        aciklama = f"[FADE ADX:{adx_str}] Ters (LONG) için onay aranıyor..."

                    tg(f"📉 Ani DUMP: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}%\n{aciklama}")

                    if mod == "FADE":
                        hizli_bulundu, hizli_fiyat = tepe_dip_reddi_var_mi(sym, "dump")
                        if hizli_bulundu:
                            tg(f"⚡ {sym_kisa} fitil+hacim reddi tespit edildi @ {hizli_fiyat:.8f} — [{mod}] LONG açılıyor (hızlı onay)...")
                            open_pos_auto(sym, kaynak_etiket)
                            break

                    onaylandi, giris_fiyat = giris_onayi_bekle(sym, "dump")
                    if onaylandi:
                        yon_metni = "SHORT" if hedef_yon == "short" else "LONG"
                        tg(f"✅ {sym_kisa} onaylandı @ {giris_fiyat:.8f} — [{mod}] {yon_metni} açılıyor...")
                        if hedef_yon == "short":
                            open_pos_short_manuel(sym, kaynak_etiket)
                        else:
                            open_pos_auto(sym, kaynak_etiket)
                        break
                    else:
                        log.info(f"[SCANNER] {sym_kisa} onay gelmedi, atlandı")
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
# BAŞLANGIÇTA ASKIDA KALAN EMİRLERİ TEMİZLE (double-fill koruması)
# ════════════════════════════════════════════
def eski_emirleri_iptal_et():
    """
    Bot her başladığında (yeniden başlatma dahil) borsada önceki oturumdan
    kalmış olabilecek DOLMAMIŞ limit emirlerini iptal eder. Bu, "eski bir
    giriş emri bot yeniden başladıktan SONRA sessizce dolup, botun az önce
    açtığı yeni pozisyonla birleşerek beklenenden büyük (double-fill)
    pozisyon oluşması" riskini kökten engeller — TLM/EPIC/ARPA
    işlemlerinde gördüğümüz ~2x boyutlu pozisyonların kök nedeni buydu.
    """
    try:
        acik_emirler = safe_api(exchange.fetch_open_orders)
        if not acik_emirler:
            log.info("[TEMİZLİK] Askıda emir yok")
            return
        iptal_sayisi = 0
        for o in acik_emirler:
            try:
                oid = o.get("id")
                sym = o.get("symbol")
                if oid and sym:
                    safe_api(exchange.cancel_order, oid, sym)
                    iptal_sayisi += 1
            except Exception as e:
                log.warning(f"[TEMİZLİK] Emir iptal hatası: {e}")
        if iptal_sayisi > 0:
            tg(f"🧹 Başlangıç temizliği: {iptal_sayisi} askıda emir iptal edildi (double-fill koruması)")
        log.info(f"[TEMİZLİK] {iptal_sayisi} askıda emir iptal edildi")
    except Exception as e:
        log.error(f"[TEMİZLİK] {e}")

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

    # Kümülatif eğri için basit SVG polyline (istemci tarafı JS gerektirmez)
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
<title>Sadık Scalp Fast — Performans Paneli</title>
<style>
  body {{ background:#0B0E11; color:#E8ECEF; font-family:-apple-system,Segoe UI,sans-serif; margin:0; padding:20px 16px 60px; }}
  .mono {{ font-family: 'JetBrains Mono', monospace; }}
  .eyebrow {{ font-size:12px; letter-spacing:1.5px; color:#6B7684; text-transform:uppercase; font-weight:600; }}
  h1 {{ margin:2px 0 18px; font-size:22px; }}
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
  <div class="eyebrow">Sadık Scalp Fast</div>
  <h1>Performans Paneli</h1>
  <div style="font-size:12px;color:#4A5361;margin-bottom:18px">{n} işlem · sayfa her yenilendiğinde güncellenir</div>

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
    <div style="font-size:11.5px;color:#8B95A1;text-transform:uppercase;letter-spacing:.5px;padding:0 8px 10px">Kümülatif Net PnL</div>
    <svg viewBox="0 0 600 160" width="100%" height="160" preserveAspectRatio="none">
      <line x1="0" y1="{sifir_y:.1f}" x2="600" y2="{sifir_y:.1f}" stroke="#2A323C" stroke-width="1"/>
      <polyline points="{svg_polyline}" fill="none" stroke="#1E90FF" stroke-width="2.5"/>
    </svg>
  </div>

  <div class="sectionlabel">İşlem Geçmişi (yeniden eskiye, son 100)</div>
  {satirlar if satirlar else '<div style="text-align:center;color:#4A5361;font-size:13px;padding:30px 0">Henüz kapanan işlem yok</div>'}
</body></html>"""

# ════════════════════════════════════════════
# HEALTH SERVER
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
    eski_emirleri_iptal_et()
    load_open_positions()
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telethon_thread, daemon=True).start()

    tg(
        "🚀 SADIK SCALP FAST — FADE TEST\n"
        "🔖 Versiyon: v5 (ADX rejim tespiti — düşük ADX'te FADE, yüksek ADX'te TREND takibi)\n\n"
        f"📡 Kaynaklar: {'CoinSonar V2 ✅' if COINSONAR_AKTIF else 'CoinSonar V2 ❌'} | "
        f"{'FuturesKripto ✅' if FUTURESKRIPTO_AKTIF else 'FuturesKripto ❌'} | Manuel ✅ | Tarayıcı ✅ (FADE)\n\n"
        f"💰 Pozisyon: {MARGIN}$ margin × {LEVERAGE}x = {POS_SIZE}$\n"
        f"🚫 SL: -%{SL_PCT} (net ≈ -${ROUNDTRIP_FEE + POS_SIZE*SL_PCT/100:.2f})\n"
        f"🎯 TP seviyeleri: " + " / ".join(f"${x:.2f}" for x in TP_LEVELS_NET) + f" | ${TRAIL_BACK_NET:.2f} geri çekilince kilitlenir\n"
        f"📐 Giriş/Çıkış: SADECE LİMİT emir (ilk kapatma denemesi %{KAPAT_ILK_AGRESIFLIK} agresif)\n"
        f"🔀 Scanner: ADX<{ADX_TREND_ESIK} → FADE (ters) | ADX≥{ADX_TREND_ESIK} → TREND takibi | RSI+uzama filtreleri eski haliyle korundu\n\n"
        "Komutlar:\n/durum | /istatistik\nCOIN long aç | COIN short aç | COIN kapat"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
