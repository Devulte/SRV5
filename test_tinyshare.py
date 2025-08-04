#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test script for TinyShare integration
"""

def test_tinyshare_basic():
    """Test basic TinyShare functionality"""
    try:
        import tinyshare as tns
        print("✅ TinyShare library imported successfully")
        
        # Test token
        token = "2cGxAf73bwxidFp688OMckn24Ie2Glw9B61H8gmqbs0200FGv46J8jVd8718e62c"
        
        # Initialize API
        pro_api = tns.pro_api(token)
        print("✅ TinyShare Pro API initialized")
        
        # Test news retrieval
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)
        
        start_date_str = start_date.strftime('%Y-%m-%d 09:00:00')
        end_date_str = end_date.strftime('%Y-%m-%d 18:00:00')
        
        print(f"Testing news retrieval from {start_date_str} to {end_date_str}")
        
        df = pro_api.news_ts(
            src='',
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        if df is not None and not df.empty:
            print(f"✅ Successfully retrieved {len(df)} news items")
            print(f"DataFrame columns: {list(df.columns)}")
            print("\nSample news item:")
            print(df.head(1).to_dict('records')[0])
        else:
            print("⚠️ No news data retrieved (this may be normal if no news in timeframe)")
        
        return True
        
    except ImportError:
        print("❌ TinyShare library not installed. Install with: pip install tinyshare")
        return False
    except Exception as e:
        print(f"❌ Error testing TinyShare: {e}")
        return False

def test_integration():
    """Test the integration module"""
    try:
        from tinyshare_integration import news_processor, sentiment_analyzer
        print("✅ TinyShare integration module imported successfully")
        
        # Test news processing
        test_stock = "000001"
        print(f"Testing news retrieval for {test_stock}...")
        
        news_items = news_processor.get_cached_news(test_stock, days_back=3)
        print(f"Retrieved {len(news_items)} news items for {test_stock}")
        
        if news_items:
            # Test sentiment calculation
            sentiment_metrics = news_processor.calculate_stock_sentiment(news_items)
            print(f"Sentiment metrics: {sentiment_metrics}")
            
            # Show sample news
            print("\nSample news:")
            for i, news in enumerate(news_items[:2]):
                print(f"{i+1}. {news['title']}")
                print(f"   Sentiment: {news['sentiment_score']:.3f}")
                print(f"   Content: {news['content'][:100]}...")
        
        return True
        
    except ImportError as e:
        print(f"❌ Integration module not available: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing integration: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing TinyShare Integration")
    print("=" * 50)
    
    # Test basic TinyShare functionality
    print("\n1. Testing basic TinyShare functionality:")
    basic_success = test_tinyshare_basic()
    
    # Test integration module
    print("\n2. Testing integration module:")
    integration_success = test_integration()
    
    print("\n" + "=" * 50)
    if basic_success and integration_success:
        print("🎉 All tests passed! TinyShare integration is working.")
    elif basic_success:
        print("⚠️ Basic TinyShare works, but integration module has issues.")
    else:
        print("❌ TinyShare basic functionality failed.")
        
    print("\nTo use TinyShare integration:")
    print("1. Install: pip install tinyshare")
    print("2. Run: streamlit run SRV4_optimized.py")
    print("3. Test news in the sidebar")