#  TP1 Docker – Exercise 4: FullStack Flask Application with PostgreSQL and Redis

##  Objective
This project is a complete fullstack environment that demonstrates how to build a RESTful Flask API connected to PostgreSQL for persistent data storage and Redis for caching.
It is fully containerized using Docker Compose, with health checks, persistent volumes, and an Adminer UI for database management.
##  Project Structure
<img width="482" height="397" alt="image" src="https://github.com/user-attachments/assets/89b71b20-0bec-48fe-856a-e8ab0962ed66" />
## File Contents
###  app.py
The main backend logic is written in Flask. It connects to PostgreSQL and Redis, provides CRUD endpoints for users, and includes caching and health checks.
py
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import json
import os
from datetime import datetime

app = Flask(__name__)

# Configuration depuis les variables d'environnement
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'db'),
    'database': os.getenv('DB_NAME', 'fullstack_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'cache'),
    'port': os.getenv('REDIS_PORT', 6379),
    'db': 0
}

def get_db_connection():
    """Établit une connexion à PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Erreur de connexion à la base: {e}")
        return None

def get_redis_connection():
    """Établit une connexion à Redis"""
    try:
        r = redis.Redis(**REDIS_CONFIG)
        r.ping()  # Test de connexion
        return r
    except Exception as e:
        print(f"Erreur de connexion à Redis: {e}")
        return None

def init_db():
    """Initialise la base de données avec la table users"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            cur.close()
            conn.close()
            print("Base de données initialisée avec succès")
        except Exception as e:
            print(f"Erreur lors de l'initialisation: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check pour vérifier la connectivité de tous les services"""
    db_status = "healthy" if get_db_connection() else "unhealthy"
    redis_status = "healthy" if get_redis_connection() else "unhealthy"
    
    return jsonify({
        'status': 'success',
        'services': {
            'database': db_status,
            'redis': redis_status
        },
        'timestamp': datetime.now().isoformat()
    }), 200 if all([db_status == "healthy", redis_status == "healthy"]) else 503

@app.route('/users', methods=['POST'])
def create_user():
    """Crée un nouvel utilisateur"""
    data = request.get_json()
    
    if not data or not data.get('name') or not data.get('email'):
        return jsonify({'error': 'Name and email are required'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id, name, email, created_at',
            (data['name'], data['email'])
        )
        user = cur.fetchone()
        conn.commit()
        
        # Invalider le cache Redis pour la liste des utilisateurs
        redis_conn = get_redis_connection()
        if redis_conn:
            redis_conn.delete('users:all')
        
        return jsonify({
            'id': user[0],
            'name': user[1],
            'email': user[2],
            'created_at': user[3].isoformat()
        }), 201
        
    except psycopg2.IntegrityError:
        return jsonify({'error': 'Email already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/users', methods=['GET'])
def get_users():
    """Récupère tous les utilisateurs avec cache Redis"""
    # Vérifier d'abord le cache Redis
    redis_conn = get_redis_connection()
    if redis_conn:
        cached_users = redis_conn.get('users:all')
        if cached_users:
            return jsonify(json.loads(cached_users)), 200
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT id, name, email, created_at FROM users ORDER BY id')
        users = cur.fetchall()
        
        # Convertir les résultats en format sérialisable
        users_list = []
        for user in users:
            user_dict = dict(user)
            user_dict['created_at'] = user_dict['created_at'].isoformat()
            users_list.append(user_dict)
        
        # Mettre en cache dans Redis (expire après 30 secondes)
        if redis_conn:
            redis_conn.setex('users:all', 30, json.dumps(users_list))
        
        return jsonify(users_list), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Récupère un utilisateur spécifique"""
    # Vérifier le cache Redis
    redis_conn = get_redis_connection()
    cache_key = f'user:{user_id}'
    if redis_conn:
        cached_user = redis_conn.get(cache_key)
        if cached_user:
            return jsonify(json.loads(cached_user)), 200
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT id, name, email, created_at FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_dict = dict(user)
        user_dict['created_at'] = user_dict['created_at'].isoformat()
        
        # Mettre en cache dans Redis (expire après 60 secondes)
        if redis_conn:
            redis_conn.setex(cache_key, 60, json.dumps(user_dict))
        
        return jsonify(user_dict), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Met à jour un utilisateur"""
    data = request.get_json()
    
    if not data or (not data.get('name') and not data.get('email')):
        return jsonify({'error': 'Name or email is required'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Construire la requête dynamiquement
        update_fields = []
        values = []
        
        if 'name' in data:
            update_fields.append("name = %s")
            values.append(data['name'])
        if 'email' in data:
            update_fields.append("email = %s")
            values.append(data['email'])
        
        values.append(user_id)
        query = f'UPDATE users SET {", ".join(update_fields)} WHERE id = %s RETURNING id, name, email, created_at'
        
        cur.execute(query, values)
        user = cur.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        conn.commit()
        
        # Invalider les caches Redis
        redis_conn = get_redis_connection()
        if redis_conn:
            redis_conn.delete('users:all')
            redis_conn.delete(f'user:{user_id}')
        
        user_dict = dict(user)
        user_dict['created_at'] = user_dict['created_at'].isoformat()
        
        return jsonify(user_dict), 200
        
    except psycopg2.IntegrityError:
        return jsonify({'error': 'Email already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Supprime un utilisateur"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM users WHERE id = %s RETURNING id', (user_id,))
        deleted_user = cur.fetchone()
        
        if not deleted_user:
            return jsonify({'error': 'User not found'}), 404
        
        conn.commit()
        
        # Invalider les caches Redis
        redis_conn = get_redis_connection()
        if redis_conn:
            redis_conn.delete('users:all')
            redis_conn.delete(f'user:{user_id}')
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    # Initialiser la base au démarrage
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)



## Dependencies (requirements.txt)
txt
Flask==2.3.3
psycopg2-binary==2.9.7
redis==4.6.0

### Dockerfile 
dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1
CMD ["python", "app.py"]

### SQL Initialization (init.sql)
sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (name, email) VALUES 
    ('John Doe', 'john.doe@example.com'),
    ('Jane Smith', 'jane.smith@example.com')
ON CONFLICT (email) DO NOTHING;

### DockerCompose
yml
version: '3.8'

services:
  web:
    build: ./app
    ports:
      - "5000:5000"
    environment:
      - DB_HOST=db
      - DB_NAME=fullstack_db
      - DB_USER=postgres
      - DB_PASSWORD=password
      - DB_PORT=5432
      - REDIS_HOST=cache
      - REDIS_PORT=6379
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=fullstack_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  adminer:
    image: adminer
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy
    environment:
      - ADMINER_DEFAULT_SERVER=db

volumes:
  postgres_data:
  redis_data:

*Explanation:*
- web : Flask API container
- db :PostgreSQL database
- cache: Redis for caching user queries
- adminer : UI for managing the PostgreSQL database
- Volumes : Persist database and cache data
- Health checks : Automatically verify container health
### Run the Stack
<img width="1062" height="461" alt="image" src="https://github.com/user-attachments/assets/6e19e228-bcea-49d4-b192-25018ccd7639" />
### Tests
*Commandes*
bash
docker compose ps
docker inspect --format="{{json .State.Health}}" fullstack-app-db-1
docker inspect --format="{{json .State.Health}}" fullstack-app-cache-1

<img width="1042" height="371" alt="image" src="https://github.com/user-attachments/assets/664d35e4-ab93-42aa-8b56-e72a95624ba7" />

*test with   Postman:*
- Create a New User
<img width="1017" height="507" alt="image" src="https://github.com/user-attachments/assets/a7eb63a6-669e-4c51-801f-cf09c725f841" />
- List All Users
![Uploading image.png…]()
