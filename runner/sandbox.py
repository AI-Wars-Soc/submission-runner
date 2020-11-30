import docker
import docker.errors
import os
from pathlib import Path
import requests

_client = docker.from_env()


def _build_status(code=200, response="", output=""):
    return {"status": int(code), "response": str(response), "output": str(output)}


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

    # Try to spin up a new container for the code to run in
    print("Creating new container for path " + path_str)
    container = None
    logs = ""
    try:
        container = _client.containers.run("aiwarssoc/sandbox",
                                           detach=True,
                                           #cpu_rt_runtime=int(os.getenv('SANDBOX_CPU_RT_RUNTIME_MICROSECONDS')),
                                           #mem_limit=os.getenv('SANDBOX_MEM_LIMIT'),
                                           #nano_cpus=int(os.getenv('SANDBOX_NANO_CPUS')),
                                           #tty=True,
                                           #network_disabled=True,
                                           network_mode='none',
                                           #read_only=True,  # marks all volumes as read only, just in case
                                           #remove=True,
                                           #auto_remove=True,
                                           environment={"SANDBOX_PYTHON_TIMEOUT": os.getenv('SANDBOX_PYTHON_TIMEOUT')},
                                           volumes={path_str: {'bind': '/exec', 'mode': 'ro'}}
                                           )
        container.start()
        print("Started container for path " + path_str)
        container.wait(timeout=int(os.getenv('SANDBOX_API_TIMEOUT')))
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        return _build_status(code=502, response="Error while starting running container: " + str(e), output=logs)
    except requests.exceptions.ReadTimeout:
        return _build_status(code=503, response="Running container timed out", output=logs)
    finally:
        if container is not None:
            logs = container.logs()
            container.remove(force=True)
        print("Finished with container for path " + path_str)

    print("Success on run for path " + path_str)
    return _build_status(code=200, response="Success!", output=logs)
