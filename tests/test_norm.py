# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Normalizer behavior the ER pipeline depends on: diacritics, noreply, aliases."""

from tools.norm import email_domain, email_norm, name_norm, org_norm, url_norm


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


def test_org_norm_folds_eth_aliases() -> None:
    assert org_norm("ETHZ") == "eth zurich"
    assert org_norm("ETH Zürich") == "eth zurich"
    assert org_norm("Eidgenössische Technische Hochschule Zürich") == "eth zurich"
    assert org_norm("Swiss Federal Institute of Technology") == "eth zurich"


def test_org_norm_strips_legal_suffixes() -> None:
    assert org_norm("GraspLab AG") == "grasplab"
    assert org_norm("Fluxon Robotics GmbH") == "fluxon robotics"
    assert org_norm("Acme Sàrl") == "acme"


def test_org_norm_folds_epfl_uzh_mit() -> None:
    assert org_norm("École Polytechnique Fédérale de Lausanne") == "epfl"
    assert org_norm("Universität Zürich") == "university of zurich"
    assert org_norm("Massachusetts Institute of Technology") == "mit"


def test_url_norm_equalizes_variants() -> None:
    assert url_norm("https://www.GraspLab.ch/") == "grasplab.ch"
    assert url_norm("http://grasplab.ch") == "grasplab.ch"
    assert url_norm("grasplab.ch/team/?utm=x#top") == "grasplab.ch/team"
    assert url_norm("") is None
