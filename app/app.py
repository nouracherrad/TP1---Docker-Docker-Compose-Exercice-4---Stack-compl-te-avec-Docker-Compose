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