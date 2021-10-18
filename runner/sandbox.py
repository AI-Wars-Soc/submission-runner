import io
import os
import re
import tarfile
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiodocker
from aiodocker.stream import Stream
from cuwais.config import config_file

from runner.config import DEBUG
from runner.logger import logger
from shared.connection import Connection
from shared.message_connection import MessagePrintConnection

DOCKER_IMAGE_NAME = "aiwarssoc/sandbox"


class InvalidEntryFile(RuntimeError):
    pass


class InvalidSubmissionError(RuntimeError):
    pass


# Converts 100K into 102400, 1g into 1024**3, etc
def _to_bytes(s: str) -> int:
    s = s.strip().lower()
    if s[-1] in {"b", "k", "m", "g"}:
        e = {"b": 0, "k": 1, "m": 2, "g": 3}[s[-1]]
        return int(s[:-2].strip()) * (1024 ** e)

    return int(s)


def _get_env_vars() -> dict:
    env_vars = dict()
    env_vars['PYTHONPATH'] = "/home/sandbox/"
    env_vars['DEBUG'] = str(config_file.get("debug"))

    return env_vars


async def _make_sandbox_container(client: aiodocker.docker.Docker, env_vars: dict) -> aiodocker.docker.DockerContainer:
    mem_limit = _to_bytes(config_file.get("submission_runner.sandbox_memory_limit"))
    max_repo_size_bytes = int(config_file.get("max_repo_size_bytes"))
    cpu_quota = int(100000 * float(config_file.get("submission_runner.sandbox_cpu_count")))

    tmpfs_flags = "rw,noexec,nosuid,noatime"  # See mount command

    # See https://docs.docker.com/engine/api/v1.30/#operation/ContainerCreate
    config = {
        "Image": DOCKER_IMAGE_NAME,
        # "Cmd": f"ls -al /",
        "Tty": True,
        "User": 'sandbox',
        "Env": [f"{key}={env_vars[key]}" for key in env_vars],
        "NetworkDisabled": True,
        "HostConfig": {
            # See https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities
            "Capdrop": [
                "AUDIT_WRITE",
                "CHOWN",
                "DAC_OVERRIDE",
                # "FOWNER",  # Allows chmod
                "FSETID",
                "KILL",
                "MKNOD",
                "NET_BIND_SERVICE",
                "NET_RAW",
                "SETFCAP",
                "SETGID",
                "SETPCAP",
                "SETUID",
                "SYS_CHROOT"
            ],
            "Tmpfs": {
                '/tmp': f'{tmpfs_flags},size=1M',
                '/var/tmp': f'{tmpfs_flags},size=1M',
                '/run/lock': f'{tmpfs_flags},size=1M',
                '/var/lock': f'{tmpfs_flags},size=1M'
            },
            "ShmSize": 1 * 1024 * 1024,
            "NetworkMode": "none",
            "CpuPeriod": 100000,
            "CpuQuota": cpu_quota,
            "Memory": mem_limit // 2,
            "MemorySwap": mem_limit,
            "OomKillDisable": True,
            "DiskQuota": max_repo_size_bytes + 2*1024*1024,
            "AutoRemove": True,
        }
    }

    container = await client.containers.create(config)
    await container.start()

    return container


def _compress_sandbox_files(fh):
    with tarfile.open(fileobj=fh, mode='w') as tar:
        tar.add("./sandbox", arcname="sandbox")
        tar.add("./shared", arcname="shared")


async def _exec_root(container: aiodocker.docker.DockerContainer, command: str):
    logger.debug(f"Container {container.id}: running {command}")
    exec_ctxt = await container.exec(command, user='root', tty=True, stdout=True)
    exec_stream: Stream = exec_ctxt.start(timeout=30)
    output = b''
    while True:
        message: aiodocker.stream.Message = await exec_stream.read_out()
        if message is None:
            break
        output += message.data
    logger.debug(f"Container {container.id}: result of command {command}: '{output.decode()}'")


async def _copy_sandbox_scripts(container: aiodocker.docker.DockerContainer):
    _sandbox_scripts = io.BytesIO()
    # Compress files to tar
    _compress_sandbox_files(_sandbox_scripts)

    # Send
    _sandbox_scripts.seek(0)
    await container.put_archive("/home/sandbox/", _sandbox_scripts.getvalue())


async def _copy_submission(container: aiodocker.docker.DockerContainer, submission_hash: str):
    submission_path = f"/home/subrunner/repositories/{submission_hash}.tar"
    # Ensure that submission is valid
    if not _is_submission_valid(submission_hash, submission_path):
        raise InvalidSubmissionError(submission_hash)

    # Make destination
    dest_path = "/home/sandbox/submission"
    await _exec_root(container, f"mkdir {dest_path}")

    # Make required init file for python
    init_path = os.path.join(dest_path, "__init__.py")
    await _exec_root(container, f"touch {init_path}")

    logger.debug(f"Container {container.id}: opening submission {submission_hash}")
    with open(submission_path, 'rb') as f:
        logger.debug(f"Container {container.id}: reading submission {submission_hash}")
        data = f.read()

    logger.debug(f"Container {container.id}: putting submission {submission_hash}")
    await container.put_archive(dest_path, data)


async def _lock_down(container: aiodocker.docker.DockerContainer):
    # Set write limits
    await _exec_root(container, "chmod -R ugo=rx /home/sandbox/")  # TODO: Very slow (~2s) because of CoW?

    if DEBUG:
        await _exec_root(container, "ls -alR /home/sandbox/")


async def _get_lines(strings: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    line = []
    async for string in strings:
        if string is None or string == b'' or string == "":
            continue
        for char in string:
            if char == "\r" or char == "\n":
                if len(line) != 0:
                    yield "".join(line)
                line = []
            else:
                line.append(char)

    if len(line) != 0:
        yield "".join(line)


def _is_script_valid(script_name: str):
    script_name_rex = re.compile("^[a-zA-Z0-9_/]*$")
    return os.path.exists("./sandbox/" + script_name + ".py") and script_name_rex.match(script_name) is not None


def _is_submission_valid(submission_hash: str, submission_path: str):
    submission_hash_rex = re.compile("^[a-f0-9]+$")
    return os.path.exists(submission_path) and submission_hash_rex.match(submission_hash) is not None


@asynccontextmanager
async def run(submission_hash: str) -> Connection:
    docker = None
    container = None

    try:
        # Attach to docker
        docker = aiodocker.Docker()

        # Create container
        logger.debug(f"Creating container for hash {submission_hash}")
        env_vars = _get_env_vars()
        container = await _make_sandbox_container(docker, env_vars)

        # Copy information
        logger.debug(f"Container {container.id}: copying scripts")
        await _copy_sandbox_scripts(container)
        logger.debug(f"Container {container.id}: copying submission")
        await _copy_submission(container, submission_hash)
        logger.debug(f"Container {container.id}: locking down")
        await _lock_down(container)

        # Start script
        logger.debug(f"Container {container.id}: running script")
        run_t = int(config_file.get('submission_runner.sandbox_run_timeout_seconds'))
        run_script_cmd = f"./sandbox/run.sh 'play.py' {run_t}"
        cmd_exec = await container.exec(cmd=run_script_cmd,
                                        user='read_only_user',
                                        stdin=True,
                                        stdout=True,
                                        stderr=True,
                                        tty=False,
                                        environment=env_vars,
                                        workdir="/home/sandbox/")
        unrun_t = int(config_file.get('submission_runner.sandbox_unrun_timeout_seconds'))
        cmd_stream: Stream = cmd_exec.start(timeout=unrun_t)

        # Set up input to the container
        async def send_handler(m: str):
            logger.debug(f"Container {container.id} <-- '{m.encode()}'")
            await cmd_stream.write_in((m + "\n").encode())

        # Set up output from the container
        async def receive_handler() -> AsyncGenerator[str, None]:
            while True:
                message: aiodocker.stream.Message = await cmd_stream.read_out()
                if message is None:
                    break
                logger.debug(f"Container {container.id} --> '{message}'")
                yield bytes(message.data).decode()

        # Process output from the container
        logger.debug(f"Container {container.id}: setting up output processing")
        lines = _get_lines(receive_handler())

        logger.debug(f"Container {container.id}: connecting")
        yield MessagePrintConnection(send_handler, lines, container.id)

    finally:
        # Clean everything up
        if container is not None:
            logger.debug(f"Container {container.id}: cleaning up")
            await container.delete(force=True)
        if docker is not None:
            await docker.close()
