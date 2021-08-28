import asyncio
import time
from contextlib import asynccontextmanager
from typing import List, Tuple

from cuwais.common import Outcome, Result
from cuwais.gamemodes import Gamemode

from runner.logger import logger
from runner.middleware import Middleware
from runner.results import ParsedResult, SingleResult
from runner import sandbox
from runner.timed_connection import TimedConnection
from shared.exceptions import MissingFunctionError, ExceptionTraceback
from shared.message_connection import HandshakeFailedError
from shared.connection import Connection, ConnectionNotActiveError, ConnectionTimedOutError


@asynccontextmanager
async def _make_container_connection(gamemode: Gamemode, submission_hash):
    try:
        async with sandbox.run(submission_hash) as new_connection:
            await new_connection.ping()
            yield new_connection
    except HandshakeFailedError as e:
        each_res = [SingleResult(Outcome.Draw, False, "", Result.UnknownResultType, "")
                    for _ in range(gamemode.player_count)]
        each_res[0].printed = "\n".join(e.prints)

        logger.error(f"Failed to handshake with container! {e.prints}")
        yield ParsedResult("", [], each_res)


@asynccontextmanager
async def with_multiple(*args) -> list:
    """
    Runs the equivalent of many 'async with' statements concurrently.
    That is, the following code snippets are the same:

    async with with_multiple(a(), b(), c()) as a, b, c:
        foo(a, b, c)

    async with a() as a:
        async with b() as b:
            async with c() as c:
                foo(a, b, c)
    """
    async def _aenter(mgr):
        aenter = type(mgr).__aenter__
        return await aenter(mgr)

    async def _aexit(mgr):
        aexit = type(mgr).__aexit__
        return await aexit(mgr, None, None, None)

    enter_coroutines = [_aenter(mgr) for mgr in args]
    res = await asyncio.gather(*enter_coroutines, return_exceptions=True)
    yield res
    exit_coroutines = [_aexit(mgr) for mgr in args]
    await asyncio.gather(*exit_coroutines, return_exceptions=True)


async def run(gamemode: Gamemode, submission_hashes=None, options=None, turns=2 << 32, connections=None) -> ParsedResult:
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

    # Create containers and recurse
    if len(submission_hashes) != 0:
        socket_awaitables = [_make_container_connection(gamemode, sub_hash) for sub_hash in submission_hashes]
        async with with_multiple(*socket_awaitables) as new_connections:
            for connection in new_connections:
                if isinstance(connection, ParsedResult):
                    return connection

                connections.append(connection)
            return await run(gamemode, [], options, turns, connections)

    # Wrap all containers in timeouts
    timeout = (gamemode.player_count + 1) * int(options.get("turn_time", 10))
    connections = [TimedConnection(connection, timeout) for connection in connections]

    # Set up linking through middleware
    logger.debug("Attaching middleware: ")
    middleware = Middleware(connections)

    # Run
    logger.debug("Running...")
    outcomes, result, moves, initial_board = await _run_loop(gamemode, middleware, options, turns)

    # Gather
    logger.debug("Completed game, shutting down containers...")
    await middleware.complete_all()
    prints = []
    for i in range(gamemode.player_count):
        prints.append(middleware.get_player_prints(i))

    results = [SingleResult(outcome, result == Result.ValidGame, name, result, prints)
               for outcome, name, prints in zip(outcomes, gamemode.players, prints)]

    parsed_result = ParsedResult(initial_board, moves, results)

    logger.debug(f"Done running gamemode {gamemode.name}! Result: {parsed_result}")
    return parsed_result


async def _run_loop(gamemode: Gamemode, middleware, options, turns) -> Tuple[List[Outcome], Result, List[str], str]:
    moves = []
    time_remaining = [int(options["turn_time"])] * gamemode.player_count
    board = gamemode.setup(**options)
    initial_encoded_board = gamemode.encode_board(board)

    player_turn = 0

    try:
        # Calculate latencies
        pings = 5
        latency = []
        for i in range(gamemode.player_count):
            tot = 0.0
            for _ in range(pings):
                tot += await middleware.ping(i)
            tot /= pings
            tot = min(tot, 0.2)  # Cap latency at 0.2s to prevent slow loris attack
            latency.append(tot)
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
            move = await middleware.call(player_turn, "make_move", board=gamemode.filter_board(board, player_turn),
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
