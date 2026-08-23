"""Tests for schema robustness against messy LLM output."""
from app.schemas.jd import MatchReport


def test_overall_score_coerces_float():
    report = MatchReport(
        overall_score=87.5,
        matched_keywords=["Python"],
        missing_keywords=["Go"],
        skill_gaps=["needs Go experience"],
        suggestions=["add a Go project"],
    )
    assert report.overall_score == 88  # rounded to int


def test_overall_score_coerces_string():
    report = MatchReport(
        overall_score="92",
        matched_keywords=[],
        missing_keywords=[],
        skill_gaps=[],
        suggestions=[],
    )
    assert report.overall_score == 92


def test_overall_score_clamps_invalid_to_zero():
    report = MatchReport(
        overall_score="not-a-number",
        matched_keywords=[],
        missing_keywords=[],
        skill_gaps=[],
        suggestions=[],
    )
    assert report.overall_score == 0
