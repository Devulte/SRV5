"""
TinyShare Integration Module for Chinese Stock News Extraction
Provides optimized news fetching and sentiment analysis capabilities
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
import jieba
import re
import pandas as pd
from config import config, NEWS_CONFIG
from performance_monitor import performance_monitor, api_monitor, memory_monitor

logger = logging.getLogger(__name__)

# Lazy import for tinyshare
def import_tinyshare():
    """Lazy import tinyshare to avoid startup penalty"""
    try:
        import tinyshare as tns
        return tns
    except ImportError:
        logger.error("tinyshare library not installed. Install with: pip install tinyshare")
        return None

class TinyShareNewsAPI:
    """Optimized TinyShare API client for news extraction using tinyshare library"""
    
    def __init__(self):
        self.token = config.get_tinyshare_token()
        self.tns = import_tinyshare()
        
        if self.tns is None:
            raise ImportError("TinyShare library not available")
        
        # Initialize TinyShare Pro API
        try:
            self.pro_api = self.tns.pro_api(self.token)
            logger.info("TinyShare Pro API initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TinyShare Pro API: {e}")
            raise e
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
    
    def _rate_limit(self):
        """Implement rate limiting to avoid API throttling"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    @api_monitor("tinyshare_news")
    def get_stock_news(self, stock_code: str = None, days_back: int = 7, limit: int = 20, src: str = '') -> List[Dict]:
        """
        Get news using TinyShare news_ts API
        
        Args:
            stock_code: Stock code (optional, can be None for general news)
            days_back: Number of days to look back
            limit: Maximum number of news items (not directly supported by API)
            src: News source filter
            
        Returns:
            List of news items with title, content, publish_time, sentiment
        """
        self._rate_limit()
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Format dates for TinyShare API (YYYY-MM-DD HH:MM:SS)
            start_date_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_date_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            # Call TinyShare news_ts API
            df = self.pro_api.news_ts(
                src=src,
                start_date=start_date_str,
                end_date=end_date_str
            )
            
            if df is not None and not df.empty:
                # Convert DataFrame to list of dictionaries
                news_items = df.to_dict('records')
                
                # Filter by stock code if provided
                if stock_code:
                    formatted_code = self._format_stock_code(stock_code)
                    # Filter news that mentions the stock code or company
                    filtered_items = []
                    for item in news_items:
                        content = str(item.get('content', '')) + str(item.get('title', ''))
                        if formatted_code in content or stock_code in content:
                            filtered_items.append(item)
                    news_items = filtered_items
                
                # Limit results
                if limit > 0:
                    news_items = news_items[:limit]
                
                # Process and enhance news items
                processed_news = []
                for item in news_items:
                    processed_item = self._process_news_item(item)
                    if processed_item:
                        processed_news.append(processed_item)
                
                logger.info(f"Retrieved {len(processed_news)} news items" + 
                           (f" for {stock_code}" if stock_code else ""))
                return processed_news
            
            else:
                logger.warning("TinyShare API returned empty DataFrame")
                return []
                
        except Exception as e:
            logger.error(f"TinyShare API error: {e}")
            return []
    
    @api_monitor("tinyshare_market_news")
    def get_market_news(self, days_back: int = 3, limit: int = 50, src: str = '') -> List[Dict]:
        """
        Get general market news using TinyShare API
        
        Args:
            days_back: Number of days to look back
            limit: Maximum number of news items
            src: News source filter
            
        Returns:
            List of market news items
        """
        # Use the same get_stock_news method but without stock code filtering
        return self.get_stock_news(stock_code=None, days_back=days_back, limit=limit, src=src)
    
    def _format_stock_code(self, stock_code: str) -> str:
        """Format stock code for TinyShare API"""
        # Remove any suffix like .SH, .SZ
        code = stock_code.split('.')[0]
        
        # Ensure 6 digits
        if len(code) < 6:
            code = code.zfill(6)
        
        return code
    
    def _process_news_item(self, item: Dict) -> Optional[Dict]:
        """Process and enhance a single news item from TinyShare DataFrame"""
        try:
            # TinyShare DataFrame column mapping - adjust based on actual column names
            title = str(item.get('title', item.get('Title', '')))
            content = str(item.get('content', item.get('Content', item.get('summary', ''))))
            
            # Handle different possible datetime column names
            publish_time = item.get('datetime', item.get('pub_time', item.get('time', '')))
            if isinstance(publish_time, pd.Timestamp):
                publish_time = publish_time.isoformat()
            elif publish_time:
                publish_time = str(publish_time)
            
            source = str(item.get('source', item.get('Source', 'TinyShare')))
            
            # Skip if no meaningful content
            if not title and not content:
                return None
            
            # Combine title and content for sentiment analysis
            full_text = f"{title} {content}".strip()
            if not full_text:
                return None
            
            # Clean and process content
            cleaned_content = self._clean_text(content)
            cleaned_title = self._clean_text(title)
            
            # Calculate sentiment score
            sentiment_score = self._calculate_sentiment(cleaned_title + ' ' + cleaned_content)
            
            return {
                'title': cleaned_title,
                'content': cleaned_content,
                'publish_time': publish_time,
                'source': source,
                'sentiment_score': sentiment_score,
                'length': len(cleaned_content),
                'processed_at': datetime.now().isoformat(),
                'raw_item': item  # Keep original for debugging
            }
            
        except Exception as e:
            logger.warning(f"Error processing news item: {e}")
            logger.debug(f"Problematic item: {item}")
            return None
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove special characters but keep Chinese characters
        text = re.sub(r'[^\u4e00-\u9fff\w\s.,!?;:]', '', text)
        
        # Limit length to avoid memory issues
        max_length = 1000
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        return text
    
    def _calculate_sentiment(self, text: str) -> float:
        """
        Calculate sentiment score using keyword matching
        
        Returns:
            Float between -1 (very negative) and 1 (very positive)
        """
        if not text:
            return 0.0
        
        # Use jieba for Chinese text segmentation
        words = list(jieba.cut(text.lower()))
        
        positive_count = 0
        negative_count = 0
        
        # Count positive keywords
        for word in words:
            if word in NEWS_CONFIG.POSITIVE_KEYWORDS:
                positive_count += 1
            elif word in NEWS_CONFIG.NEGATIVE_KEYWORDS:
                negative_count += 1
        
        # Calculate sentiment score
        total_sentiment_words = positive_count + negative_count
        
        if total_sentiment_words == 0:
            return 0.0
        
        # Normalize to -1 to 1 range
        sentiment_score = (positive_count - negative_count) / total_sentiment_words
        
        # Apply smoothing to avoid extreme values
        sentiment_score = sentiment_score * 0.8  # Dampen the score
        
        return max(-1.0, min(1.0, sentiment_score))

class NewsProcessor:
    """Optimized news processing and aggregation"""
    
    def __init__(self):
        self.api = TinyShareNewsAPI()
        self.cache = {}
        self.cache_expiry = {}
    
    @st.cache_data(ttl=NEWS_CONFIG.NEWS_CACHE_TTL)
    def get_cached_news(_self, stock_code: str, days_back: int = 7) -> List[Dict]:
        """Get news with caching"""
        return _self.api.get_stock_news(stock_code, days_back)
    
    @performance_monitor
    def get_stock_news_batch(self, stock_codes: List[str], days_back: int = 7) -> Dict[str, List[Dict]]:
        """
        Get news for multiple stocks in parallel
        
        Args:
            stock_codes: List of stock codes
            days_back: Days to look back for news
            
        Returns:
            Dict mapping stock codes to news lists
        """
        results = {}
        
        with memory_monitor("batch_news_processing"):
            # Limit batch size to prevent memory issues
            batch_size = min(len(stock_codes), 20)
            limited_codes = stock_codes[:batch_size]
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_code = {
                    executor.submit(self.get_cached_news, code, days_back): code 
                    for code in limited_codes
                }
                
                for future in as_completed(future_to_code):
                    stock_code = future_to_code[future]
                    try:
                        news_items = future.result()
                        results[stock_code] = news_items
                    except Exception as e:
                        logger.warning(f"Failed to get news for {stock_code}: {e}")
                        results[stock_code] = []
        
        return results
    
    @performance_monitor
    def calculate_stock_sentiment(self, news_items: List[Dict]) -> Dict[str, float]:
        """
        Calculate aggregated sentiment metrics for a stock
        
        Args:
            news_items: List of news items for the stock
            
        Returns:
            Dict with sentiment metrics
        """
        if not news_items:
            return {
                'overall_sentiment': 0.0,
                'recent_sentiment': 0.0,
                'news_count': 0,
                'positive_ratio': 0.0
            }
        
        # Calculate overall sentiment
        sentiment_scores = [item.get('sentiment_score', 0.0) for item in news_items]
        overall_sentiment = sum(sentiment_scores) / len(sentiment_scores)
        
        # Calculate recent sentiment (last 3 days)
        recent_cutoff = (datetime.now() - timedelta(days=3)).isoformat()
        recent_items = [
            item for item in news_items 
            if item.get('publish_time', '') >= recent_cutoff
        ]
        
        if recent_items:
            recent_scores = [item.get('sentiment_score', 0.0) for item in recent_items]
            recent_sentiment = sum(recent_scores) / len(recent_scores)
        else:
            recent_sentiment = overall_sentiment
        
        # Calculate positive news ratio
        positive_count = sum(1 for score in sentiment_scores if score > 0.1)
        positive_ratio = positive_count / len(sentiment_scores) if sentiment_scores else 0.0
        
        return {
            'overall_sentiment': overall_sentiment,
            'recent_sentiment': recent_sentiment,
            'news_count': len(news_items),
            'positive_ratio': positive_ratio
        }
    
    def get_market_sentiment(self) -> Dict[str, Any]:
        """Get overall market sentiment from general news"""
        try:
            market_news = self.api.get_market_news(days_back=3, limit=30)
            return self.calculate_stock_sentiment(market_news)
        except Exception as e:
            logger.error(f"Error getting market sentiment: {e}")
            return {
                'overall_sentiment': 0.0,
                'recent_sentiment': 0.0,
                'news_count': 0,
                'positive_ratio': 0.0
            }

# Enhanced sentiment analysis for integration
class EnhancedSentimentAnalyzer:
    """Advanced sentiment analysis with financial context"""
    
    def __init__(self):
        self.financial_multipliers = {
            # Financial terms that amplify sentiment
            '业绩': 1.5, '财报': 1.3, '营收': 1.4, '利润': 1.5,
            '亏损': -1.5, '债务': -1.3, '风险': -1.2, '违约': -1.8
        }
    
    def analyze_with_context(self, text: str, stock_info: Dict = None) -> Dict[str, float]:
        """
        Analyze sentiment with financial context
        
        Args:
            text: News text to analyze
            stock_info: Optional stock information for context
            
        Returns:
            Dict with detailed sentiment analysis
        """
        base_sentiment = self._basic_sentiment(text)
        
        # Apply financial context multipliers
        words = list(jieba.cut(text.lower()))
        multiplier = 1.0
        
        for word in words:
            if word in self.financial_multipliers:
                multiplier *= self.financial_multipliers[word]
        
        # Limit multiplier to reasonable range
        multiplier = max(0.5, min(2.0, multiplier))
        
        adjusted_sentiment = base_sentiment * multiplier
        adjusted_sentiment = max(-1.0, min(1.0, adjusted_sentiment))
        
        return {
            'base_sentiment': base_sentiment,
            'context_multiplier': multiplier,
            'final_sentiment': adjusted_sentiment,
            'confidence': min(abs(adjusted_sentiment) + 0.1, 1.0)
        }
    
    def _basic_sentiment(self, text: str) -> float:
        """Basic sentiment calculation using keyword matching"""
        words = list(jieba.cut(text.lower()))
        
        positive_count = sum(1 for word in words if word in NEWS_CONFIG.POSITIVE_KEYWORDS)
        negative_count = sum(1 for word in words if word in NEWS_CONFIG.NEGATIVE_KEYWORDS)
        
        if positive_count + negative_count == 0:
            return 0.0
        
        return (positive_count - negative_count) / (positive_count + negative_count)

# Global instances for easy access
news_processor = NewsProcessor()
sentiment_analyzer = EnhancedSentimentAnalyzer()