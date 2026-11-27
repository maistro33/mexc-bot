# Stratejiler — hepsi sadece i anına kadarki veriyi kullanır
import numpy as np

def kaydir(a, n):
    b = np.full_like(a, np.nan); b[:, n:] = a[:, :-n]; return b

def uclu_hazirla(d):
    C, O = d["C"], d["O"]
    d["g2"] = C / kaydir(C, 192) - 1
    up1 = (C > kaydir(O, 3)) & (C > kaydir(C, 4)); dn1 = (C < kaydir(O, 3)) & (C < kaydir(C, 4))
    d["s1"] = np.where(up1, 1, np.where(dn1, -1, 0))
    d["d15"] = np.sign(np.nan_to_num(C - O)).astype(int)

def uclu(d, thr):
    EV, g2, s1, d15 = d["EV"], d["g2"], d["s1"], d["d15"]
    def f(i):
        ks = np.nonzero(EV[:, i])[0]; out = []
        for k in ks:
            g = g2[k, i]
            if np.isnan(g): continue
            t = 1 if g >= thr else -1 if g <= -thr else 0
            if t and s1[k, i] == t and d15[k, i] == t: out.append((k, t))
        out.sort(key=lambda x: -abs(g2[x[0], i])); return out
    return f

def merdiven_hazirla(d, w=3):
    H, L, C = d["H"], d["L"], d["C"]; N, T = C.shape
    sh1, sh2, sl1, sl2 = (np.full((N, T), np.nan) for _ in range(4))
    for k in range(N):
        h, l = H[k], L[k]; a1 = a2 = b1 = b2 = np.nan
        for i in range(2 * w, T):
            j = i - w
            hh = h[j - w:j + w + 1]; ll = l[j - w:j + w + 1]
            if not np.isnan(h[j]) and not np.isnan(hh).any():
                if h[j] == hh.max() and h[j] > h[j - w:j].max(): a2, a1 = a1, h[j]
                if l[j] == ll.min() and l[j] < l[j - w:j].min(): b2, b1 = b1, l[j]
            sh1[k, i], sh2[k, i], sl1[k, i], sl2[k, i] = a1, a2, b1, b2
    d["sh1"], d["sh2"], d["sl1"], d["sl2"] = sh1, sh2, sl1, sl2

def merdiven(d, maxr=0.03):
    EV, C = d["EV"], d["C"]; sh1, sh2, sl1, sl2 = d["sh1"], d["sh2"], d["sl1"], d["sl2"]
    def f(i):
        out = []
        for k in np.nonzero(EV[:, i])[0]:
            c, cp = C[k, i], C[k, i - 1]
            if np.isnan(sl2[k, i]) or np.isnan(sh2[k, i]): continue
            if sl1[k, i] > sl2[k, i] and sh1[k, i] > sh2[k, i] and c > sh1[k, i] >= cp and (c - sl1[k, i]) / c <= maxr: out.append((k, 1))
            elif sh1[k, i] < sh2[k, i] and sl1[k, i] < sl2[k, i] and c < sl1[k, i] <= cp and (sh1[k, i] - c) / c <= maxr: out.append((k, -1))
        return out
    return f

def merdiven_iz(d):
    sl1, sh1 = d["sl1"], d["sh1"]
    def iz(k, i, p):
        v = sl1[k, i] * 0.999 if p["u"] == 1 else sh1[k, i] * 1.001
        return None if np.isnan(v) else v
    return iz

def patlama_hazirla(d):
    C, O, V, H, L = d["C"], d["O"], d["V"], d["H"], d["L"]
    d["hm"] = C / O - 1
    ort = (kaydir(V, 1) + kaydir(V, 2) + kaydir(V, 3) + kaydir(V, 4)) / 4
    d["vk"] = V / np.where(ort > 0, ort, np.nan)
    d["uc"] = np.where(C >= O, 1 - C / H, C / L - 1)

def patlama(d, hm=0.03, vk=3.0, uc=0.008):
    EV = d["EV"]; HM, VK, UC = d["hm"], d["vk"], d["uc"]
    def f(i):
        out = []
        for k in np.nonzero(EV[:, i])[0]:
            h = HM[k, i]
            if np.isnan(h) or abs(h) < hm or not (VK[k, i] >= vk) or not (UC[k, i] <= uc): continue
            out.append((k, 1 if h > 0 else -1))
        return out
    return f
