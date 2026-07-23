# ================================================================
# 微盘股因子自主Regime发现 — PS-Tree 混合架构（决策树分裂 + GP叶公式）
# 聚宽研究环境 | 预计 15-25 分钟 | 自主发现regime边界+分段因子公式
#
# 架构（参考 PS-Tree, Zhang et al., Swarm and Evolutionary Computation, 2022）：
#   sklearn DecisionTreeRegressor  → 自动学习"哪里切"（特征+阈值）
#   deap GP (每叶子独立)          → 自动搜索"每个regime用啥公式"
#   合并 Piecewise 表达式          → 可解释分段因子
#
# 用法：粘贴到聚宽研究环境 Jupyter Notebook，全选运行
# ================================================================

from jqdata import *
from jqfactor import *
import pandas as pd
import numpy as np
import datetime as dt
import random
import operator
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

from sklearn.tree import DecisionTreeRegressor
from deap import base, creator, tools, gp, algorithms

# ── 公共工具引用 ──
from factorUtil import (
    factorUtil,
    v_add, v_sub, v_mul, v_div, v_rank, v_abs, v_log, v_neg, v_max, v_min, v_sgn,
)
from evaluateUtil import evaluateUtil

# ==================== 参数 ====================
TRAIN_START   = '2023-01-01'
TRAIN_END     = '2024-12-31'
VAL_START     = '2025-01-01'
VAL_END       = '2026-05-01'
N_STOCKS      = 500
FREQ           = 'monthly'   # 'weekly' | 'monthly' — 周频/月频挖掘切换
TREE_MAX_DEPTH   = 2       # 决策树深度 → 最多 2^depth=4 个regime
TREE_MIN_LEAF    = 300     # 每叶子最少样本数（上次100切出1430样本小叶子过拟合）
GP_POP_SIZE      = 50      # 每叶子GP种群
GP_N_GEN         = 25      # 每叶子GP代数

# ================================================================
# Step 1/5: 准备微盘股票池数据（与现有流程完全一致）
# ================================================================
print("=" * 60)
print(f"Step 1/5: 准备微盘股票池数据（全池，无预聚类，freq={FREQ}）")
print("=" * 60)

# ── 频率自适应日期生成 ──
if FREQ == 'monthly':
    eval_dates, fwd_dates = factorUtil.build_monthly_cycle(TRAIN_START, VAL_END)
    # 月频：特征取值日 = 调仓日（每月第一个周二），前向终点 = 次月第一个周二
    feature_dates = eval_dates
else:
    weekly_tue, weekly_mon = factorUtil.build_weekly_cycle(TRAIN_START, VAL_END)
    # 周频：eval_dates=本周二, feature_dates=本周一（匹配 context.previous_date）, fwd_dates=下周一
    eval_dates    = [weekly_tue[i] for i in range(len(weekly_tue) - 1)]
    feature_dates = [weekly_mon[i] for i in range(len(weekly_tue) - 1)]
    fwd_dates     = [weekly_mon[i + 1] for i in range(len(weekly_tue) - 1)]

sec_df, st_raw, eligible_static = factorUtil.init_stock_filter(TRAIN_START, VAL_END)

feature_names = None
train_data = {}
val_data   = {}
all_labels = {}

for i in range(len(eval_dates)):
    d = eval_dates[i]               # 调仓日（池子筛选 & 前向收益起点）
    factor_d = feature_dates[i]      # 因子特征取值日
    nd = fwd_dates[i]                # 前向收益终点
    d_str = d.strftime('%Y-%m-%d')
    factor_d_str = factor_d.strftime('%Y-%m-%d')
    nd_str = nd.strftime('%Y-%m-%d')
    is_train = d_str <= TRAIN_END

    try:
        all_stocks = factorUtil.get_eligible_stocks_research(d, eligible_static, sec_df, st_raw)
        q = query(valuation.code, valuation.circulating_market_cap,
                  valuation.market_cap, valuation.pb_ratio
                  ).filter(valuation.code.in_(all_stocks)
                  ).order_by(valuation.circulating_market_cap.asc()
                  ).limit(N_STOCKS)
        fund = get_fundamentals(q, date=d_str).set_index('code')
        if len(fund) < 100:
            continue
        stocks_here = list(fund.index)

        lag_date = (factor_d - dt.timedelta(days=35)).strftime('%Y-%m-%d')
        prices = get_price(stocks_here, start_date=lag_date, end_date=factor_d_str,
                          frequency='daily',
                          fields=['close','volume','high','low'],
                          panel=False)

        cls = factorUtil.to_wide(prices, 'close', stocks_here)
        vol = factorUtil.to_wide(prices, 'volume', stocks_here)
        hgh = factorUtil.to_wide(prices, 'high', stocks_here)
        low = factorUtil.to_wide(prices, 'low', stocks_here)
        # ── rank1M对齐: 停牌过滤 ──
        stocks_here, cls, vol, hgh, low = factorUtil.filter_suspended_research(stocks_here, vol, cls, hgh, low)

        n_cols = cls.shape[1]
        if n_cols < 5 or len(stocks_here) < 50:
            continue

        feat = factorUtil.build_features(cls, vol, hgh, low, fund)
        if len(feat) < 50:
            continue
        stocks_aligned = list(feat.index)

        if feature_names is None:
            feature_names = sorted(feat.columns.tolist())

        feat_dict = {c: feat[c].values for c in feature_names}

        fwd_p = get_price(stocks_aligned, start_date=d_str, end_date=nd_str,
                         frequency='daily', fields=['close'], panel=False)
        fwd_w = fwd_p.pivot(index='code', columns='time', values='close')
        fwd_w = fwd_w.reindex(stocks_aligned)
        if fwd_w.shape[1] < 2:
            continue
        fwd_ret = fwd_w.iloc[:, -1] / fwd_w.iloc[:, 0] - 1
        fwd_ret = fwd_ret.dropna()

        common_idx = list(set(stocks_aligned) & set(fwd_ret.index))
        if len(common_idx) < 50:
            continue
        common_idx.sort(key=lambda x: stocks_aligned.index(x))

        feat_dict = {c: v[[stocks_aligned.index(s) for s in common_idx]]
                     for c, v in feat_dict.items()}
        label_arr = fwd_ret[common_idx].values

        target_dict = train_data if is_train else val_data
        target_dict[d_str] = feat_dict
        all_labels[d_str] = label_arr

    except Exception as e:
        pass

for d in list(train_data.keys()):
    if d not in all_labels:
        del train_data[d]
for d in list(val_data.keys()):
    if d not in all_labels:
        del val_data[d]
for d in list(all_labels.keys()):
    if d not in train_data and d not in val_data:
        del all_labels[d]

train_dates = sorted([d for d in train_data])
val_dates   = sorted([d for d in val_data])

unit = '月' if FREQ == 'monthly' else '周'
print(f"训练集: {len(train_dates)} {unit}, 验证集: {len(val_dates)} {unit}")
print(f"特征 ({len(feature_names)}): {feature_names}")

# ================================================================
# Step 2/5: 决策树学习Regime分裂边界
# ================================================================
print("\n" + "=" * 60)
print(f"Step 2/5: 决策树学习Regime分裂 (max_depth={TREE_MAX_DEPTH}, min_leaf={TREE_MIN_LEAF})")
print("=" * 60)

# 堆叠全部训练期数据为 (样本数, 特征数) 矩阵
X_list, y_list = [], []
for d_str in train_dates:
    feats = train_data[d_str]
    X_i = np.column_stack([feats[n] for n in feature_names])
    y_i = all_labels[d_str]
    mask = np.isfinite(X_i).all(axis=1) & np.isfinite(y_i)
    if mask.sum() >= 30:
        X_list.append(X_i[mask])
        y_list.append(y_i[mask])

X_train = np.vstack(X_list)
y_train = np.hstack(y_list)
print(f"堆叠训练矩阵: {X_train.shape} (样本={X_train.shape[0]}, 特征={X_train.shape[1]})")

# 训练决策树
dtree = DecisionTreeRegressor(
    max_depth=TREE_MAX_DEPTH,
    min_samples_leaf=TREE_MIN_LEAF,
    random_state=42,
)
dtree.fit(X_train, y_train)

n_leaves = sum(1 for i in range(dtree.tree_.node_count)
               if dtree.tree_.children_left[i] == dtree.tree_.children_right[i])
print(f"决策树节点数: {dtree.tree_.node_count}, 叶节点(Regime)数: {n_leaves}")

# --- 提取决策树的分裂结构 ---
tree = dtree.tree_

def extract_tree_paths():
    """提取从根到每个叶子的路径条件。
       返回: list of (leaf_id, [(feature_name, threshold, is_left), ...])
       is_left=True 表示 '<= threshold', False 表示 '> threshold'
    """
    paths = []
    def traverse(node_id, conditions):
        if tree.children_left[node_id] == tree.children_right[node_id]:  # leaf
            paths.append((node_id, list(conditions)))
            return
        feat_name = feature_names[tree.feature[node_id]]
        thresh = tree.threshold[node_id]
        # 左子: <= threshold
        traverse(tree.children_left[node_id],
                conditions + [(feat_name, thresh, True)])
        # 右子: > threshold
        traverse(tree.children_right[node_id],
                conditions + [(feat_name, thresh, False)])
    traverse(0, [])
    return paths

leaf_paths = extract_tree_paths()
leaf_seq = {lid: i+1 for i, (lid, _) in enumerate(leaf_paths)}

print(f"\n决策树发现的Regime结构:")
for leaf_id, conds in leaf_paths:
    parts = []
    for fn, th, is_left in conds:
        op = "<=" if is_left else ">"
        parts.append(f"{fn} {op} {th:.4g}")
    print(f"  R{leaf_seq[leaf_id]} (leaf {leaf_id}): {' AND '.join(parts)}")

# ================================================================
# Step 3/5: 每个Regime内独立运行GP搜索最优因子公式
# ================================================================
print("\n" + "=" * 60)
print(f"Step 3/5: 各Regime内GP搜索因子公式 ({len(leaf_paths)} 个叶子)")
print("=" * 60)

# 向量运算符已从 factorUtil 导入 (v_add, v_sub, v_mul, v_div, v_rank, v_abs, v_log, v_neg, v_max, v_min, v_sgn)

# ---- 为每个叶子构建对应数据的辅助函数 ----
def get_leaf_mask(feats_dict, conditions):
    """根据决策树路径条件，计算哪些样本属于该叶子。"""
    mask = None
    for fn, th, is_left in conditions:
        vals = feats_dict[fn]
        if is_left:
            m = vals <= th
        else:
            m = vals > th
        mask = m if mask is None else (mask & m)
    return mask

def build_leaf_train_data(leaf_conditions, train_dates, train_data, all_labels, feature_names):
    """提取属于该叶子的所有训练期样本"""
    X_list, y_list = [], []
    for d_str in train_dates:
        feats = train_data[d_str]
        labels = all_labels[d_str]
        mask = get_leaf_mask(feats, leaf_conditions)
        mask = mask & np.isfinite(labels)
        for fn in feature_names:
            mask = mask & np.isfinite(feats[fn])
        if mask.sum() < 5:   # 放宽门槛：小叶子也能跑GP
            continue
        X_list.append({fn: feats[fn][mask] for fn in feature_names})
        y_list.append(labels[mask])
    return X_list, y_list

# ---- 为每个叶子跑GP ----
leaf_formulas = {}   # leaf_id → (compiled_func, expression_str, train_ic)
leaf_gp_stats  = {}  # leaf_id → dict of stats

for leaf_idx, (leaf_id, conditions) in enumerate(leaf_paths):
    print(f"\n{'─'*50}")
    cond_desc = ' & '.join(
        f"{fn}{'<=' if il else '>'}{th:.3g}" for fn, th, il in conditions)
    print(f"Regime {leaf_idx+1}/{len(leaf_paths)}: [{cond_desc}]")

    leaf_X, leaf_y = build_leaf_train_data(
        conditions, train_dates, train_data, all_labels, feature_names)

    n_periods = len(leaf_X)
    n_samples = sum(len(y) for y in leaf_y)
    use_pooled = (n_periods < 15)  # 极小子集按月IC不可靠 → 池化评估
    print(f"  训练数据: {n_periods} 期, {n_samples} 样本{' (池化评估)' if use_pooled else ''}")

    if n_periods < 5 or n_samples < 100:
        print(f"  ⚠️ 数据不足，合并到同级Regime")
        continue

    # --- 构建GP引擎 ---
    # 清理Jupyter重跑残留
    for name in ['FitnessMax', 'Individual']:
        if name in creator.__dict__:
            del creator.__dict__[name]

    pset = gp.PrimitiveSet("MAIN", len(feature_names))
    pset.addPrimitive(v_add, 2)
    pset.addPrimitive(v_sub, 2)
    pset.addPrimitive(v_mul, 2)
    pset.addPrimitive(v_div, 2)
    pset.addPrimitive(v_rank, 1)
    pset.addPrimitive(v_abs, 1)
    pset.addPrimitive(v_log, 1)
    pset.addPrimitive(v_neg, 1)
    pset.addPrimitive(v_max, 2)
    pset.addPrimitive(v_min, 2)
    pset.addPrimitive(v_sgn, 1)
    pset.renameArguments(**{f"ARG{i}": n for i, n in enumerate(feature_names)})

    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)

    toolbox = base.Toolbox()
    toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=1, max_=3)
    toolbox.register("individual", tools.initIterate,
                     creator.Individual, toolbox.expr)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("compile", gp.compile, pset=pset)

    # 小叶子检测：如果按月数据不足，自动池化（合并全时段算IC）

    def eval_leaf_factor(ind, leaf_X, leaf_y, feat_names, do_pooled):
        try:
            func = toolbox.compile(ind)
        except:
            return (-999,)
        if do_pooled:
            # 池化模式：全时段合并，算一次IC
            all_pred, all_actual = [], []
            for feats, labels in zip(leaf_X, leaf_y):
                try:
                    args = [feats[n] for n in feat_names]
                    all_pred.append(func(*args).flatten())
                    all_actual.append(labels.flatten())
                except: pass
            if not all_pred:
                return (-999,)
            pred_pool = np.concatenate(all_pred)
            actual_pool = np.concatenate(all_actual)
            mask = np.isfinite(pred_pool) & np.isfinite(actual_pool)
            if mask.sum() < 30:
                return (-999,)
            ic = np.corrcoef(pred_pool[mask], actual_pool[mask])[0, 1]
            if not np.isfinite(ic) or abs(ic) < 1e-10:
                return (-999,)
            # 拦截退化解：预测值方差≈0 → 常数输出
            if np.std(pred_pool[mask]) < 1e-10:
                return (-999,)
            return (ic,)
        else:
            ics = []
            for feats, labels in zip(leaf_X, leaf_y):
                try:
                    args = [feats[n] for n in feat_names]
                    pred = func(*args).flatten()
                    actual = labels.flatten()
                    mask = np.isfinite(pred) & np.isfinite(actual)
                    if mask.sum() >= 5:
                        ic = np.corrcoef(pred[mask], actual[mask])[0, 1]
                        if np.isfinite(ic):
                            ics.append(ic)
                except: pass
            if len(ics) < 5:
                return (-999,)
            std_ic = np.std(ics)
            # 拦截退化解：常数输出 → std≈0 → 无预测力
            if std_ic < 1e-8:
                return (-999,)
            return (np.mean(ics) - 0.5 * std_ic,)

    toolbox.register("evaluate", eval_leaf_factor,
                     leaf_X=leaf_X, leaf_y=leaf_y, feat_names=feature_names,
                     do_pooled=use_pooled)
    toolbox.register("select", tools.selTournament, tournsize=3)
    toolbox.register("mate", gp.cxOnePoint)
    toolbox.register("expr_mut", gp.genFull, min_=0, max_=2)
    toolbox.register("mutate", gp.mutUniform,
                     expr=toolbox.expr_mut, pset=pset)
    toolbox.decorate("mate", gp.staticLimit(
        key=operator.attrgetter('height'), max_value=8))
    toolbox.decorate("mutate", gp.staticLimit(
        key=operator.attrgetter('height'), max_value=8))

    random.seed(42 + leaf_idx)
    np.random.seed(42 + leaf_idx)

    pop = toolbox.population(n=GP_POP_SIZE)
    hof = tools.HallOfFame(1)  # 各叶子独立取最优公式

    stats = tools.Statistics(lambda ind: ind.fitness.values[0])
    stats.register("avg", np.mean)
    stats.register("max", np.max)

    pop, logbook = algorithms.eaSimple(
        pop, toolbox, cxpb=0.5, mutpb=0.2, ngen=GP_N_GEN,
        stats=stats, halloffame=hof, verbose=False
    )

    # 取HOF最优
    if len(hof) == 0:
        print(f"  ⚠️ HOF空，跳过")
        continue
    best_ind = hof[0]
    try:
        best_func = toolbox.compile(best_ind)
        best_str = str(best_ind)
    except:
        print(f"  ⚠️ 公式编译失败")
        continue

    # 快速计算训练IC
    if use_pooled:
        all_pred_c, all_actual_c = [], []
        for feats, labels in zip(leaf_X, leaf_y):
            try:
                args = [feats[n] for n in feature_names]
                all_pred_c.append(best_func(*args).flatten())
                all_actual_c.append(labels.flatten())
            except: pass
        if all_pred_c:
            pp = np.concatenate(all_pred_c)
            aa = np.concatenate(all_actual_c)
            mask = np.isfinite(pp) & np.isfinite(aa)
            train_ic = np.corrcoef(pp[mask], aa[mask])[0, 1] if mask.sum() >= 30 else -999.0
        else:
            train_ic = -999.0
    else:
        ics_c = []
        for feats, labels in zip(leaf_X, leaf_y):
            try:
                args = [feats[n] for n in feature_names]
                pred = best_func(*args).flatten()
                actual = labels.flatten()
                mask = np.isfinite(pred) & np.isfinite(actual)
                if mask.sum() >= 5:
                    ic = np.corrcoef(pred[mask], actual[mask])[0, 1]
                    if np.isfinite(ic): ics_c.append(ic)
            except: pass
        train_ic = np.mean(ics_c) if ics_c else -999.0

    train_ir = train_ic / np.std(ics_c) if (not use_pooled and ics_c and np.std(ics_c) > 1e-12) else 0.0

    print(f"  最优公式: {best_str[:70]}{'...' if len(best_str) > 70 else ''}")
    print(f"  Train IC={train_ic:+.4f}  ICIR={train_ir:+.3f}")

    leaf_formulas[leaf_id] = (best_func, best_str, train_ic)
    leaf_gp_stats[leaf_id] = {
        'expression': best_str,
        'train_ic': round(train_ic, 4),
        'train_icir': round(train_ir, 3),
        'n_periods': n_periods,
        'n_samples': n_samples,
    }

# ================================================================
# Step 4/5: 构建分段因子 + 全量验证
# ================================================================
print("\n" + "=" * 60)
print("Step 4/5: 构建分段因子 + 验证")
print("=" * 60)

if len(leaf_formulas) == 0:
    print("\n❌ 所有Regime的GP均未收敛，无法构建分段因子。")
    print("   建议：减小TREE_MIN_LEAF或增大GP_POP_SIZE/GP_N_GEN。")
else:
    # 构建piecewise函数
    import scipy.stats as ss

    def make_piecewise_func(leaf_paths, leaf_formulas, feature_names):
        """
        构建分段因子函数。
        对每一组样本，根据决策树条件路由到对应的GP叶子公式。
        每个regime内独立排名 → 使不同子集的值域可比。
        """
        compiled_leaves = {}
        for leaf_id, conditions in leaf_paths:
            if leaf_id in leaf_formulas:
                compiled_leaves[leaf_id] = {
                    'func': leaf_formulas[leaf_id][0],
                    'conditions': conditions,
                }

        def piecewise(*args):
            # args: 按 feature_names 顺序的特征数组
            n = len(args[0])
            result = np.full(n, np.nan)

            # 为每个叶子计算掩码，独立排名后填入
            remaining = np.ones(n, dtype=bool)
            for leaf_id, info in compiled_leaves.items():
                # 计算该叶子的掩码
                mask = np.ones(n, dtype=bool)
                for fn, th, is_left in info['conditions']:
                    fi = feature_names.index(fn)
                    vals = args[fi]
                    mask = mask & (vals <= th if is_left else vals > th)

                mask = mask & remaining
                if mask.sum() >= 2:
                    sub_args = [a[mask] for a in args]
                    try:
                        leaf_result = info['func'](*sub_args).flatten()
                        # Regime内排名 → 统一 [0,1] 值域，消除跨regime尺度差异
                        ranked = ss.rankdata(leaf_result, nan_policy='omit')
                        ranked = (ranked - 1) / (len(ranked) - 1)
                        result[mask] = ranked
                        remaining[mask] = False
                    except:
                        pass

            # fallback: 未覆盖的用第一个叶子公式 + 全特征（不排名，填充即可）
            if remaining.any():
                first_func = list(compiled_leaves.values())[0]['func']
                try:
                    sub_args = [a[remaining] for a in args]
                    result[remaining] = first_func(*sub_args).flatten()
                except:
                    result[remaining] = 0.0

            return result

        return piecewise

    pw_func = make_piecewise_func(leaf_paths, leaf_formulas, feature_names)

    # ---- 全量验证 ----
    def compute_ics_on_dataset(dates, data_dict):
        ics = []
        for d_str in dates:
            try:
                feats = data_dict[d_str]
                args = [feats[n] for n in feature_names]
                pred = pw_func(*args).flatten()
                actual = all_labels[d_str].flatten()
                mask = np.isfinite(pred) & np.isfinite(actual)
                if mask.sum() >= 30:
                    ic = np.corrcoef(pred[mask], actual[mask])[0, 1]
                    if np.isfinite(ic):
                        ics.append(ic)
            except:
                pass
        return ics

    train_ics = compute_ics_on_dataset(train_dates, train_data)
    val_ics   = compute_ics_on_dataset(val_dates, val_data)

    t_ic = np.mean(train_ics) if train_ics else 0.0
    v_ic = np.mean(val_ics) if val_ics else 0.0
    t_ir = t_ic / np.std(train_ics) if len(train_ics) > 1 else 0.0
    v_ir = v_ic / np.std(val_ics) if len(val_ics) > 1 else 0.0

    print(f"\n分段因子全量验证:")
    print(f"  Train IC={t_ic:+.4f}  ICIR={t_ir:+.3f}  (N={len(train_ics)})")
    print(f"  Val   IC={v_ic:+.4f}  ICIR={v_ir:+.3f}  (N={len(val_ics)})")

    # ---- 打印各Regime的公式 ----
    print(f"\n{'─'*55}")
    print("最终分段因子表达式 (Piecewise):")
    print(f"{'─'*55}")
    for leaf_id, conditions in leaf_paths:
        if leaf_id not in leaf_formulas:
            continue
        cond_parts = []
        for fn, th, is_left in conditions:
            op = "<=" if is_left else ">"
            cond_parts.append(f"{fn} {op} {th:.4g}")
        cond_str = " AND ".join(cond_parts)
        expr_str = leaf_formulas[leaf_id][1]
        print(f"\n  R{leaf_seq[leaf_id]} IF {cond_str}:")
        print(f"    → {expr_str}")


# ================================================================
# Step 5 续: 各Regime独立六维评估 (Train/Val)
# ================================================================
print("\n" + "=" * 60)
print("Step 5/5: 各Regime独立六维评估 (Train/Val)")
print("=" * 60)

def compute_leaf_mask(feats, conditions):
    """根据分裂条件计算属于某叶子的样本掩码。"""
    mask = np.ones(len(next(iter(feats.values()))), dtype=bool)
    for fn, th, is_left in conditions:
        mask = mask & (feats[fn] <= th if is_left else feats[fn] > th)
    return mask

def build_regime_period_data(leaf_func, conditions, dates, data_dict):
    """为指定Regime构建 period_data，用于 evaluateUtil 六维评估。"""
    period_data = []
    for d_str in dates:
        try:
            feats = data_dict[d_str]
            mask = compute_leaf_mask(feats, conditions)
            if mask.sum() < 30:
                continue
            sub_args = [feats[n][mask] for n in feature_names]
            pred = leaf_func(*sub_args).flatten()
            actual = all_labels[d_str].flatten()[mask]
            valid = np.isfinite(pred) & np.isfinite(actual)
            if valid.sum() < 30:
                continue
            period_data.append({
                'date': d_str,
                'features': {'factor_val': pred[valid]},
                'forward_returns': actual[valid],
                'codes': [f"s{i}" for i in range(valid.sum())],
            })
        except:
            pass
    return period_data

if len(leaf_formulas) == 0:
    print("\n⚠️ 无有效分段因子，跳过评估。")
else:
    ordered = sorted(
        [(lid, conds) for lid, conds in leaf_paths if lid in leaf_formulas],
        key=lambda x: leaf_gp_stats[x[0]]['train_ic'], reverse=True
    )

    regime_results = []
    for rank, (leaf_id, conditions) in enumerate(ordered):
        cond_desc = ' & '.join(
            f"{fn}{'<=' if il else '>'}{th:.4g}" for fn, th, il in conditions)
        leaf_func = leaf_formulas[leaf_id][0]

        # 构建 period_data (train + val)
        train_pd = build_regime_period_data(leaf_func, conditions, train_dates, train_data)
        val_pd   = build_regime_period_data(leaf_func, conditions, val_dates, val_data)
        all_pd   = train_pd + val_pd

        if len(all_pd) < 5:
            print(f"\n  ⚠️ R{leaf_seq[leaf_id]} [{cond_desc}] 有效截面<5，跳过")
            continue

        # 全量评估
        eva_all = evaluateUtil.evaluate(
            factor_name=f"R{leaf_seq[leaf_id]} [{cond_desc[:35]}]",
            factor_func=evaluateUtil.passthrough,
            feature_names=['factor_val'],
            period_data=all_pd,
        )
        
        # 训练集评估
        eva_train = None
        if len(train_pd) >= 5:
            eva_train = evaluateUtil.evaluate(
                factor_name=f"R{leaf_seq[leaf_id]}_Train",
                factor_func=evaluateUtil.passthrough,
                feature_names=['factor_val'],
                period_data=train_pd,
            )
        
        # 验证集评估
        eva_val = None
        if len(val_pd) >= 5:
            eva_val = evaluateUtil.evaluate(
                factor_name=f"R{leaf_seq[leaf_id]}_Val",
                factor_func=evaluateUtil.passthrough,
                feature_names=['factor_val'],
                period_data=val_pd,
            )

        # 打印浓缩摘要
        m = eva_all['metrics']
        W = 62
        print(f"\n  {'─'*W}")
        print(f"  R{leaf_seq[leaf_id]} [{cond_desc}]")
        print(f"  {'─'*W}")
        print(f"  全量: IC={m['mean_ic']:+.4f}  IR={m['icir']:.3f}  "
              f"Win={m['ic_win_rate']:.1%}  t={m['t_stat']:.2f}  "
              f"趋势={m['ic_trend']}  评级={eva_all['rating']}({eva_all['rating_score']}/11)")
        if eva_train and eva_train['metrics']:
            tm = eva_train['metrics']
            print(f"  Train: IC={tm['mean_ic']:+.4f}  IR={tm['icir']:.3f}  "
                  f"Win={tm['ic_win_rate']:.1%}  n={tm['n_periods']}")
        if eva_val and eva_val['metrics']:
            vm = eva_val['metrics']
            print(f"  Val:   IC={vm['mean_ic']:+.4f}  IR={vm['icir']:.3f}  "
                  f"Win={vm['ic_win_rate']:.1%}  n={vm['n_periods']}")

        regime_results.append({
            'leaf_id': leaf_id, 'cond_desc': cond_desc,
            'train_ic_gp': leaf_gp_stats[leaf_id]['train_ic'],
            'rating': eva_all['rating'],
            'rating_score': eva_all['rating_score'],
            'all_metrics': m,
        })

        # 输出完整报告（第一个和评级为S/A的regime）
        if rank == 0 or eva_all['rating'] in ('S', 'A'):
            evaluateUtil.report(eva_all)

    # ---- 汇总对比表 ----
    print(f"\n{' 汇总对比 ':=^60}")
    hdr = f"{'Regime':<30} {'GP_Train':>8} {'全量IC':>8} {'IR':>6} "
    hdr += f"{'Win':>7} {'n':>5} {'评级':>4}"
    print(hdr)
    print(f"{'─'*60}")
    for r in regime_results:
        short = f"R{leaf_seq[r['leaf_id']]}:[{r['cond_desc'][:27]}"
        tic = r['train_ic_gp']
        m = r['all_metrics']
        print(f"{short:<30} {tic:>+8.4f} {m['mean_ic']:>+8.4f} {m['icir']:>6.3f} "
              f"{m['ic_win_rate']:>7.1%} {m['n_periods']:>5} {r['rating']:>4}")

print("\n✅ 完成。决策树自动发现Regime边界，GP为每个Regime搜索最优公式。")
print("   pw_func 可直接集成到策略中。")
print("   pw_func 可直接集成到策略中。")
