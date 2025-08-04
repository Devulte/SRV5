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
    
    def __post_init__(self):
        if self.SOURCE_PRIORITY is None:
            self.SOURCE_PRIORITY = {
                'akshare': 3,    # Fastest for real-time
                'tushare': 2,    # Most comprehensive
                'baostock': 1    # Fallback
            }

@dataclass
class AlgorithmConfig:
    """Algorithm and ML configuration"""
    # Simplified factor weights
    FACTOR_WEIGHTS: Dict[str, float] = None
    
    # Model parameters
    ENABLE_ADVANCED_ML: bool = False  # Disable complex models for speed
    ENABLE_HYPERPARAMETER_TUNING: bool = False
    
    # Scoring thresholds
    MIN_SCORE_THRESHOLD: float = 0.3
    TOP_N_DEFAULT: int = 10
    
    def __post_init__(self):
        if self.FACTOR_WEIGHTS is None:
            self.FACTOR_WEIGHTS = {
                'northbuy': 0.3,
                'turnover': 0.25,
                'callback': 0.25,
                'dt_ratio': 0.2
            }

class AppConfig:
    """Main application configuration"""
    
    def __init__(self):
        self.performance = PerformanceConfig()
        self.ui = UIConfig() 
        self.data_sources = DataSourceConfig()
        self.algorithms = AlgorithmConfig()
        
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
    
    def get_tushare_token(self) -> Optional[str]:
        """Get Tushare token from environment or config"""
        return os.getenv('TUSHARE_TOKEN', '2876ea85cb005fb5fa17c809a98174f2d5aae8b1f830110a5ead6211')
    
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