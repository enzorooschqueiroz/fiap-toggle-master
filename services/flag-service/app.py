import os
import sys
import psycopg2
import requests
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from functools import wraps
import logging
import random
import threading

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

load_dotenv() 

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")
MASTER_KEY = os.getenv("MASTER_KEY")

if not DATABASE_URL or not AUTH_SERVICE_URL:
    log.critical("Erro: DATABASE_URL e AUTH_SERVICE_URL devem ser definidos.")
    sys.exit(1)

try:
    pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL)
    log.info("Pool de conexões com o PostgreSQL inicializado.")
except psycopg2.OperationalError as e:
    log.critical(f"Erro fatal ao conectar ao PostgreSQL: {e}")
    sys.exit(1)

def require_auth(f):
    """ Middleware para validar a chave de API contra o auth-service """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "Authorization header obrigatório"}), 401
        
        try:
            validate_url = f"{AUTH_SERVICE_URL}/validate"
            response = requests.get(validate_url, headers={"Authorization": auth_header}, timeout=3)
            
            if response.status_code != 200:
                log.warning(f"Falha na validação da chave (status: {response.status_code})")
                return jsonify({"error": "Chave de API inválida"}), 401
        
        except requests.exceptions.Timeout:
            log.error("Timeout ao conectar com o auth-service")
            return jsonify({"error": "Serviço de autenticação indisponível (timeout)"}), 504 # Gateway Timeout
        except requests.exceptions.RequestException as e:
            log.error(f"Erro ao conectar com o auth-service: {e}")
            return jsonify({"error": "Serviço de autenticação indisponível"}), 503 # Service Unavailable

        return f(*args, **kwargs)
    return decorated

class Chaos:
    """Injeção de falhas para a demo de alerta + self-healing.
    Estado apenas em memória: um rollout restart volta a taxa para 0."""

    def __init__(self):
        self._rate = 0
        self._lock = threading.Lock()

    def set_rate(self, rate):
        with self._lock:
            self._rate = rate

    @property
    def rate(self):
        with self._lock:
            return self._rate


chaos = Chaos()


@app.before_request
def inject_chaos():
    if request.path == "/health" or request.path.startswith("/admin/"):
        return None
    rate = chaos.rate
    if rate > 0 and random.randint(1, 100) <= rate:  # nosec B311 - não é uso criptográfico
        log.error(f"[CHAOS] erro injetado em {request.method} {request.path} (error_rate={rate}%)")
        return jsonify({"error": "chaos: falha injetada"}), 500
    return None


@app.route('/admin/chaos', methods=['POST'])
def set_chaos():
    if not MASTER_KEY or request.headers.get("Authorization") != f"Bearer {MASTER_KEY}":
        return jsonify({"error": "Acesso não autorizado"}), 401
    data = request.get_json(silent=True) or {}
    rate = data.get("error_rate")
    if not isinstance(rate, int) or isinstance(rate, bool) or not 0 <= rate <= 100:
        return jsonify({"error": "error_rate deve ser um inteiro entre 0 e 100"}), 400
    chaos.set_rate(rate)
    log.warning(f"[CHAOS] error_rate ajustado para {rate}%")
    return jsonify({"error_rate": rate}), 200


@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "flag-service"})

@app.route('/flags', methods=['POST'])
@require_auth
def create_flag():
    """ Cria uma nova definição de feature flag """
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "'name' é obrigatório"}), 400
    
    name = data['name']
    description = data.get('description', '')
    is_enabled = data.get('is_enabled', False)
    
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO flags (name, description, is_enabled, created_at, updated_at) "
            "VALUES (%s, %s, %s, NOW(), NOW()) RETURNING *",
            (name, description, is_enabled)
        )
        new_flag = cur.fetchone()
        conn.commit()
        log.info(f"Flag '{name}' criada com sucesso.")
        return jsonify(new_flag), 201
    except psycopg2.IntegrityError:
        if conn: conn.rollback()
        log.warning(f"Tentativa de criar flag duplicada: '{name}'")
        return jsonify({"error": f"Flag '{name}' já existe"}), 409
    except Exception as e:
        if conn: conn.rollback()
        log.error(f"Erro ao criar flag: {e}")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags', methods=['GET'])
@require_auth
def get_flags():
    """ Lista todas as feature flags """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM flags ORDER BY name")
        flags = cur.fetchall()
        return jsonify(flags)
    except Exception as e:
        log.error(f"Erro ao buscar flags: {e}")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags/<string:name>', methods=['GET'])
@require_auth
def get_flag(name):
    """ Busca uma feature flag específica pelo nome """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM flags WHERE name = %s", (name,))
        flag = cur.fetchone()
        if not flag:
            return jsonify({"error": "Flag não encontrada"}), 404
        return jsonify(flag)
    except Exception as e:
        log.error(f"Erro ao buscar flag '{name}': {e}")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags/<string:name>', methods=['PUT'])
@require_auth
def update_flag(name):
    """ Atualiza uma feature flag (descrição ou status 'is_enabled') """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição obrigatório"}), 400

    fields = []
    values = []
    
    if 'description' in data:
        fields.append("description = %s")
        values.append(data['description'])
    if 'is_enabled' in data:
        fields.append("is_enabled = %s")
        values.append(data['is_enabled'])
    
    if not fields:
        return jsonify({"error": "Pelo menos um campo ('description', 'is_enabled') é obrigatório"}), 400
    
    values.append(name)
    
    query = f"UPDATE flags SET {', '.join(fields)} WHERE name = %s RETURNING *"
    
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, tuple(values))
        
        if cur.rowcount == 0:
            return jsonify({"error": "Flag não encontrada"}), 404
            
        updated_flag = cur.fetchone()
        conn.commit()
        log.info(f"Flag '{name}' atualizada com sucesso.")
        return jsonify(updated_flag), 200
    except Exception as e:
        if conn: conn.rollback()
        log.error(f"Erro ao atualizar flag '{name}': {e}")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags/<string:name>', methods=['DELETE'])
@require_auth
def delete_flag(name):
    """ Deleta uma feature flag """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute("DELETE FROM flags WHERE name = %s", (name,))
        
        if cur.rowcount == 0:
            return jsonify({"error": "Flag não encontrada"}), 404
            
        conn.commit()
        log.info(f"Flag '{name}' deletada com sucesso.")
        return "", 204 # 204 No Content
    except Exception as e:
        if conn: conn.rollback()
        log.error(f"Erro ao deletar flag '{name}': {e}")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8002))
    app.logger.info(f"Servidor de Flags iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)