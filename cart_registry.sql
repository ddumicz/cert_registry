-- Rejestr certyfikatow DORA - model CMDB v2
-- PostgreSQL 14+. Wykonaj w docelowej bazie danych.
-- Nowa instalacja: tworzy schemat i 4 tabele; nie usuwa danych.
-- UWAGA: jesli masz juz stara tabele asset_relations, uzyj
-- oddzielnego skryptu migracyjnego cert_registry_migration_v2.sql.
BEGIN;
CREATE SCHEMA IF NOT EXISTS cert_registry;

CREATE TABLE IF NOT EXISTS cert_registry.assets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_key VARCHAR(255) NOT NULL UNIQUE,
    asset_name VARCHAR(255) NOT NULL,
    asset_type VARCHAR(50) NOT NULL,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT assets_asset_type_not_blank CHECK (btrim(asset_type) <> ''),
    CONSTRAINT assets_asset_key_not_blank CHECK (btrim(asset_key) <> '')
);

CREATE TABLE IF NOT EXISTS cert_registry.certificates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sha256 CHAR(64) NOT NULL UNIQUE,
    subject TEXT,
    issuer TEXT,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT certificates_sha256_hex CHECK (sha256 ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT certificates_dates_valid CHECK (
        valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to
    )
);

CREATE TABLE IF NOT EXISTS cert_registry.certificate_assets (
    certificate_id BIGINT NOT NULL REFERENCES cert_registry.certificates(id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES cert_registry.assets(id) ON DELETE CASCADE,
    PRIMARY KEY (certificate_id, asset_id)
);

CREATE TABLE IF NOT EXISTS cert_registry.asset_relations (
    parent_asset_id BIGINT NOT NULL REFERENCES cert_registry.assets(id) ON DELETE CASCADE,
    child_asset_id BIGINT NOT NULL REFERENCES cert_registry.assets(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    PRIMARY KEY (parent_asset_id, child_asset_id, relation_type),
    CONSTRAINT asset_relations_no_self_reference CHECK (parent_asset_id <> child_asset_id),
    CONSTRAINT asset_relations_type_not_blank CHECK (btrim(relation_type) <> '')
);

CREATE INDEX IF NOT EXISTS idx_assets_ip ON cert_registry.assets (ip_address);
CREATE INDEX IF NOT EXISTS idx_assets_type ON cert_registry.assets (asset_type);
CREATE INDEX IF NOT EXISTS idx_certificates_valid_to ON cert_registry.certificates (valid_to);
CREATE INDEX IF NOT EXISTS idx_certificate_assets_asset ON cert_registry.certificate_assets (asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_relations_child ON cert_registry.asset_relations (child_asset_id);
COMMIT;

-- PRZYKLAD 1: certyfikaty znalezione na IP
-- SELECT a.asset_name, a.ip_address, c.subject, c.sha256, c.valid_to
-- FROM cert_registry.assets a
-- JOIN cert_registry.certificate_assets ca ON ca.asset_id = a.id
-- JOIN cert_registry.certificates c ON c.id = ca.certificate_id
-- WHERE a.ip_address = '10.10.1.15'::inet;

-- PRZYKLAD 2: certyfikaty systemu przez bezposrednio powiazane zasoby
-- SELECT DISTINCT s.asset_name AS system_name, a.asset_name AS asset_name,
--        a.ip_address, c.subject, c.sha256, c.valid_to
-- FROM cert_registry.assets s
-- JOIN cert_registry.asset_relations ar ON ar.parent_asset_id = s.id
-- JOIN cert_registry.assets a ON a.id = ar.child_asset_id
-- JOIN cert_registry.certificate_assets ca ON ca.asset_id = a.id
-- JOIN cert_registry.certificates c ON c.id = ca.certificate_id
-- WHERE s.asset_type = 'SYSTEM' AND s.asset_key = 'CMDB:SYSTEM-001'
-- ORDER BY a.ip_address, c.valid_to;

-- PRZYKLAD 3: certyfikaty systemu rowniez przez wielopoziomowe relacje
-- WITH RECURSIVE descendants(asset_id, path) AS (
--     SELECT s.id, ARRAY[s.id]
--     FROM cert_registry.assets s
--     WHERE s.asset_type = 'SYSTEM' AND s.asset_key = 'CMDB:SYSTEM-001'
--     UNION ALL
--     SELECT ar.child_asset_id, d.path || ar.child_asset_id
--     FROM descendants d
--     JOIN cert_registry.asset_relations ar ON ar.parent_asset_id = d.asset_id
--     WHERE NOT ar.child_asset_id = ANY(d.path)
-- )
-- SELECT DISTINCT a.asset_name, a.ip_address, c.subject, c.sha256, c.valid_to
-- FROM descendants d
-- JOIN cert_registry.assets a ON a.id = d.asset_id
-- JOIN cert_registry.certificate_assets ca ON ca.asset_id = a.id
-- JOIN cert_registry.certificates c ON c.id = ca.certificate_id
-- ORDER BY a.asset_name, c.valid_to;

-- PRZYKLAD 4: powiazanie systemu z serwerem (podstaw prawdziwe ID)
-- INSERT INTO cert_registry.asset_relations(parent_asset_id, child_asset_id, relation_type)
-- VALUES (1, 2, 'CONTAINS') ON CONFLICT DO NOTHING;

-- UWAGI:
-- 1. asset_key to stabilny identyfikator zasobu, nie samo IP.
-- 2. Jeden asset przechowuje jeden IP; IP nie jest unikalne.
-- 3. Certyfikaty pod tym samym IP moga roznic sie portem i SNI.
-- 4. Relacje sa skierowane. Przy RUNS_ON: aplikacja -> serwer.
-- 5. Zapytanie rekurencyjne idzie po wszystkich typach relacji; w praktyce
--    mozna ograniczyc typy relacji do tych istotnych dla systemu.
-- 6. CREATE TABLE IF NOT EXISTS nie migruje juz istniejacych tabel.
