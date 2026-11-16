package main

import (
	"context"
	"database/sql"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/XSAM/otelsql"
	_ "github.com/jackc/pgx/v4/stdlib"
	"github.com/joho/godotenv"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// App struct (para injeção de dependência)
type App struct {
	DB         *sql.DB
	MasterKey  string
}

func main() {
	_ = godotenv.Load()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8001"
	}

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		log.Fatal("DATABASE_URL deve ser definida")
	}

	masterKey := os.Getenv("MASTER_KEY")
	if masterKey == "" {
		log.Fatal("MASTER_KEY deve ser definida")
	}

	shutdown, err := setupTelemetry(context.Background(), "auth-service")
	if err != nil {
		log.Fatalf("Falha ao iniciar OpenTelemetry: %v", err)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdown(ctx)
	}()

	db, err := connectDB(databaseURL)
	if err != nil {
		log.Fatalf("Não foi possível conectar ao banco de dados: %v", err)
	}
	defer db.Close()

	app := &App{
		DB:         db,
		MasterKey:  masterKey,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.healthHandler)

	mux.HandleFunc("/validate", app.validateKeyHandler)

	mux.Handle("/admin/keys", app.masterKeyAuthMiddleware(http.HandlerFunc(app.createKeyHandler)))

	chaos := &Chaos{}
	mux.Handle("/admin/chaos", app.masterKeyAuthMiddleware(http.HandlerFunc(chaos.AdminHandler)))

	handler := otelhttp.NewHandler(chaos.Middleware(mux), "auth-service",
		otelhttp.WithSpanNameFormatter(func(_ string, r *http.Request) string {
			return r.Method + " " + r.URL.Path
		}))

	log.Printf("Serviço de Autenticação (Go) rodando na porta %s", port)
	if err := http.ListenAndServe(":"+port, handler); err != nil {
		log.Fatal(err)
	}
}

func connectDB(databaseURL string) (*sql.DB, error) {
	db, err := otelsql.Open("pgx", databaseURL,
		otelsql.WithAttributes(semconv.DBSystemPostgreSQL))
	if err != nil {
		return nil, err
	}

	if err = db.Ping(); err != nil {
		return nil, err
	}

	log.Println("Conectado ao PostgreSQL com sucesso!")
	return db, nil
}