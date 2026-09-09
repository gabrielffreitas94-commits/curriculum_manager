# ====== ESTÁGIO 1: Builder ======
FROM python:3.12-slim AS builder

WORKDIR /build

# Instala ferramentas essenciais de compilação e o gerenciador uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copia dependências e cria virtualenv isolado
COPY pyproject.toml uv.lock ./
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv sync --frozen --no-dev

# ====== ESTÁGIO 2: Imagem Final de Produção ======
FROM python:3.12-slim AS runner

WORKDIR /app

# Instala bibliotecas nativas essenciais para WeasyPrint e fontes legíveis para ATS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libffi-dev \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário não-privilegiado (Segurança Cloud Run)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash appuser

# Copia ambiente virtual pré-construído e o código-fonte da aplicação
COPY --from=builder /opt/venv /opt/venv
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8000

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
