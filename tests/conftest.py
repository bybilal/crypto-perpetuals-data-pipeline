import json
from pathlib import Path
import pytest

@pytest.fixture
def samples():
    root = Path(__file__).parent / "fixtures"
    return {p.stem: json.loads(p.read_text()) for p in root.glob("*.json")}

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must never access the network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
