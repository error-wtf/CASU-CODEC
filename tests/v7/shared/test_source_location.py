from pathlib import PureWindowsPath

import pytest

from v7.shared.source_location import (
    SourceLocationError,
    SourceType,
    classify_source,
    redact_url,
)


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("/music/a.mp3", SourceType.LOCAL_PATH),
        ("relative/music.mp3", SourceType.LOCAL_PATH),
        (r"C:\Music\a.mp3", SourceType.LOCAL_PATH),
        ("file:///music/a%20b.mp3", SourceType.FILE_URI),
        ("content://media/external/audio/42", SourceType.CONTENT_URI),
        ("https://example.com/live", SourceType.NETWORK_URI),
        ("youtube:video:abc", SourceType.PROVIDER_LOCATOR),
    ],
)
def test_source_classification_is_explicit(raw: str, kind: SourceType) -> None:
    assert classify_source(raw).source_type is kind


def test_file_uri_decodes_exactly_once() -> None:
    value = classify_source("file:///music/100%2520hits.mp3")
    assert value.local_path == "/music/100%20hits.mp3"


def test_windows_path_is_not_misclassified_as_uri() -> None:
    value = classify_source(r"C:\Music\track.mp3")
    assert value.source_type is SourceType.LOCAL_PATH
    assert PureWindowsPath(value.canonical).drive == "C:"


@pytest.mark.parametrize(
    "raw",
    ["", "\0bad", "file://remote-host/music.mp3", "javascript:alert(1)"],
)
def test_invalid_or_unsupported_sources_fail_closed(raw: str) -> None:
    with pytest.raises(SourceLocationError):
        classify_source(raw)


def test_network_credentials_are_rejected_and_redacted() -> None:
    raw = "https://user:password@example.com/media?token=secret&quality=best"
    with pytest.raises(SourceLocationError) as raised:
        classify_source(raw)
    assert "password" not in str(raised.value)
    assert "secret" not in str(raised.value)
    safe = redact_url(raw)
    assert "user:password" not in safe
    assert "secret" not in safe
    assert "quality=best" in safe


def test_http_canonicalization_removes_fragment_and_normalizes_host() -> None:
    value = classify_source("HTTPS://EXAMPLE.COM:443/a/../b?q=1#fragment")
    assert value.original == "HTTPS://EXAMPLE.COM:443/a/../b?q=1#fragment"
    assert value.canonical == "https://example.com:443/a/../b?q=1"


def test_content_uri_remains_a_uri_not_a_filename() -> None:
    value = classify_source("content://media/external/audio/media/7")
    assert value.source_type is SourceType.CONTENT_URI
    assert value.local_path is None
