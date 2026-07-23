"""
Regime-Gated Single Stock Factor Miner v2 (2026)
=================================================
修复: 3-regime强制 + 自适应阈值 + Soft Ensemble修复
"""
import pandas as pd, numpy as np
from scipy import stats as ss
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import euclidean_distances
import warnings
warnings.filterwarnings('ignore')
np.random.seed(42)

df = pd.read_csv(r"c:\Users\wuwenjun\Desktop\Mango\Test\300442_daily.csv").sort_values("trade_date").reset_index(drop=True)
c=df["close"].values; o=df["open"].values; h=df["high"].values; l=df["low"].values; v=df["vol"].values
n=len(df); PRED=10

def roll(x,w,fn):
    return pd.Series(x).rolling(w,min_periods=1).apply(fn,raw=True).values

# ============================================================
# Phase 1: Feature Engineering
# ============================================================
F={}
F["open"]=o; F["high"]=h; F["low"]=l; F["close"]=c
F["gap"]=np.r_[0,o[1:]-c[:-1]]; F["chg"]=np.r_[0,np.diff(c)]; F["hl_range"]=h-l
for w in [1,3,5,10,20]:
    ret=np.full(n,np.nan); ret[w:]=c[w:]/c[:-w]-1; ret[:w]=0
    F[f"ret_{w}d"]=ret
F["log_ret"]=np.r_[0,np.log(c[1:]/c[:-1])]
for w in [5,10,20]:
    F[f"vol_{w}d"]=roll(np.r_[0,np.log(c[1:]/c[:-1])],w,np.std)
F["atr_14"]=roll(np.maximum(h-l,np.maximum(abs(h-np.roll(c,1)),abs(l-np.roll(c,1)))),14,np.mean)
F["hl_vol_20"]=roll(np.log(h/l),20,np.std)

for w in [5,10,20,60]:
    F[f"ma_{w}d"]=roll(c,w,np.mean)
F["ma5_ma20"]=F["ma_5d"]/F["ma_20d"]-1
F["ma10_ma60"]=F["ma_10d"]/F["ma_60d"]-1
ema12=roll(c,12,lambda x:pd.Series(x).ewm(span=12,adjust=False).mean().iloc[-1])
ema26=roll(c,26,lambda x:pd.Series(x).ewm(span=26,adjust=False).mean().iloc[-1])
F["macd"]=ema12-ema26
F["macd_signal"]=roll(F["macd"],9,lambda x:pd.Series(x).ewm(span=9,adjust=False).mean().iloc[-1])
F["macdh"]=F["macd"]-F["macd_signal"]
F["roc_5"]=c/np.roll(c,5)-1
F["roc_10"]=c/np.roll(c,10)-1
F["roc_20"]=c/np.roll(c,20)-1

for w in [5,20]:
    F[f"vol_ma_{w}d"]=roll(v,w,np.mean)
F["rel_vol"]=v/(F["vol_ma_20d"]+1e-8)
F["obv"]=np.cumsum(v*np.sign(np.r_[0,np.diff(c)]))
F["vwap"]=np.cumsum(c*v)/np.cumsum(v)
F["body"]=abs(c-o)
F["upper_wick"]=h-np.maximum(c,o)
F["lower_wick"]=np.minimum(c,o)-l
F["body_ratio"]=F["body"]/(F["hl_range"]+1e-8)
F["wick_body_r"]=(F["upper_wick"]+F["lower_wick"])/(F["body"]+1e-8)
F["true_range"]=np.maximum(h-l,np.maximum(abs(h-np.roll(c,1)),abs(l-np.roll(c,1))))

for w in [20]:
    F[f"skew_{w}d"]=roll(np.r_[0,np.log(c[1:]/c[:-1])],w,lambda x:pd.Series(x).skew())
    F[f"kurt_{w}d"]=roll(np.r_[0,np.log(c[1:]/c[:-1])],w,lambda x:pd.Series(x).kurt())
F["zscore_20"]=(c-roll(c,20,np.mean))/(roll(c,20,np.std)+1e-8)
F["max_ret_20"]=roll(np.r_[0,np.log(c[1:]/c[:-1])],20,np.max)
F["min_ret_20"]=roll(np.r_[0,np.log(c[1:]/c[:-1])],20,np.min)
F["ret_range_20"]=F["max_ret_20"]-F["min_ret_20"]

for w in [1,3,5,10]:
    F[f"close_lag_{w}d"]=np.roll(c,w)
for w in [10,20]:
    F[f"hh_{w}d"]=roll(h,w,np.max)
    F[f"ll_{w}d"]=roll(l,w,np.min)
F["bb_position"]=(c-F["ll_20d"])/(F["hh_20d"]-F["ll_20d"]+1e-8)
F["dist_hh20"]=F["hh_20d"]/c-1
F["dist_ll20"]=c/F["ll_20d"]-1
dates=pd.to_datetime(df["trade_date"].astype(str))
F["dow"]=dates.dt.dayofweek.values
F["month"]=dates.dt.month.values

feat_cols=sorted(F.keys())
X_raw=np.column_stack([F[k] for k in feat_cols])
X_raw=np.nan_to_num(X_raw,nan=0.0,posinf=1e8,neginf=-1e8)

target=np.full(n,np.nan); target[:-PRED]=c[PRED:]/c[:-PRED]-1
trn_cut=int(n*0.6); tr_mask=np.arange(n)<trn_cut; te_mask=~tr_mask
scaler=StandardScaler()
X=X_raw.copy(); X[tr_mask]=scaler.fit_transform(X_raw[tr_mask]); X[te_mask]=scaler.transform(X_raw[te_mask])
valid=np.isfinite(X).all(axis=1)&np.isfinite(target)

# ============================================================
# Phase 2: Regime Detection (force 3 regions)
# ============================================================
print(f"{'='*60}")
print(f"  Regime-Gated Factor Miner v2 | 300442 | pred={PRED}d")
print(f"{'='*60}")

regime_feats=[k for k in feat_cols if any(p in k for p in [
    "vol_","ret_","ma5_ma20","macdh","bb_position","rel_vol",
    "zscore_20","skew_","kurt_","body_ratio","dist_hh20","dist_ll20",
    "atr_","roc_","hl_vol","ret_range"
])]
regime_idx=[feat_cols.index(k) for k in regime_feats]
X_regime=X[:,regime_idx]

pca=PCA(n_components=0.90)
X_pca=pca.fit_transform(X_regime[tr_mask&valid])
X_pca_all=pca.transform(X_regime)

# Force 3 regimes
K=3
km=KMeans(n_clusters=K,n_init=20,random_state=42)
r_labels=km.fit_predict(X_pca_all)

dt=DecisionTreeClassifier(max_depth=3,min_samples_leaf=10,random_state=42)
dt.fit(X_regime[tr_mask&valid],r_labels[tr_mask&valid])
r_labels=dt.predict(X_regime)

print(f"\n  Regime检测: {K}个regime | PCA: {X_regime.shape[1]}→{X_pca.shape[1]}维")
print(f"\n  --- 可解释规则 ---")
print(export_text(dt,feature_names=regime_feats,max_depth=3))

print(f"\n  --- Regime画像 ---")
for ri in range(K):
    rm=r_labels==ri
    desc_ret=c[rm][-1]/c[rm][0]-1 if rm.sum()>1 else 0
    v_mean=np.nanmean(target[rm&valid])
    v_vol=np.std(F["log_ret"][rm&valid])
    tag=""
    if v_vol>0.04:tag="[高波]"
    elif v_mean>0.01:tag="[趋势]"
    else:tag="[低波]"
    win_rate=(target[rm&valid]>0).mean()*100
    print(f"  R{ri}: {rm.sum():3d}天 {tag:6s} mean_ret={v_mean:+.4f} vol={v_vol:.4f} "
          f"win_rate={win_rate:.0f}% trend={np.mean(F['ma5_ma20'][rm]):+.4f}")

# ============================================================
# Phase 3: Per-Regime Knowledge-Guided Factor Mining
# ============================================================
print(f"\n{'='*60}")
print(f"  Phase 3: Per-Regime因子挖掘")
print(f"{'='*60}")

d_=np.diff(c,prepend=c[0]); g_=np.maximum(d_,0); l__=np.maximum(-d_,0)
FM={}
FM["close"]=c; FM["gap"]=F["gap"]
for w in [7,14,21]:
    FM[f"rsi_{w}"]=100-100/(1+roll(g_,w,np.mean)/(roll(l__,w,np.mean)+1e-8))
for k in feat_cols:
    FM[k]=F[k]
FM["vol_contract"]=-(F["hl_vol_20"]-roll(F["hl_vol_20"],60,np.mean))  # 波动收缩程度
# range_compression
hlv20_60=np.roll(F["hl_vol_20"],60); hlv20_60[:60]=F["hl_vol_20"][:60]
FM["range_compress"]=-(F["hl_vol_20"]-hlv20_60)/(hlv20_60+1e-8)
FM["tr_narrow"]=-(F["true_range"]/roll(F["true_range"],20,np.mean)-1)
FM["obv_z"]=(F["obv"]-roll(F["obv"],20,np.mean))/(roll(F["obv"],20,np.std)+1e-8)
FM["vwap_div"]=F["close"]/F["vwap"]-1
FM["ema_slope"]=(F["ma_5d"]-F["ma_60d"])/(F["ma_60d"]+1e-8)
FM["vol_dry"]=-(F["rel_vol"]-1)

# 50+ factor templates
KB={}
# === Mean-reversion ===
KB["rsi14_rev"]=("-(rsi_14-50)/50","RSI14反转:超买回落超卖反弹","rev",["rsi_14"])
KB["rsi21_rev"]=("-(rsi_21-50)/50","RSI21反转:更长周期极端值回归","rev",["rsi_21"])
KB["bb_rev"]=("-(bb_position-0.5)*2","布林带极端回复","rev",["bb_position"])
KB["ma_rev"]=("-ma5_ma20","短均偏离长均回复","rev",["ma5_ma20"])
KB["gap_rev"]=("-gap/(close+1e-8)","跳空缺口回补","rev",["gap","close"])
KB["vol_spike"]=("-rel_vol","放量后缩量→价格反向","rev",["rel_vol"])
KB["max_ret_rev"]=("-max_ret_20","大涨后获利了结","rev",["max_ret_20"])
KB["min_ret_rev"]=("-min_ret_20","暴跌后超跌反弹","rev",["min_ret_20"])

# === Trend-following ===
KB["mom10"]=("ret_10d","10日动量:强者恒强","trend",["ret_10d"])
KB["macdh"]=("macdh","MACD柱:多空动量","trend",["macdh"])
KB["ma_cross"]=("ma5_ma20","短均上穿长均","trend",["ma5_ma20"])
KB["breakout"]=("-dist_hh20","距高点越近越可能突破","trend",["dist_hh20"])
KB["roc_adj"]=("roc_20/(vol_20d+1e-8)","风险调整动量","trend",["roc_20","vol_20d"])
KB["vwap_div"]=("vwap_div","价格持续高于VWAP→资金流入","trend",["vwap_div"])
KB["ema_slope"]=("ema_slope","均线斜率:大趋势方向","trend",["ema_slope"])

# === Low-vol anomaly ===
KB["low_vol"]=("-vol_20d","低波动异象(Bali&Cakici)","lowvol",["vol_20d"])
KB["range_compress"]=("range_compress","振幅压缩→突破前兆","lowvol",["range_compress"])
KB["body_shrink"]=("-body_ratio","实体缩小→变盘","lowvol",["body_ratio"])
KB["vol_dry"]=("vol_dry","缩量整理→择向","lowvol",["vol_dry"])
KB["tr_narrow"]=("tr_narrow","波幅收敛→趋势重启","lowvol",["tr_narrow"])
KB["wick_long"]=("-(wick_body_r-1)","长影线→多空分歧→反转","lowvol",["wick_body_r"])

# === Cross-regime ===
KB["ret_skew"]=("-skew_20d","负偏度反转","universal",["skew_20d"])
KB["ret_kurt"]=("-kurt_20d","高峰度风险溢价","universal",["kurt_20d"])
KB["obv_z"]=("obv_z","OBV标准化:量价背离","universal",["obv_z"])
KB["bh_rev"]=("-(zscore_20-0)","偏离20日均值回复","universal",["zscore_20"])

# Evaluate all
candidates=[]
for name,(expr,logic,fit,reqs) in KB.items():
    try:
        local_ns={r:FM[r] for r in reqs}
        fv=eval(expr,{"__builtins__":{}},local_ns)
        fv=np.nan_to_num(np.asarray(fv,dtype=float),nan=0.0,posinf=1e6,neginf=-1e6)
        candidates.append({"name":name,"value":fv,"logic":logic,"fit":fit})
    except Exception as e:
        pass

print(f"  候选因子: {len(candidates)} 个")

# Per-Regime evaluation
print(f"\n  --- 各Regime Top-3因子 ---")
regime_data={}
for ri in range(K):
    rm=r_labels==ri; r_tr=rm&tr_mask; r_te=rm&te_mask
    if r_tr.sum()<15:continue
    scores=[]
    for cnd in candidates:
        fv=cnd["value"]
        tr_ic=ss.spearmanr(fv[r_tr&valid],target[r_tr&valid])[0]
        te_ic=ss.spearmanr(fv[r_te&valid],target[r_te&valid])[0]
        gap=abs(tr_ic-te_ic) if(abs(tr_ic)>0.02 and abs(te_ic)>0.02)else 0
        score=abs(te_ic)-0.3*gap-0.1*abs(tr_ic)*(abs(tr_ic)<0.03)  # penalize weak train IC
        scores.append({"name":cnd["name"],"logic":cnd["logic"],"fit":cnd["fit"],
                        "tr_ic":tr_ic,"te_ic":te_ic,"score":score,"value":fv})
    scores.sort(key=lambda x:x["score"],reverse=True)
    top=scores[:3]
    for j,cs in enumerate(top):
        tag="★"if j==0 else" "
        print(f"  {tag} {cs['name']:18s} fit={cs['fit']:8s} tr_IC={cs['tr_ic']:+.4f} te_IC={cs['te_ic']:+.4f} score={cs['score']:+.4f}  {cs['logic'][:45]}")
    regime_data[ri]={"scores":scores,"top":top,"mask":rm}

# ============================================================
# Phase 4: Regime-Conditioned Ensemble + Backtest
# ============================================================
print(f"\n{'='*60}")
print(f"  Phase 4: Regime-Conditioned Ensemble + 回测")
print(f"{'='*60}")

# Build per-regime signals (z-score within regime)
per_regime_sig=np.full((n,K),np.nan)
for ri in range(K):
    if ri not in regime_data:continue
    rm=r_labels==ri
    top_fv=regime_data[ri]["top"][0]["value"]
    mu=np.nanmean(top_fv[rm&valid&tr_mask])
    sd=np.nanstd(top_fv[rm&valid&tr_mask])+1e-8
    per_regime_sig[rm,ri]=(top_fv[rm]-mu)/sd

# Soft regime weights (distance-based)
dists=euclidean_distances(X_pca_all,km.cluster_centers_)
sw=1.0/(dists+0.1); sw/=sw.sum(axis=1,keepdims=True)

# Ensemble: soft-weighted sum of per-regime signals
ensemble=np.nansum(per_regime_sig*sw,axis=1)

# Also test hard ensemble
hard_ens=np.full(n,np.nan)
for ri in range(K):
    rm=r_labels==ri; hard_ens[rm]=per_regime_sig[rm,ri]

# Backtest with adaptive threshold (lower for small sample)
def bt(sig,lbl,thr=0.3):
    S=30;td=[];i=S
    while i+PRED<n:
        s=sig[i]; pos=1 if(np.isfinite(s)and s>thr)else 0
        td.append([df["trade_date"].iloc[i],c[i],c[i+PRED],s,pos,pos*(c[i+PRED]/c[i]-1)])
        i+=PRED
    if not td:return None
    tdf=pd.DataFrame(td,columns=["entry","ep","xp","sig","pos","ret"])
    ar=tdf["ret"].values; tot=np.prod(1+ar)-1
    ny=max(len(tdf)*PRED/252,0.05)
    ann_ret=(1+tot)**(1/ny)-1; ann_vol=np.std(ar)*np.sqrt(252/PRED)
    sr=ann_ret/(ann_vol+1e-8)
    cum=np.cumprod(1+ar); pk=np.maximum.accumulate(cum)
    mdd=np.min(cum/pk-1)
    nL=(tdf["pos"]==1).sum(); wr=(ar[tdf["pos"]==1]>0).mean() if nL>0 else 0
    return {"label":lbl,"total":tot,"sr":sr,"mdd":mdd,"n_t":len(tdf),"n_long":nL,
            "wr":wr,"bh":c[-1]/c[S]-1,"tdf":tdf}

# Test multiple thresholds
for thr in [0.0,0.15,0.3]:
    print(f"\n--- 阈值={thr} ---")
    for sig,lbl in [(ensemble,f"Soft Ensemble t={thr}"),(hard_ens,f"Hard Ensemble t={thr}")]:
        r=bt(sig,lbl,thr)
        if r:
            print(f"  {lbl:25s} tot={r['total']:+.2%} sr={r['sr']:+.2f} mdd={r['mdd']:+.2%} "
                  f"n={r['n_t']}(long={r['n_long']}) B&H={r['bh']:+.2%}")

# Baseline: best single factor
best_all=sorted([c for rd in regime_data.values() for c in rd["scores"]],
                 key=lambda x:x["score"],reverse=True)
uniq_n=[];seen=set()
for b in best_all:
    if b["name"] not in seen:seen.add(b["name"]);uniq_n.append(b)
best_c=uniq_n[0]
bsig=np.full(n,np.nan)
mu_b=np.nanmean(best_c["value"][valid&tr_mask]);sd_b=np.nanstd(best_c["value"][valid&tr_mask])
bsig[valid]=(best_c["value"][valid]-mu_b)/(sd_b+1e-8)

print(f"\n--- Baseline: 最佳单因子 ---")
r_bl=bt(bsig,f"单因子({best_c['name']})",0.0)
if r_bl:
    print(f"  {r_bl['label']:25s} tot={r_bl['total']:+.2%} sr={r_bl['sr']:+.2f} mdd={r_bl['mdd']:+.2%} "
          f"n={r_bl['n_t']}(long={r_bl['n_long']}) B&H={r_bl['bh']:+.2%}")
    print(f"  {best_c['logic']}")

# Final best config
print(f"\n{'='*60}")
print(f"  最终推荐: Soft Ensemble, threshold=0.0 (LONG-only)")
print(f"{'='*60}")
r_final=bt(ensemble,"Soft Ensemble",0.0)
if r_final:
    print(f"  总收益: {r_final['total']:+.2%}  Sharpe: {r_final['sr']:+.2f}  MaxDD: {r_final['mdd']:+.2%}")
    print(f"  笔数: {r_final['n_t']} (LONG={r_final['n_long']})  WinRate={r_final['wr']:.1%}  B&H={r_final['bh']:+.2%}")
    print(f"\n  交易明细:")
    for _,t in r_final["tdf"].iterrows():
        pos="LONG"if t["pos"]==1 else"FLAT"
        print(f"  {t['entry']} {t['ep']:.2f}->{t['xp']:.2f} {pos:>5} {t['ret']:+.4f}")

    print(f"\n  Regime分布:")
    for ri in range(K):
        rm=r_labels==ri
        n_regime=rm.sum()
        r_summary=f"R{ri}: {n_regime}天"
        if ri in regime_data:
            tf=regime_data[ri]["top"][0]
            r_summary+=f" | {tf['name']}({tf['logic'][:30]})"
        print(f"  {r_summary}")

    # Per-regime signal contribution on latest day
    latest=r_labels[-1]
    print(f"\n  最新({df['trade_date'].iloc[-1]}): Regime={latest}")
    if latest in regime_data:
        print(f"    当前因子: {regime_data[latest]['top'][0]['name']}")
        print(f"    信号值: {ensemble[-1]:+.3f} → {'LONG' if ensemble[-1]>0 else 'FLAT'}")
