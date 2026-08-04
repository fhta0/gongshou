#!/bin/bash
# 固定端口 8501 启动 Streamlit，有占用先杀

PORT=8501

# 检查端口是否被占用
PID=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$PID" ]; then
    echo "端口 $PORT 被占用 (PID: $PID)，正在终止..."
    kill -9 $PID 2>/dev/null
    sleep 2
    # 确认释放
    if lsof -ti :$PORT >/dev/null 2>&1; then
        echo "端口 $PORT 仍被占用，强制终止所有 streamlit 进程..."
        pkill -9 -f streamlit 2>/dev/null
        pkill -9 -f uvicorn 2>/dev/null
        sleep 2
    fi
fi

# 清除 Python 缓存
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

echo "启动 Streamlit (端口 $PORT)..."
exec streamlit run app.py --server.port $PORT --server.headless true
