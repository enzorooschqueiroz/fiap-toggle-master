package main

import (
	"context"
	"strings"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/go-redis/redis/extra/redisotel/v8"
	"github.com/go-redis/redis/v8"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

func TestInjectAddsTraceparent(t *testing.T) {
	otel.SetTextMapPropagator(propagation.TraceContext{})
	tp := sdktrace.NewTracerProvider()
	ctx, span := tp.Tracer("test").Start(context.Background(), "parent")
	defer span.End()

	attrs := injectTraceContext(ctx)

	tp_, ok := attrs["traceparent"]
	if !ok {
		t.Fatalf("esperado atributo traceparent, veio %v", attrs)
	}
	if tp_.DataType == nil || *tp_.DataType != "String" {
		t.Fatalf("DataType esperado String, veio %v", tp_.DataType)
	}
	traceID := span.SpanContext().TraceID().String()
	if !strings.Contains(*tp_.StringValue, traceID) {
		t.Fatalf("traceparent %q não contém trace id %s", *tp_.StringValue, traceID)
	}
}

func TestInjectWithoutSpanIsEmpty(t *testing.T) {
	otel.SetTextMapPropagator(propagation.TraceContext{})
	if attrs := injectTraceContext(context.Background()); len(attrs) != 0 {
		t.Fatalf("sem span ativo esperado mapa vazio, veio %v", attrs)
	}
}

func TestRedisHitCreatesSpan(t *testing.T) {
	mr := miniredis.RunT(t)
	mr.Set("flag_info:x", "{}")

	rec := tracetest.NewSpanRecorder()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(rec))
	otel.SetTracerProvider(tp)

	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	rdb.AddHook(redisotel.NewTracingHook())

	// Em produção o pai é o span HTTP do otelhttp; o hook só cria spans filhos.
	ctx, parent := tp.Tracer("test").Start(context.Background(), "GET /evaluate")
	if _, err := rdb.Get(ctx, "flag_info:x").Result(); err != nil {
		t.Fatalf("GET falhou: %v", err)
	}
	parent.End()
	if len(rec.Ended()) < 2 {
		t.Fatalf("esperado span do Redis além do pai no cache HIT, veio %d spans", len(rec.Ended()))
	}
}
