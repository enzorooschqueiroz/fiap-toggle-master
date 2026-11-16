package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func okHandler(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) }

func newChaosServer(c *Chaos) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", okHandler)
	mux.HandleFunc("/validate", okHandler)
	mux.HandleFunc("/admin/chaos", c.AdminHandler)
	return c.Middleware(mux)
}

func do(h http.Handler, method, path, body string) int {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
	return rec.Code
}

func TestChaosOffPassesThrough(t *testing.T) {
	h := newChaosServer(&Chaos{})
	if got := do(h, "GET", "/validate", ""); got != http.StatusOK {
		t.Fatalf("rate 0: esperado 200, veio %d", got)
	}
}

func TestChaosFullFails(t *testing.T) {
	c := &Chaos{}
	c.SetRate(100)
	if got := do(newChaosServer(c), "GET", "/validate", ""); got != http.StatusInternalServerError {
		t.Fatalf("rate 100: esperado 500, veio %d", got)
	}
}

func TestChaosHealthExempt(t *testing.T) {
	c := &Chaos{}
	c.SetRate(100)
	if got := do(newChaosServer(c), "GET", "/health", ""); got != http.StatusOK {
		t.Fatalf("/health sob chaos: esperado 200, veio %d", got)
	}
}

func TestChaosAdminSetsRate(t *testing.T) {
	h := newChaosServer(&Chaos{})
	if got := do(h, "POST", "/admin/chaos", `{"error_rate":100}`); got != http.StatusOK {
		t.Fatalf("POST chaos: esperado 200, veio %d", got)
	}
	if got := do(h, "GET", "/validate", ""); got != http.StatusInternalServerError {
		t.Fatalf("após chaos 100: esperado 500, veio %d", got)
	}
	if got := do(h, "POST", "/admin/chaos", `{"error_rate":150}`); got != http.StatusBadRequest {
		t.Fatalf("rate 150: esperado 400, veio %d", got)
	}
}
