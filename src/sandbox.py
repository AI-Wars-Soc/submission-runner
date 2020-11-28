import docker
import docker.errors
import os
from pathlib import Path
import requests

_client = docker.from_env()


def _build_status(code=200, response="", output=""):
    return {"status": code, "response": response, "output": output}


def run_folder_in_sandbox(path_str):
    """runs the given directory in a sandbox and returns a result dict:
    {
        "status": ${status code},
        "response": ${string response describing status code},
        "output": ${the output of the program (for as far as it ran)}
    }
    where status code can be the following:
    2XX => program ran properly to completion
    4XX => malformed request, eg dir doesn't exist
    5XX => program failed to run, eg timeout
    """
    path = Path(path_str)
    if (not path.exists()) or (not path.is_dir()):
        return _build_status(code=400, response="Invalid or non-existent directory: " + path_str)
    path_str = str(path.resolve())

    # Try to get the docker image
    try:
        with open('./sandbox/Dockerfile', 'r') as f:
            image, logs = _client.images.build('./sandbox', f)
    except (docker.errors.BuildError, docker.errors.APIError) as e:
        return _build_status(code=501, response="Error while getting sandbox docker image: " + e)

    # Try to spin up a new container for the code to run in
    container = None
    logs = ""
    try:
        container = _client.containers.run(image.id,
                                           detach=True,
                                           cpu_rt_runtime=os.getenv('SANDBOX_CPU_RT_RUNTIME_MICROSECONDS'),
                                           mem_limit=os.getenv('SANDBOX_MEM_LIMIT'),
                                           nano_cpus=os.getenv('SANDBOX_NANO_CPUS'),
                                           tty=True,
                                           network_disabled=True,
                                           network_mode='none',
                                           read_only=True,  # marks all volumes as read only, just in case
                                           remove=True,
                                           auto_remove=True,
                                           volumes={path_str: {'bind': '/exec', 'mode': 'ro'}})
        container.start()
        container.wait(timeout=os.getenv('SANDBOX_API_TIMEOUT'))
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        return _build_status(code=502, response="Error while starting running container: " + e, output=logs)
    except requests.exceptions.ReadTimeout:
        return _build_status(code=503, response="Running container timed out", output=logs)
    finally:
        if container is not None:
            logs = container.logs()
            container.remove(force=True)

    return _build_status(code=200, response="Success!", output=logs)
