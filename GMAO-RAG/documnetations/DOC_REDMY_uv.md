# 🚀 Guide de survie : Commandes Essentielles avec `uv`

Ce guide regroupe les commandes les plus utiles pour gérer vos projets Python, vos environnements virtuels et vos dépendances avec `uv`.

---

## 📁 1. Gestion du Projet et de l'Environnement

### Créer un nouvel environnement virtuel local
Crée un dossier `.venv` vierge dans le projet actuel.
```bash
uv venv
```

### Créer un environnement avec une version Python spécifique
```bash
uv venv --python 3.12
```

### Initialiser un tout nouveau projet
Crée la structure de base d'un projet avec un fichier `pyproject.toml`.
```bash
uv init mon-nouveau-projet
```

### Réinitialiser / Annuler une variable d'environnement (Mémoire)
Si vous avez lié par erreur votre terminal à un autre environnement :
```bash
unset UV_PROJECT_ENVIRONMENT
```

---

## 📦 2. Gestion des Dépendances (Mode Projet)
*Ces commandes lisent et mettent à jour automatiquement votre fichier `pyproject.toml`.*

### Synchroniser l'environnement
Installe ou nettoie le dossier `.venv` pour qu'il corresponde exactement au projet.
```bash
uv sync
```

### Ajouter un paquet au projet
Installe un paquet et l'ajoute aux dépendances du projet.
```bash
uv add requests
```

### Ajouter un paquet pour le développement uniquement
(Par exemple pour les tests ou le formatage de code).
```bash
uv add --dev pytest ruff
```

### Retirer un paquet du projet
```bash
uv remove requests
```

---

## 🐍 3. Gestion des Dépendances (Mode Classique / Pip)
*Si vous préférez travailler à la manière traditionnelle de `pip` avec un fichier `requirements.txt`.*

### Installer un paquet manuellement dans le .venv actuel
```bash
uv pip install flask
```

### Installer des dépendances depuis un fichier
```bash
uv pip install -r requirements.txt
```

### Exporter les paquets installés
```bash
uv pip freeze > requirements.txt
```

---

## 🏃‍♂️ 4. Exécution de Scripts et d'Outils

### Exécuter un script Python dans le contexte du projet
Lance le script en utilisant automatiquement les paquets du `.venv` local.
```bash
uv run mon_script.py
```

### Lancer une commande avec l'environnement d'un AUTRE projet
Utile pour exécuter un script sans modifier vos variables d'environnement.
```bash
uv run --python /chemin/vers/autre/projet/.venv/bin/python mon_script.py
```

### Exécuter un outil temporaire sans l'installer
Télécharge et exécute un outil éphémère (ex: `ruff` pour formater du code).
```bash
uvx ruff check .
```

---

## 🛠️ 5. Gestion des Versions Python

### Installer une version spécifique de Python sur la machine
`uv` télécharge et gère les versions de Python de manière isolée sans casser votre système.
```bash
uv python install 3.13
```

### Lister les versions de Python disponibles ou installées
```bash
uv python list
```
