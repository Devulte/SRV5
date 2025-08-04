"""
Performance monitoring and optimization utilities
"""

import time
import functools
import psutil
import gc
import logging
from typing import Any, Callable, Dict, List, Optional
from contextlib import contextmanager
import streamlit as st

logger = logging.getLogger(__name__)

class PerformanceMetrics:
    """Track and analyze performance metrics"""
    
    def __init__(self):
        self.metrics = {
            'function_calls': {},
            'memory_usage': [],
            'cache_hits': 0,
            'cache_misses': 0,
            'api_calls': {},
            'load_times': {}
        }
        self.start_time = time.time()
    
    def record_function_call(self, func_name: str, duration: float, memory_delta: float = 0):
        """Record function execution metrics"""
        if func_name not in self.metrics['function_calls']:
            self.metrics['function_calls'][func_name] = {
                'count': 0,
                'total_time': 0,
                'avg_time': 0,
                'max_time': 0,
                'min_time': float('inf'),
                'total_memory': 0
            }
        
        metrics = self.metrics['function_calls'][func_name]
        metrics['count'] += 1
        metrics['total_time'] += duration
        metrics['avg_time'] = metrics['total_time'] / metrics['count']
        metrics['max_time'] = max(metrics['max_time'], duration)
        metrics['min_time'] = min(metrics['min_time'], duration)
        metrics['total_memory'] += memory_delta
    
    def record_memory_usage(self):
        """Record current memory usage"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.metrics['memory_usage'].append({
            'timestamp': time.time(),
            'memory_mb': memory_mb
        })
        
        # Keep only last 100 measurements
        if len(self.metrics['memory_usage']) > 100:
            self.metrics['memory_usage'] = self.metrics['memory_usage'][-100:]
    
    def record_cache_event(self, hit: bool):
        """Record cache hit/miss events"""
        if hit:
            self.metrics['cache_hits'] += 1
        else:
            self.metrics['cache_misses'] += 1
    
    def record_api_call(self, api_name: str, duration: float, success: bool):
        """Record API call metrics"""
        if api_name not in self.metrics['api_calls']:
            self.metrics['api_calls'][api_name] = {
                'count': 0,
                'success_count': 0,
                'total_time': 0,
                'avg_time': 0,
                'success_rate': 0
            }
        
        metrics = self.metrics['api_calls'][api_name]
        metrics['count'] += 1
        metrics['total_time'] += duration
        metrics['avg_time'] = metrics['total_time'] / metrics['count']
        
        if success:
            metrics['success_count'] += 1
        
        metrics['success_rate'] = metrics['success_count'] / metrics['count']
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        uptime = time.time() - self.start_time
        
        return {
            'uptime_seconds': uptime,
            'current_memory_mb': current_memory,
            'peak_memory_mb': max([m['memory_mb'] for m in self.metrics['memory_usage']], default=current_memory),
            'cache_hit_rate': self.metrics['cache_hits'] / max(self.metrics['cache_hits'] + self.metrics['cache_misses'], 1),
            'slowest_functions': self._get_slowest_functions(),
            'memory_intensive_functions': self._get_memory_intensive_functions(),
            'api_performance': self.metrics['api_calls']
        }
    
    def _get_slowest_functions(self, top_n: int = 5) -> List[Dict]:
        """Get slowest functions"""
        functions = []
        for name, metrics in self.metrics['function_calls'].items():
            functions.append({
                'name': name,
                'avg_time': metrics['avg_time'],
                'max_time': metrics['max_time'],
                'total_time': metrics['total_time'],
                'count': metrics['count']
            })
        
        return sorted(functions, key=lambda x: x['avg_time'], reverse=True)[:top_n]
    
    def _get_memory_intensive_functions(self, top_n: int = 5) -> List[Dict]:
        """Get memory-intensive functions"""
        functions = []
        for name, metrics in self.metrics['function_calls'].items():
            if metrics['total_memory'] > 0:
                functions.append({
                    'name': name,
                    'total_memory': metrics['total_memory'],
                    'avg_memory': metrics['total_memory'] / metrics['count'],
                    'count': metrics['count']
                })
        
        return sorted(functions, key=lambda x: x['total_memory'], reverse=True)[:top_n]

# Global performance tracker
perf_monitor = PerformanceMetrics()

def performance_monitor(func: Callable) -> Callable:
    """Decorator to monitor function performance"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss
        
        try:
            result = func(*args, **kwargs)
            success = True
        except Exception as e:
            success = False
            raise e
        finally:
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss
            
            duration = end_time - start_time
            memory_delta = (end_memory - start_memory) / 1024 / 1024  # MB
            
            perf_monitor.record_function_call(func.__name__, duration, memory_delta)
            
            # Log slow functions
            if duration > 1.0:
                logger.warning(f"Slow function detected: {func.__name__} took {duration:.2f}s")
        
        return result
    
    return wrapper

def api_monitor(api_name: str):
    """Decorator to monitor API call performance"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                logger.error(f"API call failed: {api_name} - {e}")
                raise e
            finally:
                duration = time.time() - start_time
                perf_monitor.record_api_call(api_name, duration, success)
        
        return wrapper
    return decorator

@contextmanager
def memory_monitor(operation_name: str):
    """Context manager to monitor memory usage of operations"""
    start_memory = psutil.Process().memory_info().rss / 1024 / 1024
    start_time = time.time()
    
    try:
        yield
    finally:
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024
        duration = time.time() - start_time
        memory_delta = end_memory - start_memory
        
        logger.info(f"{operation_name}: {duration:.2f}s, {memory_delta:+.1f}MB")
        
        if memory_delta > 50:  # More than 50MB increase
            logger.warning(f"High memory usage detected: {operation_name} used {memory_delta:.1f}MB")

class MemoryOptimizer:
    """Memory optimization utilities"""
    
    @staticmethod
    def force_garbage_collection():
        """Force garbage collection and return memory freed"""
        initial_memory = psutil.Process().memory_info().rss
        
        # Force garbage collection
        collected = 0
        for generation in range(3):
            collected += gc.collect()
        
        final_memory = psutil.Process().memory_info().rss
        freed_mb = (initial_memory - final_memory) / 1024 / 1024
        
        logger.info(f"Garbage collection: {collected} objects collected, {freed_mb:.1f}MB freed")
        return freed_mb
    
    @staticmethod
    def optimize_dataframe(df, columns_to_keep: Optional[List[str]] = None):
        """Optimize pandas DataFrame memory usage"""
        if df.empty:
            return df
        
        initial_memory = df.memory_usage(deep=True).sum() / 1024 / 1024
        
        # Keep only specified columns
        if columns_to_keep:
            df = df[columns_to_keep].copy()
        
        # Optimize data types
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    # Try to convert to category if few unique values
                    if df[col].nunique() / len(df) < 0.5:
                        df[col] = df[col].astype('category')
                except:
                    pass
            elif df[col].dtype == 'int64':
                # Downcast integers
                if df[col].min() >= 0:
                    if df[col].max() < 255:
                        df[col] = df[col].astype('uint8')
                    elif df[col].max() < 65535:
                        df[col] = df[col].astype('uint16')
                    elif df[col].max() < 4294967295:
                        df[col] = df[col].astype('uint32')
                else:
                    if df[col].min() >= -128 and df[col].max() < 127:
                        df[col] = df[col].astype('int8')
                    elif df[col].min() >= -32768 and df[col].max() < 32767:
                        df[col] = df[col].astype('int16')
                    elif df[col].min() >= -2147483648 and df[col].max() < 2147483647:
                        df[col] = df[col].astype('int32')
            elif df[col].dtype == 'float64':
                # Downcast floats
                df[col] = df[col].astype('float32')
        
        final_memory = df.memory_usage(deep=True).sum() / 1024 / 1024
        reduction = initial_memory - final_memory
        
        if reduction > 1:  # Only log if significant reduction
            logger.info(f"DataFrame optimized: {reduction:.1f}MB saved ({reduction/initial_memory*100:.1f}% reduction)")
        
        return df

def show_performance_dashboard():
    """Show performance dashboard in Streamlit"""
    st.subheader("🔧 性能监控")
    
    summary = perf_monitor.get_summary()
    
    # Basic metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("运行时间", f"{summary['uptime_seconds']/60:.1f}分钟")
    
    with col2:
        st.metric("当前内存", f"{summary['current_memory_mb']:.1f}MB")
    
    with col3:
        st.metric("峰值内存", f"{summary['peak_memory_mb']:.1f}MB")
    
    with col4:
        st.metric("缓存命中率", f"{summary['cache_hit_rate']*100:.1f}%")
    
    # Performance details
    if st.button("🧹 清理内存"):
        freed = MemoryOptimizer.force_garbage_collection()
        st.success(f"已释放 {freed:.1f}MB 内存")
    
    # Slowest functions
    if summary['slowest_functions']:
        st.subheader("最慢函数")
        slow_df = st.dataframe(summary['slowest_functions'])
    
    # API performance
    if summary['api_performance']:
        st.subheader("API性能")
        api_data = []
        for api_name, metrics in summary['api_performance'].items():
            api_data.append({
                'API': api_name,
                '调用次数': metrics['count'],
                '平均时间(s)': f"{metrics['avg_time']:.2f}",
                '成功率(%)': f"{metrics['success_rate']*100:.1f}"
            })
        st.dataframe(api_data)