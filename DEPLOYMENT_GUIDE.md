# Deployment Guide - Optimized Stock Recommendation System

## Quick Start

### 1. Install Dependencies
```bash
# Install core dependencies only
pip install streamlit pandas numpy

# Install optional dependencies as needed
pip install -r requirements_optimized.txt
```

### 2. Run the Optimized Application
```bash
# Run the optimized version
streamlit run SRV4_optimized.py

# Or with environment variables
MAX_STOCKS=200 BATCH_SIZE=10 streamlit run SRV4_optimized.py
```

## Production Deployment

### Environment Setup

#### Environment Variables
```bash
# Core configuration
export TUSHARE_TOKEN="your_token_here"
export ENVIRONMENT="production"
export LOG_LEVEL="INFO"

# Performance tuning
export MAX_STOCKS=500
export BATCH_SIZE=20
export MAX_WORKERS=3
export CACHE_TTL_LONG=3600

# Feature toggles
export ENABLE_ADVANCED_ML=false
export ENABLE_HYPERPARAMETER_TUNING=false
```

#### Docker Deployment
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements_optimized.txt .
RUN pip install --no-cache-dir -r requirements_optimized.txt

# Copy application files
COPY SRV4_optimized.py .
COPY config.py .
COPY performance_monitor.py .

# Set environment variables
ENV PYTHONPATH=/app
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run application
CMD ["streamlit", "run", "SRV4_optimized.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### Docker Compose
```yaml
version: '3.8'
services:
  stock-app:
    build: .
    ports:
      - "8501:8501"
    environment:
      - TUSHARE_TOKEN=${TUSHARE_TOKEN}
      - MAX_STOCKS=500
      - BATCH_SIZE=20
      - ENVIRONMENT=production
    volumes:
      - ./data:/app/data  # For persistent cache
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Cloud Deployment Options

#### 1. Streamlit Cloud
```bash
# 1. Push to GitHub
git add .
git commit -m "Optimized version"
git push origin main

# 2. Deploy to Streamlit Cloud
# - Go to share.streamlit.io
# - Connect your repository
# - Set environment variables in the UI
```

#### 2. Heroku
```bash
# Procfile
web: streamlit run SRV4_optimized.py --server.port=$PORT --server.address=0.0.0.0

# runtime.txt
python-3.11.0
```

#### 3. AWS ECS/Fargate
```json
{
  "family": "stock-recommendation",
  "containerDefinitions": [
    {
      "name": "stock-app",
      "image": "your-ecr-repo/stock-app:latest",
      "portMappings": [
        {
          "containerPort": 8501,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "MAX_STOCKS",
          "value": "500"
        },
        {
          "name": "ENVIRONMENT",
          "value": "production"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/stock-recommendation",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "512",
  "memory": "1024"
}
```

## Performance Optimization Settings

### Production Configuration
```python
# config.py - Production overrides
class ProductionConfig(AppConfig):
    def __init__(self):
        super().__init__()
        
        # Aggressive performance settings
        self.performance.MAX_STOCKS = 300  # Reduced for stability
        self.performance.BATCH_SIZE = 15
        self.performance.MAX_WORKERS = 2   # Conservative for stability
        
        # Longer cache times
        self.performance.CACHE_TTL_LONG = 7200   # 2 hours
        self.performance.CACHE_TTL_MEDIUM = 3600 # 1 hour
        
        # Disable expensive features
        self.algorithms.ENABLE_ADVANCED_ML = False
        self.algorithms.ENABLE_HYPERPARAMETER_TUNING = False
```

### Memory Management
```bash
# Set memory limits
export STREAMLIT_SERVER_MAX_UPLOAD_SIZE=50
export STREAMLIT_SERVER_MAX_MESSAGE_SIZE=50

# Python memory optimization
export PYTHONOPTIMIZE=1
export PYTHONDONTWRITEBYTECODE=1
```

## Monitoring and Alerting

### Application Monitoring
```python
# Built-in performance dashboard
# Access at: your-app-url/?page=performance

# Custom metrics endpoint
@st.cache_data(ttl=60)
def get_health_metrics():
    return {
        "status": "healthy",
        "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
        "uptime_seconds": time.time() - start_time,
        "cache_hit_rate": get_cache_hit_rate()
    }
```

### External Monitoring
```bash
# Health check endpoint
curl -f http://your-app-url/_stcore/health

# Custom metrics endpoint (if implemented)
curl http://your-app-url/metrics
```

### Logging Configuration
```python
import logging

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
```

## Security Considerations

### API Key Management
```bash
# Never commit API keys
echo "TUSHARE_TOKEN=your_token" > .env
echo ".env" >> .gitignore

# Use environment variables or secrets management
export TUSHARE_TOKEN=$(aws ssm get-parameter --name "/app/tushare-token" --with-decryption --query 'Parameter.Value' --output text)
```

### Network Security
```yaml
# Docker compose with network isolation
networks:
  stock-network:
    driver: bridge

services:
  stock-app:
    networks:
      - stock-network
    ports:
      - "127.0.0.1:8501:8501"  # Bind to localhost only
```

## Scaling Strategies

### Horizontal Scaling
```yaml
# Docker Swarm
version: '3.8'
services:
  stock-app:
    image: stock-app:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
    ports:
      - "8501:8501"
```

### Load Balancing
```nginx
# nginx.conf
upstream stock_app {
    server app1:8501;
    server app2:8501;
    server app3:8501;
}

server {
    listen 80;
    location / {
        proxy_pass http://stock_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Common Issues

#### 1. High Memory Usage
```bash
# Check memory usage
docker stats

# Reduce batch size
export BATCH_SIZE=10
export MAX_STOCKS=200
```

#### 2. Slow API Responses
```bash
# Enable faster data source
export PREFER_AKSHARE=true

# Reduce data scope
export MAX_HISTORY_DAYS=30
```

#### 3. Cache Issues
```bash
# Clear Streamlit cache
rm -rf ~/.streamlit/cache

# Restart application
docker-compose restart stock-app
```

### Performance Debugging
```python
# Enable debug mode
export LOG_LEVEL=DEBUG
export STREAMLIT_LOGGER_LEVEL=debug

# Check performance metrics
# Access the performance dashboard in the app
```

## Backup and Recovery

### Data Backup
```bash
# Backup cache directory
tar -czf cache_backup_$(date +%Y%m%d).tar.gz ./data/cache

# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf "${BACKUP_DIR}/cache_${DATE}.tar.gz" ./data/cache
find "${BACKUP_DIR}" -name "cache_*.tar.gz" -mtime +7 -delete
```

### Recovery Procedures
```bash
# Restore from backup
tar -xzf cache_backup_20231201.tar.gz -C ./data/

# Restart services
docker-compose down
docker-compose up -d
```

## Performance Benchmarking

### Load Testing
```python
# locustfile.py
from locust import HttpUser, task, between

class StockAppUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def view_homepage(self):
        self.client.get("/")
    
    @task(2)
    def generate_recommendations(self):
        self.client.post("/", data={"action": "generate"})
```

```bash
# Run load test
locust -f locustfile.py --host=http://localhost:8501
```

### Performance Metrics
- Target response time: <3 seconds
- Memory usage: <400MB
- CPU usage: <70%
- Cache hit rate: >80%

## Maintenance

### Regular Tasks
```bash
# Weekly cleanup
docker system prune -f
docker volume prune -f

# Update dependencies
pip install --upgrade -r requirements_optimized.txt

# Restart application
docker-compose restart stock-app
```

### Health Checks
```bash
#!/bin/bash
# health_check.sh
HEALTH_URL="http://localhost:8501/_stcore/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -eq 200 ]; then
    echo "✅ Application is healthy"
    exit 0
else
    echo "❌ Application is unhealthy (HTTP $RESPONSE)"
    exit 1
fi
```

This deployment guide provides comprehensive instructions for running the optimized stock recommendation system in production environments with proper monitoring, scaling, and maintenance procedures.