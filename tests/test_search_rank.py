from __future__ import annotations

from agent_code_analyzer.search_rank import build_embedding_text, normalize_identifier, score_search_candidate
from agent_code_analyzer.search_scoring import SearchScoringStrategy


def test_score_search_candidate_prefers_exact_token_hits_over_loose_matches() -> None:
    exact = score_search_candidate(
        "mysql real escape string",
        searchable_text="file path: src/db.php\nmysql real escape string\ndef mysql_real_escape_string(): pass",
        file_path="src/db.php",
        symbol_name="mysql_real_escape_string",
        content_text="def mysql_real_escape_string(): pass",
    )
    loose = score_search_candidate(
        "mysql real escape string",
        searchable_text="file path: src/helpers.php\nreal string helper\ndef real_string_helper(): pass",
        file_path="src/helpers.php",
        symbol_name="real_string_helper",
        content_text="def real_string_helper(): pass",
    )

    assert exact > loose


def test_score_search_candidate_penalizes_generated_and_minified_files() -> None:
    normal = score_search_candidate(
        "hello world",
        searchable_text="file path: src/hello.py\nhello world\ndef hello_world(): pass",
        file_path="src/hello.py",
        symbol_name="hello_world",
        content_text="def hello_world(): pass",
    )
    noisy = score_search_candidate(
        "hello world",
        searchable_text="file path: vendor/hello.min.js\nhello world\nfunction helloWorld(){return 1}",
        file_path="vendor/hello.min.js",
        symbol_name="helloWorld",
        content_text="function helloWorld(){return 1}",
    )

    assert normal > noisy


def test_normalize_identifier_splits_acronyms_and_digits() -> None:
    assert normalize_identifier("XMLHttpRequest2") == ["xml", "http", "request", "2"]


def test_build_embedding_text_keeps_structural_hints_together() -> None:
    text = build_embedding_text(
        file_path="src/controllers/kingdom.php",
        symbol_name="KingdomController",
        signature="public function importMisc($number = 5)",
        skeleton="class KingdomController",
        source_text="function importMisc($number = 5) { return $number; }",
    )

    assert "file path: src/controllers/kingdom.php" in text
    assert "symbol: KingdomController" in text
    assert "signature: public function importMisc($number = 5)" in text
    assert "skeleton: class KingdomController" in text


def test_search_scoring_strategy_breakdown_matches_wrapper() -> None:
    strategy = SearchScoringStrategy()

    breakdown = strategy.breakdown(
        query="hello world",
        base_score=0.42,
        searchable_text="file path: src/hello.py\nhello world\ndef hello_world(): pass",
        file_path="src/hello.py",
        symbol_name="hello_world",
        unit_type="file",
        content_text="def hello_world(): pass",
    )

    assert breakdown.total == strategy.score(
        "hello world",
        base_score=0.42,
        searchable_text="file path: src/hello.py\nhello world\ndef hello_world(): pass",
        file_path="src/hello.py",
        symbol_name="hello_world",
        unit_type="file",
        content_text="def hello_world(): pass",
    )
    assert breakdown.total == score_search_candidate(
        "hello world",
        base_score=0.42,
        searchable_text="file path: src/hello.py\nhello world\ndef hello_world(): pass",
        file_path="src/hello.py",
        symbol_name="hello_world",
        unit_type="file",
        content_text="def hello_world(): pass",
    )
    assert breakdown.generated_multiplier == 1.0

    noisy = strategy.breakdown(
        query="hello world",
        searchable_text="file path: vendor/hello.min.js\nhello world\nfunction helloWorld(){return 1}",
        file_path="vendor/hello.min.js",
        symbol_name="helloWorld",
        content_text="function helloWorld(){return 1}",
    )

    assert noisy.generated_multiplier == 0.75
    assert noisy.total < breakdown.total
