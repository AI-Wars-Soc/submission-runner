import docker
import docker.errors
import os
import re
import requests
import logging

_client = docker.from_env()


def _build_status(code=200, response="", output=""):
    return {"status": int(code), "response": str(response), "output": str(output)}


def make_sandbox_container(scripts_volume_name, env_vars, run_script_cmd):
    return _client.containers.run(
            "aiwarssoc/sandbox",
            detach=True,
            #cpu_rt_runtime=int(os.getenv('SANDBOX_CPU_RT_RUNTIME_MICROSECONDS')),
            #mem_limit=os.getenv('SANDBOX_MEM_LIMIT'),
            #nano_cpus=int(os.getenv('SANDBOX_NANO_CPUS')),
            tty=True,
            #network_disabled=True,
            network_mode='none',
            #read_only=True,  # marks all volumes as read only, just in case
            #remove=True,
            #auto_remove=True,
            volumes={scripts_volume_name: {'bind': '/exec', 'mode': 'ro'}},
            environment=env_vars,
            command=run_script_cmd
            )


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
    # Ensure that script is valid
    _script_name_rex = re.compile("^[a-zA-Z0-9]+\\.py$")
    if script_name not in os.listdir("/exec") or _script_name_rex.match(script_name) is None:
        return _build_status(code=401, response="Invalid script to run: " + script_name, output="")

    # Ensure volume is present
    scripts_volume_name = str(os.getenv('SANDBOX_SCRIPTS_VOLUME'))
    if scripts_volume_name not in [v.name for v in _client.volumes.list()]:
        return _build_status(code=402, response="Scripts volume not present: " + scripts_volume_name, output="")

    # Get variables
    var_names = ['SANDBOX_PYTHON_TIMEOUT', 'SANDBOX_CONTAINER_TIMEOUT', 'SANDBOX_API_TIMEOUT']
    env_vars = {name: str(os.getenv(name)) for name in var_names}
    if None in env_vars.values():
        return _build_status(code=403, response="Not all required environment variables are set", output="")

    identifier = str({"script": script_name, "vars": env_vars})

    # Try to spin up a new container for the code to run in
    print("Creating new container for " + identifier)
    container = None
    logs = ""
    try:
        run_script_cmd = "sh -c 'timeout $SANDBOX_PYTHON_TIMEOUT python3 /exec/{path}'".format(path=script_name)
        container = make_sandbox_container(scripts_volume_name, env_vars, run_script_cmd)
        container.start()
        container.wait(timeout=int(env_vars['SANDBOX_API_TIMEOUT']))
    except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
        return _build_status(code=502, response="Error while starting running container: " + str(e), output=logs)
    except requests.exceptions.ReadTimeout:
        return _build_status(code=503, response="Running container timed out", output=logs)
    finally:
        if container is not None:
            logs = container.logs()
            container.remove(force=True)
        print("Finished with container for " + identifier)

    print("Success on run for " + identifier)
    return _build_status(code=200, response="Success!", output=logs)
