from typing import Iterator

import chess

from shared.messages import Message, MessageType


def none_parser(messages: Iterator[Message]):
    return list(messages)


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

    return {"printed": prints, "results": results, "end": end}


def chess_parser(messages: Iterator[Message]):
    prints = ([], [], [])
    moves = []
    player_turn = 0
    controller = -1  # -1 for host, 0 for player 0, 1 for player 1
    initial_state = None
    board = None
    loser = -1
    healthy = True
    outcome = ""

    for message in messages:
        if message.message_type == MessageType.PRINT:
            prints[controller + 1].append(message.data["str"])
        elif message.message_type == MessageType.RESULT:
            result_type = message.data["type"]
            if result_type == "initial_board":
                initial_state = message.data["board_state"]
                board = chess.Board(initial_state, chess960=message.data["chess960"])
                player_turn = int(message.data["player_id"])
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
                    healthy = False
                    outcome = "illegal-move"
                    break
                board.push(move)
                if board.fen() != message.data["board_state"]:
                    loser = player_turn
                    healthy = False
                    outcome = "illegal-board"
                    break
            elif result_type == "invalid_move":
                loser = player_turn
                healthy = False
                outcome = "illegal-move"
                break
            elif result_type == "result":
                result = message.data["result"]
                if result == "loss":
                    loser = player_turn
                else:
                    loser = -1
                outcome = message.data["reason"]
                break
            else:
                loser = -1
                healthy = False
                outcome = "unknown-result-type"
                break

    host_prints = "\n".join(prints[0])
    player_prints = ["\n".join(prints[1]), "\n".join(prints[2])]

    return {"host_prints": host_prints, "player_prints": player_prints, "initial_state": initial_state,
            "moves": moves, "loser": loser, "healthy": healthy, "outcome": outcome}


def get(parser):
    if parser == "none":
        return none_parser
    if parser == "chess":
        return chess_parser

    return default_parser
