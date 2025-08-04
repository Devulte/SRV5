# TinyShare 新闻集成设置指南

## 📰 关于 TinyShare

TinyShare 是一个专业的中文股市新闻数据源，为股票推荐系统提供实时新闻和情感分析功能。

## 🚀 快速设置

### 1. 安装 TinyShare 库
```bash
pip install tinyshare
```

### 2. 获取访问令牌
您已经有了 TinyShare 令牌：
```
2cGxAf73bwxidFp688OMckn24Ie2Glw9B61H8gmqbs0200FGv46J8jVd8718e62c
```

### 3. 配置令牌
有两种方式配置令牌：

#### 方式 A: 环境变量（推荐）
```bash
export TINYSHARE_TOKEN="2cGxAf73bwxidFp688OMckn24Ie2Glw9B61H8gmqbs0200FGv46J8jVd8718e62c"
```

#### 方式 B: 修改配置文件
令牌已经在 `config.py` 文件中预配置好了。

### 4. 测试集成
```bash
# 运行测试脚本
python test_tinyshare.py

# 或者启动应用测试
streamlit run SRV4_optimized.py
```

## 🔧 功能特性

### 新闻获取
- **实时新闻**: 获取最新的中文股市新闻
- **个股新闻**: 针对特定股票的相关新闻
- **市场新闻**: 整体市场动态和宏观新闻

### 情感分析
- **智能分词**: 使用 jieba 进行中文文本分词
- **关键词匹配**: 基于金融领域关键词的情感评分
- **多维指标**: 整体情绪、近期情绪、积极比例等

### 数据处理
- **自动缓存**: 30分钟缓存避免重复请求
- **批量处理**: 支持多股票并行新闻获取
- **内存优化**: 智能清理和垃圾回收

## 📊 使用方法

### 在应用中使用

1. **启动应用**:
   ```bash
   streamlit run SRV4_optimized.py
   ```

2. **查看状态**: 应用会显示 "✅ TinyShare 新闻数据源已就绪"

3. **测试新闻**: 在侧边栏的"新闻测试"区域输入股票代码进行测试

4. **生成推荐**: 推荐结果会包含新闻情绪得分

### 编程接口

```python
from tinyshare_integration import news_processor, sentiment_analyzer

# 获取个股新闻
news_items = news_processor.get_cached_news("000001", days_back=7)

# 计算情感指标
sentiment_metrics = news_processor.calculate_stock_sentiment(news_items)

# 高级情感分析
advanced_sentiment = sentiment_analyzer.analyze_with_context(
    text="公司业绩大幅增长，利润创历史新高",
    stock_info={"code": "000001"}
)
```

## 🎯 集成效果

### 推荐系统增强
- **新闻情绪因子**: 占最终得分的 15% 权重
- **实时情绪更新**: 7天滚动窗口的新闻情绪分析
- **可视化展示**: 在推荐结果中显示情绪得分和emoji

### 性能优化
- **智能缓存**: 避免频繁API调用
- **批量处理**: 提高多股票分析效率
- **内存管理**: 自动清理和优化

## 🔍 故障排除

### 常见问题

#### 1. 导入错误
```
ImportError: No module named 'tinyshare'
```
**解决方案**: 确保已安装 tinyshare 库
```bash
pip install tinyshare
```

#### 2. API 错误
```
TinyShare API error: Invalid token
```
**解决方案**: 检查令牌配置是否正确

#### 3. 无新闻数据
```
未找到相关新闻
```
**可能原因**:
- 时间范围内确实没有相关新闻
- 股票代码格式不正确
- API 暂时不可用

### 调试模式
启用详细日志：
```bash
export LOG_LEVEL=DEBUG
streamlit run SRV4_optimized.py
```

## 📈 性能指标

### 新闻获取性能
- **平均响应时间**: 1-3 秒
- **批量处理**: 20个股票并行
- **缓存命中率**: >80%

### 情感分析准确性
- **关键词覆盖**: 48个正面词汇 + 24个负面词汇
- **金融语境**: 特殊金融术语权重调整
- **情绪范围**: -1.0 (极负面) 到 +1.0 (极正面)

## 🔒 安全注意事项

1. **令牌保护**: 不要在代码中硬编码令牌
2. **速率限制**: 自动控制API调用频率
3. **错误处理**: 优雅的降级和错误恢复

## 📝 示例代码

### 基础用法
```python
import tinyshare as tns
from datetime import datetime, timedelta

# 初始化
token = "你的令牌"
pro_api = tns.pro_api(token)

# 获取新闻
end_date = datetime.now()
start_date = end_date - timedelta(days=1)

df = pro_api.news_ts(
    src='',
    start_date=start_date.strftime('%Y-%m-%d 00:00:00'),
    end_date=end_date.strftime('%Y-%m-%d 23:59:59')
)

print(f"获取到 {len(df)} 条新闻")
```

### 与推荐系统集成
```python
# 在推荐流程中
news_sentiment = score_calculator._get_news_sentiment("000001")
final_score = base_score * 0.85 + (news_sentiment + 1) / 2 * 0.15
```

## 📞 支持

如果遇到问题，可以：
1. 查看应用日志和错误信息
2. 运行 `python test_tinyshare.py` 进行诊断
3. 检查网络连接和API状态
4. 确认令牌有效性

---

**注意**: TinyShare 是第三方服务，请确保遵守其使用条款和限制。