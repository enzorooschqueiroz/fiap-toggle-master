package main

import (
	"context"
	"testing"
)

// Regressão: resource.Merge falhava com "conflicting Schema URL" quando o
// semconv importado divergia do usado por resource.Default() no SDK.
func TestSetupTelemetryInitializes(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
	shutdown, err := setupTelemetry(context.Background(), "test-service")
	if err != nil {
		t.Fatalf("setupTelemetry falhou: %v", err)
	}
	_ = shutdown(context.Background())
}
