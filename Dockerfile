# PhotoBook — FastAPI + SQLite 单体
FROM python:3.12-slim

# 7z 用于采集流程解压 RAR/ZIP;curl 供健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
        p7zip-full curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖(利用层缓存)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY app ./app

# 非root运行;数据目录由卷挂载
RUN useradd -m -u 1000 photobook \
    && mkdir -p /data/db /data/media /data/library \
    && chown -R photobook:photobook /data /app
USER photobook

ENV DATA_DIR=/data/db \
    MEDIA_DIR=/data/media \
    LIBRARY_DIR=/data/library \
    PHOTOBOOK_HOST=0.0.0.0 \
    PHOTOBOOK_PORT=8777 \
    PYTHONUNBUFFERED=1

EXPOSE 8777

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8777/healthz || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8777"]
