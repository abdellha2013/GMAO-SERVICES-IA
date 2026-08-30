"""Tests de la validation anti-phishing de l'URL encodée dans le QR."""

from __future__ import annotations

from gmao_ocr.qr.validation import (
    EQUIPEMENT_URL_RE,
    extract_id_from_url,
    host_matches_allowed,
    validate_qr_url,
    validate_qr_url_reason,
)

VALID = "https://mondomaine.com/api/equipements/5"


def test_extract_valid():
    assert extract_id_from_url(VALID) == 5


def test_extract_http_and_trailing_slash():
    assert extract_id_from_url("http://host.example/api/equipements/42/") == 42


def test_extract_large_id():
    assert extract_id_from_url("https://h/api/equipements/123456789") == 123456789


def test_reject_non_equipement_path():
    assert extract_id_from_url("https://mondomaine.com/api/autres/5") is None
    assert extract_id_from_url("https://mondomaine.com/equipements/5") is None


def test_reject_unknown_host_when_restricted():
    assert validate_qr_url(VALID, ["mondomaine.com"]) == 5
    assert validate_qr_url("https://attacker.com/api/equipements/5", ["mondomaine.com"]) is None


def test_accept_any_host_when_empty_allowlist():
    assert validate_qr_url(VALID, []) == 5


def test_regex_group_names():
    m = EQUIPEMENT_URL_RE.match(VALID)
    assert m is not None
    assert m.group("host") == "mondomaine.com"
    assert m.group("id") == "5"


def test_reject_non_http_url():
    assert extract_id_from_url("ftp://mondomaine.com/api/equipements/5") is None


def test_host_matches_allowed():
    assert host_matches_allowed("https://mondomaine.com/api/equipements/5", []) is True
    assert host_matches_allowed("https://mondomaine.com/api/equipements/5", ["mondomaine.com"]) is True
    assert host_matches_allowed("https://x.mondomaine.com/api/equipements/5", ["mondomaine.com"]) is True
    assert host_matches_allowed("https://attacker.com/api/equipements/5", ["mondomaine.com"]) is False


def test_hostname_with_port_ignored_for_matching():
    # Le port ne doit pas casser la comparaison d'hôte (localhost:8001 → localhost).
    assert host_matches_allowed("http://localhost:8001/api/equipements/1", ["localhost"]) is True
    assert host_matches_allowed("http://localhost:8001/api/equipements/1", ["10.96.93.203"]) is False


def test_localhost_accepted_when_allowed():
    assert validate_qr_url("http://localhost:8001/api/equipements/1", ["localhost"]) == 1


def test_reason_distinguishes_path_from_host():
    # Chemin valide + hôte interdit → motif clair, distinct du chemin invalide.
    ok_id, reason = validate_qr_url_reason("http://localhost:8001/api/equipements/1", [])
    assert ok_id == 1 and reason is None

    _, reason = validate_qr_url_reason("http://localhost:8001/api/equipements/1", ["10.96.93.203"])
    assert reason == "Domaine non autorisé"

    _, reason = validate_qr_url_reason("http://localhost:8001/autre/chemin", ["localhost"])
    assert reason == "URL non reconnue"
