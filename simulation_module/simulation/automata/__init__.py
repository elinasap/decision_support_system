"""
Конечные автоматы модели производственного процесса.

Четыре автомата, работающие параллельно и синхронизирующиеся через события:
- PhaseAutomaton    - фаза детали (waiting/processing/done)
- BlockAutomaton    - состояние блока техоперации (idle/busy/blocked)
- BufferAutomaton   - состояние хранилища (empty/has_items/full)
- QualityAutomaton  - качество детали (normal/defective/repaired/accepted/scrapped)
"""

from simulation.automata.base import (
    StateMachine,
    Transition,
    IllegalTransitionError,
    GuardFailedError,
)

__all__ = [
    "StateMachine",
    "Transition",
    "IllegalTransitionError",
    "GuardFailedError",
]
