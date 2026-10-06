"""The launcher must not mistake another server for its own child."""
import socket
from unittest.mock import Mock

import pytest

from run_agent_demo import check_ports, check_processes


def test_occupied_port_is_rejected_without_stopping_existing_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match=f"Port {port} is unavailable"):
            check_ports([port])
        with socket.create_connection(("127.0.0.1", port)):
            pass


def test_preflight_releases_available_ports():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    check_ports([port])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))


def test_preflight_allows_restart_after_server_closes_connection():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)) as client:
            connection, _ = listener.accept()
            connection.close()
            assert client.recv(1) == b""
    check_ports([port])


@pytest.mark.parametrize("name", ["backend", "ai", "worker", "stt"])
def test_every_child_exit_reports_code_and_log(name, tmp_path):
    processes = {key: Mock() for key in ["backend", "ai", "worker", "stt"]}
    for process in processes.values():
        process.poll.return_value = None
    processes[name].poll.return_value = 7
    with pytest.raises(RuntimeError, match=f"{name} exited with code 7; read") as error:
        check_processes(processes, tmp_path)
    assert str(tmp_path / f"{name}.log") in str(error.value)
