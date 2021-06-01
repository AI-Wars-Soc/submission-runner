import json
import logging
import os
from typing import Dict, Callable

from cuwais.config import config_file

from runner import parsers
from runner.middleware import Middleware
from runner.parsers import ParsedResult
from runner.sandbox import TimedContainer

_type_names = {
    "boolean": lambda b: str(b).lower().startswith("t"),
    "string": str,
    "float": float,
    "integer": int
}


class Gamemode:
    def __init__(self, name, script, parser: Callable[[Middleware], ParsedResult], players, options):
        self.name = str(name)
        self.script = str(script) + ".py"
        self.parse = parsers.get(parser)
        self.players = int(players)
        self.options = dict(options)

    @staticmethod
    def get(name):
        return _gamemodes[name]

    def create_env_vars(self, **kwargs) -> Dict[str, str]:
        possible_parameters = {k for k in self.options.keys()}
        required_parameters = {k for k in possible_parameters if "default" not in self.options[k]}

        extras = {k for k in kwargs.keys() if k not in possible_parameters}
        if len(extras) != 0:
            raise TypeError(f"Unknown parameter(s): {', '.join(extras)}")

        missing = {k for k in required_parameters if k not in kwargs.keys()}
        if len(extras) != 0:
            raise TypeError(f"Missing parameter(s): {', '.join(missing)}")

        env_vars = {}
        for key, data in self.options.items():
            if key in kwargs:
                env_vars[key] = kwargs[key]
            else:
                env_vars[key] = data["default"]

            target_type = _type_names[data["type"]]
            env_vars[key] = str(target_type(env_vars[key]))

        return env_vars

    def run(self, submission_hashes=None, options=None) -> ParsedResult:
        if submission_hashes is None:
            submission_hashes = []
        if options is None:
            options = dict()
        logging.info("Request for gamemode " + self.name)

        # Create containers
        timeout = int(config_file.get("submission_runner.host_parser_timeout_seconds"))
        containers = []
        for submission_hash in submission_hashes:
            container = TimedContainer(timeout, submission_hash)
            containers.append(container)

        # Set up linking through middleware
        env_vars = self.create_env_vars(**options)
        middleware = Middleware(containers, env_vars)

        # Run
        res = self.parse(middleware)

        # Clean up
        middleware.complete_all()

        for container in containers:
            container.stop()

        return res


def _parse():
    script_dir = os.path.dirname(__file__)
    rel_path = "gamemodes.json"
    abs_file_path = os.path.join(script_dir, rel_path)

    with open(abs_file_path, "r") as fp:
        data = json.load(fp)

    for name, info in data.items():
        yield Gamemode(name, info["script"], info.get("parser", "default"),
                       info["players"], info.get("options", dict()))


_gamemodes = {gm.name: gm for gm in _parse()}
