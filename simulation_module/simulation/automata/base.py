"""
Базовый класс конечного автомата.

Реализует расширенный конечный автомат (Extended Finite State Machine, EFSM):
классический автомат (S, Sigma, delta, s_0, F) + охранные условия на переходах.

Архитектура:
- Таблица переходов задается как словарь на уровне класса-наследника
  (гибридный подход: структура переходов деклатативная, действия - методы).
- Для каждой пары (state, event) может быть несколько вариантов перехода
  с разными охранными условиями. Выбирается первый, чье условие истинно.
- Действия при переходе вызываются как методы класса-наследника
  (on_<new_state>, on_exit_<old_state>), если определены.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Transition:
    """Описание одного перехода в таблице переходов автомата."""
    from_state: Any
    event: Any
    to_state: Any
    # Охранное условие. Принимает context (любые данные, нужные для проверки).
    # Если None - условие всегда истинно.
    guard: Optional[Callable[[Any], bool]] = None
    # Читаемое описание условия - для диагностики и логирования.
    guard_description: str = ""


class IllegalTransitionError(Exception):
    """Переход не определен в таблице автомата."""
    pass


class GuardFailedError(Exception):
    """Переход определен, но ни одно охранное условие не выполнено."""
    pass


class StateMachine:
    """
    Базовый класс конечного автомата.

    Классы-наследники должны определить:
    - INITIAL_STATE: начальное состояние
    - TRANSITIONS: список объектов Transition
    - TERMINAL_STATES: множество терминальных состояний (опционально)
    """

    INITIAL_STATE: Any = None
    TRANSITIONS: list[Transition] = []
    TERMINAL_STATES: set[Any] = set()

    def __init__(self, owner: Any = None):
        """
        owner - объект, которому принадлежит этот автомат
        (например, DetailInstance для автомата фазы).
        Используется в действиях при переходе и в охранных условиях.
        """
        if self.INITIAL_STATE is None:
            raise ValueError(
                f"{type(self).__name__}: INITIAL_STATE не задан"
            )
        self._state: Any = self.INITIAL_STATE
        self.owner = owner
        self._history: list[tuple[Any, Any, Any]] = []  # (from, event, to)

    @property
    def state(self) -> Any:
        """Текущее состояние автомата."""
        return self._state

    @property
    def history(self) -> list[tuple[Any, Any, Any]]:
        """История переходов: список кортежей (from_state, event, to_state)."""
        return list(self._history)

    def is_terminal(self) -> bool:
        """Находится ли автомат в терминальном состоянии."""
        return self._state in self.TERMINAL_STATES

    def can_handle(self, event: Any, context: Any = None) -> bool:
        """
        Проверка: можно ли обработать событие в текущем состоянии.
        Возвращает True, если есть хотя бы один подходящий переход
        с выполненным охранным условием.
        """
        return self._find_transition(event, context) is not None

    def fire(self, event: Any, context: Any = None) -> Any:
        """
        Обработать событие. Возвращает новое состояние.

        Исключения:
        - IllegalTransitionError: нет перехода (state, event) в таблице
        - GuardFailedError: переход есть, но охранные условия не выполнены
        """
        transition = self._find_transition(event, context)

        if transition is None:
            # Различаем два случая для лучшей диагностики.
            has_any = any(
                t.from_state == self._state and t.event == event
                for t in self.TRANSITIONS
            )
            if has_any:
                raise GuardFailedError(
                    f"{type(self).__name__}: переход "
                    f"({self._state!r}, {event!r}) существует, но ни одно "
                    f"охранное условие не выполнено"
                )
            else:
                raise IllegalTransitionError(
                    f"{type(self).__name__}: нет перехода для "
                    f"({self._state!r}, {event!r})"
                )

        old_state = self._state
        new_state = transition.to_state

        # Действия: сначала выход из старого состояния, потом вход в новое.
        self._invoke_action(f"on_exit_{self._safe_name(old_state)}", context)
        self._state = new_state
        self._invoke_action(f"on_enter_{self._safe_name(new_state)}", context)

        self._history.append((old_state, event, new_state))
        return new_state

    def reset(self) -> None:
        """Сбросить автомат в начальное состояние. Историю очистить."""
        self._state = self.INITIAL_STATE
        self._history.clear()

    # --- внутренняя кухня ---

    def _find_transition(self, event: Any, context: Any) -> Optional[Transition]:
        """
        Найти первый подходящий переход для текущего состояния и события,
        у которого выполнено охранное условие.
        """
        for t in self.TRANSITIONS:
            if t.from_state != self._state or t.event != event:
                continue
            if t.guard is None or t.guard(context):
                return t
        return None

    def _invoke_action(self, method_name: str, context: Any) -> None:
        """Вызвать метод-действие, если он определен в классе-наследнике."""
        method = getattr(self, method_name, None)
        if callable(method):
            method(context)

    @staticmethod
    def _safe_name(state: Any) -> str:
        """Безопасное имя состояния для имени метода действия."""
        if hasattr(state, "name"):  # для Enum
            return state.name.lower()
        return str(state).lower()
