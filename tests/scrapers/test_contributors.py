"""Bot filter and core-contributor rule: the G2 'zero bots harvested' gate."""

from scrapers.github.contributors import core_contributors, is_bot
from scrapers.github.models import ContributorStat


def stat(login: str, contributions: int, user_type: str = "User") -> ContributorStat:
    return ContributorStat(login=login, user_id=1, contributions=contributions, user_type=user_type)


def test_bot_filter_catches_all_three_shapes() -> None:
    assert is_bot("anything", "Bot")
    assert is_bot("dependabot[bot]", "User")
    assert is_bot("codecov", "User")
    assert is_bot("renovate", "User")
    assert not is_bot("dev01", "User")
    assert not is_bot("robotics-fan", "User")


def test_core_rule_threshold_and_rank() -> None:
    stats = [
        stat("a", 100),
        stat("b", 50),
        stat("c", 6),
        stat("d", 2),  # below max(3, ceil(0.05*158)=8)
    ]
    core = core_contributors(stats)
    assert [entry.login for entry in core] == ["a", "b"]


def test_core_rule_small_repo_uses_min_contributions() -> None:
    stats = [stat("a", 5), stat("b", 3), stat("c", 2)]
    # total 10 -> threshold max(3, ceil(0.5)) = 3
    assert [entry.login for entry in core_contributors(stats)] == ["a", "b"]


def test_core_rule_caps_at_five() -> None:
    stats = [stat(f"dev{i}", 100 - i) for i in range(8)]
    assert len(core_contributors(stats)) == 5


def test_bots_dropped_before_share_computation() -> None:
    stats = [
        stat("dependabot[bot]", 10_000, "Bot"),
        stat("human", 40),
        stat("helper", 5),
    ]
    # With the bot dropped, total is 45 -> threshold 3; both humans qualify.
    assert [entry.login for entry in core_contributors(stats)] == ["human", "helper"]
