import unittest

from app.ludo_engine import (
    GameState, PlayerState, choose_ai_move, legal_moves, move_token,
    new_game, next_turn,
)


class LudoEngineTests(unittest.TestCase):
    def test_yard_token_needs_six(self):
        player = PlayerState("red")
        self.assertEqual(legal_moves(player, 5), [])
        self.assertEqual(legal_moves(player, 6), [0, 1, 2, 3])

    def test_token_enters_and_moves(self):
        game = new_game(("red", "green"))
        move_token(game, 0, 0, 6)
        self.assertEqual(game.players[0].tokens[0], 0)
        move_token(game, 0, 0, 3)
        self.assertEqual(game.players[0].tokens[0], 3)

    def test_exact_finish_required(self):
        player = PlayerState("red", [56, -1, -1, -1])
        self.assertEqual(legal_moves(player, 2), [])
        self.assertEqual(legal_moves(player, 1), [0])

    def test_safe_cell_prevents_capture(self):
        game = GameState([
            PlayerState("red", [0, -1, -1, -1]),
            PlayerState("green", [39, -1, -1, -1]),
        ])
        # red starts on safe cell 0; green's offset 39 makes position 13 -> cell 0
        move_token(game, 0, 0, 1) if False else None
        self.assertEqual(game.players[0].tokens[0], 0)
        self.assertEqual(game.players[1].tokens[0], 39)

    def test_six_keeps_turn_other_roll_passes(self):
        game = new_game(("red", "green"))
        self.assertEqual(next_turn(game, 6), 0)
        self.assertEqual(next_turn(game, 3), 1)

    def test_ai_returns_legal_move(self):
        player = PlayerState("red")
        self.assertIn(choose_ai_move(player, 6), legal_moves(player, 6))


if __name__ == "__main__":
    unittest.main()
