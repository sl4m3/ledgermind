"""Provider-independent native decision grammar; no models, keys or inference.

v1 remains a saved-task compatibility grammar. v2 requires explicit subject
addresses because question identifiers are not part of model inference.
"""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

def validate_decision_request(request: Mapping[str, Any], *, enforce_transport_limits: bool = False) -> None:
    if set(request) != {"schema_version", "state", "questions"} or request["schema_version"] not in (1, 2):
        raise ValueError("invalid closed decision request")
    questions = request["questions"]
    if not isinstance(request["state"], (str, dict, list)) or not isinstance(questions, dict) or not questions:
        raise ValueError("missing decision state/questions")
    for ref, q in questions.items():
        if (
            not isinstance(ref, str)
            or not ref.strip()
            or not isinstance(q, dict)
            or not {"type", "instructions"} <= set(q) <= {"type", "instructions", "criteria"}
        ):
            raise ValueError("invalid decision question")
        def described(value):
            return isinstance(value, (str, dict, list)) and bool(value.strip() if isinstance(value, str) else value)
        if not described(q["instructions"]):
            raise ValueError("invalid decision instructions")
        criteria = q.get("criteria")
        if q["type"] == "choice":
            valid = isinstance(criteria, dict) and 1 <= len(criteria) and (len(criteria) <= 255 or request["schema_version"] == 1 and not enforce_transport_limits) and all(isinstance(k, str) and k.strip() and (v is None or described(v)) for k, v in criteria.items())
        elif q["type"] == "noul":
            valid = criteria is None or isinstance(criteria, dict) and set(criteria) <= {"true", "false"} and all(described(v) for v in criteria.values())
        elif q["type"] == "score":
            valid = isinstance(criteria, list) and 2 <= len(criteria) <= 10 and all(described(v) for v in criteria)
        else:
            valid = False
        if not valid:
            raise ValueError("invalid closed criteria")
        if request["schema_version"] == 2:
            ins = q["instructions"]
            if not isinstance(ins, dict) or not isinstance(ins.get("question"), str) or not ins["question"].strip() or not isinstance(ins.get("subjects"), list) or not ins["subjects"]:
                raise ValueError("native questions require explicit subject addresses, not only question IDs")
            for pointer in ins["subjects"]:
                if not isinstance(pointer, str) or not pointer.startswith("/"):
                    raise ValueError("invalid native subject address")
                value = request["state"]
                try:
                    for part in pointer[1:].split("/"):
                        part = part.replace("~1", "/").replace("~0", "~")
                        if isinstance(value,list):
                            # RFC6901 / Rust Value.pointer indices, not Python
                            # negative indexing or permissive int('00').
                            if not part.isascii() or not part.isdecimal() or (len(part)>1 and part.startswith('0')):
                                raise ValueError('invalid array subject address')
                            value=value[int(part)]
                        else:
                            value=value[part]
                except (KeyError, ValueError, TypeError, IndexError) as exc:
                    raise ValueError("unknown native subject address") from exc
