import io
import tarfile

import docker
import docker.errors
import docker.types.daemon
import os
import re
import concurrent.futures
import requests
from shared.messages import MessageType, Message, Receiver
from typing import Iterator
import logging

_client = docker.from_env()


def make_sandbox_container(env_vars, run_script_cmd):
    return _client.containers.run("aiwarssoc/sandbox",
                                  detach=True,
                                  # remove=True,
                                  mem_limit=os.getenv('SANDBOX_MEM_LIMIT'),
                                  nano_cpus=int(os.getenv('SANDBOX_NANO_CPUS')),
                                  tty=True,
                                  network_mode='none',
                                  read_only=True,  # marks all volumes as read only, just in case
                                  environment=env_vars,
                                  command=run_script_cmd
                                  )


def _get_lines(strings):
    line = []
    for string in strings:
        string = string.decode()
        for char in string:
            if char == "\r" or char == "\n":
                if len(line) != 0:
                    yield "".join(line)
                line = []
            else:
                line.append(char)

    if len(line) != 0:
        yield "".join(line)


def _get_logs(container):
    return str(container.logs(timestamps=True))


def _async_kill(container, timeout: int, identifier: str):
    try:
        container.wait(timeout=timeout)
    except docker.errors.APIError as kill_e:
        msg = "Error while waiting for container " + identifier + ": " + str(kill_e)
        logging.error(msg)
        return Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)
    except requests.exceptions.ReadTimeout:
        msg = "Container Timeout: " + identifier
        logging.error(msg)
        container.remove(force=True)
        return Message(MessageType.ERROR_PROCESS_TIMEOUT, msg)
    return None


def _make_command(script_name: str):
    return """sh -c 
            '
                PYTHONPATH=PYTHONPATH:/exec ;
                if timeout $SANDBOX_PYTHON_TIMEOUT python3 /exec/sandbox/{path} || true ;
                then
                    echo "Done" ;
                else
                    echo "Timeout" ;
                fi ;
            '
            """.format(path=script_name)


def _copy_sandbox_files(container):
    # Compress files to tar
    fh = io.BytesIO()
    with tarfile.open(fileobj=fh, mode='w:gz') as tar:
        tar.add("/exec/sandbox", arcname="sandbox")
        tar.add("/exec/shared", arcname="shared")

    # Send
    container.put_archive("/exec/", fh.read())
    fh.close()


def run_in_sandbox(script_name) -> Iterator[Message]:
    """runs the given script in a sandbox and returns a result list.
    Each item in the list is of type 'Message' and is either output from the sandbox
    or an error while trying to run the sandbox.
    """
    logging.info("Request for script " + script_name)

    # Ensure that script is valid
    script_name_rex = re.compile("^[a-zA-Z0-9_/]+\\.py$")
    if (not os.path.exists("/exec/sandbox/" + script_name)) or script_name_rex.match(script_name) is None:
        logging.error("No such script " + script_name)
        yield Message(MessageType.ERROR_INVALID_ENTRY_FILE, script_name)
        return

    # Get variables
    var_names = ['SANDBOX_PYTHON_TIMEOUT', 'SANDBOX_CONTAINER_TIMEOUT']
    env_vars = {name: str(os.getenv(name)) for name in var_names}
    unset = list(filter(lambda v: env_vars[v] is None, env_vars.keys()))
    if len(unset) != 0:
        msg = "Not all required environment variables are set: " + str(unset)
        logging.error(msg)
        yield Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)

    identifier = str({"script": script_name, "vars": env_vars})

    # Try to spin up a new container for the code to run in
    logging.info("Creating new container for " + identifier)
    container = None
    logs = ""
    try:
        run_script_cmd = _make_command(script_name)
        container = make_sandbox_container(env_vars, run_script_cmd)
        _copy_sandbox_files(container)
        container.start()
        stream = container.attach(stdout=True, stderr=True, stream=True, logs=True)
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        msg = "Error while running container: {}".format(str(e))
        if container is not None:
            msg += ". Logs: {}".format(logs)
        logging.error(msg)
        yield Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)
        return

    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Set an async timer for killing the sandbox if it takes too long
        kill_future = executor.submit(_async_kill, (container, int(env_vars['SANDBOX_CONTAINER_TIMEOUT']), identifier))

        # Process lines
        lines = _get_lines(stream)
        receiver = Receiver(lines)
        yield from receiver.messages

        # Check if there was a timeout
        kill_result = kill_future.result()
        if kill_result is not None:
            yield kill_result

    logging.info("Finished sandbox for " + identifier)
