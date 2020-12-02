import docker
import docker.errors
import os
from pathlib import Path
import requests

_client = docker.from_env()


def _build_status(code=200, response="", output=""):
    return {"status": int(code), "response": str(response), "output": str(output)}


def run_folder_in_sandbox(script_name):
    """runs the given script in a sandbox and returns a result dict:
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
    identifier = "script " + script_name

    # Ensure that script is valid
    if script_name not in os.listdir("/exec"):
        return _build_status(code=401, response="Invalid script to run: " + script_name, output="")

    # Ensure volume is present
    scripts_volume_name = os.getenv('SANDBOX_SCRIPTS_VOLUME')
    if scripts_volume_name not in [v.name for v in _client.volumes.list()]:
        return _build_status(code=402, response="Scripts volume not present: " + scripts_volume_name, output="")

    # Try to spin up a new container for the code to run in
    print("Creating new container for " + identifier, flush=True)
    container = None
    logs = ""
    try:
        container = _client.containers.run(
            "aiwarssoc/sandbox",
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
            environment={"SANDBOX_PYTHON_TIMEOUT": os.getenv('SANDBOX_PYTHON_TIMEOUT'),
                         "SANDBOX_CONTAINER_TIMEOUT": os.getenv('SANDBOX_CONTAINER_TIMEOUT')},
            volumes={scripts_volume_name: {'bind': '/exec', 'mode': 'ro'}},
            command="sleep infinity",
            user=0
            )
        container.start()
        print("Started container for " + identifier, flush=True)

        # Run python script with timeout
        print(container.exec_run("sh -c timeout $SANDBOX_PYTHON_TIMEOUT python3 /exec/" + script_name), flush=True)

        # container.wait(timeout=int(os.getenv('SANDBOX_API_TIMEOUT')))
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        return _build_status(code=502, response="Error while starting running container: " + str(e), output=logs)
    except requests.exceptions.ReadTimeout:
        return _build_status(code=503, response="Running container timed out", output=logs)
    finally:
        if container is not None:
            logs = container.logs()
            container.remove(force=True)
        print("Finished with container for " + identifier, flush=True)

    print("Success on run for " + identifier, flush=True)
    return _build_status(code=200, response="Success!", output=logs)
