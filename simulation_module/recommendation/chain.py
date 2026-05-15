"""
recommendation/chain.py

Выявление цепочек голодания / блокировки (starvation/blocking chains).

Цепочка — причинно-следственная связь вида:
    «ОТК перегружен → буфер перед ОТК полон → сборка заблокирована →
     буфер корпусов пуст → фрезеровка простаивает»

Алгоритм идёт от «проблемной» позиции ВВЕРХ по топологии:
    1. Берём стартовый блок с признаком overload / blockage / overflow.
    2. Смотрим его upstream-буферы (upstream_map).
    3. Если буфер пуст (empty_ratio > 0.8) — ищем кто его питает
       (downstream_map: {buf_id: [block_id, ...]} — кто выходит в этот буфер).
    4. Если питающий блок сам заблокирован или простаивает — добавляем в цепочку.
    5. Повторяем от нового блока.
"""

from __future__ import annotations

from recommendation.diagnosis import Sign


_CHAIN_START_SIGNS = frozenset({
    "overload",
    "overload_and_blockage",
    "blockage",
    "overflow",
})

_EMPTY_RATIO_THRESHOLD = 0.80   # буфер считается «пустым»
_BLOCKED_RATIO_MIN     = 0.20   # питающий блок «заблокирован»
_IDLE_RATIO_MIN        = 0.40   # питающий блок «простаивает»


def find_chains(
    signs:          list[Sign],
    upstream_map:   dict[str, list[str]],
    downstream_map: dict[str, list[str]],
    block_metrics:  dict,
    buf_metrics:    dict,
) -> list[list[str]]:
    """
    Обходит граф от проблемных блоков вверх по топологии,
    собирая цепочки причинно-следственных связей.

    Параметры:
        signs          — все признаки из DiagnosisResult.all_signs
        upstream_map   — {block_id: [buf_id, ...]} буферы перед блоком
        downstream_map — {buf_id: [block_id, ...]} блоки, выходящие в буфер
        block_metrics  — dict[str, BlockMetrics] из SimulationResult
        buf_metrics    — dict[str, BufferMetrics] из SimulationResult

    Возвращает список цепочек; каждая цепочка — список block_id
    от «симптома» (хвост) к «первопричине» (голова).
    """
    # Начальные точки — блоки с ключевыми признаками
    start_blocks = [
        s.block_id for s in signs
        if s.sign_type in _CHAIN_START_SIGNS and s.block_id is not None
    ]

    chains: list[list[str]] = []

    for start in start_blocks:
        chain: list[str] = [start]
        current = start
        visited: set[str] = {start}

        while True:
            upstream_bufs = upstream_map.get(current, [])
            next_block: str | None = None

            for buf_id in upstream_bufs:
                bm = buf_metrics.get(buf_id)
                if bm is None:
                    continue
                if bm.empty_ratio <= _EMPTY_RATIO_THRESHOLD:
                    continue

                # Буфер пуст — ищем питающий блок
                feeders = downstream_map.get(buf_id, [])
                for feeder in feeders:
                    if feeder in visited:
                        continue
                    m = block_metrics.get(feeder)
                    if m is None:
                        continue
                    idle_ratio = 1.0 - m.utilization - m.blocked_ratio
                    if m.blocked_ratio > _BLOCKED_RATIO_MIN or idle_ratio > _IDLE_RATIO_MIN:
                        next_block = feeder
                        break
                if next_block is not None:
                    break

            if next_block is None:
                break

            chain.append(next_block)
            visited.add(next_block)
            current = next_block

        if len(chain) > 1:
            chains.append(chain)

    return chains
