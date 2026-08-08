# Turtle Execution Engine -- single image, runs identically locally and on
# Railway.
#
# THE DEFAULT CONTAINER IS PAPER AND CANNOT REACH THE VENUE.
# ENGINE_CONFIG_PATH below points at a paper configuration, so the engine
# wires a MockExchangeAdapter: no network, no venue writes. Going live is
# a DELIBERATE act -- mount a live configuration file and point
# ENGINE_CONFIG_PATH at it. Setting TURTLE_EXEC_MODE=live alone will NOT
# do it: config/loader.py fails closed when the variable contradicts the
# file, so `docker run -e TURTLE_EXEC_MODE=live` refuses to boot rather
# than silently trading.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ENGINE_CONFIG_PATH=deploy/engine.paper.toml \
    ENGINE_STORE_PATH=data/events.log \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt requirements-app.txt ./
RUN pip install -r requirements-app.txt

# Copy the whole project (engine + trading_system + app + deploy + dashboard).
COPY . .

# Durable state (event store + logs) lives here; mount a volume in prod.
RUN mkdir -p data/logs && \
    useradd --create-home --uid 10001 turtle && \
    chown -R turtle:turtle /app
USER turtle

EXPOSE 8000

# Container-level liveness (Railway also uses /health via railway.json).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; \
port=os.environ.get('PORT') or os.environ.get('APP_PORT','8000'); \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health'%port,timeout=4).status==200 else 1)"

# The canonical launcher -- the same one run_local.* and operators use, so
# the container runs the same product rather than a strategy-less variant
# of it. Reads PORT (Railway) or APP_PORT (local); same command everywhere.
CMD ["python", "-m", "scripts.run_platform"]
