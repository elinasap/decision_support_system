"""
validation/__init__.py

Публичный интерфейс пакета validation.

    from validation import validate, ValidationResult
"""

from .result    import ValidationResult
from .validator import validate, check_ports, check_edges, check_operations, check_control

__all__ = [
    "validate",
    "ValidationResult",
    "check_ports", "check_edges", "check_operations", "check_control",
]
