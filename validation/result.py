"""
validation/result.py

Результат валидации модели.

Разделяет ошибки (блокируют сохранение) и предупреждения
(не блокируют, но показываются оператору).
"""

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Модель валидна, если нет ни одной ошибки."""
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> None:
        """Объединяет результаты нескольких проверок в один."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "Схема корректна"
        lines = []
        for e in self.errors:
            lines.append(f"[ОШИБКА] {e}")
        for w in self.warnings:
            lines.append(f"[ПРЕДУПРЕЖДЕНИЕ] {w}")
        return "\n".join(lines)
