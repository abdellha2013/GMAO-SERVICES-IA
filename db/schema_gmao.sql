-- ============================================================
-- GMAO — Schéma complet MySQL compatible Laravel
-- Source : migrations Laravel (jingerkarmaF12)
-- Base   : gmao
--
-- Usage :
--   mysql -u root -p gmao < db/schema_gmao.sql
--   ou via phpMyAdmin / MySQL Workbench
-- ============================================================

CREATE DATABASE IF NOT EXISTS gmao
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE gmao;

-- ============================================================
-- NETTOYAGE (ordre pour respecter les FK)
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS message_chats;
DROP TABLE IF EXISTS conversation_rags;
DROP TABLE IF EXISTS document_chunks;
DROP TABLE IF EXISTS messages_source;
DROP TABLE IF EXISTS panne_chunks;
DROP TABLE IF EXISTS affectations;
DROP TABLE IF EXISTS pannes;
DROP TABLE IF EXISTS ordre_travails;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS demande_interventions;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS utilisateurs;
DROP TABLE IF EXISTS equipements;
DROP TABLE IF EXISTS specialites;
DROP TABLE IF EXISTS roles;
DROP TABLE IF EXISTS cache_locks;
DROP TABLE IF EXISTS cache;
DROP TABLE IF EXISTS sessions;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- 1. ROLES
-- ============================================================

CREATE TABLE roles (
    id_role INT UNSIGNED AUTO_INCREMENT,
    nom_role VARCHAR(50) NOT NULL,
    description TEXT NULL,
    created_at TIMESTAMP NULL DEFAULT NULL,
    updated_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id_role),
    UNIQUE KEY uq_roles_nom_role (nom_role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 2. SPÉCIALITÉS
-- ============================================================

CREATE TABLE specialites (
    id_specialite INT UNSIGNED AUTO_INCREMENT,
    nom_specialite VARCHAR(100) NOT NULL,
    description TEXT NULL,
    created_at TIMESTAMP NULL DEFAULT NULL,
    updated_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id_specialite),
    UNIQUE KEY uq_specialites_nom (nom_specialite)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. UTILISATEURS
-- ============================================================

CREATE TABLE utilisateurs (
    id_utilisateur INT UNSIGNED AUTO_INCREMENT,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    mot_de_passe VARCHAR(255) NOT NULL,
    telephone VARCHAR(20) NULL,
    photo_profil VARCHAR(255) NULL,
    statut ENUM('actif','inactif','suspendu') NOT NULL DEFAULT 'actif',
    id_role INT UNSIGNED NOT NULL,
    id_specialite INT UNSIGNED NULL,
    created_at TIMESTAMP NULL DEFAULT NULL,
    updated_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id_utilisateur),
    UNIQUE KEY uq_utilisateurs_email (email),
    CONSTRAINT fk_utilisateurs_role
        FOREIGN KEY (id_role) REFERENCES roles(id_role)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_utilisateurs_specialite
        FOREIGN KEY (id_specialite) REFERENCES specialites(id_specialite)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 4. ÉQUIPEMENTS
-- ============================================================

CREATE TABLE equipements (
    id_equipement INT UNSIGNED AUTO_INCREMENT,
    nom_equipement VARCHAR(255) NOT NULL,
    marque VARCHAR(255) NULL,
    modele VARCHAR(255) NULL,
    numero_serie VARCHAR(255) NOT NULL,
    date_acquisition DATE NULL,
    date_mise_service DATE NULL,
    etat ENUM('fonctionnel','en_panne','maintenance','hors_service') NOT NULL DEFAULT 'fonctionnel',
    criticite ENUM('faible','moyenne','elevee','critique') NOT NULL DEFAULT 'faible',
    description TEXT NULL,
    localisation VARCHAR(255) NULL,
    code_qr VARCHAR(255) NOT NULL,
    signature_cryptographique TEXT NOT NULL,
    created_at TIMESTAMP NULL DEFAULT NULL,
    updated_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id_equipement),
    UNIQUE KEY uq_equipements_numero_serie (numero_serie),
    UNIQUE KEY uq_equipements_code_qr (code_qr)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 5. DEMANDE INTERVENTIONS
-- ============================================================

CREATE TABLE demande_interventions (
    id_demande INT UNSIGNED AUTO_INCREMENT,
    titre VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    priorite ENUM('faible','moyenne','elevee','critique') NOT NULL DEFAULT 'faible',
    statut ENUM('en_attente','validee','refusee','en_cours','terminee') NOT NULL DEFAULT 'en_attente',
    date_creation TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_validation TIMESTAMP NULL DEFAULT NULL,
    id_equipement INT UNSIGNED NOT NULL,
    id_utilisateur INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_demande),
    CONSTRAINT fk_demande_equipement
        FOREIGN KEY (id_equipement) REFERENCES equipements(id_equipement)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_demande_utilisateur
        FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id_utilisateur)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 6. ORDRES DE TRAVAIL
-- ============================================================

CREATE TABLE ordre_travails (
    id_ot INT UNSIGNED AUTO_INCREMENT,
    titre VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    priorite ENUM('faible','moyenne','elevee','critique') NOT NULL,
    statut ENUM('planifie','en_cours','suspendu','termine') NOT NULL DEFAULT 'planifie',
    date_planifiee DATETIME NULL,
    date_debut DATETIME NULL,
    date_fin DATETIME NULL,
    temps_reel INT NULL,
    commentaire_cloture TEXT NULL,
    id_demande INT UNSIGNED NOT NULL,
    id_equipement INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_ot),
    CONSTRAINT fk_ot_demande
        FOREIGN KEY (id_demande) REFERENCES demande_interventions(id_demande)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ot_equipement
        FOREIGN KEY (id_equipement) REFERENCES equipements(id_equipement)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 7. PANNES
-- ============================================================

CREATE TABLE pannes (
    id_panne INT UNSIGNED AUTO_INCREMENT,
    titre VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    gravite ENUM('faible','moyenne','grave','critique') NOT NULL,
    date_detection DATETIME NOT NULL,
    cause TEXT NULL,
    solution TEXT NULL,
    symptomes TEXT NULL,
    id_equipement INT UNSIGNED NOT NULL,
    id_ot INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_panne),
    CONSTRAINT fk_panne_equipement
        FOREIGN KEY (id_equipement) REFERENCES equipements(id_equipement)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_panne_ot
        FOREIGN KEY (id_ot) REFERENCES ordre_travails(id_ot)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 8. AFFECTATIONS
-- ============================================================

CREATE TABLE affectations (
    id_affectation INT UNSIGNED AUTO_INCREMENT,
    date_affectation DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    role_intervention VARCHAR(255) NOT NULL,
    statut ENUM('assignee','en_cours','terminee','annulee') NOT NULL DEFAULT 'assignee',
    commentaire TEXT NULL,
    id_utilisateur INT UNSIGNED NOT NULL,
    id_ot INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_affectation),
    CONSTRAINT fk_affectation_utilisateur
        FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id_utilisateur)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_affectation_ot
        FOREIGN KEY (id_ot) REFERENCES ordre_travails(id_ot)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 9. DOCUMENTS
-- ============================================================

CREATE TABLE documents (
    id_document INT UNSIGNED AUTO_INCREMENT,
    titre VARCHAR(255) NOT NULL,
    nom_fichier VARCHAR(255) NOT NULL,
    type_fichier VARCHAR(255) NULL,
    chemin_fichier VARCHAR(255) NOT NULL,
    taille BIGINT UNSIGNED NOT NULL,
    version VARCHAR(255) NOT NULL DEFAULT '1.0',
    date_importation TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT NULL,
    id_equipement INT UNSIGNED NULL,
    PRIMARY KEY (id_document),
    CONSTRAINT fk_document_equipement
        FOREIGN KEY (id_equipement) REFERENCES equipements(id_equipement)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 10. DOCUMENT CHUNKS (RAG)
-- ============================================================

CREATE TABLE document_chunks (
    id_chunk INT UNSIGNED AUTO_INCREMENT,
    contenu LONGTEXT NOT NULL,
    ordre_chunk INT NOT NULL,
    nombre_tokens INT NOT NULL,
    id_document INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_chunk),
    CONSTRAINT fk_chunk_document
        FOREIGN KEY (id_document) REFERENCES documents(id_document)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 11. CONVERSATIONS RAG
-- ============================================================

CREATE TABLE conversation_rags (
    id_conversation INT UNSIGNED AUTO_INCREMENT,
    titre VARCHAR(255) NOT NULL,
    date_debut TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_fin TIMESTAMP NULL DEFAULT NULL,
    id_utilisateur INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_conversation),
    CONSTRAINT fk_conversation_utilisateur
        FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id_utilisateur)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 12. MESSAGES CHAT
-- ============================================================

CREATE TABLE message_chats (
    id_message INT UNSIGNED AUTO_INCREMENT,
    contenu LONGTEXT NOT NULL,
    type_message ENUM('user','assistant','system') NOT NULL,
    date_envoi TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sources LONGTEXT NULL,
    id_conversation INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_message),
    CONSTRAINT fk_message_conversation
        FOREIGN KEY (id_conversation) REFERENCES conversation_rags(id_conversation)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 13. AUDIT LOGS
-- ============================================================

CREATE TABLE audit_logs (
    id_audit INT UNSIGNED AUTO_INCREMENT,
    action VARCHAR(255) NOT NULL,
    nom_table VARCHAR(255) NOT NULL,
    id_enregistrement BIGINT UNSIGNED NOT NULL,
    ancienne_valeur LONGTEXT NULL,
    nouvelle_valeur LONGTEXT NULL,
    adresse_ip VARCHAR(45) NULL,
    navigateur VARCHAR(255) NULL,
    date_action TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id_utilisateur INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_audit),
    CONSTRAINT fk_audit_utilisateur
        FOREIGN KEY (id_utilisateur) REFERENCES utilisateurs(id_utilisateur)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 14. SESSIONS (Laravel)
-- ============================================================

CREATE TABLE sessions (
    id VARCHAR(255) NOT NULL,
    user_id INT UNSIGNED NULL,
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    payload LONGTEXT NOT NULL,
    last_activity INT NOT NULL,
    INDEX idx_sessions_user_id (user_id),
    INDEX idx_sessions_last_activity (last_activity),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 15. CACHE (Laravel)
-- ============================================================

CREATE TABLE cache (
    `key` VARCHAR(255) NOT NULL,
    value MEDIUMTEXT NOT NULL,
    expiration BIGINT NOT NULL,
    INDEX idx_cache_expiration (expiration),
    PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE cache_locks (
    `key` VARCHAR(255) NOT NULL,
    owner VARCHAR(255) NOT NULL,
    expiration BIGINT NOT NULL,
    INDEX idx_cache_locks_expiration (expiration),
    PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- SEEDERS — Rôles
-- ============================================================

INSERT INTO roles (id_role, nom_role, description, created_at, updated_at) VALUES
(1, 'Admin',      'Administrateur',            NOW(), NOW()),
(2, 'Responsable','Responsable de maintenance', NOW(), NOW()),
(3, 'Technicien', 'Technicien de maintenance',  NOW(), NOW()),
(4, 'Demandeur',  'Utilisateur standard',       NOW(), NOW());

-- ============================================================
-- SEEDERS — Utilisateur IA (pour GMAO-API)
-- ============================================================

-- Mot de passe : NULL (pas d'auth UI pour l'IA)
INSERT INTO utilisateurs (id_utilisateur, nom, prenom, email, mot_de_passe, statut, id_role, id_specialite, created_at, updated_at)
VALUES (1, 'Assistant', 'IA GMAO', 'ia@gmao.local', '', 'actif', 1, NULL, NOW(), NOW());

-- ============================================================
-- SEEDERS — Équipements (12 machines de test)
-- Source : GMAO-ML/db/user&demende_intervention.sql
-- ============================================================

INSERT INTO equipements (id_equipement, nom_equipement, marque, modele, numero_serie, date_acquisition, date_mise_service, etat, criticite, description, localisation, code_qr, signature_cryptographique, created_at, updated_at) VALUES
(1,  'Compresseur industriel', 'Atlas Copco',    'GA 75',     'AC-GA75-001',    '2022-03-15', '2022-04-01', 'fonctionnel', 'elevee',     'Compresseur industriel pour alimentation du réseau pneumatique.',               'Atelier A - Zone 1',     'QR-EQP-001', 'SIG-EQP-001', NOW(), NOW()),
(2,  'Pompe hydraulique',      'Bosch Rexroth',  'A10VSO',    'BR-A10VSO-002',  '2021-06-20', '2021-07-05', 'fonctionnel', 'critique',   'Pompe hydraulique principale du système de production.',                        'Atelier A - Zone 2',     'QR-EQP-002', 'SIG-EQP-002', NOW(), NOW()),
(3,  'Moteur électrique',      'Siemens',        '1LE1001',   'SI-1LE1001-003', '2023-01-10', '2023-02-01', 'fonctionnel', 'moyenne',    'Moteur électrique triphasé utilisé sur une ligne de production.',               'Ligne de production 1',  'QR-EQP-003', 'SIG-EQP-003', NOW(), NOW()),
(4,  'Convoyeur industriel',   'SEW-Eurodrive',  'DRN',       'SEW-DRN-004',    '2022-09-12', '2022-10-01', 'maintenance', 'elevee',     'Convoyeur pour le transport automatique des produits.',                         'Ligne de production 1',  'QR-EQP-004', 'SIG-EQP-004', NOW(), NOW()),
(5,  'Tour CNC',               'Mazak',          'QT-200',    'MZ-QT200-005',   '2020-11-05', '2021-01-15', 'fonctionnel', 'critique',   'Machine-outil CNC destinée à l''usinage de pièces métalliques.',                'Atelier d''usinage',     'QR-EQP-005', 'SIG-EQP-005', NOW(), NOW()),
(6,  'Fraiseuse CNC',          'Haas',           'VF-2',      'HA-VF2-006',     '2021-04-18', '2021-05-10', 'fonctionnel', 'elevee',     'Fraiseuse CNC utilisée pour l''usinage de précision.',                          'Atelier d''usinage',     'QR-EQP-006', 'SIG-EQP-006', NOW(), NOW()),
(7,  'Chaudière industrielle', 'Bosch',          'Uni 3000',  'BO-UNI3000-007', '2019-08-25', '2019-10-01', 'fonctionnel', 'critique',   'Chaudière industrielle utilisée pour la production de vapeur.',                 'Salle énergétique',      'QR-EQP-007', 'SIG-EQP-007', NOW(), NOW()),
(8,  'Ventilateur industriel', 'ABB',            'ACH580',    'ABB-ACH580-008', '2023-05-12', '2023-06-01', 'en_panne',    'moyenne',    'Ventilateur industriel pour la ventilation de la zone de production.',          'Atelier B - Zone 1',     'QR-EQP-008', 'SIG-EQP-008', NOW(), NOW()),
(9,  'Groupe électrogène',      'Caterpillar',    'C18',       'CAT-C18-009',    '2020-02-10', '2020-03-01', 'fonctionnel', 'critique',   'Groupe électrogène de secours pour l''alimentation électrique.',                'Local énergie',          'QR-EQP-009', 'SIG-EQP-009', NOW(), NOW()),
(10, 'Robot industriel',       'ABB',            'IRB 2600',  'ABB-IRB2600-010','2022-12-01', '2023-01-15', 'fonctionnel', 'critique',   'Robot industriel utilisé pour les opérations automatisées de production.',      'Ligne robotisée',        'QR-EQP-010', 'SIG-EQP-010', NOW(), NOW()),
(11, 'Machine de soudage',     'Fronius',        'TPS 500i',  'FR-TPS500I-011', '2021-09-14', '2021-10-01', 'fonctionnel', 'elevee',     'Système de soudage industriel automatisé.',                                    'Atelier soudage',        'QR-EQP-011', 'SIG-EQP-011', NOW(), NOW()),
(12, 'Presse hydraulique',     'Schuler',        'HP 500',    'SC-HP500-012',   '2018-07-20', '2018-09-01', 'hors_service','critique',   'Presse hydraulique industrielle actuellement hors service.',                    'Atelier B - Zone 3',     'QR-EQP-012', 'SIG-EQP-012', NOW(), NOW());
