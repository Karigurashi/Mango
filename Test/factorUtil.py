# ================================================================
# 因子挖掘公用工具模块 — 向量运算符 & 数据管线
# 所有挖掘脚本通过 import 引用，禁止重复定义
#
# 用法：
#   from factorUtil import factorUtil
#   from factorUtil import v_add, v_sub, v_mul, v_div, v_rank, v_abs, v_log, v_neg, v_max, v_min, v_sgn
#   weekly_tue, weekly_mon = factorUtil.build_weekly_cycle(TRAIN_START, VAL_END)
# ================================================================

from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
import datetime
from collections import defaultdict


# ================================================================
# 模块级向量运算符（供 deap GP 引擎使用，必须为普通函数）
# ================================================================
def v_add(a, b):  return np.add(np.float64(a), np.float64(b))
def v_sub(a, b):  return np.subtract(np.float64(a), np.float64(b))
def v_mul(a, b):  return np.multiply(np.float64(a), np.float64(b))

def v_div(a, b):
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.divide(np.float64(a), np.float64(b))
        r = np.where(np.isfinite(r), r, 0.0)
    return r

def v_rank(x):
    x = np.float64(x).flatten()
    if len(x) < 2:
        return np.zeros_like(x)
    return pd.Series(x).rank(pct=True).values

def v_abs(x):   return np.abs(np.float64(x))
def v_log(x):   return np.log(np.maximum(np.abs(np.float64(x)), 1e-8))
def v_neg(x):   return -np.float64(x)
def v_max(a,b): return np.maximum(np.float64(a), np.float64(b))
def v_min(a,b): return np.minimum(np.float64(a), np.float64(b))
def v_sgn(x):   return np.sign(np.float64(x))


class factorUtil:
    """因子挖掘公用工具 — 全静态方法（研报环境）"""

    # ================================================================
    # 一、因子挖掘 — 数据管线
    # ================================================================

    @classmethod
    def build_weekly_cycle(cls, train_start, val_end, skip_months=(1, 4)):
        """
        生成周频日期列表（周一特征日 + 周二调仓日），剔除财报季
        返回: (weekly_tue, weekly_mon)
        """
        all_td = get_trade_days(train_start, val_end)
        weekly_tue = []
        weekly_mon = []
        i = 0
        while i < len(all_td):
            iso = all_td[i].isocalendar()
            yr, wk = iso[0], iso[1]
            j = i
            while j < len(all_td):
                iso_j = all_td[j].isocalendar()
                if iso_j[0] == yr and iso_j[1] == wk:
                    j += 1
                else:
                    break
            week_days = all_td[i:j]
            if len(week_days) >= 2:
                d_tue = week_days[1]
                if d_tue.month not in skip_months:
                    weekly_tue.append(d_tue)
                    weekly_mon.append(week_days[0])
            i = j
        n = len(weekly_tue)
        print(f"周频日期: {n} (特征周一, 前向周二→下周一, 已剔除{skip_months}月财报季)")
        return weekly_tue, weekly_mon

    @classmethod
    def build_monthly_cycle(cls, train_start, val_end, skip_months=(1, 4)):
        """
        生成月频日期列表：每月第一个周二为因子取值日，次月第一个周二为前向收益终点。
        与周频对齐：同样剔除财报季月份。
        返回: (monthly_d, monthly_next_d)
           monthly_d:      本月因子取值日（第一个周二）
           monthly_next_d: 次月因子取值日（前向收益终点）
        """
        all_td = get_trade_days(train_start, val_end)
        # 按月份分组
        months = defaultdict(list)
        for d in all_td:
            months[(d.year, d.month)].append(d)

        monthly_d = []
        monthly_next_d = []
        month_keys = sorted(months.keys())
        for mi in range(len(month_keys) - 1):
            yr_m = month_keys[mi]
            yr_n = month_keys[mi + 1]
            # 本月第一个周二（同周频逻辑：iso weekday 2=周二）
            tues = [d for d in months[yr_m] if d.isocalendar()[2] == 2]
            if not tues:
                continue
            d_tue = tues[0]
            if d_tue.month in skip_months:
                continue
            # 次月第一个周二
            next_tues = [d for d in months[yr_n] if d.isocalendar()[2] == 2]
            if not next_tues:
                continue
            monthly_d.append(d_tue)
            monthly_next_d.append(next_tues[0])

        n = len(monthly_d)
        print(f"月频日期: {n} (每月第一个周二取值, 次月第一个周二为前向终点, 已剔除{skip_months}月财报季)")
        return monthly_d, monthly_next_d

    @classmethod
    def init_stock_filter(cls, train_start, val_end):
        """
        初始化股票过滤状态：获取全量股票列表 + 预取动态 ST 状态（逐日）
        + 一次性剔除静态不可投板块（科创板68/创业板30/北交4&8/退市）
        返回: (sec_df, st_raw, eligible_static)
          eligible_static: list[str] 已剔除静态不可投的候选股（不含 ST，ST 动态判断）
        """
        sec_df = get_all_securities(['stock'])
        st_raw = get_extras('is_st', list(sec_df.index),
                           start_date=train_start, end_date=val_end, df=True)

        # ── 静态过滤：仅板块 + 退市（ST 是动态数据，不在初始化阶段剔除）──
        eligible_static = []
        for s in sec_df.index:
            if s[0] in ('4', '8') or s[:2] in ('68', '30'):
                continue
            if '退' in str(sec_df.loc[s, 'display_name']):
                continue
            eligible_static.append(s)
        print(f"静态过滤: {len(sec_df)} → {len(eligible_static)}  (剔除{len(sec_df)-len(eligible_static)}只/板块+退市)")
        return sec_df, st_raw, eligible_static

    @classmethod
    def get_eligible_stocks_research(cls, eval_date, eligible_static, sec_df, st_raw, min_list_days=375):
        """
        研报环境动态过滤（静态过滤已在 init_stock_filter 中完成）：
          动态ST过滤: 逐期查询 is_st（is_st=1 剔除）
          次新股过滤: 上市不足 min_list_days 天
        返回: list[str]
        """
        cutoff = eval_date - datetime.timedelta(days=min_list_days)
        d_str = eval_date.strftime('%Y-%m-%d')

        # ── 当周 ST 状态：一次取出整行，不再逐股 .loc ──
        if d_str not in st_raw.index:
            return []
        st_row = st_raw.loc[d_str]          # Series, index=stock_code

        result = []
        for s in eligible_static:
            # 动态 ST 检查（Series 单键访问，远快于 DataFrame.loc[row,col]）
            if st_row.get(s, 1) == 1:
                continue
            # 次新股过滤
            if sec_df.loc[s, 'start_date'] > cutoff:
                continue
            result.append(s)
        return result

    @staticmethod
    def to_wide(prices, field, stocks_here):
        """
        将 panel=False 格式的 get_price 结果透视为宽表 (index=code, columns=time)
        返回: pd.DataFrame
        """
        w = prices.pivot(index='code', columns='time', values=field)
        return w.reindex(stocks_here)

    @staticmethod
    def filter_suspended_research(stocks_here, vol_df, cls_df, hgh_df, low_df):
        """
        研报环境停牌过滤：剔除最后一日成交量为 0 的股票
        返回: (stocks_here, cls_df, vol_df, hgh_df, low_df)
        """
        if vol_df.shape[1] > 0:
            active = vol_df.iloc[:, -1] > 0
            stocks_here = [s for s in stocks_here if s in active.index and active.get(s, False)]
            cls_df, vol_df, hgh_df, low_df = [
                df.loc[stocks_here] for df in (cls_df, vol_df, hgh_df, low_df)
            ]
        return stocks_here, cls_df, vol_df, hgh_df, low_df

    @staticmethod
    def build_features(cls_df, vol_df, hgh_df, low_df, fund_df):
        """
        从 OHLCV + fundamentals 构建 11 维特征 DataFrame
        返回: pd.DataFrame (index=stock_code)
        """
        feat = pd.DataFrame(index=cls_df.index)
        n_cols = cls_df.shape[1]
        feat['ret_1d']   = cls_df.iloc[:, -1] / cls_df.iloc[:, -2] - 1
        feat['ret_5d']   = cls_df.iloc[:, -1] / cls_df.iloc[:, -6] - 1 if n_cols >= 6 else feat['ret_1d']
        feat['ret_20d']  = cls_df.iloc[:, -1] / cls_df.iloc[:, -21] - 1 if n_cols >= 21 else feat['ret_1d']
        feat['amplitude']= (hgh_df.iloc[:, -1] - low_df.iloc[:, -1]) / cls_df.iloc[:, -2]
        cap_s = fund_df['circulating_market_cap'].reindex(feat.index)
        feat['turnover'] = vol_df.iloc[:, -1] / (cap_s * 10000)
        if n_cols >= 6:
            vol_5d_avg = vol_df.iloc[:, -6:-1].mean(axis=1)
            feat['vol_ratio'] = vol_df.iloc[:, -1] / (vol_5d_avg + 1)
        else:
            feat['vol_ratio'] = 1.0
        feat['volume']   = vol_df.iloc[:, -1]
        feat['close']    = cls_df.iloc[:, -1]
        feat['cir_cap']  = cap_s
        feat['mktcap']   = fund_df['market_cap'].reindex(feat.index)
        feat['pb']       = fund_df['pb_ratio'].reindex(feat.index).fillna(0)
        return feat.dropna()
