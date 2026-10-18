FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALPHATRACE_HOST=0.0.0.0 \
    ALPHATRACE_PORT=8000

WORKDIR /app

COPY . .

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN python -m compileall -q app.py alpha_trace tests
RUN python -m unittest discover -s tests -v

EXPOSE 8000

CMD ["python", "app.py"]
