"""
Tests for ResponseParser robustness with malformed LLM JSON output.
"""
import pytest
from ledgermind.core.reasoning.enrichment.parser import ResponseParser


class TestResponseParserRobustness:
    """Test JSON parsing with various malformed inputs."""

    def test_valid_json(self):
        """Should parse valid JSON."""
        text = '{"title": "Test", "rationale": "Because"}'
        result = ResponseParser.parse_json(text)
        assert result is not None
        assert result["title"] == "Test"

    def test_json_with_code_block(self):
        """Should extract JSON from markdown code block."""
        text = '''Here is the result:
```json
{"title": "Test", "rationale": "Because"}
```
Some more text.'''
        result = ResponseParser.parse_json(text)
        assert result is not None
        assert result["title"] == "Test"

    def test_json_with_escape_sequences(self):
        """Should handle escape sequences in rationale."""
        # LLM sometimes generates invalid escapes like \m instead of \\m
        text = '{"title": "Test", "rationale": "Path is C:\\my\\folder"}'
        result = ResponseParser.parse_json(text)
        assert result is not None
        assert "Path" in result["rationale"]

    def test_json_with_unescaped_quotes_in_string(self):
        """Should handle unescaped quotes inside strings."""
        # This is the common error: "text "quoted" more" instead of "text \"quoted\" more"
        text = '{"title": "Test", "rationale": "This is "quoted" text"}'
        result = ResponseParser.parse_json(text)
        # May or may not succeed depending on the heuristic
        # At minimum, should not crash
        assert result is None or "title" in result

    def test_json_with_control_characters(self):
        """Should strip control characters."""
        # Control characters like \x00-\x1F break json.loads
        text = '{"title": "Test\x00", "rationale": "Because\x1F"}'
        result = ResponseParser.parse_json(text)
        assert result is not None
        assert result["title"] == "Test"

    def test_json_with_nested_lists(self):
        """Should handle nested structures."""
        text = '''{
            "title": "Test",
            "keywords": ["one", ["two", "three"], "four"],
            "strengths": ["first", "second"]
        }'''
        result = ResponseParser.parse_json(text)
        assert result is not None
        assert len(result["keywords"]) >= 3

    def test_empty_input(self):
        """Should return None for empty input."""
        assert ResponseParser.parse_json("") is None
        assert ResponseParser.parse_json(None) is None

    def test_no_json_object(self):
        """Should return None when no JSON object found."""
        text = "This is just plain text without any JSON"
        result = ResponseParser.parse_json(text)
        assert result is None

    def test_truncated_json(self):
        """Should handle truncated JSON gracefully."""
        text = '{"title": "Test", "rationale": "Incomplete'
        result = ResponseParser.parse_json(text)
        # May fail, but should not crash
        assert result is None or isinstance(result, dict)

    def test_real_llm_malformed_response(self):
        """Test with a realistic malformed LLM response."""
        # Simulating actual LLM output with various issues
        text = '''Based on my analysis, here is the consolidated result:

```json
{
    "title": "Стандартизация Процессов",
    "target": "docs",
    "rationale": "Проект занимается формализацией процессов \\nдля улучшения документации",
    "keywords": ["Documentation", "Process Optimization", "Стандарты"],
    "strengths": [
        "Повышение качества кода",
        "Улучшение поддерживаемости"
    ],
    "objections": [
        "Требуется время на внедрение",
        "Риск бюрократизации"
    ]
}
```

This consolidation captures the key themes from all documents.'''
        
        result = ResponseParser.parse_json(text)
        assert result is not None
        assert result["title"] == "Стандартизация Процессов"
        assert "Documentation" in result["keywords"]


class TestCleanKeywords:
    """Test keyword cleaning functionality."""

    def test_simple_list(self):
        """Should clean simple keyword list."""
        raw = ["one", "two", "three"]
        result = ResponseParser.clean_keywords(raw)
        assert set(result) == {"one", "two", "three"}

    def test_nested_lists(self):
        """Should flatten nested lists."""
        raw = ["one", ["two", "three"], "four"]
        result = ResponseParser.clean_keywords(raw)
        assert set(result) == {"one", "two", "three", "four"}

    def test_keywords_with_parentheses(self):
        """Should split keywords with parenthetical explanations."""
        raw = ["Documentation (Process)", "Standards"]
        result = ResponseParser.clean_keywords(raw)
        assert "Documentation" in result
        assert "Process" in result
        assert "Standards" in result

    def test_empty_input(self):
        """Should handle empty input."""
        assert ResponseParser.clean_keywords([]) == []
        assert ResponseParser.clean_keywords({}) == []

    def test_non_list_input(self):
        """Should convert non-list to list."""
        result = ResponseParser.clean_keywords("single")
        assert result == ["single"]
