"""Keep recovery information visible without changing the market-data table."""
# Import io for use below.
import io
# Import json for use below.
import json
# Import subprocess for use below.
import subprocess
# Import sys for use below.
import sys
# Import Path from pathlib for use below.
from pathlib import Path

# Import Console from rich.console for use below.
from rich.console import Console
# Import cli, summary from crypto_pipeline for use below.
from crypto_pipeline import cli, summary
# Import PROJECT_ROOT, DB_PATH from crypto_pipeline.config for use below.
from crypto_pipeline.config import PROJECT_ROOT, DB_PATH


# Define test default database location with the inputs listed below.
def test_default_database_location():
    # Verify the expected condition: DB_PATH == PROJECT_ROOT / 'data/db/market_data.sqlite3'.
    assert DB_PATH == PROJECT_ROOT / 'data/db/market_data.sqlite3'


# Define test log footer uses real paths without interpreting markup with the inputs listed below.
def test_log_footer_uses_real_paths_without_interpreting_markup(tmp_path, monkeypatch):
    # Call io.StringIO with the supplied arguments; store the result in output.
    output = io.StringIO()
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(cli, 'console', Console(file=output, width=200))
    # Construct the path or ratio from the specified components; store the result in directory.
    directory = tmp_path / '[example]'
    # Print the current run ID and the locations of its log files.
    cli.display_run_logs(directory, 'example-run', True)
    # Call output.getvalue with the supplied arguments; store the result in text.
    text = output.getvalue()
    # Verify the expected condition: 'example-run' in text.
    assert 'example-run' in text
    # Verify the expected condition: str(directory / 'example-run.jsonl') in text.
    assert str(directory / 'example-run.jsonl') in text
    # Verify the expected condition: str(directory / 'example-run.log') in text.
    assert str(directory / 'example-run.log') in text


# Define test failure footer points to error log with the inputs listed below.
def test_failure_footer_points_to_error_log(tmp_path):
    # Run the command and capture its exit status and any requested output; store the result in result.
    result = subprocess.run([
        sys.executable, 'src/run_pipeline.py', '--offline',
        '--raw-dir', str(tmp_path / 'missing'), '--log-dir', str(tmp_path / 'logs'),
        '--db-path', str(tmp_path / 'test.sqlite3'), '--human-log',
    ], text=True, capture_output=True)
    # Verify the expected condition: result.returncode == 1.
    assert result.returncode == 1
    # Verify the expected condition: 'JSONL log:' in result.stdout and 'Human log:' in result.stdout.
    assert 'JSONL log:' in result.stdout and 'Human log:' in result.stdout
    # Call next with the supplied arguments; store the result in path.
    path = next((tmp_path / 'logs').glob('*.jsonl'))
    # Verify the expected condition: path.stem in result.stdout.
    assert path.stem in result.stdout
    # Verify the expected condition: json.loads(path.read_text().splitlines()[-1])['event'] == 'failed'.
    assert json.loads(path.read_text().splitlines()[-1])['event'] == 'failed'


# Define test warnings visible in terminal with the inputs listed below.
def test_warnings_visible_in_terminal(monkeypatch, tmp_path, capsys):
    # Construct the path or ratio from the specified components; store the result in raw.
    raw = tmp_path / 'raw'
    # Create the needed output directory, including missing parents.
    raw.mkdir()
    # Write the specified text to the file.
    (raw / 'example.json').write_text('[]')
    # Construct the path or ratio from the specified components; store the result in database.
    database = tmp_path / 'existing.sqlite3'
    # Call database.touch with the supplied arguments.
    database.touch()
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(cli, 'RAW_DIR', raw)
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(cli, 'DB_PATH', database)
    # Call monkeypatch.setattr with the supplied arguments.
    monkeypatch.setattr(cli, 'load_sqlite', lambda: {'invalid_records': 0, 'file_errors': 1})
    # Coordinate fetch, normalization, database storage and terminal reporting.
    cli.run_pipeline(offline=True)
    # Verify the expected condition: 'data-quality warnings' in capsys.readouterr().out.
    assert 'data-quality warnings' in capsys.readouterr().out
