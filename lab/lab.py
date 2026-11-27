# 🔬 Dürüst test laboratuvarı
#  - bütün coinler tek zaman ızgarasında (15 dk)
#  - evren her mumda O ANKİ bilgiyle: son 24 saat |değişim| sıralaması, 24s hacim ≥ MIN_HAC, en az 2 gün verisi olan, eski coin değil
#  - portföy: kasa, toplam ve yön sınırı, coin başına tek işlem, kapanıştan sonra bekleme
#  - giriş: sinyal mumunun KAPANIŞINDAN sonraki mumun açılışından (+kayma); çıkış: aynı mum içinde önce stop (kötümser)
import numpy as np, os, glob

ESKI = {"BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "LTC", "BCH", "BNB", "XLM", "ETC", "DOT", "LINK", "SHIB", "AVAX", "XMR", "UNI", "ATOM",
        "FIL", "NEAR", "SOL", "HBAR", "AAVE", "QNT", "ALGO", "VET", "ICP", "EOS", "XTZ", "THETA", "MKR", "AXS", "SAND", "MANA"}
TK, MK, KY = 0.0006, 0.0002, 0.0005
NOT = 15.0          # 3 $ × 5x
ADIM = 900_000

def yukle(klasor):
    ds = sorted(glob.glob(os.path.join(klasor, "*.npy")))
    A = {os.path.basename(d)[:-4]: np.load(d) for d in ds}
    A = {s: a for s, a in A.items() if len(a) > 200 and s[:-4] not in ESKI}
    t0 = min(a[0, 0] for a in A.values()); t1 = max(a[-1, 0] for a in A.values())
    L = int((t1 - t0) // ADIM) + 1; S = sorted(A); N = len(S)
    O, H, Lo, C, V = (np.full((N, L), np.nan) for _ in range(5))
    for k, s in enumerate(S):
        a = A[s]; ix = ((a[:, 0] - t0) // ADIM).astype(int)
        O[k, ix], H[k, ix], Lo[k, ix], C[k, ix], V[k, ix] = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    T = t0 + np.arange(L) * ADIM
    return {"S": S, "O": O, "H": H, "L": Lo, "C": C, "V": V, "T": T}

def evren_hazirla(d, min_hac=3e6, n_ev=40):
    C, V = d["C"], d["V"]; N, L = C.shape
    ch = np.full((N, L), np.nan); ch[:, 96:] = C[:, 96:] / C[:, :-96] - 1
    cs = np.nancumsum(np.nan_to_num(V), axis=1); v24 = np.zeros_like(cs); v24[:, 96:] = cs[:, 96:] - cs[:, :-96]
    yas = np.cumsum(~np.isnan(C), axis=1)                               # kaç mumdur verisi var
    uygun = (v24 >= min_hac) & (yas >= 200) & ~np.isnan(ch)
    skor = np.where(uygun, np.abs(ch), -1.0)
    EV = np.zeros((N, L), dtype=bool)
    sira = np.argsort(-skor, axis=0)[:n_ev]                             # her mumda en hareketli n_ev
    for i in range(L):
        top = sira[:, i]; ok = skor[top, i] > 0; EV[top[ok], i] = True
    d["EV"] = EV; d["ch24"] = ch; d["v24"] = v24
    return d

def simule(d, sinyal, i0, i1, sl=0.08, tpa=0.01, lag=2, maxbar=24, tek_tp=None, yon_max=5, top_max=10, bekle=2, kasa0=100.0, iz=None, geri=0.0, gw=4, ters_ac=False, tp_ters=0):
    """sinyal(i) → [(coin_index, yön)] ; i0..i1 arası mumlar. tek_tp: sabit hedef oranı (merdiven yok). iz: (coin,i,pozisyon)→yeni stop (merdiven izi)"""
    O, H, L, C = d["O"], d["H"], d["L"], d["C"]
    acik = {}; son_cik = {}; T = []; kasa = kasa0; lim = {}
    for i in range(i0, i1):
        for k in list(lim):                                              # geri çekilme limitleri
            u, p, son = lim[k]
            if i > son or k in acik: del lim[k]; continue
            if (u == 1 and L[k, i] <= p) or (u == -1 and H[k, i] >= p):
                del lim[k]
                if len(acik) < top_max and sum(1 for q in acik.values() if q["u"] == u) < yon_max:
                    acik[k] = {"u": u, "g": p, "st": p * (1 - u * sl), "k": 0, "i": i}
        # 1) açık işlemleri bu mumla yönet
        for k in list(acik):
            p = acik[k]; u = p["u"]; h, l, c = H[k, i], L[k, i], C[k, i]
            if np.isnan(c): continue
            lo, hi = (l, h) if u == 1 else (h, l)
            if tp_ters == 2 and p["k"] >= 1 and not p.get("ters") and u * (p["st"] - p["g"]) < 0: p["st"] = p["g"]   # B: TP1 gördüyse girişe dönünce çık
            if u * (lo - p["st"]) <= 0:
                cik = p["st"] * (1 - u * KY) if u * (O[k, i] - p["st"]) > 0 else O[k, i] * (1 - u * KY); ucr = TK
            else:
                cik = None
                if tek_tp is not None:
                    hd = p["g"] * (1 + u * tek_tp)
                    if u * (hi - hd) >= 0: cik, ucr = hd, MK
                else:
                    while u * (hi - p["g"] * (1 + u * tpa * (p["k"] + 1))) >= 0:
                        p["k"] += 1
                        if p["k"] >= lag:
                            ad = p["g"] * (1 + u * tpa * (p["k"] - lag + 1))
                            if u * (ad - p["st"]) > 0: p["st"] = ad
                if cik is None and iz is not None:
                    yeni = iz(k, i, p)
                    if yeni is not None and u * (yeni - p["st"]) > 0: p["st"] = yeni
                if cik is None and i - p["i"] >= maxbar: cik, ucr = c * (1 - u * 0.0003), TK
            if cik is not None:
                a = NOT / p["g"]; pnl = a * u * (cik - p["g"]) - NOT * TK - a * cik * ucr
                kasa += pnl; T.append((d["T"][p["i"]], d["T"][i], u, pnl, k)); del acik[k]; son_cik[k] = i
                kosul = (ters_ac and ucr == TK and u * (cik - p["g"]) < 0) or (tp_ters and ucr == TK and p["k"] >= 1 and u * (cik - p["st"]) <= 1e-12 + abs(cik) * 0.002)
                if kosul and not p.get("ters") and i + 1 < i1 and not np.isnan(O[k, i + 1]):   # ters yönde aç
                    if len(acik) < top_max and sum(1 for q in acik.values() if q["u"] == -u) < yon_max:
                        g2 = O[k, i + 1] * (1 - u * KY); acik[k] = {"u": -u, "g": g2, "st": g2 * (1 + u * sl), "k": 0, "i": i + 1, "ters": 1}
        # 2) bu mumun kapanışındaki sinyaller → sonraki mumda giriş
        if i + 1 >= i1: continue
        for k, u in sinyal(i):
            if k in acik or i - son_cik.get(k, -999) < bekle or len(acik) >= top_max: continue
            if sum(1 for p in acik.values() if p["u"] == u) >= yon_max: continue
            o = O[k, i + 1]
            if np.isnan(o): continue
            if geri > 0:
                if k not in lim: lim[k] = (u, C[k, i] * (1 - u * geri), i + gw)
                continue
            g = o * (1 + u * KY)
            acik[k] = {"u": u, "g": g, "st": g * (1 - u * sl), "k": 0, "i": i + 1}
    return T

def ozet(T):
    if not T: return {"n": 0, "top": 0.0, "kaz": 0, "dd": 0.0}
    p = np.array([t[3] for t in sorted(T, key=lambda t: t[1])]); eq = np.cumsum(p)
    return {"n": len(p), "top": round(float(p.sum()), 1), "kaz": round(float((p > 0).mean() * 100)), "dd": round(float((np.maximum.accumulate(eq) - eq).max()), 1)}
