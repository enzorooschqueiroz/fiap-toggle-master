package main

import (
	"encoding/json"
	"log"
	"math/rand"
	"net/http"
	"strings"
	"sync/atomic"
)

// Chaos injeta erros 500 propositalmente (demo de alerta + self-healing).
// O estado vive só em memória: um rollout restart volta a taxa para 0.
type Chaos struct {
	rate atomic.Int32
}

func (c *Chaos) SetRate(p int) { c.rate.Store(int32(p)) }

func (c *Chaos) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" || strings.HasPrefix(r.URL.Path, "/admin/") {
			next.ServeHTTP(w, r)
			return
		}
		if rate := int(c.rate.Load()); rate > 0 && rand.Intn(100) < rate {
			log.Printf("[CHAOS] erro injetado em %s %s (error_rate=%d%%)", r.Method, r.URL.Path, rate)
			http.Error(w, `{"error": "chaos: falha injetada"}`, http.StatusInternalServerError)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (c *Chaos) AdminHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "método não permitido", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		ErrorRate *int `json:"error_rate"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.ErrorRate == nil ||
		*body.ErrorRate < 0 || *body.ErrorRate > 100 {
		http.Error(w, `{"error": "error_rate deve ser um inteiro entre 0 e 100"}`, http.StatusBadRequest)
		return
	}
	c.SetRate(*body.ErrorRate)
	log.Printf("[CHAOS] error_rate ajustado para %d%%", *body.ErrorRate)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]int{"error_rate": *body.ErrorRate})
}
