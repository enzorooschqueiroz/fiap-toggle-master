FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
ENV PATH=/root/.local/bin:$PATH
RUN pip install --no-cache-dir --user -r requirements.txt \
    && opentelemetry-bootstrap -a requirements > /tmp/otel-reqs.txt \
    && pip install --no-cache-dir --user -r /tmp/otel-reqs.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8002
CMD ["opentelemetry-instrument", "gunicorn", "app:app", "--bind", "0.0.0.0:8002"]
