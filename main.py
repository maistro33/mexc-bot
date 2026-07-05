#!/usr/bin/env python3
"""
FVG/SMC STRATEJİSİ — GEÇMİŞ VERİYLE BACKTEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Amaç: "Profesyonel FVG bot" stratejisinin (günlük+4h trend teyidi +
likidite süpürmesi + 15m FVG girişi + R bazlı kademeli TP/başa baş)
GERÇEK GEÇMİŞ VERİDE ne sıklıkta sinyal ürettiğini ve sonuçlarının ne
olduğunu gösterir — günlerce canlı beklemek yerine dakikalar içinde.

ÖNEMLİ: Bu script gerçek para KULLANMAZ, hiçbir emir açmaz. Sadece
geçmiş OHLCV verisini indirip, aynı sinyal mantığını "olsaydı ne olurdu"
şeklinde simüle eder (yani mum-mum ilerleyerek, o ana kadarki veriyle
karar verip, GELECEĞİ görmeden test eder — bakış-öne (look-ahead) hatası
olmaması için özenle yazılmıştır).

ÇALIŞTIRMA:
  pip install ccxt pandas --break-system-packages   (gerekirse)
  python3 fvg_backtest.py

Varsayılan olarak son ~120 günü, en yüksek hacimli ~30 coin üzerinde
test eder (ayarlanabilir, aşağıdaki CONFIG bölümüne bak).
"""

import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

# ════════════════════════════════════════════
# CONFIG — istediğin gibi değiştirebilirsin
# ════════════════════════════════════════════
GECMIS_GUN     = 365     # kaç gün geriye gidilecek (1 yıl)
TOP_COINS      = 100     # en yüksek hacimli kaç coin denenecek
MIN_VOLUME     = 5_000_000
BUFFER_PCT     = 0.0015
LEV            = 10
MARGIN         = 10
TP_SPLIT       = [0.4, 0.3, 0.3]

exchange = ccxt.bitget({"options": {"defaultType": "swap"}, "enableRateLimit": True})


# ════════════════════════════════════════════
# GEÇMİŞ VERİ ÇEKME (sayfalama ile — tek çağrı yetmez, uzun geçmiş için)
# ════════════════════════════════════════════
def gecmis_veri_cek(symbol, timeframe, gun_sayisi):
    """Bitget'ten `gun_sayisi` kadar geriye giden OHLCV verisini sayfalayarak çeker."""
    ms_baslangic = int((datetime.now(timezone.utc) - timedelta(days=gun_sayisi)).timestamp() * 1000)
    tum_mumlar = []
    since = ms_baslangic
    while True:
        try:
            mumlar = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            print(f"  [HATA] {symbol} {timeframe}: {e}")
            break
        if not mumlar:
            break
        tum_mumlar.extend(mumlar)
        if len(mumlar) < 2:
            break
        yeni_since = mumlar[-1][0] + 1
        if yeni_since <= since:
            break
        since = yeni_since
        if mumlar[-1][0] >= int(datetime.now(timezone.utc).timestamp() * 1000) - 60_000:
            break
        time.sleep(exchange.rateLimit / 1000)
    if not tum_mumlar:
        return None
    df = pd.DataFrame(tum_mumlar, columns=["t", "o", "h", "l", "c", "v"])
    df = df.drop_duplicates(subset="t").sort_values("t").reset_index(drop=True)
    return df


def sembol_listesi_al(top_n, min_hacim):
    tickers = exchange.fetch_tickers()
    filtreli = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        vol = data.get("quoteVolume") or 0
        if vol >= min_hacim:
            filtreli.append((sym, vol))
    filtreli.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtreli[:top_n]]


# ════════════════════════════════════════════
# SİNYAL MANTIĞI (orijinal bottan BİREBİR alınmıştır — mum-mum ilerleyecek
# şekilde uyarlanmıştır, bakış-öne hatası yok: her karar SADECE o ana
# kadarki mumlarla veriliyor)
# ════════════════════════════════════════════
def yon_belirle(d_df, h4_df, i_d, i_h4):
    """d_df/h4_df: günlük/4h DataFrame. i_d/i_h4: şu anki (dahil) son index."""
    if i_d < 2 or i_h4 < 2:
        return None
    d_high = d_df["h"].iloc[i_d - 1]
    d_high_onceki = d_df["h"].iloc[i_d - 2]
    d_low = d_df["l"].iloc[i_d - 1]
    d_low_onceki = d_df["l"].iloc[i_d - 2]

    h_high = h4_df["h"].iloc[i_h4 - 1]
    h_high_onceki = h4_df["h"].iloc[i_h4 - 2]
    h_low = h4_df["l"].iloc[i_h4 - 1]
    h_low_onceki = h4_df["l"].iloc[i_h4 - 2]

    if d_high > d_high_onceki and h_high > h_high_onceki:
        return "long"
    if d_low < d_low_onceki and h_low < h_low_onceki:
        return "short"
    return None


def likidite_supurmesi(h1_df, i_h1, direction):
    if i_h1 < 30:
        return False
    pencere_low = h1_df["l"].iloc[i_h1 - 30:i_h1 - 1]
    pencere_high = h1_df["h"].iloc[i_h1 - 30:i_h1 - 1]
    son_low = h1_df["l"].iloc[i_h1 - 1]
    son_high = h1_df["h"].iloc[i_h1 - 1]
    if direction == "long":
        return son_low < pencere_low.min()
    else:
        return son_high > pencere_high.max()


def giris_modeli(m15_df, i_m15, direction):
    if i_m15 < 60:
        return None
    o = m15_df["o"]; h = m15_df["h"]; l = m15_df["l"]; c = m15_df["c"]

    idx = i_m15 - 1
    body = abs(c.iloc[idx] - o.iloc[idx])
    avg_body = sum(abs(c.iloc[idx - k] - o.iloc[idx - k]) for k in range(1, 10)) / 9
    if body < avg_body * 1.5:
        return None

    if direction == "long" and h.iloc[idx - 2] < l.iloc[idx]:
        entry = (h.iloc[idx - 2] + l.iloc[idx]) / 2
        swing_low = l.iloc[idx - 14: idx + 1].min()
        sl = swing_low - (swing_low * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l.iloc[idx - 2] > h.iloc[idx]:
        entry = (l.iloc[idx - 2] + h.iloc[idx]) / 2
        swing_high = h.iloc[idx - 14: idx + 1].max()
        sl = swing_high + (swing_high * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None


# ════════════════════════════════════════════
# İŞLEM SİMÜLASYONU (R bazlı, kademeli TP + başa baş)
# ════════════════════════════════════════════
def islemi_simule_et(m15_df, giris_idx, direction, entry, sl):
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    tp1 = entry + risk if direction == "long" else entry - risk
    tp2 = entry + 2 * risk if direction == "long" else entry - 2 * risk
    tp3 = entry + 3 * risk if direction == "long" else entry - 3 * risk

    kalan = 1.0
    r_toplam = 0.0
    aktif_sl = sl
    tp1_oldu = tp2_oldu = False

    for i in range(giris_idx, len(m15_df)):
        h = m15_df["h"].iloc[i]; l = m15_df["l"].iloc[i]

        sl_vuruldu = (l <= aktif_sl) if direction == "long" else (h >= aktif_sl)
        if sl_vuruldu:
            r_bu_parca = (aktif_sl - entry) / risk if direction == "long" else (entry - aktif_sl) / risk
            r_toplam += r_bu_parca * kalan
            return {"r": r_toplam, "sure_mum": i - giris_idx, "sonuc": "SL/BE", "cikis_i": i}

        if not tp1_oldu:
            tp1_vuruldu = (h >= tp1) if direction == "long" else (l <= tp1)
            if tp1_vuruldu:
                r_toplam += 1.0 * TP_SPLIT[0]
                kalan -= TP_SPLIT[0]
                tp1_oldu = True
                aktif_sl = entry  # başa baş

        if tp1_oldu and not tp2_oldu:
            tp2_vuruldu = (h >= tp2) if direction == "long" else (l <= tp2)
            if tp2_vuruldu:
                r_toplam += 2.0 * TP_SPLIT[1]
                kalan -= TP_SPLIT[1]
                tp2_oldu = True

        if tp2_oldu:
            tp3_vuruldu = (h >= tp3) if direction == "long" else (l <= tp3)
            if tp3_vuruldu:
                r_toplam += 3.0 * TP_SPLIT[2]
                return {"r": r_toplam, "sure_mum": i - giris_idx, "sonuc": "TP3", "cikis_i": i}

    return {"r": r_toplam, "sure_mum": len(m15_df) - giris_idx, "sonuc": "AÇIK_KALDI(veri bitti)", "cikis_i": len(m15_df) - 1}


# ════════════════════════════════════════════
# ADIM 1: HER COIN İÇİN ADAY SİNYALLERİ TOPLA (henüz simüle etmeden)
# ════════════════════════════════════════════
def coin_sinyalleri_bul(symbol):
    print(f"[{symbol}] veri indiriliyor...")
    d_df   = gecmis_veri_cek(symbol, "1d", GECMIS_GUN + 5)
    h4_df  = gecmis_veri_cek(symbol, "4h", GECMIS_GUN + 5)
    h1_df  = gecmis_veri_cek(symbol, "1h", GECMIS_GUN + 5)
    m15_df = gecmis_veri_cek(symbol, "15m", GECMIS_GUN + 5)

    if any(df is None or len(df) < 60 for df in [d_df, h4_df, h1_df, m15_df]):
        print(f"[{symbol}] yetersiz veri, atlandı")
        return None, []

    sinyaller = []
    for i in range(60, len(m15_df)):
        simdiki_zaman = m15_df["t"].iloc[i]

        i_d = d_df[d_df["t"] <= simdiki_zaman].shape[0]
        i_h4 = h4_df[h4_df["t"] <= simdiki_zaman].shape[0]
        i_h1 = h1_df[h1_df["t"] <= simdiki_zaman].shape[0]

        direction = yon_belirle(d_df, h4_df, i_d, i_h4)
        if not direction:
            continue
        if not likidite_supurmesi(h1_df, i_h1, direction):
            continue
        setup = giris_modeli(m15_df, i + 1, direction)
        if not setup:
            continue

        sinyaller.append({
            "symbol": symbol, "i": i, "t": simdiki_zaman,
            "direction": direction, "entry": setup["entry"], "sl": setup["sl"],
        })

    print(f"[{symbol}] {len(sinyaller)} aday sinyal bulundu")
    return m15_df, sinyaller


# ════════════════════════════════════════════
# ADIM 2: TÜM SİNYALLERİ ZAMANA GÖRE SIRALA, TEK-POZİSYON (MAX_POS=1)
# KISITINI PORTFÖY GENELİNDE GERÇEKÇİ ŞEKİLDE UYGULA
# ════════════════════════════════════════════
def portfoy_simulasyonu(tum_m15, tum_sinyaller):
    tum_sinyaller.sort(key=lambda s: s["t"])

    islemler = []
    sonraki_musait_zaman = -1

    for sig in tum_sinyaller:
        if sig["t"] < sonraki_musait_zaman:
            continue  # o an başka bir coinde pozisyon açıkmış (MAX_POS=1) — bu sinyal kaçırılır

        m15_df = tum_m15[sig["symbol"]]
        sonuc = islemi_simule_et(m15_df, sig["i"], sig["direction"], sig["entry"], sig["sl"])
        if not sonuc:
            continue

        cikis_i = sonuc["cikis_i"]
        cikis_zaman = m15_df["t"].iloc[min(cikis_i, len(m15_df) - 1)]

        sonuc["symbol"] = sig["symbol"]
        sonuc["direction"] = sig["direction"]
        sonuc["zaman"] = datetime.fromtimestamp(sig["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        islemler.append(sonuc)

        sonraki_musait_zaman = cikis_zaman

    return islemler





def main():
    print(f"═══ FVG/SMC BACKTEST — son {GECMIS_GUN} gün, en yüksek hacimli {TOP_COINS} coin ═══\n")
    semboller = sembol_listesi_al(TOP_COINS, MIN_VOLUME)
    print(f"{len(semboller)} coin bulundu: {', '.join(s.split('/')[0] for s in semboller[:10])}...\n")

    tum_m15 = {}
    tum_sinyaller = []
    for sym in semboller:
        try:
            m15_df, sinyaller = coin_sinyalleri_bul(sym)
            if m15_df is not None:
                tum_m15[sym] = m15_df
                tum_sinyaller.extend(sinyaller)
        except Exception as e:
            print(f"[{sym}] HATA: {e}")

    print(f"\nToplam aday sinyal (tüm coinlerde): {len(tum_sinyaller)}")
    print("Portföy genelinde MAX_POS=1 kısıtı uygulanıyor (gerçek bot davranışı)...\n")

    tum_islemler = portfoy_simulasyonu(tum_m15, tum_sinyaller)

    if not tum_islemler:
        print("\nHİÇ İŞLEM BULUNAMADI — filtre çok sıkı olabilir veya veri çekilemedi.")
        return

    df = pd.DataFrame(tum_islemler)
    kazanan = df[df["r"] > 0]
    kaybeden = df[df["r"] <= 0]

    print("\n" + "═" * 50)
    print(f"TOPLAM İŞLEM: {len(df)} (aday sinyal: {len(tum_sinyaller)}, MAX_POS=1 nedeniyle {len(tum_sinyaller)-len(df)} kaçırıldı)")
    print(f"Kazanan: {len(kazanan)} ({len(kazanan)/len(df)*100:.1f}%)")
    print(f"Kaybeden: {len(kaybeden)} ({len(kaybeden)/len(df)*100:.1f}%)")
    print(f"Toplam R: {df['r'].sum():+.2f}")
    print(f"Ortalama R/işlem: {df['r'].mean():+.3f}")
    print(f"Ortalama kazanan R: {kazanan['r'].mean():+.3f}" if len(kazanan) else "Kazanan yok")
    print(f"Ortalama kaybeden R: {kaybeden['r'].mean():+.3f}" if len(kaybeden) else "Kaybeden yok")
    print(f"Ortalama işlem süresi: {df['sure_mum'].mean()*15:.0f} dakika")
    print(f"Aya ortalama işlem: {len(df)/GECMIS_GUN*30:.2f}")
    print("═" * 50)

    df.to_csv("fvg_backtest_sonuclar.csv", index=False)
    print("\nDetaylı sonuçlar 'fvg_backtest_sonuclar.csv' dosyasına kaydedildi.")


if __name__ == "__main__":
    main()
