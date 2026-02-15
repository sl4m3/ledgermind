from typing import Any, Dict, List, Optional

class ToolSchemaGenerator:
    """Генератор JSON Schema для инструментов памяти, соответствующих agent-memory-core."""

    VALID_PROVIDERS = {"openai", "anthropic", "gemini", "ollama"}

    @classmethod
    def _validate_provider(cls, provider: str) -> str:
        if provider not in cls.VALID_PROVIDERS:
            return "openai"
        return provider

    @classmethod
    def get_decision_tool_schema(cls, provider: str = "openai") -> Dict[str, Any]:
        """Возвращает схему инструмента record_decision."""
        provider = cls._validate_provider(provider)
        schema = {
            "name": "record_decision",
            "description": "Записывает стратегическое решение в долгосрочную семантическую память.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Краткий заголовок решения."
                    },
                    "target": {
                        "type": "string",
                        "description": "Объект или область, к которой относится решение (например, 'auth_system', 'ui_layout')."
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Обоснование: почему было принято именно это решение."
                    },
                    "consequences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список ожидаемых последствий или правил, вытекающих из решения."
                    }
                },
                "required": ["title", "target", "rationale"]
            }
        }

        if provider == "anthropic":
            return {
                "name": schema["name"],
                "description": schema["description"],
                "input_schema": schema["parameters"]
            }
        
        return schema

    @classmethod
    def get_supersede_tool_schema(cls, provider: str = "openai") -> Dict[str, Any]:
        """Возвращает схему инструмента supersede_decision."""
        provider = cls._validate_provider(provider)
        schema = {
            "name": "supersede_decision",
            "description": "Заменяет одно или несколько старых решений новым, обновляя семантическую память.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Заголовок нового решения."
                    },
                    "target": {
                        "type": "string",
                        "description": "Область применения (должна совпадать с таргетом старых решений)."
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Причина пересмотра и обоснование нового подхода."
                    },
                    "old_decision_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список ID устаревших решений (например, ['DEC-001'])."
                    },
                    "consequences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Новые последствия или правила."
                    }
                },
                "required": ["title", "target", "rationale", "old_decision_ids"]
            }
        }

        if provider == "anthropic":
            return {
                "name": schema["name"],
                "description": schema["description"],
                "input_schema": schema["parameters"]
            }
        
        return schema
