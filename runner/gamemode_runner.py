import time
from concurrent.futures.thread import ThreadPoolExecutor
from typing import List, Tuple, Union

from cuwais.common import Outcome, Result
from cuwais.gamemodes import Gamemode

from runner.logger import logger
from runner.middleware import Middleware
from runner.results import ParsedResult, SingleResult
from runner.sandbox import TimedContainer
from shared.exceptions import MissingFunctionError, ExceptionTraceback
from shared.message_connection import HandshakeFailedError
from shared.connection import Connection, ConnectionNotActiveError, ConnectionTimedOutError


def run(gamemode: Gamemode, submission_hashes=None, options=None, turns=2 << 32, connections=None) -> ParsedResult:
    if submission_hashes is None:
        submission_hashes = []
    submission_hashes = list(submission_hashes)
    if options is None:
        options = dict()
    options = {**gamemode.options, **options}
    if connections is None:
        connections = []
    connections: List[Connection]

    turns = int(turns)

    logger.debug(f"Request for gamemode {gamemode.name}")

    if len(connections) + len(submission_hashes) != gamemode.player_count:
        raise RuntimeError("Invalid number of players total")

    # Create containers
    timeout = (gamemode.player_count + 1) * int(options.get("turn_time", 10))

    def connect(submission_hash) -> Union[Tuple[None, ParsedResult], Tuple[TimedContainer, Connection]]:
        new_container = TimedContainer(timeout, submission_hash)
        try:
            new_connection = new_container.run()
        except HandshakeFailedError as e:
            each_res = [SingleResult(Outcome.Draw, False, "", Result.UnknownResultType, "")
                        for _ in range(gamemode.player_count)]
            for i_hash, h in enumerate(submission_hashes):
                if h == submission_hash:
                    each_res[i_hash].printed = "\n".join(e.prints)

            logger.error(f"Failed to handshake with container! {e.prints}")
            return None, ParsedResult("", [], each_res)
        new_connection.ping()
        return new_container, new_connection

    containers = []
    try:
        logger.debug("Creating all required timed containers: ")

        # Create all required AIs
        executor = ThreadPoolExecutor(max_workers=len(submission_hashes))
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
        outcomes, result, moves, initial_board = _run_loop(gamemode, middleware, options, turns)

        # Gather
        logger.debug("Completed game, shutting down containers...")
        middleware.complete_all()
        prints = []
        for i in range(gamemode.player_count):
            prints.append(middleware.get_player_prints(i))

        results = [SingleResult(outcome, result == Result.ValidGame, name, result, prints)
                   for outcome, name, prints in zip(outcomes, gamemode.players, prints)]

        parsed_result = ParsedResult(initial_board, moves, results)
    finally:
        # Clean up
        for container in containers:
            container.stop()

    logger.debug(f"Done running gamemode {gamemode.name}!")
    return parsed_result


def _run_loop(gamemode: Gamemode, middleware, options, turns) -> Tuple[List[Outcome], Result, List[str], str]:
    moves = []
    time_remaining = [int(options["turn_time"])] * gamemode.player_count
    board = gamemode.setup(**options)
    initial_encoded_board = gamemode.encode_board(board)

    player_turn = 0

    try:
        # Calculate latencies
        latency = [sum([middleware.ping(i) for _ in range(5)]) / 5 for i in range(gamemode.player_count)]
    except (ConnectionNotActiveError, ConnectionTimedOutError):
        # Shouldn't crash, it's our fault if it does :(
        return [Outcome.Draw] * gamemode.player_count, Result.UnknownResultType, moves, initial_encoded_board
    latency = sum(latency) / len(latency)
    logger.debug(f"Latency for container communication: {latency}s")

    def make_win(winner):
        res = [Outcome.Loss] * gamemode.player_count
        res[winner] = Outcome.Win
        return res

    def make_loss(loser):
        res = [Outcome.Win] * gamemode.player_count
        res[loser] = Outcome.Loss
        return res

    for _ in range(turns):
        start_time = time.time_ns()
        try:
            move = middleware.call(player_turn, "make_move", board=gamemode.filter_board(board, player_turn),
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

        move = gamemode.parse_move(move)

        logger.debug(f"Got move {move}")

        if not gamemode.is_move_legal(board, move):
            logger.debug(f"Move is not legal {move}")
            return make_loss(player_turn), Result.IllegalMove, moves, initial_encoded_board

        moves.append(gamemode.encode_move(move, player_turn))
        board = gamemode.apply_move(board, move)

        if gamemode.is_win(board, player_turn):
            return make_win(player_turn), Result.ValidGame, moves, initial_encoded_board

        if gamemode.is_loss(board, player_turn):
            return make_loss(player_turn), Result.ValidGame, moves, initial_encoded_board

        if gamemode.is_draw(board, player_turn):
            return [Outcome.Draw] * gamemode.player_count, Result.ValidGame, moves, initial_encoded_board

        player_turn += 1
        player_turn %= gamemode.player_count

    return [Outcome.Draw] * gamemode.player_count, Result.GameUnfinished, moves, initial_encoded_board
