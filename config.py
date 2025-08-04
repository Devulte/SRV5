"""
Performance-optimized configuration for Stock Recommendation System
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class PerformanceConfig:
    """Performance-related configuration"""
    # Memory management
    MAX_MEMORY_MB: int = 512  # Maximum memory usage
    CACHE_SIZE: int = 1000  # Number of items in custom cache
    BATCH_SIZE: int = 20  # Processing batch size
    MAX_STOCKS: int = 500  # Maximum stocks to analyze
    
    # Caching TTL (seconds)
    CACHE_TTL_SHORT: int = 900   # 15 minutes
    CACHE_TTL_MEDIUM: int = 1800  # 30 minutes  
    CACHE_TTL_LONG: int = 3600   # 1 hour
    
    # Threading
    MAX_WORKERS: int = 3  # Concurrent worker threads
    TIMEOUT_SECONDS: int = 30  # API timeout
    
    # Data limits
    MAX_HISTORY_DAYS: int = 60  # Maximum historical data
    MIN_VOLUME_THRESHOLD: int = 1000  # Minimum volume filter
    MIN_MARKET_CAP: float = 5e8  # Minimum market cap (500M)

@dataclass 
class UIConfig:
    """UI performance configuration"""
    INITIAL_SIDEBAR_STATE: str = "collapsed"
    DEFAULT_THEME: str = "light"
    ENABLE_ANIMATIONS: bool = False  # Disable for performance
    CHART_HEIGHT: int = 300  # Reduced chart height
    TABLE_PAGE_SIZE: int = 20  # Pagination for large tables

@dataclass
class DataSourceConfig:
    """Data source priority and configuration"""
    # Priority order for data sources (higher number = higher priority)
    SOURCE_PRIORITY: Dict[str, int] = None
    
    # Retry configuration
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0  # seconds
    
    # Data source specific limits
    TUSHARE_DAILY_LIMIT: int = 200  # requests per minute
    AKSHARE_BATCH_SIZE: int = 50  # stocks per request
    TINYSHARE_NEWS_LIMIT: int = 100  # news items per request
    
    def __post_init__(self):
        if self.SOURCE_PRIORITY is None:
            self.SOURCE_PRIORITY = {
                'akshare': 4,     # Fastest for real-time data
                'tinyshare': 3,   # Best for news data
                'tushare': 2,     # Most comprehensive stock data
                'baostock': 1     # Fallback
            }

@dataclass
class AlgorithmConfig:
    """Algorithm and ML configuration"""
    # Simplified factor weights
    FACTOR_WEIGHTS: Dict[str, float] = None
    
    # Model parameters
    ENABLE_ADVANCED_ML: bool = False  # Disable complex models for speed
    ENABLE_HYPERPARAMETER_TUNING: bool = False
    ENABLE_NEWS_SENTIMENT: bool = True  # Enable news sentiment analysis
    
    # Scoring thresholds
    MIN_SCORE_THRESHOLD: float = 0.3
    TOP_N_DEFAULT: int = 10
    
    # News sentiment configuration
    NEWS_SENTIMENT_WEIGHT: float = 0.15  # Weight of news sentiment in final score
    NEWS_LOOKBACK_DAYS: int = 7  # Days to look back for news
    
    def __post_init__(self):
        if self.FACTOR_WEIGHTS is None:
            self.FACTOR_WEIGHTS = {
                'northbuy': 0.3,
                'turnover': 0.25,
                'callback': 0.25,
                'dt_ratio': 0.15,
                'news_sentiment': 0.05  # Add news sentiment factor
            }

@dataclass
class NewsConfig:
    """News processing configuration"""
    # TinyShare configuration
    TINYSHARE_TOKEN: str = "2cGxAf73bwxidFp688OMckn24Ie2Glw9B61H8gmqbs0200FGv46J8jVd8718e62c"
    TINYSHARE_BASE_URL: str = "https://api.tinyshare.cn"
    
    # News processing limits
    MAX_NEWS_PER_STOCK: int = 20
    NEWS_CACHE_TTL: int = 1800  # 30 minutes
    
    # Sentiment analysis keywords
    POSITIVE_KEYWORDS: List[str] = None
    NEGATIVE_KEYWORDS: List[str] = None
    
    def __post_init__(self):
        if self.POSITIVE_KEYWORDS is None:
            self.POSITIVE_KEYWORDS = [
                '上涨', '利好', '增长', '盈利', '突破', '创新', '扩张', '收购',
                '合作', '签约', '中标', '获批', '升级', '优化', '领先', '成功',
                '业绩', '分红', '回购', '重组', '转型', '发展', '机遇', '潜力'
            ]
        
        if self.NEGATIVE_KEYWORDS is None:
            self.NEGATIVE_KEYWORDS = [
                '下跌', '亏损', '风险', '下滑', '危机', '违约', '退市', '暂停',
                '调查', '处罚', '诉讼', '减持', '质押', '债务', '亏损', '停产',
                '裁员', '关闭', '取消', '延期', '失败', '问题', '困难', '挑战'
            ]

class AppConfig:
    """Main application configuration"""
    
    def __init__(self):
        self.performance = PerformanceConfig()
        self.ui = UIConfig() 
        self.data_sources = DataSourceConfig()
        self.algorithms = AlgorithmConfig()
        self.news = NewsConfig()
        
        # Environment-based overrides
        self._apply_env_overrides()
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        # Performance overrides
        if os.getenv('MAX_STOCKS'):
            self.performance.MAX_STOCKS = int(os.getenv('MAX_STOCKS'))
        
        if os.getenv('BATCH_SIZE'):
            self.performance.BATCH_SIZE = int(os.getenv('BATCH_SIZE'))
        
        if os.getenv('MAX_WORKERS'):
            self.performance.MAX_WORKERS = int(os.getenv('MAX_WORKERS'))
        
        # Feature toggles
        if os.getenv('ENABLE_ADVANCED_ML', '').lower() == 'true':
            self.algorithms.ENABLE_ADVANCED_ML = True
            
        if os.getenv('ENABLE_HYPERPARAMETER_TUNING', '').lower() == 'true':
            self.algorithms.ENABLE_HYPERPARAMETER_TUNING = True
        
        if os.getenv('ENABLE_NEWS_SENTIMENT', '').lower() == 'false':
            self.algorithms.ENABLE_NEWS_SENTIMENT = False
        
        # News configuration overrides
        if os.getenv('TINYSHARE_TOKEN'):
            self.news.TINYSHARE_TOKEN = os.getenv('TINYSHARE_TOKEN')
        
        if os.getenv('NEWS_LOOKBACK_DAYS'):
            self.algorithms.NEWS_LOOKBACK_DAYS = int(os.getenv('NEWS_LOOKBACK_DAYS'))
    
    def get_tushare_token(self) -> Optional[str]:
        """Get Tushare token from environment or config"""
        return os.getenv('TUSHARE_TOKEN', '2876ea85cb005fb5fa17c809a98174f2d5aae8b1f830110a5ead6211')
    
    def get_tinyshare_token(self) -> str:
        """Get TinyShare token from environment or config"""
        return os.getenv('TINYSHARE_TOKEN', self.news.TINYSHARE_TOKEN)
    
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return os.getenv('ENVIRONMENT', 'production').lower() == 'development'
    
    def get_log_level(self) -> str:
        """Get logging level"""
        return os.getenv('LOG_LEVEL', 'INFO').upper()

# Global config instance
config = AppConfig()

# Export commonly used values
PERFORMANCE_CONFIG = config.performance
UI_CONFIG = config.ui
DATA_SOURCE_CONFIG = config.data_sources
ALGORITHM_CONFIG = config.algorithms
NEWS_CONFIG = config.news