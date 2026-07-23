"""分析R2(低波区)什么时候结束——历史上R2是怎麼退出的"""
import pandas as pd, numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import StandardScaler

df=pd.read_csv('300442_daily.csv').sort_values('trade_date').reset_index(drop=True)
c=df['close'].values; o=df['open'].values; h=df['high'].values; l=df['low'].values; v=df['vol'].values
n=len(df)
dates=df['trade_date'].astype(str).values

def roll(x,w,fn):
    return pd.Series(x).rolling(w,min_periods=1).apply(fn,raw=True).values

F={}
F['close']=c; F['open']=o; F['high']=h; F['low']=l
F['gap']=np.r_[0,o[1:]-c[:-1]]; F['hl_range']=h-l
for ww in [1,3,5,10,20]:
    ret=np.full(n,np.nan); ret[ww:]=c[ww:]/c[:-ww]-1; ret[:ww]=0
    F[f'ret_{ww}d']=ret
F['log_ret']=np.r_[0,np.log(c[1:]/c[:-1])]
for ww in [5,10,20]:
    F[f'vol_{ww}d']=roll(np.r_[0,np.log(c[1:]/c[:-1])],ww,np.std)
F['atr_14']=roll(np.maximum(h-l,np.maximum(abs(h-np.roll(c,1)),abs(l-np.roll(c,1)))),14,np.mean)
F['hl_vol_20']=roll(np.log(h/l),20,np.std)
for ww in [5,10,20,60]:
    F[f'ma_{ww}d']=roll(c,ww,np.mean)
F['ma5_ma20']=F['ma_5d']/F['ma_20d']-1
ema12=roll(c,12,lambda x:pd.Series(x).ewm(span=12,adjust=False).mean().iloc[-1])
ema26=roll(c,26,lambda x:pd.Series(x).ewm(span=26,adjust=False).mean().iloc[-1])
F['macd']=ema12-ema26
F['macdh']=F['macd']-roll(F['macd'],9,lambda x:pd.Series(x).ewm(span=9,adjust=False).mean().iloc[-1])
for ww in [5,20]: F[f'vol_ma_{ww}d']=roll(v,ww,np.mean)
F['rel_vol']=v/(F['vol_ma_20d']+1e-8)
F['body_ratio']=abs(c-o)/(F['hl_range']+1e-8)
F['wick_body_r']=(h-np.maximum(c,o)+np.minimum(c,o)-l)/(abs(c-o)+1e-8)
for ww in [20]:
    F[f'skew_{ww}d']=roll(np.r_[0,np.log(c[1:]/c[:-1])],ww,lambda x:pd.Series(x).skew())
    F[f'kurt_{ww}d']=roll(np.r_[0,np.log(c[1:]/c[:-1])],ww,lambda x:pd.Series(x).kurt())
F['zscore_20']=(c-roll(c,20,np.mean))/(roll(c,20,np.std)+1e-8)
F['max_ret_20']=roll(np.r_[0,np.log(c[1:]/c[:-1])],20,np.max)
F['min_ret_20']=roll(np.r_[0,np.log(c[1:]/c[:-1])],20,np.min)
F['ret_range_20']=F['max_ret_20']-F['min_ret_20']
for ww in [10,20]:
    F[f'hh_{ww}d']=roll(h,ww,np.max); F[f'll_{ww}d']=roll(l,ww,np.min)
F['bb_position']=(c-F['ll_20d'])/(F['hh_20d']-F['ll_20d']+1e-8)
F['dist_hh20']=F['hh_20d']/c-1; F['dist_ll20']=c/F['ll_20d']-1
F['roc_20']=c/np.roll(c,20)-1

feat_cols=sorted(F.keys())
X_raw=np.column_stack([F[k] for k in feat_cols])
X_raw=np.nan_to_num(X_raw,nan=0.0,posinf=1e8,neginf=-1e8)

trn_cut=int(n*0.6); tr_mask=np.arange(n)<trn_cut; te_mask=~tr_mask
scaler=StandardScaler()
X=X_raw.copy(); X[tr_mask]=scaler.fit_transform(X_raw[tr_mask]); X[te_mask]=scaler.transform(X_raw[te_mask])

regime_feats=[k for k in feat_cols if any(p in k for p in [
    'vol_','ret_','ma5_ma20','macdh','bb_position','rel_vol',
    'zscore_20','skew_','kurt_','body_ratio','dist_hh20','dist_ll20',
    'atr_','roc_','hl_vol','ret_range'
])]
regime_idx=[feat_cols.index(k) for k in regime_feats]
X_regime=X[:,regime_idx]

pca=PCA(n_components=0.90); X_pca=pca.fit_transform(X_regime[tr_mask]); X_pca_all=pca.transform(X_regime)
km=KMeans(n_clusters=3,n_init=20,random_state=42)
r_labels=km.fit_predict(X_pca_all)
dt=DecisionTreeClassifier(max_depth=3,min_samples_leaf=10,random_state=42)
dt.fit(X_regime[tr_mask],r_labels[tr_mask])
r_labels=dt.predict(X_regime)

# ---- R2 exit analysis ----
print("="*65)
print("  R2(低波区) 退出规律分析")
print("="*65)

# Find R2→non-R2 transition points
r2_exits = []
for i in range(1, n):
    if r_labels[i-1]==2 and r_labels[i]!=2:
        r2_exits.append(i)

# For each R2 block, what triggered the exit?
print(f"\n  R2退出共 {len(r2_exits)} 次\n")
print(f"  {'日期':<12s} {'退出前价':>8s} {'进入哪区':>8s} {'触因'}")
print(f"  {'-'*55}")

for exit_idx in r2_exits:
    next_regime = r_labels[exit_idx]
    exit_price = c[exit_idx]
    # What changed?
    vol_20d = F['vol_20d'][exit_idx]
    bb_pos = F['bb_position'][exit_idx]
    # Previous day values
    prev_vol = F['vol_20d'][exit_idx-1]
    prev_bb = F['bb_position'][exit_idx-1]
    
    # Determine trigger
    triggers = []
    if vol_20d > prev_vol * 1.3:
        triggers.append(f"波动率跳升 {prev_vol:.3f}→{vol_20d:.3f}")
    if bb_pos < prev_bb - 0.1:
        triggers.append(f"价格破位 bb={bb_pos:.2f}")
    if abs(F['ret_1d'][exit_idx]) > 0.05:
        triggers.append(f"单日波动{F['ret_1d'][exit_idx]:+.1%}")
    
    reg_name = {0:"震荡区",1:"暴涨区",2:"低波区"}[next_regime]
    trigger_str = ", ".join(triggers) if triggers else "缓慢过渡"
    print(f"  {dates[exit_idx]:<12s} {exit_price:>8.2f} {reg_name:>8s}   {trigger_str}")

# Now: current state
print(f"\n{'='*65}")
print(f"  当前状态: {dates[-1]}")
print(f"{'='*65}")
print(f"  当前Regime: R2(低波区)")
print(f"  价格: {c[-1]:.2f}")
print(f"  vol_20d: {F['vol_20d'][-1]:.4f}")
print(f"  bb_position: {F['bb_position'][-1]:.3f}")
print(f"  R2已持续: {(np.sum(r_labels[-20:]==2))}天 (近20天)")
r2_start_idx = np.where(np.diff(np.r_[[0], r_labels==2])==1)[0]
last_start = r2_start_idx[-1] if len(r2_start_idx)>0 else 0
print(f"  R2连续: 从{dates[last_start]} 至今")
print(f"  持续: {n - last_start} 天")

# Find what would trigger R2 exit (based on decision tree rules)
# R2 rule: bb_position > -0.58 AND vol_20d <= 0.15
# Exit if: bb_position <= -0.58 OR vol_20d > 0.15
print(f"\n  R2退出条件:")
print(f"  ✓ 波动率突破: vol_20d > 0.15  (当前={F['vol_20d'][-1]:.4f})")
print(f"  ✓ 价格极端破位: bb_position <= -0.58  (当前={F['bb_position'][-1]:.3f})")

# What would vol_20d need to become?
v20 = F['vol_20d'][-1]
bb = F['bb_position'][-1]
print(f"\n  距离波动率触发出局: 还需 {0.15-v20:.4f} ({0.15/v20:.1f}x 当前水平)")

# Historical vol_20d distribution
all_v20 = F['vol_20d'][~np.isnan(F['vol_20d'])]
pct = (all_v20 > 0.15).mean() * 100
print(f"  历史上 vol_20d>0.15 占比: {pct:.1f}%")

# Recent vol trend
recent_vol = F['vol_20d'][-10:]
print(f"  近10天vol_20d趋势: {recent_vol[-1]:.4f} (均值={np.mean(recent_vol):.4f})")
if np.mean(recent_vol[-5:]) > np.mean(recent_vol[:5]):
    print(f"  >> 波动率在上升中")
else:
    print(f"  >> 波动率还在下降/横盘")

# Average R2 duration
r2_mask = r_labels == 2
blocks = []
start = None
for i in range(n):
    if r2_mask[i] and start is None: start = i
    if not r2_mask[i] and start is not None:
        blocks.append(i - start)
        start = None
if start is not None: blocks.append(n - start)
# Exclude 1-day blocks
real_blocks = [b for b in blocks if b >= 3]
print(f"\n  R2历史持续天数(≥3天): {sorted(real_blocks)}")
print(f"  平均持续: {np.mean(real_blocks):.0f}天")
print(f"  当前已持续: {blocks[-1] if blocks else '?'}天")
