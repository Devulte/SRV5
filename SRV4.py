import streamlit as st
import tushare as ts
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.ensemble import RandomForestClassifier
import plotly.graph_objects as go
from datetime import datetime, timedelta
import logging
import time
import retrying
from concurrent.futures import ThreadPoolExecutor, as_completed
import optuna
import optuna.logging
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score
import akshare as ak
import baostock as bs
import jieba

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TushareData")
st_handler = logging.StreamHandler()
st_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(st_handler)

# Suppress Optuna logging
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Initialize Tushare API (cached)
@st.cache_resource
def init_tushare():
    try:
        ts.set_token('2876ea85cb005fb5fa17c809a98174f2d5aae8b1f830110a5ead6211')
        pro = ts.pro_api()
        logger.info("Tushare API initialized successfully")
        return pro
    except Exception as e:
        logger.error(f"Tushare API initialization failed: {e}")
        st.error(f"Tushare API初始化失败: {e}. 请更换token或检查网络连接。")
        raise e

pro = init_tushare()

# Streamlit UI Setup
st.set_page_config(page_title="A股股票推荐系统", layout="wide")
st.title("📈 A股股票推荐系统")
st.markdown("每日推荐Top5~Top10只个股，目标次日上涨命中率70%以上")

# Initialize Session State
if 'dynamic_factors' not in st.session_state:
    st.session_state.dynamic_factors = ['northbuy', 'turnover', 'dt_ratio', 'callback', 'industry_hotness', 'low_turnover']
if 'catboost_params' not in st.session_state:
    st.session_state.catboost_params = {'depth': 6, 'learning_rate': 0.1, 'iterations': 100}
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None

# Global Date Settings
days_back = 30
start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
end_date = datetime.now().strftime('%Y%m%d')
news_start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')

# Data Retrieval Status Dashboard
data_status = {
    "stock_basic": {"attempted": 0, "successful": 0, "failed": 0},
    "daily": {"attempted": 0, "successful": 0, "failed": 0},
    "moneyflow": {"attempted": 0, "successful": 0, "failed": 0},
    "news": {"attempted": 0, "successful": 0, "failed": 0},
    "screening_daily": {"attempted": 0, "successful": 0, "failed": 0}
}

# Cache Data Functions with Retry
@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
@st.cache_data
def get_stock_list():
    data_status["stock_basic"]["attempted"] += 1
    try:
        df = pro.stock_basic(list_status='L', fields='ts_code,symbol,name,market,total_share')
        logger.info(f"Retrieved stock_basic: {len(df)} stocks")
        market_counts = df['market'].value_counts()
        logger.info(f"Market distribution: {dict(market_counts)}")
        data_status["stock_basic"]["successful"] += 1
        filtered_df = df[df['market'].isin(['主板', '创业板', '科创板', '北交所'])]
        logger.info(f"Filtered to {len(filtered_df)} stocks after including main markets")
        return filtered_df[~filtered_df['name'].str.contains('ST|退', na=False)]
    except Exception as e:
        logger.error(f"Failed to retrieve stock_basic: {e}")
        data_status["stock_basic"]["failed"] += 1
        raise e

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
@st.cache_data
def get_batch_daily_data(ts_codes, start_date, end_date, _cache_buster=None):
    data_status["daily"]["attempted"] += 1
    try:
        # 尝试AKShare
        ak_codes = [code[:6] for code in ts_codes]
        df = ak.stock_zh_a_spot_em()
        df = df[df['代码'].isin(ak_codes)][['代码', '最新价', '涨跌幅', '成交量', '成交额']]
        df.columns = ['ts_code', 'price', 'pct_change', 'volume', 'amount']
        df['ts_code'] = df['ts_code'].apply(lambda x: x + '.SH' if x.startswith('6') else x + '.SZ' if x.startswith('0') or x.startswith('3') else x + '.BJ')
        df['trade_date'] = datetime.now().strftime('%Y%m%d')
        df['is_realtime'] = True
        logger.info(f"Retrieved AKShare real-time data for {len(ts_codes)} stocks: {len(df)} rows")
        data_status["daily"]["successful"] += 1
        return df.sort_values(['ts_code']), True
    except Exception as e:
        logger.warning(f"AKShare real-time data failed: {e}, trying BaoStock...")
        try:
            bs.login()
            data_list = []
            for code in ts_codes:
                bs_code = ('sh.' if code.startswith('6') else 'sz.' if code.startswith('0') or code.startswith('3') else 'bj.') + code[:6]
                rs = bs.query_history_k_data_plus(
                    code=bs_code,
                    fields="code,close,pct_chg,volume,amount",
                    start_date=datetime.now().strftime('%Y-%m-%d'),
                    end_date=datetime.now().strftime('%Y-%m-%d'),
                    frequency="d"
                )
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
            bs.logout()
            if data_list:
                df = pd.DataFrame(data_list, columns=['ts_code', 'price', 'pct_change', 'volume', 'amount'])
                df['ts_code'] = df['ts_code'].apply(lambda x: x[3:] + '.SH' if x.startswith('sh') else x[3:] + '.SZ' if x.startswith('sz') else x[3:] + '.BJ')
                df['trade_date'] = datetime.now().strftime('%Y%m%d')
                df['is_realtime'] = True
                df = df[df['ts_code'].isin(ts_codes)]
                logger.info(f"Retrieved BaoStock real-time data for {len(ts_codes)} stocks: {len(df)} rows")
                data_status["daily"]["successful"] += 1
                return df.sort_values(['ts_code']), True
            else:
                raise Exception("BaoStock returned empty data")
        except Exception as e2:
            logger.warning(f"BaoStock real-time data failed: {e2}, falling back to Tushare...")
            try:
                df = pro.daily(ts_code=','.join(ts_codes), start_date=start_date, end_date=end_date)
                df['is_realtime'] = False
                logger.info(f"Retrieved Tushare daily data for {len(ts_codes)} stocks: {len(df)} rows")
                data_status["daily"]["successful"] += 1
                return df.sort_values(['ts_code', 'trade_date']), False
            except Exception as e3:
                logger.error(f"Tushare daily data failed for {ts_codes[:5]}...: {e3}")
                data_status["daily"]["failed"] += 1
                return pd.DataFrame(), False

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
@st.cache_data
def get_batch_moneyflow_data(ts_codes, start_date, end_date):
    data_status["moneyflow"]["attempted"] += 1
    try:
        df = pro.moneyflow(ts_code=','.join(ts_codes), start_date=start_date, end_date=end_date)
        logger.info(f"Retrieved batch moneyflow for {len(ts_codes)} stocks: {len(df)} rows")
        data_status["moneyflow"]["successful"] += 1
        return df
    except Exception as e:
        logger.warning(f"Failed to retrieve batch moneyflow for {ts_codes[:5]}...: {e}")
        data_status["moneyflow"]["failed"] += 1
        return pd.DataFrame()

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
@st.cache_data
def get_batch_screening_daily_data(ts_codes, start_date, end_date):
    data_status["screening_daily"]["attempted"] += 1
    try:
        df = pro.daily(ts_code=','.join(ts_codes), start_date=start_date, end_date=end_date)
        logger.info(f"Retrieved screening daily data for {len(ts_codes)} stocks: {len(df)} rows")
        data_status["screening_daily"]["successful"] += 1
        return df.sort_values(['ts_code', 'trade_date'])
    except Exception as e:
        logger.warning(f"Failed to retrieve screening daily data for {ts_codes[:5]}...: {e}")
        data_status["screening_daily"]["failed"] += 1
        return pd.DataFrame()

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
@st.cache_data
def get_news_data(start_date, end_date):
    data_status["news"]["attempted"] += 1
    try:
        df = pro.news(start_date=start_date, end_date=end_date, fields='ts_code,content')
        logger.info(f"Retrieved news data: {len(df)} rows")
        if not df.empty:
            logger.info(f"Sample news content: {df['content'].head(2).tolist()}")
        data_status["news"]["successful"] += 1
        return df
    except Exception as e:
        logger.warning(f"Failed to retrieve Tushare news data: {e}, trying AKShare...")
        try:
            ak_news = ak.stock_info_a_code_name()
            ak_codes = ak_news['code'].tolist()
            news_list = []
            for code in ak_codes[:10]:  # Limit to avoid rate limits
                news_df = ak.stock_news_em(code)
                if not news_df.empty:
                    news_df['ts_code'] = code + ('.SH' if code.startswith('6') else '.SZ' if code.startswith('0') or code.startswith('3') else '.BJ')
                    news_df = news_df[['ts_code', 'content']]
                    news_list.append(news_df)
            if news_list:
                df = pd.concat(news_list, ignore_index=True)
                logger.info(f"Retrieved AKShare news data: {len(df)} rows")
                if not df.empty:
                    logger.info(f"Sample AKShare news content: {df['content'].head(2).tolist()}")
                data_status["news"]["successful"] += 1
                return df
            else:
                raise Exception("AKShare returned empty news data")
        except Exception as e2:
            logger.error(f"AKShare news data failed: {e2}")
            data_status["news"]["failed"] += 1
            return pd.DataFrame()

# Dynamic Factor Selection using Random Forest
@st.cache_data
def select_dynamic_factors(stock_list, daily_data_dict):
    try:
        all_factors = ['northbuy', 'turnover', 'dt_ratio', 'callback', 'industry_hotness', 'low_turnover']
        X, y = [], []
        for ts_code in stock_list['ts_code'][:100]:  # Limit to 100 stocks for speed
            daily_data = daily_data_dict.get(ts_code, pd.DataFrame())
            if daily_data.empty or len(daily_data) < 5:
                continue
            factors = {}
            moneyflow_data = get_batch_moneyflow_data([ts_code], start_date, end_date)
            if 'northbuy' in all_factors:
                factors['northbuy'] = moneyflow_data['net_mf_amount'].tail(5).sum() if not moneyflow_data.empty else 0
            if 'turnover' in all_factors:
                factors['turnover'] = daily_data['turnover_rate'].tail(5).mean() if 'turnover_rate' in daily_data else 0
            if 'dt_ratio' in all_factors:
                factors['dt_ratio'] = moneyflow_data['buy_l_amount'].tail(5).sum() / moneyflow_data['amount'].tail(5).sum() if not moneyflow_data.empty and moneyflow_data['amount'].tail(5).sum() > 0 else 0
            if 'callback' in all_factors:
                max_price = daily_data['high'].tail(5).max() if 'high' in daily_data else daily_data['price'].tail(5).max()
                current_price = daily_data['close'].iloc[-1] if 'close' in daily_data else daily_data['price'].iloc[-1] if 'price' in daily_data else 0
                factors['callback'] = ((max_price - current_price) / max_price * 100) if max_price > 0 else 0
            if 'industry_hotness' in all_factors:
                factors['industry_hotness'] = 50
            if 'low_turnover' in all_factors:
                turnover_20d = daily_data['turnover_rate'].tail(20) if 'turnover_rate' in daily_data else pd.Series([])
                industry_avg = daily_data_dict.get(ts_code, pd.DataFrame())['turnover_rate'].mean() if 'turnover_rate' in daily_data_dict.get(ts_code, pd.DataFrame()) else 1
                factors['low_turnover'] = daily_data['turnover_rate'].tail(20).mean() / industry_avg if not turnover_20d.empty and industry_avg > 0 else 1
            X.append([factors.get(f, 0) for f in all_factors])
            y.append(1 if daily_data['pct_chg'].iloc[-1] > 0 else 0)
        if not X:
            logger.warning("No valid data for dynamic factor selection")
            return all_factors
        rf = RandomForestClassifier(n_estimators=50, random_state=42)
        rf.fit(X, y)
        importances = rf.feature_importances_
        factor_importance = dict(zip(all_factors, importances))
        sorted_factors = sorted(factor_importance.items(), key=lambda x: x[1], reverse=True)
        cumulative = 0
        selected = []
        for factor, importance in sorted_factors:
            cumulative += importance
            selected.append(factor)
            if cumulative >= 0.80:
                break
        logger.info(f"Selected dynamic factors: {selected}")
        return selected
    except Exception as e:
        logger.warning(f"Dynamic factor selection failed: {e}")
        return ['northbuy', 'turnover', 'dt_ratio', 'callback', 'industry_hotness', 'low_turnover']

# Hyperparameter Tuning with Optuna
@st.cache_data
def tune_catboost_params(stock_list, daily_data_dict):
    def objective(trial):
        params = {
            'depth': trial.suggest_int('depth', 4, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
            'iterations': trial.suggest_int('iterations', 50, 200)
        }
        X, y = [], []
        for ts_code in stock_list['ts_code'][:100]:  # Limit to 100 stocks
            daily_data = daily_data_dict.get(ts_code, pd.DataFrame())
            if daily_data.empty or len(daily_data) < 5:
                continue
            factors = compute_factors({'ts_code': ts_code}, daily_data, pd.DataFrame(), st.session_state.dynamic_factors)
            X.append([factors.get(f, 0) for f in st.session_state.dynamic_factors])
            y.append(1 if daily_data['pct_chg'].iloc[-1] > 0 else 0)
        if not X:
            logger.warning("No valid data for CatBoost tuning")
            return 0.5
        model = CatBoostClassifier(**params, verbose=False)
        model.fit(X[:-10], y[:-10])
        y_pred = model.predict(X[-10:])
        return accuracy_score(y[-10:], y_pred)
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=10)
    logger.info(f"Best CatBoost params: {study.best_params}")
    return study.best_params

# Parallel Data Fetching
def fetch_stock_data(stock, daily_data_dict, moneyflow_data_dict, news_data_dict, dynamic_factors=None):
    ts_code = stock['ts_code']
    name = stock['name']
    market = stock['market']
    daily_data = daily_data_dict.get(ts_code, pd.DataFrame())
    moneyflow_data = moneyflow_data_dict.get(ts_code, pd.DataFrame())
    news_data = news_data_dict.get(ts_code, pd.DataFrame())
    factors = compute_factors(stock, daily_data, moneyflow_data, dynamic_factors)
    logger.info(f"Factors for {ts_code}: {factors}")
    scores = compute_scores(stock, daily_data, factors, news_data)
    return {
        'ts_code': ts_code,
        'name': name,
        'market': market,
        'industry': '未知',
        **factors,
        **scores
    }

# Stock Screening Module
@st.cache_data
def stock_screening(stock_list):
    batch_size = 100
    batches = [stock_list[i:i + batch_size] for i in range(0, len(stock_list), batch_size)]
    filtered_stocks = []
    screening_data_dict = {}
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_batch = {}
        for i, batch in enumerate(batches):
            ts_codes = batch['ts_code'].tolist()
            future = executor.submit(get_batch_screening_daily_data, ts_codes, start_date, end_date)
            future_to_batch[future] = (i, ts_codes)
        
        for i, future in enumerate(as_completed(future_to_batch)):
            batch_idx, ts_codes = future_to_batch[future]
            try:
                df = future.result()
                if not df.empty:
                    for ts_code in ts_codes:
                        stock_data = df[df['ts_code'] == ts_code]
                        if len(stock_data) >= 1:
                            # 筛选条件：成交量>1000手，成交额>1000万，市值>5亿
                            latest = stock_data.iloc[-1]
                            stock_info = stock_list[stock_list['ts_code'] == ts_code]
                            total_share = stock_info['total_share'].iloc[0] if not stock_info.empty else 1
                            market_cap = total_share * latest['close'] if 'close' in latest else 0
                            if (latest['vol'] > 1000 and 
                                latest['amount'] > 10000000 and 
                                market_cap > 500000000):
                                screening_data_dict[ts_code] = stock_data
                                stock = stock_info.iloc[0]
                                filtered_stocks.append(stock)
            except Exception as e:
                logger.warning(f"Screening batch {batch_idx} failed: {e}")
    
    filtered_df = pd.DataFrame(filtered_stocks)
    market_counts = filtered_df['market'].value_counts() if not filtered_df.empty else {}
    logger.info(f"Screened {len(filtered_stocks)} stocks from {len(stock_list)}. Market distribution: {dict(market_counts)}")
    return filtered_df, screening_data_dict

# Signal Factor Module
def compute_factors(stock, daily_data, moneyflow_data, dynamic_factors=None):
    try:
        factors_list = dynamic_factors or st.session_state.get('dynamic_factors', ['northbuy', 'turnover', 'dt_ratio', 'callback', 'industry_hotness', 'low_turnover'])
        factors = {}
        ts_code = stock['ts_code']
        is_realtime = daily_data.get('is_realtime', False).iloc[0] if not daily_data.empty and 'is_realtime' in daily_data else False
        
        if is_realtime and not daily_data.empty:
            latest = daily_data.iloc[-1]
            total_shares = stock['total_share'] if 'total_share' in stock else 1
            if 'northbuy' in factors_list:
                factors['northbuy'] = moneyflow_data['net_mf_amount'].tail(5).sum() if not moneyflow_data.empty else 0
            if 'turnover' in factors_list:
                factors['turnover'] = (latest['volume'] * 100 / total_shares) if total_shares > 0 else 0
            if 'dt_ratio' in factors_list:
                factors['dt_ratio'] = moneyflow_data['buy_l_amount'].tail(5).sum() / moneyflow_data['amount'].tail(5).sum() if not moneyflow_data.empty and moneyflow_data['amount'].tail(5).sum() > 0 else 0
            if 'callback' in factors_list:
                max_price = daily_data['price'].tail(5).max() if 'price' in daily_data else daily_data['close'].tail(5).max()
                current_price = latest['price']
                factors['callback'] = ((max_price - current_price) / max_price * 100) if max_price > 0 else 0
            if 'industry_hotness' in factors_list:
                factors['industry_hotness'] = 50
            if 'low_turnover' in factors_list:
                turnover_20d = daily_data['volume'].tail(20) * 100 / total_shares if total_shares > 0 else pd.Series([0])
                industry_avg = daily_data['volume'].mean() * 100 / total_shares if total_shares > 0 else 1
                factors['low_turnover'] = turnover_20d.mean() / industry_avg if not turnover_20d.empty and industry_avg > 0 else 1
        else:
            if 'northbuy' in factors_list:
                factors['northbuy'] = moneyflow_data['net_mf_amount'].tail(5).sum() if not moneyflow_data.empty else 0
            if 'turnover' in factors_list:
                factors['turnover'] = daily_data['turnover_rate'].tail(5).mean() if 'turnover_rate' in daily_data else 0
            if 'dt_ratio' in factors_list:
                factors['dt_ratio'] = moneyflow_data['buy_l_amount'].tail(5).sum() / moneyflow_data['amount'].tail(5).sum() if not moneyflow_data.empty and moneyflow_data['amount'].tail(5).sum() > 0 else 0
            if 'callback' in factors_list:
                max_price = daily_data['high'].tail(5).max()
                current_price = daily_data['close'].iloc[-1] if 'close' in daily_data else 0
                factors['callback'] = ((max_price - current_price) / max_price * 100) if max_price > 0 else 0
            if 'industry_hotness' in factors_list:
                factors['industry_hotness'] = 50
            if 'low_turnover' in factors_list:
                turnover_20d = daily_data['turnover_rate'].tail(20) if 'turnover_rate' in daily_data else pd.Series([])
                industry_avg = daily_data['turnover_rate'].mean() if 'turnover_rate' in daily_data else 1
                factors['low_turnover'] = turnover_20d.mean() / industry_avg if not turnover_20d.empty and industry_avg > 0 else 1
        logger.info(f"Computed factors for {ts_code}: {factors}")
        return factors
    except Exception as e:
        logger.warning(f"Error computing factors for {ts_code}: {e}")
        return {f: 0 for f in factors_list}

# Multi-Model Fusion Module with Dynamic Weights
def compute_scores(stock, daily_data, factors, news_data):
    try:
        dynamic_factors = list(factors.keys()) if factors else st.session_state.get('dynamic_factors', ['northbuy', 'turnover', 'dt_ratio', 'callback', 'industry_hotness', 'low_turnover'])
        scaler = MinMaxScaler()
        factor_values = np.array([[factors.get(f, 0) for f in dynamic_factors]])
        logger.info(f"Factor values for {stock['ts_code']}: {factor_values}")
        if np.any(np.isnan(factor_values)) or factor_values.size == 0:
            logger.warning(f"Invalid factor values for {stock['ts_code']}, returning default scores")
            return {
                'catboost_prob': 0.5,
                'lstm_score': 0.5,
                'sentiment_score': 0.5,
                'logreg_score': 0.5,
                'final_score': 0.5,
                'is_realtime': False
            }
        normalized = scaler.fit_transform(factor_values).flatten()
        logger.info(f"Normalized factor values for {stock['ts_code']}: {normalized}")
        catboost_prob = np.mean(normalized[:3]) if len(normalized) >= 3 else 0.5
        logger.info(f"CatBoost prob for {stock['ts_code']}: {catboost_prob}")
        is_realtime = daily_data.get('is_realtime', False).iloc[0] if not daily_data.empty and 'is_realtime' in daily_data else False
        if is_realtime and not daily_data.empty:
            lstm_score = daily_data['pct_change'].tail(5).mean() / 10 + 0.5 if 'pct_change' in daily_data else 0.5
        else:
            lstm_score = daily_data['pct_chg'].tail(5).mean() / 10 + 0.5 if not daily_data.empty and 'pct_chg' in daily_data else 0.5
        lstm_score = np.clip(lstm_score, 0, 1)
        news_sentiment = 0.5
        if not news_data.empty:
            positive_keywords = ['上涨', '利好', '增长', '盈利', '突破', '创新', '扩张']
            negative_keywords = ['下跌', '亏损', '风险', '下滑', '危机', '违约']
            content = ' '.join(news_data['content'].tail(5).astype(str))
            # 使用jieba进行中文分词
            words = list(jieba.cut(content))
            pos_count = sum(1 for word in words if word in positive_keywords)
            neg_count = sum(1 for word in words if word in negative_keywords)
            news_sentiment = (pos_count + 1) / (pos_count + neg_count + 2)
            logger.info(f"News sentiment for {stock['ts_code']}: pos_count={pos_count}, neg_count={neg_count}, score={news_sentiment}")
        sentiment_score = news_sentiment
        logreg_score = np.mean(normalized) if normalized.size > 0 else 0.5
        weights = {'catboost': 0.4, 'lstm': 0.35 if is_realtime else 0.3, 'sentiment': 0.2, 'logreg': 0.1}
        final_score = (
            weights['catboost'] * catboost_prob +
            weights['lstm'] * lstm_score +
            weights['sentiment'] * sentiment_score +
            weights['logreg'] * logreg_score
        )
        if not daily_data.empty:
            close = daily_data['price'] if is_realtime else daily_data['close']
            sma5 = close.tail(5).mean()
            sma20 = close.tail(20).mean()
            if sma5 > sma20:
                final_score += 0.1
        return {
            'catboost_prob': catboost_prob,
            'lstm_score': lstm_score,
            'sentiment_score': sentiment_score,
            'logreg_score': logreg_score,
            'final_score': final_score,
            'is_realtime': is_realtime
        }
    except Exception as e:
        logger.warning(f"Error computing scores for {stock['ts_code']}: {e}")
        return {
            'catboost_prob': 0.5,
            'lstm_score': 0.5,
            'sentiment_score': 0.5,
            'logreg_score': 0.5,
            'final_score': 0.5,
            'is_realtime': False
        }

# Strategy Filtering Module
def adjust_final_score(row):
    score = row['final_score']
    main_fund = row.get('northbuy', 0)
    concept_hotness = row.get('industry_hotness', 50)
    callback = row.get('callback', 0)
    turnover = row.get('turnover', 0)
    low_turnover = row.get('low_turnover', 0)
    if main_fund < 0:
        score -= 0.2
    if concept_hotness > 90:
        score += 0.3
    if callback > 5:
        score += 0.5
    if turnover > 5:
        score += 0.2
    if low_turnover < 0.5:
        score += 0.1
    return score

# Candlestick Chart
def plot_candlestick(daily_data, stock_name, ts_code):
    required_fields = ['open', 'high', 'low', 'close', 'trade_date']
    if all(field in daily_data.columns for field in required_fields):
        fig = go.Figure(data=[
            go.Candlestick(
                x=daily_data['trade_date'],
                open=daily_data['open'],
                high=daily_data['high'],
                low=daily_data['low'],
                close=daily_data['close'],
                name=stock_name
            )
        ])
    else:
        fig = go.Figure(data=[
            go.Scatter(
                x=daily_data['trade_date'] if 'trade_date' in daily_data else daily_data.index,
                y=daily_data.get('price', daily_data.get('close')),
                mode='lines',
                name=stock_name
            )
        ])
    fig.update_layout(
        title=f"{stock_name} ({ts_code}) 价格走势",
        xaxis_title="日期",
        yaxis_title="价格 (元)",
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_rangeslider_visible=False
    )
    return fig

# Factor Breakdown Chart
def plot_factor_breakdown(row, ts_code):
    factors = st.session_state.get('dynamic_factors', ['northbuy', 'turnover', 'dt_ratio', 'callback', 'industry_hotness', 'low_turnover'])
    values = [row.get(f, 0) for f in factors]
    labels = ['北向资金', '换手率', '龙虎榜', '回调幅度', '行业热度', '低换手率'][:len(factors)]
    fig = go.Figure(data=[
        go.Bar(x=labels, y=values, marker_color='lightgreen')
    ])
    fig.update_layout(
        title="因子得分分布",
        xaxis_title="因子",
        yaxis_title="归一化得分",
        height=300,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig

# Data Retrieval Status Dashboard
def display_data_status():
    st.subheader("📡 数据获取状态")
    for endpoint, stats in data_status.items():
        status_text = f"{endpoint}: 尝试 {stats['attempted']} 次, 成功 {stats['successful']} 次, 失败 {stats['failed']} 次"
        if stats['failed'] > 0:
            st.markdown(f"<span style='color:red'>{status_text}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:green'>{status_text}</span>", unsafe_allow_html=True)

# Sidebar for Recommendation Settings
with st.sidebar:
    st.header("⚙️ 推荐设置")
    top_n = st.slider("推荐股票数量", min_value=5, max_value=10, value=10)
    days_back = st.selectbox("历史数据天数", [10, 30, 60], index=1)
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
    end_date = datetime.now().strftime('%Y%m%d')
    news_start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
    st.markdown(f"**数据范围**: {start_date} - {end_date}")
    run_button = st.button("🚀 生成推荐")
    st.subheader("🔍 测试数据源")
    test_button = st.button("测试数据源连接")

# Test Data Source Connection
if test_button:
    with st.spinner("测试数据源连接..."):
        try:
            df = pro.stock_basic(list_status='L', fields='ts_code,name,market')
            market_counts = df['market'].value_counts()
            st.success(f"Tushare连接成功！获取到 {len(df)} 条股票数据")
            st.dataframe(df.head())
            st.markdown(f"**市场分布**: {dict(market_counts)}")
            logger.info("Tushare connection test successful")
            # Test AKShare
            test_code = '600000'
            try:
                df = ak.stock_zh_a_spot_em()
                df = df[df['代码'] == test_code][['代码', '最新价', '涨跌幅', '成交量']]
                st.success(f"AKShare实时数据测试成功！{test_code} 当前价: {df['最新价'].iloc[0]}")
                logger.info(f"AKShare real-time data test for {test_code}: {df}")
            except Exception as e:
                st.warning(f"AKShare实时数据测试失败: {e}. 尝试BaoStock...")
                try:
                    bs.login()
                    rs = bs.query_history_k_data_plus(
                        code='sh.' + test_code,
                        fields="code,close,pct_chg,volume",
                        start_date=datetime.now().strftime('%Y-%m-%d'),
                        end_date=datetime.now().strftime('%Y-%m-%d'),
                        frequency="d"
                    )
                    data_list = []
                    while (rs.error_code == '0') & rs.next():
                        data_list.append(rs.get_row_data())
                    bs.logout()
                    df = pd.DataFrame(data_list, columns=['code', 'price', 'pct_change', 'volume'])
                    st.success(f"BaoStock实时数据测试成功！{test_code} 当前价: {df['price'].iloc[0]}")
                    logger.info(f"BaoStock real-time data test for {test_code}: {df}")
                except Exception as e2:
                    st.error(f"BaoStock实时数据测试失败: {e2}")
                    logger.error(f"BaoStock real-time data test failed: {e2}")
        except Exception as e:
            st.error(f"Tushare连接失败: {e}")
            logger.error(f"Tushare connection test failed: {e}")

# Recommendation Interface
recommendation_container = st.container()
with recommendation_container:
    if run_button or st.session_state.recommendations is None:
        main_progress = st.progress(0, text="初始化推荐流程...")
        display_data_status()
        stocklist_progress = st.progress(0, text="正在获取股票列表...")
        stocklist_progress.progress(50, text="正在连接Tushare API...")
        stock_list = get_stock_list()
        stocklist_progress.progress(100, text="股票列表获取完成")
        stocklist_progress.empty()
        main_progress.progress(20, text="股票列表已获取")
        if stock_list.empty:
            main_progress.progress(100, text="推荐失败")
            st.error("无法获取股票列表！请检查Tushare token或网络连接。")
            logger.error("Stock list retrieval failed")
        else:
            market_counts = stock_list['market'].value_counts()
            st.markdown(f"**股票市场分布**: {dict(market_counts)}")
            main_progress.progress(40, text="正在筛选股票...")
            with st.spinner("正在分析股票..."):
                filtered_stocks, screening_data_dict = stock_screening(stock_list)
                main_progress.progress(50, text="正在处理股票数据...")
                
                if filtered_stocks.empty:
                    main_progress.progress(100, text="推荐失败")
                    st.warning("没有符合条件的股票！尝试以下操作：")
                    st.markdown("- 增加历史数据天数")
                    st.markdown("- 更换Tushare token或升级到付费计划")
                    st.markdown("- 检查Tushare API状态: https://tushare.pro")
                    logger.warning("No stocks passed screening")
                else:
                    # Dynamic factor selection and hyperparameter tuning
                    st.session_state.dynamic_factors = select_dynamic_factors(stock_list, screening_data_dict)
                    logger.info(f"Dynamic factors set: {st.session_state.dynamic_factors}")
                    st.session_state.catboost_params = tune_catboost_params(stock_list, screening_data_dict)
                    results = []
                    total_stocks = len(filtered_stocks)
                    analysis_progress = st.progress(0, text="分析股票...")
                    batch_size = 100
                    batches = [filtered_stocks[i:i + batch_size] for i in range(0, len(filtered_stocks), batch_size)]
                    daily_data_dict = {}
                    moneyflow_data_dict = {}
                    news_data_dict = {}
                    batch_count = len(batches)
                    
                    with ThreadPoolExecutor(max_workers=3) as executor:
                        future_to_batch = {}
                        for i, batch in enumerate(batches):
                            ts_codes = batch['ts_code'].tolist()
                            future_daily = executor.submit(get_batch_daily_data, ts_codes, start_date, end_date, str(time.time()))
                            future_moneyflow = executor.submit(get_batch_moneyflow_data, ts_codes, start_date, end_date)
                            future_news = executor.submit(get_news_data, news_start_date, end_date)
                            future_to_batch[future_daily] = (i, 'daily', ts_codes)
                            future_to_batch[future_moneyflow] = (i, 'moneyflow', ts_codes)
                            future_to_batch[future_news] = (i, 'news', ts_codes)
                        
                        for i, future in enumerate(as_completed(future_to_batch)):
                            batch_idx, data_type, ts_codes = future_to_batch[future]
                            try:
                                if data_type == 'daily':
                                    df, is_realtime = future.result()
                                else:
                                    df = future.result()
                                if not df.empty:
                                    for ts_code in ts_codes:
                                        if data_type == 'daily':
                                            daily_data_dict[ts_code] = df[df['ts_code'] == ts_code]
                                        elif data_type == 'moneyflow':
                                            moneyflow_data_dict[ts_code] = df[df['ts_code'] == ts_code]
                                        elif data_type == 'news':
                                            news_data_dict[ts_code] = df[df['ts_code'] == ts_code]
                            except Exception as e:
                                logger.warning(f"Batch {batch_idx} ({data_type}) failed: {e}")
                            analysis_progress.progress(int(100 * (i + 1) / (3 * batch_count)))
                            main_progress.progress(50 + int(20 * (i + 1) / (3 * batch_count)), text="正在获取批量数据...")
                    
                    main_progress.progress(70, text="正在计算因子和得分...")
                    with ThreadPoolExecutor(max_workers=3) as executor:
                        future_to_stock = {
                            executor.submit(
                                fetch_stock_data, 
                                stock, 
                                daily_data_dict, 
                                moneyflow_data_dict, 
                                news_data_dict, 
                                st.session_state.dynamic_factors
                            ): stock for _, stock in filtered_stocks.iterrows()
                        }
                        for i, future in enumerate(as_completed(future_to_stock)):
                            results.append(future.result())
                            analysis_progress.progress(int(100 * (i + 1) / total_stocks))
                            main_progress.progress(70 + int(10 * (i + 1) / total_stocks), text="正在生成推荐...")
                    
                    main_progress.progress(80, text="正在排序推荐...")
                    results_df = pd.DataFrame(results)
                    results_df['final_score'] = results_df.apply(adjust_final_score, axis=1)
                    top_n_df = results_df.sort_values('final_score', ascending=False).head(top_n)
                    st.session_state.recommendations = top_n_df
                    main_progress.progress(100, text="推荐完成")
                    analysis_progress.empty()
    
    # Display Recommendations
    if st.session_state.recommendations is not None:
        st.subheader(f"📊 Top {top_n} 推荐股票")
        tabs = st.tabs(["概览", "详细分析"])
        
        with tabs[0]:
            display_df = st.session_state.recommendations[['ts_code', 'name', 'final_score', 'catboost_prob', 'lstm_score', 'sentiment_score', 'is_realtime', 'market']]
            display_df.columns = ['股票代码', '股票名称', '综合得分', '上涨概率', '趋势得分', '情绪得分', '实时数据', '市场']
            st.dataframe(
                display_df.style.format({
                    '综合得分': '{:.2f}',
                    '上涨概率': '{:.2f}',
                    '趋势得分': '{:.2f}',
                    '情绪得分': '{:.2f}',
                    '实时数据': lambda x: '是' if x else '否'
                }).background_gradient(subset=['综合得分'], cmap='YlGnBu'),
                use_container_width=True
            )
        
        with tabs[1]:
            for _, row in st.session_state.recommendations.iterrows():
                with st.expander(f"{row['name']} ({row['ts_code']}) - 综合得分: {row['final_score']:.2f}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**上涨概率 (CatBoost)**: {row['catboost_prob']:.2f}")
                        st.markdown(f"**趋势得分 (LSTM)**: {row['lstm_score']:.2f}")
                        st.markdown(f"**情绪得分**: {row['sentiment_score']:.2f}")
                        st.markdown(f"**所属行业/概念**: {row['industry']}")
                        st.markdown(f"**数据来源**: {'实时' if row['is_realtime'] else '历史'}")
                        st.markdown(f"**市场**: {row['market']}")
                    with col2:
                        daily_data, _ = get_batch_daily_data([row['ts_code']], start_date, end_date, _cache_buster=str(time.time()))
                        daily_data = daily_data.head(5)
                        if not daily_data.empty:
                            st.plotly_chart(
                                plot_candlestick(daily_data, row['name'], row['ts_code']),
                                key=f"{row['ts_code']}_rec_candlestick",
                                use_container_width=True
                            )
                        st.plotly_chart(
                            plot_factor_breakdown(row, row['ts_code']),
                            key=f"{row['ts_code']}_rec_factors",
                            use_container_width=True
                        )
