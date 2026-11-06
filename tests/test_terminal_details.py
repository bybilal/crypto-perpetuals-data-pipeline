"""Keep recovery information visible without changing the market-data table."""
import io
import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from crypto_pipeline import cli, summary
from crypto_pipeline.config import PROJECT_ROOT, DB_PATH


def test_default_database_location():
    assert DB_PATH == PROJECT_ROOT / 'data/db/market_data.sqlite3'


def test_log_footer_uses_real_paths_without_interpreting_markup(tmp_path, monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(cli, 'console', Console(file=output, width=200))
    directory = tmp_path / '[example]'
    cli.display_run_logs(directory, 'example-run', True)
    text = output.getvalue()
    assert 'example-run' in text
    assert str(directory / 'example-run.jsonl') in text
    assert str(directory / 'example-run.log') in text


def test_failure_footer_points_to_error_log(tmp_path):
    result = subprocess.run([
        sys.executable, 'src/run_pipeline.py', '--offline',
        '--raw-dir', str(tmp_path / 'missing'), '--log-dir', str(tmp_path / 'logs'),
        '--db-path', str(tmp_path / 'test.sqlite3'), '--human-log',
    ], text=True, capture_output=True)
    assert result.returncode == 1
    assert 'JSONL log:' in result.stdout and 'Human log:' in result.stdout
    path = next((tmp_path / 'logs').glob('*.jsonl'))
    assert path.stem in result.stdout
    assert json.loads(path.read_text().splitlines()[-1])['event'] == 'failed'


def test_warnings_visible_in_terminal(monkeypatch, tmp_path, capsys):
    raw = tmp_path / 'raw'
    raw.mkdir()
    (raw / 'example.json').write_text('[]')
    database = tmp_path / 'existing.sqlite3'
    database.touch()
    monkeypatch.setattr(cli, 'RAW_DIR', raw)
    monkeypatch.setattr(cli, 'DB_PATH', database)
    monkeypatch.setattr(cli, 'load_sqlite', lambda: {'invalid_records': 0, 'file_errors': 1})
    cli.run_pipeline(offline=True)
    assert 'data-quality warnings' in capsys.readouterr().out
