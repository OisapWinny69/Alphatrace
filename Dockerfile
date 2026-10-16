FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALPHATRACE_HOST=0.0.0.0 \
    ALPHATRACE_PORT=8000

WORKDIR /app

COPY . .

RUN python -m compileall -q app.py signal_lens tests

EXPOSE 8000

CMD ["python", "app.py"]
