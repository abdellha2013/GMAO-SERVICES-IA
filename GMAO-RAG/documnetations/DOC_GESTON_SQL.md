# MySQL - Commandes utiles pour le projet GMAO AI Service

## 📦 1. Gestion du Service (Terminal Bash)

### Démarrer le serveur MySQL
```bash
sudo systemctl start mysql
```

### Arrêter le serveur
```bash
sudo systemctl stop mysql
```

### Redémarrer le serveur
```bash
sudo systemctl restart mysql
```

### Vérifier l'état du serveur
```bash
sudo systemctl status mysql
```

---

## 🔑 2. Connexion et Utilisateurs

### Se connecter en ligne de commande (Terminal Bash)
```bash
mysql -u root -p
```
*Note : Le système vous demandera ensuite de saisir le mot de passe.*

### Quitter la console MySQL (Console MySQL)
```sql
EXIT;
```
*Alternative : `QUIT;`*

### Afficher les utilisateurs existants (Console MySQL)
```sql
SELECT user, host FROM mysql.user;
```

### Modifier le mot de passe de root (Console MySQL)
```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY 'nouveau_mot_de_passe';
```

### Recharger les privilèges (Console MySQL)
```sql
FLUSH PRIVILEGES;
```

---

## 🗄️ 3. Gestion des Bases de Données (Console MySQL)

### Afficher les bases de données
```sql
SHOW DATABASES;
```

### Créer la base de données du projet
```sql
CREATE DATABASE IF NOT EXISTS gmao_rag;
```
*Alternative : `CREATE DATABASE gmao_rag;`*

### Utiliser/Sélectionner la base de données
```sql
USE gmao_rag;
```

### Supprimer la base de données
```sql
DROP DATABASE gmao_rag;
```

---

## 📋 4. Gestion des Tables (Console MySQL)

### Afficher les tables de la base sélectionnée
```sql
SHOW TABLES;
```

### Décrire la structure d'une table
```sql
DESCRIBE nom_table;
```
*Alternative : `DESC nom_table;`*

### Supprimer une table
```sql
DROP TABLE nom_table;
```

---

## 💾 5. Manipulation des Données (Console MySQL)

### Sélectionner toutes les lignes
```sql
SELECT * FROM nom_table;
```

### Insérer une nouvelle ligne
```sql
INSERT INTO nom_table (colonne1, colonne2) VALUES ('valeur1', 'valeur2');
```

### Modifier des données existantes
```sql
UPDATE nom_table SET colonne='nouvelle valeur' WHERE id=1;
```

### Supprimer une ligne
```sql
DELETE FROM nom_table WHERE id=1;
```

---

## 📥 6. Sauvegarde et Restauration (Terminal Bash)

### Exporter la base de données (Backup)
```bash
mysqldump -u root -p gmao_rag > gmao_rag.sql
```

### Restaurer la base de données
```bash
mysql -u root -p gmao_rag < gmao_rag.sql
```

---

## 🚀 7. Raccourcis Rapides (Terminal Bash)
*Ces commandes s'exécutent directement depuis le terminal sans entrer dans la console MySQL.*

### Créer la base en une seule ligne
```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS gmao_rag;"
```

### Vérifier les bases existantes en une seule ligne
```bash
mysql -u root -p -e "SHOW DATABASES;"
```

---

## 🛠️ 8. Dépannage et Logs (Terminal Bash)

### Vérifier les processus MySQL actifs
```bash
ps -ef | grep mysqld
```

### Consulter les 100 derniers messages d'erreur
```bash
sudo tail -n 100 /var/log/mysql/error.log
```

### Vérifier les journaux système (systemd)
```bash
sudo journalctl -xeu mysql.service
```
