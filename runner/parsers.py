import json
import random
import time
from typing import List, Callable

import chess
from cuwais.common import Outcome, Result

from runner.middleware import Middleware
from shared.messages import Encoder


class SingleResult(dict):
    def __init__(self, outcome: Outcome, healthy: bool, player_id: str, result: Result, printed: str):
        self.outcome = outcome
        self.healthy = healthy
        self.player_id = player_id
        self.result = result
        printed = printed[:1000]
        self.printed = printed

        super().__init__(outcome=outcome.value, healthy=healthy, player_id=player_id, result_code=str(result.value),
                         printed=printed)


class ParsedResult(dict):
    def __init__(self, moves: list, submission_results: List[SingleResult]):
        self.recording = json.dumps(moves, cls=Encoder)
        self.submission_results = submission_results

        super().__init__(recording=moves, submission_results=submission_results)

    @property
    def outcomes(self):
        return [r.outcome for r in self.submission_results]

    @outcomes.setter
    def outcomes(self, values):
        for value, result in zip(values, self.submission_results):
            result.outcome = value

    @property
    def healths(self):
        return [r.healthy for r in self.submission_results]

    @healths.setter
    def healths(self, values):
        for value, result in zip(values, self.submission_results):
            result.healthy = value

    @property
    def player_ids(self):
        return [r.player_id for r in self.submission_results]

    @player_ids.setter
    def player_ids(self, values):
        for value, result in zip(values, self.submission_results):
            result.player_id = value


def default_parser(middleware: Middleware) -> ParsedResult:
    messages = middleware.complete_all()
    prints = []
    for i in range(middleware.player_count):
        prints.append(middleware.get_player_prints(i))
    return ParsedResult(messages, [SingleResult(Outcome.Draw, True, "unknown", Result.ValidGame, pp) for pp in prints])


def info_parser(middleware: Middleware) -> ParsedResult:
    middleware.send_data(0, array=[0, "test", 1, "2", None], kwarg1="hello", kwarg2=["list", "of", "things"])
    messages = middleware.complete_all()
    prints = []
    for i in range(middleware.player_count):
        prints.append(middleware.get_player_prints(i))
    return ParsedResult(messages, [SingleResult(Outcome.Draw, True, "debug", Result.ValidGame, pp) for pp in prints])


def play_chess(middleware: Middleware):
    latency = [sum([middleware.ping(i) for _ in range(10)]) / 10 for i in range(2)]
    print(f"latencies: {latency}", flush=True)

    board = chess.Board.from_chess960_pos(random.randint(0, 959))
    player_turn = 0
    time_remaining = [10, 10]
    moves = []

    def make_loss(p):
        return Outcome.Loss if p == 0 else Outcome.Win, Outcome.Loss if p == 1 else Outcome.Win

    while not board.is_game_over():
        start_time = time.time_ns()
        move = middleware.call(player_turn, "make_move", board=board, time_remaining=time_remaining[player_turn])
        end_time = time.time_ns()

        t = (end_time - start_time) / 1e9
        t -= latency[player_turn]
        time_remaining[player_turn] -= t

        if time_remaining[player_turn] <= 0:
            return make_loss(player_turn), Result.Timeout, moves

        if isinstance(move, str):
            move = chess.Move.from_uci(move)

        if not isinstance(move, chess.Move) or move not in board.legal_moves:
            return make_loss(player_turn), Result.IllegalMove, moves

        moves.append(move)
        board.push(move)

        player_turn = 1 - player_turn

    if board.is_checkmate():
        # Because we increment the player id, the losing player is always the current player
        return make_loss(player_turn), Result.ValidGame, moves
    elif board.is_stalemate() or board.is_insufficient_material() or board.is_seventyfive_moves():
        return (Outcome.Draw, Outcome.Draw), Result.ValidGame, moves
    return (Outcome.Draw, Outcome.Draw), Result.UnknownResultType, moves


def chess_parser(middleware: Middleware) -> ParsedResult:
    (outcome1, outcome2), result, moves = play_chess(middleware)

    middleware.complete_all()
    prints = []
    for i in range(middleware.player_count):
        prints.append(middleware.get_player_prints(i))

    results = [SingleResult(outcome1, result == Result.ValidGame, "white", result, prints[0]),
               SingleResult(outcome2, result == Result.ValidGame, "black", result, prints[1])]
    return ParsedResult(moves, results)


def get(parser) -> Callable[[Middleware], ParsedResult]:
    if parser == "info":
        return info_parser
    if parser == "chess":
        return chess_parser

    return default_parser
