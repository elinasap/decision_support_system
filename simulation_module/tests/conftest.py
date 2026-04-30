"""
Настройка pytest для доступа к модулям simulation из тестов.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в sys.path, чтобы работало
# from simulation.automata.phase import ...
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
