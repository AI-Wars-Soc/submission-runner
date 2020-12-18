import asyncio
import concurrent.futures
import tarfile
from queue import Queue

import docker
import docker.errors
import docker.types.daemon
import os
import re

import requests
from docker.models.containers import Container
from shared.messages import MessageType, Message, Receiver
from typing import Iterator
import logging

_client = docker.from_env()


_COMPRESSED_PATH = '/tmp/sandbox/compressed.tar'


def make_sandbox_container(env_vars) -> Container:
    return _client.containers.run("aiwarssoc/sandbox",
                                  detach=True,
                                  remove=True,
                                  mem_limit=env_vars['SANDBOX_MEM_LIMIT'],
                                  memswap_limit=env_vars['SANDBOX_MEM_LIMIT'],
                                  cpu_period=100000,
                                  cpu_quota=int(100000 * float(env_vars['SANDBOX_CPU_COUNT'])),
                                  tty=True,
                                  network_mode='none',
                                  # read_only=True,  # marks all volumes as read only, just in case
                                  environment=env_vars,
                                  command="sh -c 'sleep $SANDBOX_CONTAINER_TIMEOUT'",
                                  user='sandbox',
                                  tmpfs={
                                      '/tmp': 'size=64M,uid=1000',
                                      '/var/tmp': 'size=64M,uid=1001'
                                  })


def _make_command(script_name: str):
    return "./sandbox/run.sh '{path}'".format(path=script_name)


def _compress_sandbox_files():
    with tarfile.open(_COMPRESSED_PATH, mode='w') as tar:
        tar.add("/exec/sandbox", arcname="sandbox")
        tar.add("/exec/shared", arcname="shared")


def _copy_sandbox_files(container: Container):
    # Compress files to tar
    if (not os.path.exists(_COMPRESSED_PATH)) or bool(os.getenv('SANDBOX_API_DEBUG')):
        _compress_sandbox_files()

    # Send
    with open(_COMPRESSED_PATH, 'rb') as f:
        data = f.read()
        container.put_archive("/home/sandbox/", data)

    # Fix ownership
    container.exec_run("chown -R sandbox:sandbox /home/sandbox/", user='root')
    container.exec_run("chmod -R ugo=rx /home/sandbox/", user='root')
    logging.debug(container.exec_run(cmd="ls -a -l /home/sandbox/", user='root').output.decode())


def _error(message_type: MessageType, identifier: str, **kwargs) -> Message:
    data = dict({'identifier': identifier}, **kwargs)

    message = Message(message_type, data)

    logging.error("{}: {}".format(message_type, str(data)))

    return message


def _stop_container(container: Container):
    try:
        if container is not None and container.status in {"running", "created", "restarting", "paused"}:
            container.stop(timeout=3)
    except docker.errors.NotFound:
        pass


def _timeout_container(container, timeout: int, identifier: str):
    try:
        container.wait(timeout=timeout)
    except docker.errors.APIError as kill_e:
        error = str(kill_e)
        return _error(MessageType.ERROR_INVALID_DOCKER_CONFIG, identifier, error=error)
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
        _stop_container(container)
        return _error(MessageType.ERROR_PROCESS_TIMEOUT, identifier)
    return None


def _get_lines(strings):
    line = []
    for string in strings:
        if string is None or string == "":
            continue
        string = str(string.decode())
        for char in string:
            if char == "\r" or char == "\n":
                if len(line) != 0:
                    yield "".join(line)
                line = []
            else:
                line.append(char)

    if len(line) != 0:
        yield "".join(line)


def _run_in_container(container: Container, script_name: str, env_vars: dict):
    container.unpause()
    _copy_sandbox_files(container)
    run_script_cmd = _make_command(script_name)
    (exit_code, stream) = container.exec_run(cmd=run_script_cmd,
                                             user='sandbox',
                                             stream=True,
                                             environment=env_vars,
                                             workdir="/home/sandbox/")

    # Process lines
    lines = _get_lines(stream)
    receiver = Receiver(lines)
    iterator = receiver.get_messages_iterator()
    yield from iterator


def _is_script_valid(script_name: str):
    script_name_rex = re.compile("^[a-zA-Z0-9_/]+\\.py$")
    return os.path.exists("/exec/sandbox/" + script_name) and script_name_rex.match(script_name) is not None


def _get_env_vars() -> dict:
    var_names = ['SANDBOX_COMMAND_TIMEOUT', 'SANDBOX_CONTAINER_TIMEOUT', 'SANDBOX_PARSER_TIMEOUT',
                 'SANDBOX_MEM_LIMIT', 'SANDBOX_CPU_COUNT']
    env_vars = {name: str(os.getenv(name)) for name in var_names}
    env_vars['PYTHONPATH'] = "/home/sandbox/"
    return env_vars


def _run_in_sandbox(script_name: str) -> Iterator[Message]:
    # Ensure that script is valid
    if not _is_script_valid(script_name):
        yield _error(MessageType.ERROR_INVALID_ENTRY_FILE, str({"name": script_name}))
        return

    # Get variables
    env_vars = _get_env_vars()
    identifier = str({"script": script_name, "vars": env_vars})
    unset = list(filter(lambda v: env_vars[v] is None, env_vars.keys()))
    if len(unset) != 0:
        error = f"Required environment variables are unset {str(unset)}"
        yield _error(MessageType.ERROR_INVALID_DOCKER_CONFIG, identifier, error=error)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Try to spin up a new container for the code to run in
        logging.info("Creating new container for " + identifier)
        container = None
        kill_future = None
        try:
            # Make container
            container = make_sandbox_container(env_vars)
            container.pause()

            # Start timeout timer
            timeout = int(env_vars['SANDBOX_PARSER_TIMEOUT'])
            kill_future = executor.submit(_timeout_container, container, timeout, identifier)

            # Start script
            messages = _run_in_container(container, script_name, env_vars)
            for message in messages:
                yield message
        except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
            yield _error(MessageType.ERROR_INVALID_DOCKER_CONFIG, identifier, error=str(e))
            return
        finally:
            _stop_container(container)
            logging.info("Finished sandbox for " + identifier)

            # Check if there was a timeout
            kill_result = kill_future.result()
            if kill_result is not None:
                yield kill_result


def run_in_sandbox(script_name: str) -> Iterator[Message]:
    """runs the given script in a sandbox and returns a result list.
    Each item in the list is of type 'Message' and is either output from the sandbox
    or an error while trying to run the sandbox.
    """
    logging.info("Request for script " + script_name)

    messages = _run_in_sandbox(script_name)
    yield from Message.filter_middle_ends_to_prints(messages)
