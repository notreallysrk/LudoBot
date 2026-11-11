"""Pure Ludo rules engine for Ludo Arena.

Positions: -1 = yard, 0..51 = shared track, 52..56 = home lane,
57 = finished. Each player has a start offset on the shared 52-cell ring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

TRACK_LENGTH = 52
HOME_LANE_LENGTH = 6  # entry cell plus five lane cells; 57 is finished
TOKENS_PER_PLAYER = 4
PLAYERS = ("red", "green", "yellow", "blue")
START_OFFSETS = {"red": 0, "green": 13, "yellow": 26, "blue": 39}
SAFE_CELLS = frozenset({0, 8, 13, 21, 26, 34, 39, 47})


@dataclass
class PlayerState:
    color: str
    tokens: list[int] = field(default_factory=lambda: [-1] * TOKENS_PER_PLAYER)

    def __post_init__(self):
        if self.color not in PLAYERS:
            raise ValueError(f"Unknown player color: {self.color}")
        if len(self.tokens) != TOKENS_PER_PLAYER:
            raise ValueError("Each player must have exactly four tokens")
        if any(type(p) is not int or p < -1 or p > 57 for p in self.tokens):
            raise ValueError("Token positions must be between -1 and 57")


@dataclass
class GameState:
    players: list[PlayerState]
    current_player: int = 0
    last_roll: int | None = None
    status: str = "active"

    def __post_init__(self):
        if not 2 <= len(self.players) <= 4:
            raise ValueError("A Ludo game needs 2 to 4 players")
        if len({p.color for p in self.players}) != len(self.players):
            raise ValueError("Player colors must be unique")
        if not 0 <= self.current_player < len(self.players):
            raise ValueError("Invalid current player index")


def global_cell(color: str, position: int) -> int | None:
    """Return shared-ring cell for an active track token, else None."""
    if color not in START_OFFSETS:
        raise ValueError(f"Unknown player color: {color}")
    if not 0 <= position < TRACK_LENGTH:
        return None
    return (START_OFFSETS[color] + position) % TRACK_LENGTH


def legal_moves(player: PlayerState, dice: int) -> list[int]:
    """Token indexes movable for this dice result."""
    if type(dice) is not int or not 1 <= dice <= 6:
        raise ValueError("Dice value must be an integer from 1 to 6")
    moves = []
    for index, position in enumerate(player.tokens):
        if position == 57:
            continue
        if position == -1:
            if dice == 6:
                moves.append(index)
        elif position + dice <= 57:
            moves.append(index)
    return moves


def move_token(state: GameState, player_index: int, token_index: int, dice: int) -> list[tuple[str, int]]:
    """Apply one legal move and return captured (color, token_index) pairs."""
    if state.status != "active":
        raise ValueError("Game is not active")
    if player_index != state.current_player:
        raise ValueError("It is not this player's turn")
    if type(token_index) is not int or not 0 <= token_index < TOKENS_PER_PLAYER:
        raise ValueError("Invalid token index")
    player = state.players[player_index]
    if token_index not in legal_moves(player, dice):
        raise ValueError("Illegal token move")

    old = player.tokens[token_index]
    new = 0 if old == -1 else old + dice
    player.tokens[token_index] = new
    captured: list[tuple[str, int]] = []

    # Captures happen only on the shared track, never in home lanes.
    cell = global_cell(player.color, new)
    if cell is not None and cell not in SAFE_CELLS:
        for opponent in state.players:
            if opponent is player:
                continue
            for idx, pos in enumerate(opponent.tokens):
                if global_cell(opponent.color, pos) == cell:
                    opponent.tokens[idx] = -1
                    captured.append((opponent.color, idx))

    if all(pos == 57 for pos in player.tokens):
        state.status = "finished"
    state.last_roll = dice
    return captured


def next_turn(state: GameState, dice: int) -> int:
    """Advance turn unless a six was rolled or the game is over."""
    if state.status != "active":
        return state.current_player
    if dice != 6:
        state.current_player = (state.current_player + 1) % len(state.players)
    state.last_roll = None
    return state.current_player


def choose_ai_move(player: PlayerState, dice: int) -> int | None:
    """Deterministic basic AI: finish, capture, leave yard, then advance."""
    options = legal_moves(player, dice)
    if not options:
        return None
    # Prefer a token closest to finishing; yard tokens are selected before
    # ordinary movement when no token is already one move from home.
    return max(options, key=lambda i: (player.tokens[i] == 56 and dice == 1,
                                       player.tokens[i] == -1,
                                       player.tokens[i], -i))


def new_game(colors: Iterable[str] = ("red", "green", "yellow", "blue")) -> GameState:
    return GameState(players=[PlayerState(color=c) for c in colors])
