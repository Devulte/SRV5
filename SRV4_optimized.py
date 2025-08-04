import streamlit as st
from datetime import datetime, timedelta
import logging
import time
import asyncio
from typing import Dict, List, Optional, Tuple, Any
import gc

# Lazy imports for heavy dependencies
@st.cache_resource
def get_heavy_imports():
    """Lazy load heavy ML and data processing libraries"""
    import pandas as pd
    import numpy as np
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score
    import plotly.graph_objects as go
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import retrying
    
    return {
        'pd': pd,
        'np': np,
        'MinMaxScaler': MinMaxScaler,
        'RandomForestClassifier': RandomForestClassifier,
        'accuracy_score': accuracy_score,
        'go': go,
        'ThreadPoolExecutor': ThreadPoolExecutor,
        'as_completed': as_completed,
        'retrying': retrying
    }

# Conditional imports for optional features
def import_optional_ml():
    """Import optional ML libraries only when needed"""
    try:
        import optuna
        import optuna.logging
        from catboost import CatBoostClassifier
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        return {'optuna': optuna, 'CatBoostClassifier': CatBoostClassifier}
    except ImportError:
        return None

def import_data_sources():
    """Import data source libraries only when needed"""
    sources = {}
    try:
        import tushare as ts
        sources['tushare'] = ts
    except ImportError:
        pass
    
    try:
        import akshare as ak
        sources['akshare'] = ak
    except ImportError:
        pass
    
    try:
        import baostock as bs
        sources['baostock'] = bs
    except ImportError:
        pass
    
    try:
        import jieba
        sources['jieba'] = jieba
    except ImportError:
        pass
    
    return sources

# Optimized logging setup
@st.cache_resource
def setup_logging():
    """Setup logging with caching to avoid recreation"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    return logging.getLogger("StockRecommendation")

logger = setup_logging()

# Configuration class for better organization
class AppConfig:
    """Centralized configuration management"""
    def __init__(self):
        self.TUSHARE_TOKEN = '2876ea85cb005fb5fa17c809a98174f2d5aae8b1f830110a5ead6211'
        self.DEFAULT_DAYS_BACK = 30
        self.DEFAULT_TOP_N = 10
        self.MAX_WORKERS = 3
        self.BATCH_SIZE = 100
        self.CACHE_TTL = 3600  # 1 hour
        self.MAX_STOCKS_FOR_ANALYSIS = 500  # Limit to prevent memory issues
        
    @property
    def date_range(self):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.DEFAULT_DAYS_BACK)
        return start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')

config = AppConfig()

# Memory-efficient data structures
class DataCache:
    """Memory-efficient caching with automatic cleanup"""
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
    
    def get(self, key: str):
        if key in self.cache:
            self.access_times[key] = time.time()
            return self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        if len(self.cache) >= self.max_size:
            self._cleanup()
        self.cache[key] = value
        self.access_times[key] = time.time()
    
    def _cleanup(self):
        """Remove least recently used items"""
        sorted_items = sorted(self.access_times.items(), key=lambda x: x[1])
        to_remove = sorted_items[:len(sorted_items) // 2]
        for key, _ in to_remove:
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
        gc.collect()

# Global cache instance
data_cache = DataCache()

# Streamlit configuration with performance optimizations
st.set_page_config(
    page_title="A股股票推荐系统", 
    layout="wide",
    initial_sidebar_state="collapsed"  # Reduce initial render
)

# Lazy initialization of session state
def init_session_state():
    """Initialize session state with minimal data"""
    defaults = {
        'dynamic_factors': ['northbuy', 'turnover', 'dt_ratio', 'callback'],
        'catboost_params': {'depth': 6, 'learning_rate': 0.1, 'iterations': 100},
        'recommendations': None,
        'data_sources_initialized': False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# Optimized Tushare initialization
@st.cache_resource(ttl=config.CACHE_TTL)
def init_tushare():
    """Initialize Tushare API with caching and error handling"""
    try:
        sources = import_data_sources()
        if 'tushare' not in sources:
            raise ImportError("Tushare not available")
        
        ts = sources['tushare']
        ts.set_token(config.TUSHARE_TOKEN)
        pro = ts.pro_api()
        logger.info("Tushare API initialized successfully")
        return pro
    except Exception as e:
        logger.error(f"Tushare API initialization failed: {e}")
        st.error(f"Tushare API初始化失败: {e}")
        return None

# Async-like pattern for better UX
class DataFetcher:
    """Optimized data fetching with memory management"""
    
    def __init__(self):
        self.imports = get_heavy_imports()
        self.pd = self.imports['pd']
        self.retrying = self.imports['retrying']
        self.sources = import_data_sources()
        self.pro = init_tushare()
    
    @st.cache_data(ttl=config.CACHE_TTL)
    def get_stock_list(self) -> Optional['pd.DataFrame']:
        """Get filtered stock list with memory optimization"""
        if not self.pro:
            return self.pd.DataFrame()
        
        try:
            # Use more specific fields to reduce memory usage
            df = self.pro.stock_basic(
                list_status='L', 
                fields='ts_code,symbol,name,market,total_share'
            )
            
            # Filter early to reduce memory footprint
            filtered_df = df[
                df['market'].isin(['主板', '创业板', '科创板']) &  # Exclude 北交所 for performance
                ~df['name'].str.contains('ST|退', na=False)
            ].head(config.MAX_STOCKS_FOR_ANALYSIS)  # Limit dataset size
            
            logger.info(f"Retrieved {len(filtered_df)} stocks")
            return filtered_df
            
        except Exception as e:
            logger.error(f"Failed to retrieve stock list: {e}")
            return self.pd.DataFrame()
    
    @st.cache_data(ttl=1800)  # 30 minutes cache
    def get_batch_data_optimized(self, ts_codes: List[str], data_type: str = 'daily') -> 'pd.DataFrame':
        """Optimized batch data retrieval with fallback strategy"""
        if not ts_codes:
            return self.pd.DataFrame()
        
        # Try AKShare first for real-time data (faster)
        if data_type == 'daily' and 'akshare' in self.sources:
            try:
                ak = self.sources['akshare']
                df = ak.stock_zh_a_spot_em()
                ak_codes = [code[:6] for code in ts_codes]
                filtered_df = df[df['代码'].isin(ak_codes)][:50]  # Limit results
                
                if not filtered_df.empty:
                    # Standardize column names
                    result_df = filtered_df[['代码', '最新价', '涨跌幅', '成交量', '成交额']].copy()
                    result_df.columns = ['ts_code', 'price', 'pct_change', 'volume', 'amount']
                    result_df['ts_code'] = result_df['ts_code'].apply(
                        lambda x: x + ('.SH' if x.startswith('6') else '.SZ')
                    )
                    result_df['trade_date'] = datetime.now().strftime('%Y%m%d')
                    result_df['is_realtime'] = True
                    
                    return result_df
            except Exception as e:
                logger.warning(f"AKShare failed: {e}")
        
        # Fallback to Tushare
        if self.pro:
            try:
                start_date, end_date = config.date_range
                
                if data_type == 'daily':
                    df = self.pro.daily(
                        ts_code=','.join(ts_codes[:50]),  # Limit batch size
                        start_date=start_date, 
                        end_date=end_date
                    )
                elif data_type == 'moneyflow':
                    df = self.pro.moneyflow(
                        ts_code=','.join(ts_codes[:50]),
                        start_date=start_date, 
                        end_date=end_date
                    )
                else:
                    return self.pd.DataFrame()
                
                df['is_realtime'] = False
                return df
                
            except Exception as e:
                logger.error(f"Tushare {data_type} failed: {e}")
        
        return self.pd.DataFrame()

# Lightweight factor computation
class FactorCalculator:
    """Memory-efficient factor calculation"""
    
    def __init__(self):
        self.imports = get_heavy_imports()
        self.np = self.imports['np']
        self.pd = self.imports['pd']
    
    def compute_basic_factors(self, stock_data: Dict, daily_data: 'pd.DataFrame') -> Dict[str, float]:
        """Compute only essential factors to reduce computation"""
        factors = {}
        
        if daily_data.empty:
            return {f: 0.0 for f in st.session_state.dynamic_factors}
        
        try:
            # Simplified factor calculation
            latest = daily_data.iloc[-1] if len(daily_data) > 0 else {}
            
            if 'northbuy' in st.session_state.dynamic_factors:
                factors['northbuy'] = float(latest.get('amount', 0)) / 1e8  # Simplified proxy
            
            if 'turnover' in st.session_state.dynamic_factors:
                factors['turnover'] = float(latest.get('volume', 0)) / 1e6  # Simplified
            
            if 'dt_ratio' in st.session_state.dynamic_factors:
                factors['dt_ratio'] = 0.5  # Placeholder - would need complex calculation
            
            if 'callback' in st.session_state.dynamic_factors:
                if len(daily_data) >= 5:
                    recent_high = daily_data['price'].tail(5).max() if 'price' in daily_data else daily_data.get('close', pd.Series([0])).tail(5).max()
                    current_price = float(latest.get('price', latest.get('close', 0)))
                    factors['callback'] = ((recent_high - current_price) / recent_high * 100) if recent_high > 0 else 0
                else:
                    factors['callback'] = 0
            
            return factors
            
        except Exception as e:
            logger.warning(f"Factor calculation error: {e}")
            return {f: 0.0 for f in st.session_state.dynamic_factors}

# Simplified scoring system
class ScoreCalculator:
    """Lightweight scoring system"""
    
    def __init__(self):
        self.imports = get_heavy_imports()
        self.np = self.imports['np']
    
    def compute_score(self, factors: Dict[str, float], daily_data: 'pd.DataFrame') -> Dict[str, float]:
        """Simplified scoring algorithm"""
        try:
            # Simple weighted average of factors
            factor_values = list(factors.values())
            if not factor_values:
                return {'final_score': 0.5, 'is_realtime': False}
            
            # Normalize to 0-1 range
            max_val = max(factor_values) if factor_values else 1
            min_val = min(factor_values) if factor_values else 0
            range_val = max_val - min_val if max_val != min_val else 1
            
            normalized_scores = [(v - min_val) / range_val for v in factor_values]
            final_score = self.np.mean(normalized_scores)
            
            # Add momentum bonus
            if not daily_data.empty and len(daily_data) >= 2:
                recent_change = daily_data['pct_change'].tail(2).mean() if 'pct_change' in daily_data else 0
                if recent_change > 0:
                    final_score += 0.1
            
            is_realtime = daily_data.get('is_realtime', pd.Series([False])).iloc[0] if not daily_data.empty and 'is_realtime' in daily_data else False
            
            return {
                'final_score': float(self.np.clip(final_score, 0, 1)),
                'catboost_prob': final_score,
                'lstm_score': final_score,
                'sentiment_score': 0.5,  # Simplified
                'is_realtime': bool(is_realtime)
            }
            
        except Exception as e:
            logger.warning(f"Score calculation error: {e}")
            return {'final_score': 0.5, 'is_realtime': False}

# Main application class
class StockRecommendationApp:
    """Main application with optimized structure"""
    
    def __init__(self):
        self.data_fetcher = DataFetcher()
        self.factor_calculator = FactorCalculator()
        self.score_calculator = ScoreCalculator()
        self.imports = get_heavy_imports()
        self.pd = self.imports['pd']
    
    def show_header(self):
        """Render header with minimal HTML"""
        st.title("📈 A股股票推荐系统")
        st.markdown("轻量级股票推荐系统 - 优化版本")
    
    def show_sidebar(self):
        """Optimized sidebar with better defaults"""
        with st.sidebar:
            st.header("⚙️ 设置")
            
            top_n = st.slider("推荐数量", 5, 20, 10)
            days_back = st.selectbox("数据天数", [10, 30, 60], index=1)
            
            # Update config
            config.DEFAULT_DAYS_BACK = days_back
            config.DEFAULT_TOP_N = top_n
            
            return st.button("🚀 生成推荐", type="primary")
    
    @st.cache_data(ttl=1800)
    def process_recommendations(_self, num_stocks: int = 100) -> 'pd.DataFrame':
        """Optimized recommendation processing"""
        try:
            # Get stock list
            stock_list = _self.data_fetcher.get_stock_list()
            if stock_list.empty:
                return _self.pd.DataFrame()
            
            # Limit processing for performance
            limited_stocks = stock_list.head(num_stocks)
            
            # Process in smaller batches
            batch_size = 20
            results = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i in range(0, len(limited_stocks), batch_size):
                batch = limited_stocks.iloc[i:i+batch_size]
                ts_codes = batch['ts_code'].tolist()
                
                # Get batch data
                daily_data = _self.data_fetcher.get_batch_data_optimized(ts_codes, 'daily')
                
                for _, stock in batch.iterrows():
                    ts_code = stock['ts_code']
                    stock_daily = daily_data[daily_data['ts_code'] == ts_code] if not daily_data.empty else _self.pd.DataFrame()
                    
                    # Calculate factors and scores
                    factors = _self.factor_calculator.compute_basic_factors(stock.to_dict(), stock_daily)
                    scores = _self.score_calculator.compute_score(factors, stock_daily)
                    
                    # Combine results
                    result = {
                        'ts_code': ts_code,
                        'name': stock['name'],
                        'market': stock['market'],
                        **factors,
                        **scores
                    }
                    results.append(result)
                
                # Update progress
                progress = (i + batch_size) / len(limited_stocks)
                progress_bar.progress(min(progress, 1.0))
                status_text.text(f"处理中... {i+batch_size}/{len(limited_stocks)}")
            
            progress_bar.empty()
            status_text.empty()
            
            # Create and sort results
            results_df = _self.pd.DataFrame(results)
            if not results_df.empty:
                results_df = results_df.sort_values('final_score', ascending=False)
            
            return results_df
            
        except Exception as e:
            logger.error(f"Recommendation processing failed: {e}")
            return _self.pd.DataFrame()
    
    def show_recommendations(self, recommendations_df: 'pd.DataFrame'):
        """Display recommendations with optimized rendering"""
        if recommendations_df.empty:
            st.warning("暂无推荐结果")
            return
        
        st.subheader(f"📊 推荐结果 (前{config.DEFAULT_TOP_N})")
        
        # Show summary table
        display_columns = ['ts_code', 'name', 'final_score', 'market', 'is_realtime']
        display_df = recommendations_df[display_columns].head(config.DEFAULT_TOP_N)
        display_df.columns = ['代码', '名称', '得分', '市场', '实时数据']
        
        st.dataframe(
            display_df.style.format({
                '得分': '{:.3f}',
                '实时数据': lambda x: '✓' if x else '✗'
            }).background_gradient(subset=['得分'], cmap='RdYlGn'),
            use_container_width=True
        )
        
        # Show basic statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("推荐股票数", len(display_df))
        with col2:
            st.metric("平均得分", f"{display_df['得分'].mean():.3f}")
        with col3:
            realtime_count = display_df['实时数据'].sum()
            st.metric("实时数据源", f"{realtime_count}/{len(display_df)}")
    
    def run(self):
        """Main application loop"""
        self.show_header()
        
        # Show data source status
        if not st.session_state.data_sources_initialized:
            with st.spinner("初始化数据源..."):
                sources = import_data_sources()
                available_sources = list(sources.keys())
                st.session_state.data_sources_initialized = True
                
                if available_sources:
                    st.success(f"可用数据源: {', '.join(available_sources)}")
                else:
                    st.error("无可用数据源，请安装相关依赖")
                    return
        
        run_analysis = self.show_sidebar()
        
        if run_analysis:
            with st.spinner("生成推荐中..."):
                recommendations = self.process_recommendations()
                st.session_state.recommendations = recommendations
        
        # Show cached recommendations
        if st.session_state.recommendations is not None:
            self.show_recommendations(st.session_state.recommendations)

# Performance monitoring
def show_performance_info():
    """Show performance information"""
    with st.expander("性能信息", expanded=False):
        import psutil
        import sys
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("内存使用", f"{psutil.Process().memory_info().rss / 1024 / 1024:.1f} MB")
            st.metric("Python版本", f"{sys.version.split()[0]}")
        
        with col2:
            st.metric("缓存项目", len(data_cache.cache))
            st.metric("Streamlit版本", st.__version__)

# Main execution
if __name__ == "__main__":
    try:
        app = StockRecommendationApp()
        app.run()
        
        # Show performance info in sidebar
        with st.sidebar:
            show_performance_info()
            
    except Exception as e:
        st.error(f"应用启动失败: {e}")
        logger.error(f"Application startup failed: {e}")