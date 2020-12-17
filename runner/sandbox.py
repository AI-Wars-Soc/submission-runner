import tarfile
import docker
import docker.errors
import docker.types.daemon
import os
import re
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
                                  nano_cpus=int(env_vars['SANDBOX_NANO_CPUS']),
                                  tty=True,
                                  network_mode='none',
                                  # read_only=True,  # marks all volumes as read only, just in case
                                  environment=env_vars,
                                  command="sh -c 'sleep $SANDBOX_CONTAINER_TIMEOUT'",
                                  user='sandbox'
                                  )


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
    for subdir in ["sandbox", "shared"]:
        logging.debug(container.exec_run("chown -R sandbox:sandbox /home/sandbox/"+subdir, user='root').output.decode())
        logging.debug(container.exec_run(cmd="ls -a -l /home/sandbox/" + subdir, user='root').output.decode())


def _error(message: Message):
    logging.error("{}: {}".format(message.message_type.value, str(message.data)))


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
    container.start()
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


def run_in_sandbox(script_name: str) -> Iterator[Message]:
    """runs the given script in a sandbox and returns a result list.
    Each item in the list is of type 'Message' and is either output from the sandbox
    or an error while trying to run the sandbox.
    """
    logging.info("Request for script " + script_name)

    # Ensure that script is valid
    script_name_rex = re.compile("^[a-zA-Z0-9_/]+\\.py$")
    if (not os.path.exists("/exec/sandbox/" + script_name)) or script_name_rex.match(script_name) is None:
        msg = Message(MessageType.ERROR_INVALID_ENTRY_FILE, {"name": script_name})
        _error(msg)
        yield msg
        return

    # Get variables
    var_names = ['SANDBOX_COMMAND_TIMEOUT', 'SANDBOX_CONTAINER_TIMEOUT', 'SANDBOX_PARSER_TIMEOUT',
                 'SANDBOX_MEM_LIMIT', 'SANDBOX_NANO_CPUS']
    env_vars = {name: str(os.getenv(name)) for name in var_names}
    identifier = str({"script": script_name, "vars": env_vars})
    unset = list(filter(lambda v: env_vars[v] is None, env_vars.keys()))
    if len(unset) != 0:
        msg = {"identifier": identifier, "error": "Required environment variables are unset", "vars": unset}
        msg = Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)
        _error(msg)
        yield msg
    env_vars['PYTHONPATH'] = "/home/sandbox/"

    # Try to spin up a new container for the code to run in
    logging.info("Creating new container for " + identifier)
    container = None
    try:
        container = make_sandbox_container(env_vars)
        messages = _run_in_container(container, script_name, env_vars)
        yield from Message.filter_middle_ends_to_prints(messages)
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        msg = {"identifier": identifier, "error": str(e)}
        msg = Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)
        _error(msg)
        yield msg
        return
    finally:
        print(container.status, flush=True)
        if container is not None and container.status in {"running", "created", "restarting", "paused"}:
            container.kill()
        logging.info("Finished sandbox for " + identifier)
