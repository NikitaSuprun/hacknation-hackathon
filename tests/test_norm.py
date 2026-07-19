# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Mechanical normalizer behavior: diacritics, noreply bans, suffix stripping."""

from tools.norm import email_domain, email_norm, name_norm, org_key, url_norm


def test_name_norm_strips_diacritics_and_titles() -> None:
    assert name_norm("Dr. Léna Físcher") == "lena fischer"
    assert name_norm("Prof. Jürgen Groß, PhD") == "jurgen gross"
    assert name_norm("  Wei   Zhang ") == "wei zhang"


def test_name_norm_is_idempotent() -> None:
    once = name_norm("Dr. Léna Físcher")
    assert name_norm(once) == once


def test_email_norm_bans_github_noreply() -> None:
    assert email_norm("1001+lenafischer@users.noreply.github.com") is None
    assert email_norm("lenafischer@users.noreply.github.com") is None


def test_email_norm_bans_generic_inboxes() -> None:
    assert email_norm("info@grasplab.ch") is None
    assert email_norm("Admin@example.com") is None


def test_email_norm_lowers_valid_addresses() -> None:
    assert email_norm("Lena.Fischer@ethz.CH") == "lena.fischer@ethz.ch"
    assert email_norm("not-an-email") is None
    assert email_norm("two@@ats.com") is None


def test_email_domain_blocking_key() -> None:
    assert email_domain("Lena.Fischer@ethz.CH") == "ethz.ch"
    assert email_domain("info@grasplab.ch") is None


def test_org_key_strips_legal_suffixes_and_accents() -> None:
    assert org_key("GraspLab AG") == "grasplab"
    assert org_key("Fluxon Robotics GmbH") == "fluxon robotics"
    assert org_key("Acme Sàrl") == "acme"
    assert org_key("ETH Zürich") == "eth zurich"


def test_org_key_is_mechanical_only() -> None:
    # Semantic folding (ETHZ -> ETH Zurich) lives in tools.institutions.
    assert org_key("ETHZ") == "ethz"
    assert org_key("Universität Zürich") == "universitat zurich"


def test_url_norm_equalizes_variants() -> None:
    assert url_norm("https://www.GraspLab.ch/") == "grasplab.ch"
    assert url_norm("http://grasplab.ch") == "grasplab.ch"
    assert url_norm("grasplab.ch/team/?utm=x#top") == "grasplab.ch/team"
    assert url_norm("") is None
