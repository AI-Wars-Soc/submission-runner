import abc
import logging
import random
import time
from typing import List

import chess
from cuwais.common import Outcome, Result
from cuwais.config import config_file

from runner.middleware import Middleware, ContainerConnectionFailedError, SubmissionNotActiveError
from runner.results import ParsedResult, SingleResult
from runner.sandbox import TimedContainer
from shared.exceptions import MissingFunctionError, ExceptionTraceback

_type_names = {
    "boolean": lambda b: str(b).lower().startswith("t"),
    "string": str,
    "float": float,
    "integer": int
}


class Gamemode:
    def __init__(self, name: str, players: List[str], options: dict):
        self._name = str(name)
        self._players = list(players)
        self._options = {"turn_time": 10, **dict(options)}

    @property
    def player_count(self):
        return len(self._players)

    @abc.abstractmethod
    def _setup(self, **options):
        """Gets the board that will be used by a game instance"""
        pass

    def _filter_board(self, board, player: int):
        """Used to hide parts of the board, or transform the board into a form used by the player given"""
        return board

    def _parse_move(self, move):
        """Optionally used to parse the returned move, eg if the AI can return a string or an object"""
        return move

    @abc.abstractmethod
    def _is_move_legal(self, board, move) -> bool:
        """Checks if a move can be made with a given board"""
        pass

    @abc.abstractmethod
    def _apply_move(self, board, move):
        """Applies the move to the board and returns the new board"""
        pass

    @abc.abstractmethod
    def _is_win(self, board, player):
        """Checks if the board is in a won position given the player just moved"""
        pass

    @abc.abstractmethod
    def _is_loss(self, board, player):
        """Checks if the board is in a lost position given the player just moved"""
        pass

    @abc.abstractmethod
    def _is_draw(self, board, player):
        """Checks if the board is in a drawn position given the player just moved"""
        pass

    def run(self, submission_hashes=None, options=None, turns=2 << 32) -> ParsedResult:
        if submission_hashes is None:
            submission_hashes = []
        if options is None:
            options = dict()
        logging.info("Request for gamemode " + self._name)

        # Create containers
        timeout = int(config_file.get("submission_runner.host_parser_timeout_seconds"))
        containers = []
        try:
            for submission_hash in submission_hashes:
                container = TimedContainer(timeout, submission_hash)
                containers.append(container)

            # Set up linking through middleware
            middleware = Middleware(containers)

            # Run
            outcomes, result, moves = self._run_loop(middleware, {**self._options, **options}, turns)

            # Gather
            middleware.complete_all()
            prints = []
            for i in range(self.player_count):
                prints.append(middleware.get_player_prints(i))

            results = [SingleResult(outcome, result == Result.ValidGame, name, result, prints)
                       for outcome, name, prints in zip(outcomes, self._players, prints)]

            parsed_result = ParsedResult(moves, results)
        except ContainerConnectionFailedError as e:
            each_res = [SingleResult(Outcome.Draw, False, "", Result.BrokenEntryPoint, "") for _ in submission_hashes]
            each_res[e.container_index].printed = "\n".join(e.prints)

            return ParsedResult([], each_res)
        finally:
            # Clean up
            for container in containers:
                container.stop()

        return parsed_result

    def _run_loop(self, middleware, options, turns):
        moves = []
        time_remaining = [options["turn_time"]] * self.player_count
        board = self._setup(**options)

        player_turn = 0

        latency = [sum([middleware.ping(i) for _ in range(5)]) / 5 for i in range(self.player_count)]
        latency = sum(latency) / len(latency)

        def make_win(winner):
            res = [Outcome.Loss] * self.player_count
            res[winner] = Outcome.Win
            return res

        def make_loss(loser):
            res = [Outcome.Win] * self.player_count
            res[loser] = Outcome.Loss
            return res

        for _ in range(turns):
            start_time = time.time_ns()
            try:
                move = middleware.call(player_turn, "make_move", board=self._filter_board(board, player_turn),
                                       time_remaining=time_remaining[player_turn])
            except SubmissionNotActiveError:
                return make_loss(player_turn), Result.ProcessKilled, moves
            end_time = time.time_ns()

            t = (end_time - start_time) / 1e9
            t -= latency
            time_remaining[player_turn] -= t

            if time_remaining[player_turn] <= 0:
                return make_loss(player_turn), Result.Timeout, moves

            if isinstance(move, MissingFunctionError):
                return make_loss(player_turn), Result.BrokenEntryPoint, moves

            if isinstance(move, ExceptionTraceback):
                return make_loss(player_turn), Result.Exception, moves

            move = self._parse_move(move)

            if not self._is_move_legal(board, move):
                return make_loss(player_turn), Result.IllegalMove, moves

            moves.append(move)
            board = self._apply_move(board, move)

            if self._is_win(board, player_turn):
                return make_win(player_turn), Result.ValidGame, moves

            if self._is_loss(board, player_turn):
                return make_loss(player_turn), Result.ValidGame, moves

            if self._is_draw(board, player_turn):
                return [Outcome.Draw] * self.player_count, Result.ValidGame, moves

            player_turn += 1
            player_turn %= self.player_count

    @staticmethod
    def get(gamemode_name):
        return {"chess": ChessGamemode()}.get(gamemode_name, None)


class ChessGamemode(Gamemode):
    def __init__(self):
        super(ChessGamemode, self).__init__(name="chess", players=["white", "black"], options={"chess_960": True})

    def _setup(self, chess_960, **kwargs):
        if chess_960:
            return chess.Board.from_chess960_pos(random.randint(0, 959))

        return chess.Board()

    def _is_win(self, board, move):
        return board.is_checkmate()

    def _is_draw(self, board, move):
        return board.is_stalemate() or board.is_insufficient_material() or board.is_seventyfive_moves()

    def _is_loss(self, board, move):
        return False

    def _parse_move(self, move):
        if isinstance(move, str):
            move = chess.Move.from_uci(move)
        return move

    def _is_move_legal(self, board, move):
        if move is None:
            return False
        if not isinstance(move, chess.Move):
            return False
        if move not in board.legal_moves:
            return False
        return True

    def _apply_move(self, board: chess.Board, move):
        board.push(move)
        return board
