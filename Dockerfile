FROM python:3.11-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data && chown app:app /app/data
COPY --chown=app:app boot.py server.py collector.py analytics.py ./
COPY --chown=app:app web/ ./web/
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 DB_PATH=/app/data/trenchnet.sqlite
EXPOSE 8080
CMD ["python", "boot.py"]
