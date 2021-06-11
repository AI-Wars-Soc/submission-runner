import io
import logging
import os
import re
import tarfile
import threading
from ssl import SSLSocket
from typing import Iterator, Optional

import docker
import docker.errors
import docker.types.daemon
import docker.utils.socket
import requests
from cuwais.config import config_file
from docker.models.containers import Container

from shared.messages import Connection

_client = docker.from_env()


class InvalidEntryFile(RuntimeError):
    pass


class InvalidSubmissionError(RuntimeError):
    pass


class ContainerTimedOutException(RuntimeError):
    def __init__(self, container):
        self.container = container
        super().__init__()


class TimedContainer:
    """
    A container which lives for a maximum of `timeout`ms.
    Commands can be run on the container and files transferred to it,
    but all of this must be done within the timeout given.
    After this, the container will force close
    """
    _container: Optional[Container]

    def __init__(self, timeout: int, submission_hash: str):
        self.timeout = timeout
        self.submission_hash = submission_hash

        # Create container
        self._env_vars = TimedContainer._get_env_vars()
        self._container = TimedContainer._make_sandbox_container(self._env_vars)

        # Copy information
        self._copy_sandbox_scripts()
        self._copy_submission(submission_hash)
        self._lock_down()

        # Create kill thread
        self._kill_thread = threading.Thread(target=TimedContainer._timeout_method, args=(self, timeout,))
        self._kill_thread.setDaemon(True)
        self._kill_thread.start()
        self._timed_out = False
        self._stopped = False

    def stop(self):
        self._stopped = True
        try:
            if self._container is not None \
                    and self._container.status in {"running", "created", "restarting", "paused"}:
                self._container.stop(timeout=0)
                # self._container.remove()
        except docker.errors.NotFound:
            pass
        finally:
            self._container = None
            self._kill_thread.join()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @staticmethod
    def _get_env_vars() -> dict:
        env_vars = dict()
        env_vars['PYTHONPATH'] = "/home/sandbox/"

        return env_vars

    @staticmethod
    def _make_sandbox_container(env_vars) -> Container:
        mem_limit = str(config_file.get("submission_runner.sandbox_memory_limit"))
        disk_limit = str(int(config_file.get("submission_runner.sandbox_disk_limit_megabytes"))) + "M"
        unrun_t = int(config_file.get('submission_runner.sandbox_unrun_timeout_seconds'))
        cpu_quota = int(100000 * float(config_file.get("submission_runner.sandbox_cpu_count")))
        return _client.containers.run("aiwarssoc/sandbox",
                                      detach=True,
                                      remove=True,
                                      mem_limit=mem_limit,
                                      memswap_limit=mem_limit,
                                      cpu_period=100000,
                                      cpu_quota=cpu_quota,
                                      tty=False,
                                      stream=True,
                                      network_mode='none',
                                      cap_drop=["ALL"],
                                      # read_only=True,  # marks all volumes as read only, just in case
                                      environment=env_vars,
                                      command=f"sh -c 'sleep {unrun_t}'",
                                      user='sandbox',
                                      tmpfs={
                                          '/tmp': f'size={disk_limit}',
                                          '/var/tmp': f'size={disk_limit}',
                                          '/run/lock': f'size=1M',
                                          '/var/lock': f'size=1M'
                                      })

    @staticmethod
    def _compress_sandbox_files(fh):
        with tarfile.open(fileobj=fh, mode='w') as tar:
            tar.add("./sandbox", arcname="sandbox")
            tar.add("./shared", arcname="shared")

    def _copy_sandbox_scripts(self):
        with io.BytesIO() as fh:
            # Compress files to tar
            TimedContainer._compress_sandbox_files(fh)

            # Send
            self._container.put_archive("/home/sandbox/", fh.getvalue())

    def _lock_down(self):
        # Set write limits
        logging.debug(self._container.exec_run("chown -hvR root /home/sandbox/", user="root"))
        logging.debug(self._container.exec_run("chmod -R ugo=rx /home/sandbox/", user="root"))

    def _timeout_method(self, timeout: int):
        try:
            self._container.wait(timeout=timeout)
        except requests.exceptions.ReadTimeout or requests.exceptions.ConnectionError:
            if not self._stopped:
                self._timed_out = True
                self.stop()

    @staticmethod
    def _read(socket, n=4096):
        """
        Reads at most n bytes from socket
        Pulled from docker API (docker.utils.socket) with the removal of the below lines
        because they cause infinite hanging
        TODO: See if there is a better solution to this
        """

        recoverable_errors = (docker.utils.socket.errno.EINTR, docker.utils.socket.errno.EDEADLK, docker.utils.socket.errno.EWOULDBLOCK)

        # if docker.utils.socket.six.PY3 and not isinstance(socket, docker.utils.socket.NpipeSocket):
            # docker.utils.socket.select.select([socket], [], [])

        try:
            if hasattr(socket, 'recv'):
                return socket.recv(n)
            if docker.utils.socket.six.PY3 and isinstance(socket, getattr(docker.utils.socket.pysocket, 'SocketIO')):
                return socket.read(n)
            return os.read(socket.fileno(), n)
        except EnvironmentError as e:
            if e.errno not in recoverable_errors:
                raise

    @staticmethod
    def _frames_iter_no_tty(socket):
        """
        Returns a generator of data read from the socket when the tty setting is
        not enabled.

        Taken from docker.utils.socket
        """
        while True:
            (stream, n) = docker.utils.socket.next_frame_header(socket)
            if n < 0:
                break
            while n > 0:
                result = TimedContainer._read(socket, n)
                if result is None:
                    continue
                data_length = len(result)
                if data_length == 0:
                    # We have reached EOF
                    return
                n -= data_length
                yield result.decode()

    @staticmethod
    def _get_lines(strings: Iterator[str]) -> Iterator[str]:
        line = []
        for string in strings:
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

    def _add_timeout_exception(self, iterator):
        yield from iterator

        if self._timed_out:
            raise ContainerTimedOutException(self)

    def _add_stop(self, iterator):
        yield from iterator

        self.stop()

    @staticmethod
    def _is_script_valid(script_name: str):
        script_name_rex = re.compile("^[a-zA-Z0-9_/]*$")
        return os.path.exists("./sandbox/" + script_name + ".py") and script_name_rex.match(script_name) is not None

    def run(self, script_name: str, extra_args: dict) -> Connection:
        if extra_args is None:
            extra_args = dict()

        # Ensure that script is valid
        if not TimedContainer._is_script_valid(script_name):
            raise InvalidEntryFile(script_name)

        # Get env vars
        env_vars = {**self._env_vars, **extra_args}

        # Start script
        run_t = int(config_file.get('submission_runner.sandbox_run_timeout_seconds'))
        run_script_cmd = f"./sandbox/run.sh '{script_name}.py' {run_t}"
        socket: SSLSocket
        _, socket = self._container.exec_run(cmd=run_script_cmd,
                                             user='sandbox',
                                             stream=True,
                                             socket=True,
                                             stdin=True,
                                             tty=False,
                                             environment=env_vars,
                                             workdir="/home/sandbox/")

        # Set up input to the container
        def send_handler(m: str):
            socket.write((m + "\n").encode())

        # Process output from the container
        socket.settimeout(self.timeout)
        strings = TimedContainer._frames_iter_no_tty(socket)
        lines = TimedContainer._get_lines(strings)
        received = self._add_stop(self._add_timeout_exception(lines))

        return Connection(send_handler, received)

    @staticmethod
    def _is_submission_valid(submission_hash: str, submission_path: str):
        submission_hash_rex = re.compile("^[a-f0-9]+$")
        return os.path.exists(submission_path) and submission_hash_rex.match(submission_hash) is not None

    def _copy_submission(self, submission_hash: str):
        submission_path = f"/home/subrunner/repositories/{submission_hash}.tar"
        # Ensure that submission is valid
        if not TimedContainer._is_submission_valid(submission_hash, submission_path):
            raise InvalidSubmissionError(submission_hash)

        # Make destination
        dest_path = "/home/sandbox/submission"
        self._container.exec_run(f"mkdir {dest_path}", user='root')

        # Make required init file for python
        init_path = os.path.join(dest_path, "__init__.py")
        self._container.exec_run(f"touch {init_path}", user='root')

        with open(submission_path, 'rb') as f:
            data = f.read()
            self._container.put_archive(dest_path, data)

    def __str__(self):
        return f"TimedContainer<{self._container}>"
