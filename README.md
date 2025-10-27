# TP1---Docker-Docker-Compose-Exercice-4---Stack-compl-te-avec-Docker-Compose


## 1️⃣ Créer le dossier du projet

```cmd
cd C:\Users\PC\Documents
mkdir fullstack-app
cd fullstack-app
```

---
<img width="717" height="202" alt="image" src="https://github.com/user-attachments/assets/96f9115f-a02d-44ce-b0f8-d167fc1ed8c1" />

## 2️⃣ Structure du projet

```
fullstack-app/
├── app/
│   ├── app.py
│   ├── requirements.txt
├── docker-compose.yml
├── .env
```

* `app/` → contient ton API Flask et le fichier des dépendances.
* `.env` → pour les variables d’environnement.
* `docker-compose.yml` → orchestration des services.

---

## 3️⃣ Exemple minimal de `app.py` (Flask API)

```python
from flask import Flask, jsonify, request
import os
import psycopg2

app = Flask(__name__)

# Connexion à PostgreSQL
conn = psycopg2.connect(
    host=os.environ.get('POSTGRES_HOST'),
    database=os.environ.get('POSTGRES_DB'),
    user=os.environ.get('POSTGRES_USER'),
    password=os.environ.get('POSTGRES_PASSWORD')
)
cursor = conn.cursor()

@app.route('/users', methods=['POST'])
def create_user():
    data = request.json
    cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (data['name'], data['email']))
    conn.commit()
    return jsonify({'status': 'user created'}), 201

@app.route('/users', methods=['GET'])
def list_users():
    cursor.execute("SELECT id, name, email FROM users")
    users = cursor.fetchall()
    return jsonify(users)

# Ajouter GET /users/<id>, PUT /users/<id>, DELETE /users/<id> de la même façon

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## 4️⃣ `requirements.txt` (dépendances Flask et PostgreSQL)

```
Flask==2.3.5
psycopg2-binary==2.9.9
redis==5.3.4
```

---

## 5️⃣ Exemple minimal `docker-compose.yml`

```yaml
version: '3.8'

services:
  web:
    build: ./app
    container_name: flask-app
    env_file: .env
    ports:
      - "5000:5000"
    depends_on:
      - db
      - cache
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/users"]
      interval: 30s
      timeout: 5s
      retries: 3

  db:
    image: postgres:15-alpine
    container_name: postgres-db
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - db_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 30s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    container_name: redis-cache
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  adminer:
    image: adminer
    container_name: adminer
    ports:
      - "8080:8080"

volumes:
  db_data:
```

---

## 6️⃣ `.env` (variables d’environnement)

```
POSTGRES_USER=admin
POSTGRES_PASSWORD=secret
POSTGRES_DB=usersdb
POSTGRES_HOST=db
```

---

## 7️⃣ Construire et lancer la stack

```cmd
docker-compose up --build
```

* L’option `--build` reconstruit l’image `web` à partir de ton Dockerfile si nécessaire.
* La stack inclut Flask, PostgreSQL, Redis et Adminer.

---
<img width="1446" height="127" alt="image" src="https://github.com/user-attachments/assets/bb9a0333-8f33-4068-9f69-6083008aad41" />


## 8️⃣ Vérifier la santé des services

```cmd
docker ps
docker inspect --format="{{json .State.Health}}" flask-app
docker inspect --format="{{json .State.Health}}" postgres-db
docker inspect --format="{{json .State.Health}}" redis-cache
```

---

## 9️⃣ Tester les endpoints (avec Postman ou curl)

```cmd
# Créer un utilisateur
curl -X POST -H "Content-Type: application/json" -d "{\"name\":\"Noura\",\"email\":\"noura@example.com\"}" http://localhost:5000/users

# Lister les utilisateurs
curl http://localhost:5000/users
```

* Ajouter les endpoints `GET /users/<id>`, `PUT /users/<id>`, `DELETE /users/<id>` de la même façon dans `app.py`.

---

Si tu veux, Noura, je peux te préparer **un guide CMD complet pour l’Exercice 4**, avec toutes les commandes Windows pour créer les dossiers, fichiers, construire la stack et tester l’API rapidement.

Veux‑tu que je fasse ça ?
