from typing import Any, Iterable

from shared.messages import Connection


class Middleware:
    def __init__(self, connections: Iterable[Connection]):
        self._connections = list(connections)

    @property
    def player_count(self):
        return len(self._connections)

    def complete_all(self):
        return [self._connections[player_id].complete() for player_id in range(self.player_count)]

    def call(self, player_id, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        return self._connections[player_id].call(method_name, *args, **kwargs)

    def ping(self, player_id) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        return self._connections[player_id].ping()

    def get_player_prints(self, i):
        return self._connections[i].get_prints()
