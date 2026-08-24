-- Active: 1787484567085@@127.0.0.1@3306@gmao_rag
-- ============================================================
-- GMAO-RAG
-- VERSION DE TEST
-- 3 TABLES INDÉPENDANTES
-- AUCUNE FOREIGN KEY
-- AUCUNE DÉPENDANCE EXTERNE
-- ============================================================

CREATE DATABASE IF NOT EXISTS gmao_rag
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE gmao_rag;


-- ============================================================
-- NETTOYAGE DES ANCIENNES TABLES
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS demande_interventions;
DROP TABLE IF EXISTS utilisateurs;
DROP TABLE IF EXISTS equipements;

SET FOREIGN_KEY_CHECKS = 1;


-- ============================================================
-- 1. EQUIPEMENTS
-- ============================================================

CREATE TABLE equipements (

    id_equipement INT UNSIGNED AUTO_INCREMENT,

    nom_equipement VARCHAR(255) NULL,

    marque VARCHAR(255) NULL,

    modele VARCHAR(255) NULL,

    numero_serie VARCHAR(255) NULL,

    date_acquisition DATE NULL,

    date_mise_service DATE NULL,

    etat ENUM(
        'fonctionnel',
        'en_panne',
        'maintenance',
        'hors_service'
    ) NULL DEFAULT 'fonctionnel',

    criticite ENUM(
        'faible',
        'moyenne',
        'elevee',
        'critique'
    ) NULL DEFAULT 'faible',

    description TEXT NULL,

    localisation VARCHAR(255) NULL,

    code_qr VARCHAR(255) NULL,

    signature_cryptographique TEXT NULL,

    created_at TIMESTAMP NULL DEFAULT NULL,

    updated_at TIMESTAMP NULL DEFAULT NULL,

    PRIMARY KEY (id_equipement),

    UNIQUE KEY uq_equipements_numero_serie (numero_serie),

    UNIQUE KEY uq_equipements_code_qr (code_qr)

) ENGINE=InnoDB
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;


-- ============================================================
-- 2. UTILISATEURS
-- ============================================================

CREATE TABLE utilisateurs (

    id_utilisateur INT UNSIGNED AUTO_INCREMENT,

    nom VARCHAR(100) NULL,

    prenom VARCHAR(100) NULL,

    email VARCHAR(255) NULL,

    mot_de_passe VARCHAR(255) NULL,

    telephone VARCHAR(20) NULL,

    photo_profil VARCHAR(255) NULL,

    statut ENUM(
        'actif',
        'inactif',
        'suspendu'
    ) NULL DEFAULT 'actif',

    id_role INT UNSIGNED NULL,


    id_specialite INT UNSIGNED NULL,

    created_at TIMESTAMP NULL DEFAULT NULL,

    updated_at TIMESTAMP NULL DEFAULT NULL,

    PRIMARY KEY (id_utilisateur),

    UNIQUE KEY uq_utilisateurs_email (email)

) ENGINE=InnoDB
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;


-- ============================================================
-- 3. DEMANDE INTERVENTIONS
-- ============================================================

CREATE TABLE demande_interventions (

    id_demande INT UNSIGNED AUTO_INCREMENT,

    titre VARCHAR(255) NULL,

    description TEXT NULL,

    priorite ENUM(
        'faible',
        'moyenne',
        'elevee',
        'critique'
    ) NULL DEFAULT 'faible',

    statut ENUM(
        'en_attente',
        'validee',
        'refusee',
        'en_cours',
        'terminee'
    ) NULL DEFAULT 'en_attente',

    date_creation TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,

    date_validation TIMESTAMP NULL DEFAULT NULL,

    id_equipement INT UNSIGNED NULL,


    id_utilisateur INT UNSIGNED NULL,

    PRIMARY KEY (id_demande)

) ENGINE=InnoDB
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;



-- INSERT INTO utilisateurs (
--     nom,
--     prenom,
--     email,
--     mot_de_passe,
--     telephone,
--     photo_profil,
--     statut,
--     id_role,
--     id_specialite
-- )
-- VALUES (
--     'IA',
--     'Assistant GMAO',
--     'ia@gmao.local',
--     NULL,
--     NULL,
--     NULL,
--     'actif',
--     NULL,
--     NULL
-- );





-- USE gmao_rag;

-- -- Insertion des équipements dans la table "equipements"
-- INSERT INTO equipements (
--     nom_equipement,
--     marque,
--     modele,
--     numero_serie,
--     date_acquisition,
--     date_mise_service,
--     etat,
--     criticite,
--     description,
--     localisation,
--     code_qr,
--     signature_cryptographique
-- )
-- VALUES
  
--     ('Compresseur industriel', 'Atlas Copco', 'GA 75', 'AC-GA75-001',
--      '2022-03-15', '2022-04-01', 'fonctionnel', 'elevee',
--      'Compresseur industriel pour alimentation du réseau pneumatique.',
--      'Atelier A - Zone 1', 'QR-EQP-001', 'SIG-EQP-001'),

  
--     ('Pompe hydraulique', 'Bosch Rexroth', 'A10VSO', 'BR-A10VSO-002',
--      '2021-06-20', '2021-07-05', 'fonctionnel', 'critique',
--      'Pompe hydraulique principale du système de production.',
--      'Atelier A - Zone 2', 'QR-EQP-002', 'SIG-EQP-002'),

  
--     ('Moteur électrique', 'Siemens', '1LE1001', 'SI-1LE1001-003',
--      '2023-01-10', '2023-02-01', 'fonctionnel', 'moyenne',
--      'Moteur électrique triphasé utilisé sur une ligne de production.',
--      'Ligne de production 1', 'QR-EQP-003', 'SIG-EQP-003'),


--     ('Convoyeur industriel', 'SEW-Eurodrive', 'DRN', 'SEW-DRN-004',
--      '2022-09-12', '2022-10-01', 'maintenance', 'elevee',
--      'Convoyeur pour le transport automatique des produits.',
--      'Ligne de production 1', 'QR-EQP-004', 'SIG-EQP-004'),


--     ('Tour CNC', 'Mazak', 'QT-200', 'MZ-QT200-005',
--      '2020-11-05', '2021-01-15', 'fonctionnel', 'critique',
--      'Machine-outil CNC destinée à l''usinage de pièces métalliques.',
--      'Atelier d''usinage', 'QR-EQP-005', 'SIG-EQP-005'),


--     ('Fraiseuse CNC', 'Haas', 'VF-2', 'HA-VF2-006',
--      '2021-04-18', '2021-05-10', 'fonctionnel', 'elevee',
--      'Fraiseuse CNC utilisée pour l''usinage de précision.',
--      'Atelier d''usinage', 'QR-EQP-006', 'SIG-EQP-006'),


--     ('Chaudière industrielle', 'Bosch', 'Uni 3000', 'BO-UNI3000-007',
--      '2019-08-25', '2019-10-01', 'fonctionnel', 'critique',
--      'Chaudière industrielle utilisée pour la production de vapeur.',
--      'Salle énergétique', 'QR-EQP-007', 'SIG-EQP-007'),


--     ('Ventilateur industriel', 'ABB', 'ACH580', 'ABB-ACH580-008',
--      '2023-05-12', '2023-06-01', 'en_panne', 'moyenne',
--      'Ventilateur industriel pour la ventilation de la zone de production.',
--      'Atelier B - Zone 1', 'QR-EQP-008', 'SIG-EQP-008'),


--     ('Groupe électrogène', 'Caterpillar', 'C18', 'CAT-C18-009',
--      '2020-02-10', '2020-03-01', 'fonctionnel', 'critique',
--      'Groupe électrogène de secours pour l''alimentation électrique.',
--      'Local énergie', 'QR-EQP-009', 'SIG-EQP-009'),


--     ('Robot industriel', 'ABB', 'IRB 2600', 'ABB-IRB2600-010',
--      '2022-12-01', '2023-01-15', 'fonctionnel', 'critique',
--      'Robot industriel utilisé pour les opérations automatisées de production.',
--      'Ligne robotisée', 'QR-EQP-010', 'SIG-EQP-010'),


--     ('Machine de soudage', 'Fronius', 'TPS 500i', 'FR-TPS500I-011',
--      '2021-09-14', '2021-10-01', 'fonctionnel', 'elevee',
--      'Système de soudage industriel automatisé.',
--      'Atelier soudage', 'QR-EQP-011', 'SIG-EQP-011'),

--     ('Presse hydraulique', 'Schuler', 'HP 500', 'SC-HP500-012',
--      '2018-07-20', '2018-09-01', 'hors_service', 'critique',
--      'Presse hydraulique industrielle actuellement hors service.',
--      'Atelier B - Zone 3', 'QR-EQP-012', 'SIG-EQP-012');