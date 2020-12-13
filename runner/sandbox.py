import docker
import docker.errors
import os
import re
import requests
from shared.messages import MessageType, Message, Receiver
from typing import Iterator
import logging

_client = docker.from_env()


def make_sandbox_container(scripts_volume_name, env_vars, run_script_cmd):
    return _client.containers.run(
            "aiwarssoc/sandbox",
            detach=True,
            mem_limit=os.getenv('SANDBOX_MEM_LIMIT'),
            nano_cpus=int(os.getenv('SANDBOX_NANO_CPUS')),
            tty=True,
            network_mode='none',
            read_only=True,  # marks all volumes as read only, just in case
            volumes={scripts_volume_name: {'bind': '/exec', 'mode': 'ro'}},
            environment=env_vars,
            command=run_script_cmd
            )


def run_folder_in_sandbox(script_name) -> Iterator[Message]:
    """runs the given script in a sandbox and returns a result list.
    Each item in the list is of type 'Message' and is either output from the sandbox
    or an error while trying to run the sandbox.
    """
    logging.info("Request for script " + script_name)

    # Ensure that script is valid
    _script_name_rex = re.compile("^[a-zA-Z0-9]+\\.py$")
    if script_name not in os.listdir("/sandbox-scripts-src") or _script_name_rex.match(script_name) is None:
        logging.error("No such script " + script_name)
        yield Message(MessageType.ERROR_INVALID_ENTRY_FILE, script_name)
        return

    # Ensure volume is present
    scripts_volume_name = str(os.getenv('SANDBOX_SCRIPTS_VOLUME'))
    if scripts_volume_name not in [v.name for v in _client.volumes.list()]:
        msg = "Scripts volume not present: " + scripts_volume_name
        logging.error(msg)
        yield Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)
        return

    # Get variables
    var_names = ['SANDBOX_PYTHON_TIMEOUT', 'SANDBOX_CONTAINER_TIMEOUT', 'SANDBOX_API_TIMEOUT']
    env_vars = {name: str(os.getenv(name)) for name in var_names}
    unset = list(filter(lambda v: env_vars[v] is None, env_vars.keys()))
    if len(unset) != 0:
        msg = "Not all required environment variables are set: " + str(unset)
        logging.error(msg)
        yield Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)

    identifier = str({"script": script_name, "vars": env_vars})

    # Try to spin up a new container for the code to run in
    container = None
    logging.info("Creating new container for " + identifier)
    try:
        run_script_cmd = "sh -c 'timeout $SANDBOX_PYTHON_TIMEOUT python3 /exec/{path}'".format(path=script_name)
        container = make_sandbox_container(scripts_volume_name, env_vars, run_script_cmd)
        container.start()
        container.wait(timeout=int(env_vars['SANDBOX_API_TIMEOUT']))
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        msg = "Error while running container: " + str(e)
        logging.error(msg)
        yield Message(MessageType.ERROR_INVALID_DOCKER_CONFIG, msg)
        return
    except requests.exceptions.ReadTimeout:
        msg = "Running container timed out"
        logging.info("Finished due to timeout for " + identifier)
        yield Message(MessageType.ERROR_PROCESS_TIMEOUT, msg)
        return
    finally:
        if container is not None:
            logs = container.logs().decode()
            receiver = Receiver(logs.split("\n"))
            yield from receiver.messages
            container.remove(force=True)

    logging.info("Finished sandbox for " + identifier)
