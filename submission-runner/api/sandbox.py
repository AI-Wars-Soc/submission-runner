import json
import docker
import docker.errors
import os


_client = docker.from_env()


def _build_status(code=200, response=""):
    return {"status": code, "response": response}


def run_folder_in_sandbox(path):
    """runs the given directory in a sandbox and returns a result dict:
    {
        "status": ${status code},
        "response": ${string response, either error code or program output}
    }
    where status code can be the following:
    200 => program ran properly to completion
    400 => malformed request, eg dir doesn't exist
    500 => program failed to run, eg timeout
    """
    if not os.path.isdir(path):
        return _build_status(code=400, response="Invalid or non-existent directory")

    # Try to get the docker image
    try:
        image = _client.images.build('sandbox/Dockerfile')
    except docker.errors.BuildError:
    container = _client.containers.run('bfirsh/reticulate-splines',
                                      detach=True)
