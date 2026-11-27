import sys,time,numpy as np;sys.path.insert(0,'.')
from lab import yukle,evren_hazirla,ozet,TK,MK,KY,NOT
d=yukle('veri');evren_hazirla(d)
O,H,L,C,V,T=d['O'],d['H'],d['L'],d['C'],d['V'],d['T'];N,LL=C.shape
def kay(a,n):
    b=np.full_like(a,np.nan);b[:,n:]=a[:,:-n];return b
# 2 günlük (192 mum) en yüksek/en düşük — sadece geçmiş
from numpy.lib.stride_tricks import sliding_window_view as sw
def rmax(a,w):
    o=np.full_like(a,np.nan);o[:,w-1:]=np.nanmax(sw(a,w,axis=1),axis=2);return o
def rmin(a,w):
    o=np.full_like(a,np.nan);o[:,w-1:]=np.nanmin(sw(a,w,axis=1),axis=2);return o
H2=rmax(H,192);L2=rmin(L,192)
def sim(u,esik,yak,lim,sl,tp,i0,i1,maxa=3,gecerli=192,sure=672):
    bek={};acik={};Tr=[];son={}
    for i in range(i0,i1):
        # bekleyen limitler
        for k in list(bek):
            b=bek[k]
            if i>b['son']: del bek[k];continue
            if (u==1 and L[k,i]<=b['p']) or (u==-1 and H[k,i]>=b['p']):
                if len(acik)<maxa: acik[k]={'g':b['p'],'i':i}
                del bek[k]
        for k in list(acik):
            p=acik[k];g=p['g'];st=g*(1-u*sl);hd=g*(1+u*tp);cik=None
            if np.isnan(C[k,i]): continue
            lo,hi=(L[k,i],H[k,i]) if u==1 else (H[k,i],L[k,i])
            if u*(lo-st)<=0: cik,uc=st*(1-u*KY),TK
            elif u*(hi-hd)>=0: cik,uc=hd,MK
            elif i-p['i']>=sure: cik,uc=C[k,i],TK
            if cik is not None:
                a=NOT/g;Tr.append((T[p['i']],T[i],u,a*u*(cik-g)-NOT*MK-a*cik*uc,k));del acik[k];son[k]=i
        if i%16!=15: continue                        # 4 saatlik mum kapanışı
        for k in np.nonzero(d['v24'][:,i]>=3e6)[0]:
            if k in acik or k in bek or i-son.get(k,-9999)<16: continue
            c=C[k,i]
            if np.isnan(c) or np.isnan(H2[k,i]): continue
            if u==1 and c/H2[k,i]-1<=-esik and c<=L2[k,i]*(1+yak): bek[k]={'p':c*(1-lim),'son':i+gecerli}
            if u==-1 and c/L2[k,i]-1>=esik and c>=H2[k,i]*(1-yak): bek[k]={'p':c*(1+lim),'son':i+gecerli}
    return Tr
B=[200+(LL-200)*q//4 for q in range(5)]
for ad,u,e in (("🔻 DİP LONG (2 günde -%20, dibe %2, %3 aşağı limit, stop %15, hedef %15)",1,0.20),("🔺 TEPE SHORT (2 günde +%30, tepeye %2, %3 yukarı limit, stop %15, hedef %15)",-1,0.30)):
    r=[ozet(sim(u,e,0.02,0.03,0.15,0.15,B[q],B[q+1])) for q in range(4)]
    print(ad);[print('  ay',q+1,x) for q,x in enumerate(r)];print('  TOPLAM',round(sum(x['top'] for x in r),1))
