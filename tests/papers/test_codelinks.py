# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Code-link extraction: suffixes, trailing punctuation, hosts, dedupe."""

from scrapers.papers.codelinks import extract_code_links


def urls(text: str) -> list[str]:
    return [link.url for link in extract_code_links(text)]


def test_git_suffix_stripped() -> None:
    assert urls("Code: github.com/a/b.git") == ["https://github.com/a/b"]


def test_trailing_punctuation_excluded() -> None:
    assert urls("See github.com/a/b.") == ["https://github.com/a/b"]
    assert urls("(github.com/a/b)") == ["https://github.com/a/b"]
    assert urls("github.com/a/b, and more") == ["https://github.com/a/b"]
    assert urls("[github.com/a/b];") == ["https://github.com/a/b"]


def test_end_of_string_matches() -> None:
    assert urls("github.com/a/b") == ["https://github.com/a/b"]


def test_dotted_and_hyphenated_names() -> None:
    assert urls("github.com/grasp-lab/grasp.anything ") == [
        "https://github.com/grasp-lab/grasp.anything"
    ]


def test_gitlab_and_huggingface_variants() -> None:
    assert urls("gitlab.com/team/tool and huggingface.co/org/model") == [
        "https://gitlab.com/team/tool",
        "https://huggingface.co/org/model",
    ]
    assert urls("Demo: huggingface.co/spaces/slamlab/sparse-maps") == [
        "https://huggingface.co/slamlab/sparse-maps"
    ]


def test_owner_without_repo_is_no_match() -> None:
    assert urls("see github.com/owner for details") == []


def test_dedupe_preserves_first_occurrence_order() -> None:
    text = "github.com/a/b then gitlab.com/c/d then github.com/a/b again"
    assert urls(text) == ["https://github.com/a/b", "https://gitlab.com/c/d"]


def test_case_insensitive_host_dedupe() -> None:
    assert len(extract_code_links("GitHub.com/A/B and github.com/a/b")) == 1
