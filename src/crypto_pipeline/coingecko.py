"""Small free/Demo client; original response bytes are saved before parsing."""
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .events import emit

BASE = 'https://api.coingecko.com/api/v3/'
ENDPOINTS = {
    'bitcoin': 'coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false',
    'categories': 'coins/categories/list',
}


def request_bytes(endpoint, key=None):
    """Bound retries; never log credentials, response error bodies or request headers."""
    headers = {'Accept': 'application/json', 'User-Agent': 'crypto-pipeline/0.1'}
    if key:
        headers['x-cg-demo-api-key'] = key
    for attempt in range(3):
        try:
            with urlopen(Request(BASE + endpoint, headers=headers), timeout=30) as response:
                return response.read()
        except HTTPError as error:
            status = error.code
            retry = error.headers.get('Retry-After', '')
            error.close()
            if status not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'CoinGecko HTTP {status}; check free/Demo access or retry later') from None
            delay = max(15 * 2**attempt, int(retry) if retry.isdigit() else 0)
            if delay > 60 or (retry and not retry.isdigit()):
                raise RuntimeError('CoinGecko requests a later retry; stopped without retrying early') from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('CoinGecko transport failed after 3 attempts') from None
            delay = 15 * 2**attempt
        emit('coingecko_fetch', 'retry', attempt=attempt + 1, delay_seconds=delay)
        time.sleep(delay)


def capture(raw_dir, key=None):
    """Each genuine capture has a unique directory; a manifest makes offline replay explicit."""
    directory = Path(raw_dir) / uuid.uuid4().hex
    directory.mkdir(parents=True)
    manifest = {'version': 1, 'responses': {}}
    for name, endpoint in ENDPOINTS.items():
        body = request_bytes(endpoint, key)
        retrieved = datetime.now(timezone.utc)
        path = directory / (name + '.json')
        path.write_bytes(body)
        manifest['responses'][name] = {
            'endpoint': endpoint, 'retrieved_at_ms': int(retrieved.timestamp() * 1000),
            'sha256': hashlib.sha256(body).hexdigest(),
        }
        emit('coingecko_fetch', 'saved', file=str(path), bytes=len(body))
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return directory
