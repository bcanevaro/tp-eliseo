# Imagen única de Eliseo: el panel y el bot usan el mismo código y comparten la base en ./data.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY eliseo ./eliseo
COPY scripts ./scripts
COPY prompts ./prompts
COPY evaluation ./evaluation
COPY data/consorcios ./data/consorcios

# Sin usuario root: la base vive en el volumen /app/data.
RUN useradd --create-home eliseo && chown -R eliseo /app
USER eliseo

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "eliseo/panel/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
