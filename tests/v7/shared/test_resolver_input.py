import pytest

from v7.shared.resolver_input import (
    ResolverInputError,
    split_multi_input,
    youtube_playlist_id,
)


def test_multi_input_uses_only_documented_separators_and_preserves_order() -> None:
    assert split_multi_input(" a , b;\nc\r\nd ") == ("a", "b", "c", "d")


def test_duplicate_inputs_are_preserved_for_occurrence_layer() -> None:
    assert split_multi_input("a,a") == ("a", "a")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=x&list=PL123", "PL123"),
        ("https://youtu.be/x?list=PL456", "PL456"),
        ("https://music.youtube.com/playlist?list=PL789", "PL789"),
        ("https://youtube.com/watch?v=x", None),
    ],
)
def test_playlist_id_requires_supported_youtube_host(url: str, expected: str | None) -> None:
    assert youtube_playlist_id(url) == expected


def test_foreign_host_list_parameter_is_not_a_youtube_playlist() -> None:
    assert youtube_playlist_id("https://attacker.invalid/?list=PL123") is None


@pytest.mark.parametrize(
    "value",
    ["", "   ", "\0bad", "x" * 16385],
)
def test_invalid_input_fails_without_partial_result(value: str) -> None:
    with pytest.raises(ResolverInputError):
        split_multi_input(value)


def test_token_limit_is_checked_before_append() -> None:
    assert len(split_multi_input("a,b,c", limit=3)) == 3
    with pytest.raises(ResolverInputError) as raised:
        split_multi_input("a,b,c,d", limit=3)
    assert raised.value.code == "INPUT_LIMIT_EXCEEDED"


def test_invalid_playlist_id_is_rejected() -> None:
    assert youtube_playlist_id("https://youtube.com/playlist?list=%00") is None
    assert youtube_playlist_id("https://youtube.com/playlist?list=" + "x" * 1025) is None
