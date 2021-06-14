import json
from typing import List

from cuwais.common import Outcome, Result

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
    def __init__(self, initial_board: str, moves: List[str], submission_results: List[SingleResult]):
        self._recording = {"initial_board": initial_board, "moves": moves}
        self._submission_results = submission_results

        super().__init__(recording=self._recording, submission_results=submission_results)

    @property
    def outcomes(self):
        return [r.outcome for r in self._submission_results]

    @outcomes.setter
    def outcomes(self, values):
        for value, result in zip(values, self._submission_results):
            result.outcome = value

    @property
    def healths(self):
        return [r.healthy for r in self._submission_results]

    @healths.setter
    def healths(self, values):
        for value, result in zip(values, self._submission_results):
            result.healthy = value

    @property
    def player_ids(self):
        return [r.player_id for r in self._submission_results]

    @player_ids.setter
    def player_ids(self, values):
        for value, result in zip(values, self._submission_results):
            result.player_id = value
