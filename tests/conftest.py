# Import json for use below.
import json
# Import Path from pathlib for use below.
from pathlib import Path
# Import pytest for use below.
import pytest

# Define samples with the inputs listed below.
@pytest.fixture
def samples():
    # Construct the path or ratio from the specified components; store the result in root.
    root = Path(__file__).parent / "fixtures"
    # Return {p.stem: json.loads(p.read_text()) for p in root.glob('*.json')} to the caller.
    return {p.stem: json.loads(p.read_text()) for p in root.glob("*.json")}

# Define no network with the inputs listed below.
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # Import socket for use below.
    import socket
    # Define blocked with the inputs listed below.
    def blocked(*args, **kwargs):
        # Stop this operation with AssertionError('Tests must never access the network').
        raise AssertionError("Tests must never access the network")
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(socket.socket, "connect", blocked)
