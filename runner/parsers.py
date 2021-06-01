import json
from typing import List, Callable

from cuwais.common import Outcome, Result

from runner.middleware import Middleware


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
        self.recording = json.dumps(moves)
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


def chess_parser(middleware: Middleware) -> ParsedResult:
    print(middleware.call(0, "make_move", board=None, time_remaining=0))
    messages = middleware.complete_all()
    prints = []
    for i in range(middleware.player_count):
        prints.append(middleware.get_player_prints(i))
    return ParsedResult(messages, [SingleResult(Outcome.Draw, True, "debug", Result.ValidGame, pp) for pp in prints])
    """prints = ([], [], [])
    controller = -1  # -1 for host, 0 for player 0, 1 for player 1
    moves = []
    initial_state = None
    board = None
    loser = -1
    healths = [True, True]
    outcome_txt = None

    for message in container_output_streams:
        if message.message_type == MessageType.PRINT:
            prints[controller + 1].append(message.data["str"])
        elif message.message_type == MessageType.RESULT:
            result_type = message.data["type"]
            player_turn = int(message.data["player_id"])
            if result_type == "initial_board":
                initial_state = message.data["board_state"]
                board = chess.Board(initial_state, chess960=message.data["chess960"])
                controller = -1
            elif result_type == "ai_start":
                controller = int(message.data["player_id"])
            elif result_type == "ai_end":
                controller = -1
            elif result_type == "move":
                move = message.data["move"]
                moves.append(move)
                move = chess.Move.from_uci(move)
                if move not in board.legal_moves:
                    loser = player_turn
                    healths[player_turn] = False
                    outcome_txt = "illegal-move"
                    break
                board.push(move)
                if board.fen() != message.data["board_state"]:
                    loser = player_turn
                    healths[player_turn] = False
                    outcome_txt = "illegal-board"
                    break
            elif result_type == "invalid_move":
                loser = player_turn
                healths[player_turn] = False
                outcome_txt = "illegal-move"
                break
            elif result_type == "result":
                result = message.data["result"]
                if result == "loss":
                    loser = player_turn
                else:
                    loser = -1
                outcome_txt = message.data["reason"]
                break
            elif result_type == "missing_function":
                loser = player_turn
                healths[player_turn] = False
                outcome_txt = "broken-entry-point"
            else:
                loser = -1
                healths = [False, False]
                outcome_txt = "unknown-result-type"
                break
        elif message.message_type in Message.ERROR_TYPES:
            loser = controller
            if controller >= 0:
                healths[controller] = False
            outcome_txt = {MessageType.ERROR_PROCESS_TIMEOUT: "timeout",
                           MessageType.ERROR_INVALID_MESSAGE_TYPE: "invalid-message-type",
                           MessageType.ERROR_INVALID_ATTACHED_KEY: "invalid-attached-key",
                           MessageType.ERROR_INVALID_ENTRY_FILE: "invalid-entry-file",
                           MessageType.ERROR_INVALID_NEW_KEY: "invalid-new-key",
                           MessageType.ERROR_INVALID_SUBMISSION: "invalid-submission",
                           MessageType.ERROR_PROCESS_KILLED: "process-killed",
                           }[message.message_type]
            break

    # If a player was in control of the game and the game ended, that player probably caused a crash
    if outcome_txt is None:
        outcome_txt = "game-unfinished"
        if controller != -1:
            healths[controller] = False
            loser = controller

    host_prints = "\n".join(prints[0])
    player_prints = ["\n".join(prints[1]), "\n".join(prints[2])]
    moves = ",".join(moves)

    if loser == -1:  # Draw
        outcome = [Outcome.Draw, Outcome.Draw]
    elif loser == 0:  # White win
        outcome = [Outcome.Loss, Outcome.Win]
    else:  # Black win
        outcome = [Outcome.Win, Outcome.Loss]

    if board is None:
        healths = [False, False]
        final_board = None
    else:
        final_board = board.fen()

    submission_results = [SingleResult(o, h, p) for o, h, p in zip(outcome, healths, ["white", "black"])]

    record = {"host_prints": host_prints, "player_prints": player_prints, "initial_state": initial_state,
              "moves": moves, "loser": loser, "outcome_txt": outcome_txt, "final_board": final_board}
    return ParsedResult(record, submission_results)"""


def get(parser) -> Callable[[Middleware], ParsedResult]:
    if parser == "info":
        return info_parser
    if parser == "chess":
        return chess_parser

    return default_parser
