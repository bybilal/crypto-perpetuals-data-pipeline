"""File-only operational events, independent of Rich's terminal console."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import re
import uuid

_current = ContextVar("pipeline_log", default=None)
_ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

def emit(stage, event, **fields):
    sink = _current.get()
    if sink is None:
        return
    machine, human, run_id = sink
    row = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
           "run_id": run_id, "stage": stage, "event": event, **fields}
    machine.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    machine.flush()
    if human:
        # JSON-escaped field values also prevent control characters or multiline injection.
        details = json.dumps(fields, ensure_ascii=True, default=str)
        human.write(_ansi.sub("", f"{row['timestamp']} {run_id} {stage}: {event} {details}") + "\n")
        human.flush()

@contextmanager
def logging_run(directory, human=False):
    directory.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    with (directory / f"{run_id}.jsonl").open("x", encoding="utf-8") as machine:
        human_file = (directory / f"{run_id}.log").open("x", encoding="utf-8") if human else None
        token = _current.set((machine, human_file, run_id))
        try:
            yield run_id
        finally:
            _current.reset(token)
            if human_file:
                human_file.close()
