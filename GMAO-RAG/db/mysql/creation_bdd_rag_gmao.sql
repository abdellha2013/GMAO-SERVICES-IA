-- ============================================================================
-- GMAO-RAG — Création de la base et des tables du périmètre RAG
-- Portée : Document, Panne, Chunk_rag (+ sous-types), Conversation_rag,
--          Message_chat, Message_source
-- Les colonnes qui référencent des tables hors périmètre (Équipement,
-- Utilisateur, OrdreTravail) sont NULL et SANS contrainte FK : ces tables
-- n'existent pas encore dans cette base. Lors de l'intégration dans le
-- système complet (base stricte), ajouter les FOREIGN KEY correspondantes
-- via ALTER TABLE (voir section 9 en bas de fichier).
-- ============================================================================

CREATE DATABASE IF NOT EXISTS gmao_rag
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;



-- ----------------------------------------------------------------------------
-- 1. DOCUMENT
-- ----------------------------------------------------------------------------
CREATE TABLE document (
    id_document         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    titre               VARCHAR(255)    NOT NULL,
    nom_fichier         VARCHAR(255)    NOT NULL,
    type_fichier        ENUM('PDF','DOCX','TXT','HTML','MD','CSV','JSON','XLSX') NOT NULL,
    chemin_fichier      VARCHAR(255)    NOT NULL,
    taille              BIGINT UNSIGNED NOT NULL,
    version             VARCHAR(20)     NULL,
    date_importation    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    statut_indexation   ENUM('En_attente','Indexe','Echec') NOT NULL DEFAULT 'En_attente',
    description         TEXT            NULL,

    -- FK externe hors périmètre RAG : NULL, non contrainte ici
    id_equipement       INT UNSIGNED    NULL
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 2. PANNE
--    Colonnes métier reprises telles quelles du MCD général (chap. 2.9 du
--    rapport de conception) ; seul statut_indexation est ajouté pour le RAG.
-- ----------------------------------------------------------------------------
CREATE TABLE panne (
    id_panne            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    titre               VARCHAR(150)    NOT NULL,
    description         TEXT            NULL,
    gravite             ENUM('Faible','Moyenne','Elevee','Critique') NOT NULL,
    date_detection      DATETIME        NOT NULL,
    cause               TEXT            NULL,
    solution            TEXT            NULL,
    symptomes           TEXT            NULL,
    statut_indexation   ENUM('En_attente','Indexe','Echec') NOT NULL DEFAULT 'En_attente',

    -- FK externes hors périmètre RAG : NULL, non contraintes ici
    id_equipement       INT UNSIGNED    NULL,
    id_ot               INT UNSIGNED    NULL
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 3. CHUNK_RAG (supertype générique — un par fragment indexé, Document ou Panne)
-- ----------------------------------------------------------------------------
CREATE TABLE chunk_rag (
    id_chunk            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    contenu             TEXT            NOT NULL,
    ordre_chunk         INT UNSIGNED    NOT NULL,
    nombre_tokens       INT UNSIGNED    NULL,
    type_source         ENUM('Document','Panne') NOT NULL,
    statut_embedding    ENUM('En_attente','Indexe','Echec') NOT NULL DEFAULT 'En_attente',
    date_indexation     DATETIME        NULL
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 4. DOCUMENT_CHUNK (sous-type de CHUNK_RAG, spécifique aux Document)
--    Interne au périmètre RAG -> FK strictement contrainte.
-- ----------------------------------------------------------------------------
CREATE TABLE document_chunk (
    id_chunk        INT UNSIGNED PRIMARY KEY,
    id_document     INT UNSIGNED NOT NULL,

    CONSTRAINT fk_docchunk_chunk
        FOREIGN KEY (id_chunk) REFERENCES chunk_rag(id_chunk)
        ON DELETE CASCADE,
    CONSTRAINT fk_docchunk_document
        FOREIGN KEY (id_document) REFERENCES document(id_document)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 5. PANNE_CHUNK (sous-type de CHUNK_RAG, spécifique aux Panne)
--    Interne au périmètre RAG -> FK strictement contrainte.
-- ----------------------------------------------------------------------------
CREATE TABLE panne_chunk (
    id_chunk        INT UNSIGNED PRIMARY KEY,
    id_panne        INT UNSIGNED NOT NULL,

    CONSTRAINT fk_pannechunk_chunk
        FOREIGN KEY (id_chunk) REFERENCES chunk_rag(id_chunk)
        ON DELETE CASCADE,
    CONSTRAINT fk_pannechunk_panne
        FOREIGN KEY (id_panne) REFERENCES panne(id_panne)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 6. CONVERSATION_RAG
-- ----------------------------------------------------------------------------
CREATE TABLE conversation_rag (
    id_conversation     INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    titre               VARCHAR(200)    NULL,
    date_debut          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_fin            DATETIME        NULL,

    -- FK externe hors périmètre RAG : NULL, non contrainte ici
    id_utilisateur      INT UNSIGNED    NULL
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 7. MESSAGE_CHAT
--    Interne au périmètre RAG -> FK strictement contrainte.
-- ----------------------------------------------------------------------------
CREATE TABLE message_chat (
    id_message          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    contenu             TEXT            NOT NULL,
    type_message        ENUM('Question','Reponse') NOT NULL,
    date_envoi          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    indice_confiance    FLOAT           NULL,
    statut_reponse      ENUM('Ok','Sans_source','Erreur') NULL,
    id_conversation     INT UNSIGNED    NOT NULL,

    CONSTRAINT fk_message_conversation
        FOREIGN KEY (id_conversation) REFERENCES conversation_rag(id_conversation)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 8. MESSAGE_SOURCE (traduction MLD de l'association N,N "Citer")
--    Interne au périmètre RAG -> FK strictement contrainte.
-- ----------------------------------------------------------------------------
CREATE TABLE message_source (
    id_message_source   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    score_pertinence    FLOAT           NOT NULL,
    id_message          INT UNSIGNED    NOT NULL,
    id_chunk            INT UNSIGNED    NOT NULL,

    CONSTRAINT fk_msgsource_message
        FOREIGN KEY (id_message) REFERENCES message_chat(id_message)
        ON DELETE CASCADE,
    CONSTRAINT fk_msgsource_chunk
        FOREIGN KEY (id_chunk) REFERENCES chunk_rag(id_chunk)
        ON DELETE CASCADE,

    UNIQUE KEY uq_message_chunk (id_message, id_chunk)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 9. À faire lors de l'intégration dans la base complète (stricte)
--    Une fois Équipement, Utilisateur, OrdreTravail créés, activer les FK :
-- ----------------------------------------------------------------------------
-- ALTER TABLE document       ADD CONSTRAINT fk_document_equipement
--     FOREIGN KEY (id_equipement) REFERENCES equipement(id_equipement);
-- ALTER TABLE panne          ADD CONSTRAINT fk_panne_equipement
--     FOREIGN KEY (id_equipement) REFERENCES equipement(id_equipement);
-- ALTER TABLE panne          ADD CONSTRAINT fk_panne_ot
--     FOREIGN KEY (id_ot) REFERENCES ordretravail(id_ot);
-- ALTER TABLE conversation_rag ADD CONSTRAINT fk_conversation_utilisateur
--     FOREIGN KEY (id_utilisateur) REFERENCES utilisateur(id_utilisateur);
