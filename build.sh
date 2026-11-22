#!/usr/bin/env bash
# Exit on error
set -o errexit

# Installation des dépendances
pip install --upgrade pip
pip install -r requirements.txt

# Collecte des fichiers statiques
python manage.py collectstatic --no-input

# Application des migrations de base de données
python manage.py migrate
