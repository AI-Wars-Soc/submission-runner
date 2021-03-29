import importlib


def get_player_function(player_id: int, module_name: str, function_name: str):
    try:
        module = importlib.import_module(f'sandbox.submission{player_id + 1}.{module_name}')
    except ModuleNotFoundError as e:
        raise MissingFunctionError()

    try:
        return module.__getattribute__(function_name)
    except AttributeError as e:
        raise MissingFunctionError()


class MissingFunctionError(AttributeError):
    pass
