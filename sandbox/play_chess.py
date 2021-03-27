import os
import random

import chess
import time

from shared.messages import Sender
from sandbox.submission1.ai import make_move as player1_make_move
from sandbox.submission2.ai import make_move as player2_make_move


def make_result(result_type, reason):
    return {"type": "result", "result": result_type, "reason": reason}


def make_message(board: chess.Board, player_id: int, players):
    return {"board_state": board.fen(), "player_id": player_id, "players": [player.to_dict() for player in players]}


class Player:
    def __init__(self, i, t, fn):
        self.index = i
        self.time_remaining = t
        self.move_function = fn

    def deduct(self, t):
        self.time_remaining -= t

    def is_out_of_time(self):
        return self.time_remaining < 0

    def get_move(self, board):
        board_copy = chess.Board(board.fen(), chess960=board.chess960)

        start_time = time.time_ns()
        move = self.move_function(board_copy, self.time_remaining)
        end_time = time.time_ns()

        self.time_remaining -= (end_time - start_time) / 1e9

        return move

    def to_dict(self):
        return {"id": self.index, "time": self.time_remaining}


def main():
    sender = Sender()

    is_960 = os.getenv("chess960").lower().startswith("t")
    chess_clock_time = float(os.getenv("chess_clock"))

    if is_960:
        board = chess.Board.from_chess960_pos(random.randint(0, 959))
    else:
        board = chess.Board()

    players = [Player(i, chess_clock_time, fn) for i, fn in enumerate([player1_make_move, player2_make_move])]
    player_id = 0

    sender.send_result({"type": "initial_board", "chess960": is_960,
                        **make_message(board, player_id, players)})

    while not board.is_game_over():
        player = players[player_id]

        sender.send_result({"type": "ai_start", "player_id": player_id})
        move = player.get_move(board)
        sender.send_result({"type": "ai_end", "player_id": player_id})

        if player.is_out_of_time():
            sender.send_result({**make_result("loss", "timeout"),
                                **make_message(board, player_id, players)})
            return

        if isinstance(move, str):
            move = chess.Move.from_uci(move)

        if not isinstance(move, chess.Move) or move not in board.legal_moves:
            sender.send_result({"type": "invalid_move", "attempted_move": move.uci(),
                                **make_message(board, player_id, players)})
            return

        board.push(move)
        sender.send_result({"type": "move", "move": move.uci(),
                            **make_message(board, player_id, players)})

        player_id += 1
        player_id %= len(players)

    if board.is_checkmate():
        # Because we tick on the player id, the losing player is always the current player
        sender.send_result({**make_result("loss", "checkmate"),
                            **make_message(board, player_id, players)})
    elif board.is_stalemate():
        sender.send_result({**make_result("stalemate", "no-legal-moves"),
                            **make_message(board, player_id, players)})
    elif board.is_insufficient_material():
        sender.send_result({**make_result("stalemate", "insufficient-material"),
                            **make_message(board, player_id, players)})
    elif board.is_seventyfive_moves():
        sender.send_result({**make_result("stalemate", "seventyfive-moves"),
                            **make_message(board, player_id, players)})
    else:
        sender.send_result({**make_result("stalemate", "unknown"),
                            **make_message(board, player_id, players)})


if __name__ == "__main__":
    main()
