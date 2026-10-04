"""Shared normalization result records."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameRejection:
    game_id: str
    reason: str
    raw_row_count: int
