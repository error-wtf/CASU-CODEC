import ast

from tools.release_gate_guard import _is_source_string_assert


def _assert_expression(source: str) -> ast.expr:
    statement = ast.parse(source).body[0]
    assert isinstance(statement, ast.Assert)
    return statement.test


def test_guard_detects_source_text_pseudo_acceptance_assertions():
    assert _is_source_string_assert(_assert_expression(
        'assert "def cycle_video_track" in source'))
    assert _is_source_string_assert(_assert_expression(
        'assert "class Backend" not in player'))


def test_guard_accepts_runtime_player_status_membership_assertion():
    assert not _is_source_string_assert(_assert_expression(
        'assert "sink underrun" in player.status.value'))


def test_guard_checks_boolean_members_without_confusing_unrelated_values():
    assert _is_source_string_assert(_assert_expression(
        'assert ready and "def feature" in source'))
    assert not _is_source_string_assert(_assert_expression(
        'assert ready and "playing" in controller.player.status.value'))
