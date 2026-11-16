FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
RUN useradd --uid 10001 --no-create-home healer
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app.py .
ENV HOME=/tmp
USER 10001
EXPOSE 8080
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4"]
