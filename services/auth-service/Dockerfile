FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY . .
RUN sed -i '/\t"fmt"/d' main.go && \
    sed -i '/\t"crypto\/sha256"/d' handlers.go && \
    sed -i '/\t"encoding\/hex"/d' handlers.go && \
    sed -i '/\t"fmt"/d' key.go && \
    sed -i 's|\t"github.com/jackc/pgx/v4/stdlib"|\t_ "github.com/jackc/pgx/v4/stdlib"|' main.go && \
    go mod tidy && CGO_ENABLED=0 GOOS=linux go build -o /app/auth-service .

FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/auth-service .
EXPOSE 8001
CMD ["./auth-service"]
