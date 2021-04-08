import json
from typing import Iterator, List, Callable

import chess
from cuwais.common import Outcome

from shared.messages import Message, MessageType


class SingleResult(dict):
    def __init__(self, outcome: Outcome, healthy: bool, player_id: str):
        self.outcome = outcome
        self.healthy = healthy
        self.player_id = player_id

        super().__init__(outcome=outcome.value, healthy=healthy, player_id=player_id)


class ParsedResult(dict):
    def __init__(self, recording: dict, submission_results: List[SingleResult]):
        recording["outcome_txt"] = recording.get("outcome_txt", "unknown")
        recording["player_prints"] = recording.get("player_prints", [])
        recording["player_prints"] = [[p[:1000] for p in player[:100]] for player in recording["player_prints"]]
        self.recording = json.dumps(recording)
        self.submission_results = submission_results

        super().__init__(recording=recording, submission_results=submission_results)

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


def default_parser(messages: Iterator[Message]):
    prints = []
    results = []
    end = None

    for message in messages:
        if message.message_type == MessageType.PRINT:
            prints.append(message.data["str"])
        elif message.message_type == MessageType.RESULT:
            results.append(message.data)
        elif message.message_type in Message.END_TYPES:
            end = message

    prints = "\n".join(prints)
    end = dict(end)

    record = {"printed": prints, "results": results, "end": end}
    return ParsedResult(record, [])


def chess_parser(messages: Iterator[Message]):
    prints = ([], [], [])
    moves = []
    controller = -1  # -1 for host, 0 for player 0, 1 for player 1
    initial_state = None
    board = None
    loser = -1
    healths = [True, True]
    outcome_txt = None

    for message in messages:
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
    if controller != -1 and outcome_txt is None:
        healths[controller] = False
        outcome_txt = "game-unfinished"
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
    return ParsedResult(record, submission_results)


def get(parser) -> Callable[[Iterator[Message]], ParsedResult]:
    if parser == "chess":
        return chess_parser

    return default_parser
