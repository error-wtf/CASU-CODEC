"""Release builds must not erase unrelated cross-platform artifacts."""

from pathlib import Path


def test_debian_builder_preserves_dist_directory():
    script = (Path(__file__).parents[1] / "packaging" / "build_debs.sh").read_text(
        encoding="utf-8")
    assert 'rm -rf "$out"' not in script
    assert "stage_root=$(mktemp -d" in script
    assert "trap 'rm -rf \"$stage_root\"' EXIT" in script
