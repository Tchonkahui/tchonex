# TCHONEX - ERP Modulaire Simplifié

TCHONEX est une plateforme ERP modulaire simplifiée conçue pour permettre à chaque entreprise de gérer ses activités en activant uniquement les modules nécessaires.

---

## 🛠️ Prérequis

- Python 3.10+ (recommandé 3.11, 3.12 ou 3.13)
- Git

---

## 💻 Lancement en Local

### 1. Cloner le projet ou se placer dans le dossier
```bash
cd projet_Tchonex
```

### 2. Créer et activer l'environnement virtuel
- **Sur Windows (PowerShell) :**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```
- **Sur macOS / Linux :**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement (optionnel en local)
Copiez le fichier `.env.example` en `.env` :
- Par défaut sans configuration, le projet fonctionne en local avec **SQLite** et `DEBUG=True`.

### 5. Appliquer les migrations de base de données
```bash
python manage.py migrate
```

### 6. Lancer le serveur de développement
```bash
python manage.py runserver
```
Rendez-vous sur [http://127.0.0.1:8000/](http://127.0.0.1:8000/) pour voir la page d'accueil de TCHONEX.

---

## 🚀 Déploiement sur Render

1. Poussez votre code sur un dépôt GitHub (voir commandes ci-dessous).
2. Connectez-vous sur [Render.com](https://render.com/) et créez un **Web Service**.
3. Liez votre dépôt GitHub **TCHONEX**.
4. Remplissez les champs de configuration :
   - **Environment** : `Python 3`
   - **Build Command** : `./build.sh`
   - **Start Command** : `gunicorn config.wsgi:application`
5. Ajoutez les **Variables d'environnement** (Environment Variables) dans Render :
   - `PYTHON_VERSION` : `3.13.0` (ou votre version de Python)
   - `DEBUG` : `False`
   - `SECRET_KEY` : *(générez une chaîne aléatoire sécurisée)*
   - `DATABASE_URL` : *(ajoutez l'URL de connexion PostgreSQL fournie par Render Postgres)*
6. Cliquez sur **Deploy Web Service**.
