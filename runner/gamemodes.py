import abc
import random
import time
from concurrent.futures.thread import ThreadPoolExecutor
from typing import List, Tuple, Union

import chess
from cuwais.common import Outcome, Result
from cuwais.config import config_file

from runner.logger import logger
from runner.middleware import Middleware, ConnectionNotActiveError, PlayerConnection, ConnectionTimedOutError
from runner.results import ParsedResult, SingleResult
from runner.sandbox import TimedContainer
from shared.exceptions import MissingFunctionError, ExceptionTraceback
from shared.messages import HandshakeFailedError, Connection

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

    @abc.abstractmethod
    def _encode_move(self, move, player) -> str:
        """Converts a move to a string form for storing or transmitting"""
        pass

    @abc.abstractmethod
    def _encode_board(self, board) -> str:
        """Converts a board to a string form for storing or transmitting"""
        pass

    def run(self, submission_hashes=None, options=None, turns=2 << 32) -> ParsedResult:
        if submission_hashes is None:
            submission_hashes = []
        submission_hashes = list(submission_hashes)
        if options is None:
            options = dict()
        logger.debug(f"Request for gamemode {self._name}")

        # Create containers
        timeout = int(config_file.get("submission_runner.host_parser_timeout_seconds"))

        def connect(submission_hash) -> Union[Tuple[None, ParsedResult], Tuple[TimedContainer, PlayerConnection]]:
            new_container = TimedContainer(timeout, submission_hash)
            try:
                new_connection = PlayerConnection(new_container.run())
            except HandshakeFailedError as e:
                each_res = [SingleResult(Outcome.Draw, False, "", Result.UnknownResultType, "")
                            for _ in range(self.player_count)]
                for i_hash, h in enumerate(submission_hashes):
                    if h == submission_hash:
                        each_res[i_hash].printed = "\n".join(e.prints)

                logger.error("Failed to handshake with container!")
                return None, ParsedResult("", [], each_res)
            new_connection.ping()
            return new_container, new_connection

        containers = []
        try:
            logger.debug("Creating all required timed containers: ")

            # Create all required AIs
            executor = ThreadPoolExecutor(max_workers=len(submission_hashes))
            connections = []
            for container, connection in executor.map(connect, submission_hashes):
                if container is None:
                    return connection
                containers.append(container)
                connections.append(connection)

            # Set up linking through middleware
            logger.debug("Attaching middleware: ")
            middleware = Middleware(connections)

            # Run
            logger.debug("Running...")
            outcomes, result, moves, initial_board = self._run_loop(middleware, {**self._options, **options}, turns)

            # Gather
            logger.debug("Completed game, shutting down containers...")
            middleware.complete_all()
            prints = []
            for i in range(self.player_count):
                prints.append(middleware.get_player_prints(i))

            results = [SingleResult(outcome, result == Result.ValidGame, name, result, prints)
                       for outcome, name, prints in zip(outcomes, self._players, prints)]

            parsed_result = ParsedResult(initial_board, moves, results)
        finally:
            # Clean up
            for container in containers:
                container.stop()

        logger.debug(f"Done running gamemode {self._name}!")
        return parsed_result

    def _run_loop(self, middleware, options, turns) -> Tuple[List[Outcome], Result, List[str], str]:
        moves = []
        time_remaining = [options["turn_time"]] * self.player_count
        board = self._setup(**options)
        initial_encoded_board = self._encode_board(board)

        player_turn = 0

        try:
            # Calculate latencies
            latency = [sum([middleware.ping(i) for _ in range(5)]) / 5 for i in range(self.player_count)]
        except (ConnectionNotActiveError, ConnectionTimedOutError):
            # Shouldn't crash, it's our fault if it does :(
            return [Outcome.Draw] * self.player_count, Result.UnknownResultType, moves, initial_encoded_board
        latency = sum(latency) / len(latency)
        logger.debug(f"Latency for container communication: {latency}s")

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
            except ConnectionNotActiveError:
                return make_loss(player_turn), Result.ProcessKilled, moves, initial_encoded_board
            except ConnectionTimedOutError:
                return make_loss(player_turn), Result.Timeout, moves, initial_encoded_board
            end_time = time.time_ns()

            t = (end_time - start_time) / 1e9
            t -= latency
            time_remaining[player_turn] -= t

            if time_remaining[player_turn] <= 0:
                return make_loss(player_turn), Result.Timeout, moves, initial_encoded_board

            if isinstance(move, MissingFunctionError):
                return make_loss(player_turn), Result.BrokenEntryPoint, moves, initial_encoded_board

            if isinstance(move, ExceptionTraceback):
                return make_loss(player_turn), Result.Exception, moves, initial_encoded_board

            move = self._parse_move(move)

            if not self._is_move_legal(board, move):
                return make_loss(player_turn), Result.IllegalMove, moves, initial_encoded_board

            moves.append(self._encode_move(move, player_turn))
            board = self._apply_move(board, move)

            if self._is_win(board, player_turn):
                return make_win(player_turn), Result.ValidGame, moves, initial_encoded_board

            if self._is_loss(board, player_turn):
                return make_loss(player_turn), Result.ValidGame, moves, initial_encoded_board

            if self._is_draw(board, player_turn):
                return [Outcome.Draw] * self.player_count, Result.ValidGame, moves, initial_encoded_board

            player_turn += 1
            player_turn %= self.player_count

        return [Outcome.Draw] * self.player_count, Result.GameUnfinished, moves, initial_encoded_board

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

    def _apply_move(self, board: chess.Board, move: chess.Move):
        board.push(move)
        return board

    def _encode_move(self, move: chess.Move, player: int) -> str:
        return move.uci()

    def _encode_board(self, board: chess.Board) -> str:
        return board.fen()
