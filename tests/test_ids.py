# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Golden-value tests: identical input must mint the identical UUID on any machine."""

import pytest

from tools import ids


def test_namespace_is_frozen() -> None:
    assert str(ids.DEALFLOW_NS) == "9f0b6a60-b89b-57d5-876b-27fe702f78a6"


def test_psr_id_golden() -> None:
    assert ids.psr_id("github", "1001") == "a7d5bff2-b9f7-548e-ae89-d4bb66f629b6"


def test_project_id_golden() -> None:
    assert ids.project_id(500123) == "efce0d66-c110-555a-a79b-bfb96fa3ef11"


def test_hacknation_project_id_golden() -> None:
    assert ids.hacknation_project_id("hn-proj-001") == "7cbc2f38-bdc7-5803-84d5-37d500070f5a"


def test_publication_id_coalesce_order() -> None:
    assert ids.publication_id("10.1000/xyz", "2506.01234", "W1") == (
        "401bc6a0-b12d-5244-8eb0-07ad92aa1f2d"
    )
    assert ids.publication_id(None, "2506.01234", "W1") == ("7bb0249b-d0ce-531e-a0a0-e2c83d447015")
    assert ids.publication_id(None, None, "W1") == "b66bdab7-2d0e-53c0-b318-15da8765cfbf"
    with pytest.raises(ValueError, match="publication needs"):
        ids.publication_id(None, None, None)


def test_company_and_venture_ids_golden() -> None:
    assert ids.company_id("CHE-123.456.789") == "74229476-5bcd-5d9c-bba1-0c6b57b69e31"
    repo_project = ids.project_id(500123)
    assert ids.venture_id("repo", repo_project) == "f18481a4-a59c-5dab-adf1-bf4beca5a626"


def test_link_id_golden_and_method_sensitivity() -> None:
    assert ids.link_id("p", "s", "det_email") == "135b158f-db9d-5799-be03-4b4dfd96f618"
    assert ids.link_id("p", "s", "det_orcid") != ids.link_id("p", "s", "det_email")


def test_random_ids_are_unique() -> None:
    assert ids.new_random_id() != ids.new_random_id()
