import importlib

from shared.exceptions import MissingFunctionError


def get_player_function(module_name: str, function_name: str):
    try:
        module = importlib.import_module(f'submission.{module_name}')
    except ModuleNotFoundError:
        raise MissingFunctionError()

    try:
        return module.__getattribute__(function_name)
    except AttributeError:
        raise MissingFunctionError()
