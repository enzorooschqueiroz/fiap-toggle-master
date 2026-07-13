FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY . .
RUN sed -i '/\t"context"/d' evaluator.go && \
    sed -i '/\t"crypto\/sha1"/i\\t"os"' evaluator.go && \
    go mod tidy && CGO_ENABLED=0 GOOS=linux go build -o /app/evaluation-service .

FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/evaluation-service .
EXPOSE 8004
CMD ["./evaluation-service"]
