import json
import os
from typing import Iterator, Dict


_type_names = {
    "boolean": bool,
    "string": str,
    "float": float,
    "integer": int
}


class Gamemode:
    def __init__(self, name, script, players, options):
        self.name = str(name)
        self.script = str(script) + ".py"
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


def _parse():
    script_dir = os.path.dirname(__file__)
    rel_path = "gamemodes.json"
    abs_file_path = os.path.join(script_dir, rel_path)

    with open(abs_file_path, "r") as fp:
        data = json.load(fp)

    for name, info in data.items():
        yield Gamemode(name, info["script"], info["players"], info.get("options", dict()))


_gamemodes = {gm.name: gm for gm in _parse()}
