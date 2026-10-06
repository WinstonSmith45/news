FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY news_parser ./news_parser
COPY sources.yaml alembic.ini ./

RUN useradd --system --no-create-home app
USER app

CMD ["python", "-m", "news_parser"]
