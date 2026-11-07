"""Atomic Bitcoin-only loading of a complete, checksum-verified capture."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from .foundation import measurement_text
from ..coingecko import ENDPOINTS
from ..events import emit


def decode(body):
    return json.loads(body, parse_float=Decimal, parse_int=Decimal,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def normalize(body, category_body):
    """Resolve category names only against unique provider-supplied IDs, never slugify."""
    coin, definitions = decode(body), decode(category_body)
    if not isinstance(coin, dict) or coin.get('id') != 'bitcoin':
        raise ValueError('Only CoinGecko bitcoin is supported')
    market = coin.get('market_data')
    if not isinstance(market, dict) or not market:
        raise ValueError('Missing market_data')
    stamp = market.get('last_updated')
    timestamp = None
    if stamp is not None:
        dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('Provider timestamp must include timezone')
        delta = dt.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        timestamp = delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000
        if timestamp < 0:
            raise ValueError('Negative provider timestamp')
    def usd(field):
        value = market.get(field)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError('Expected currency map: ' + field)
        return measurement_text(value.get('usd'))
    values = [usd('current_price'), usd('market_cap'), usd('fully_diluted_valuation')]
    values += [measurement_text(market.get(f)) for f in ('circulating_supply','total_supply','max_supply')]
    values += [usd('total_volume')]
    if not isinstance(definitions, list):
        raise ValueError('Category definitions must be a list')
    names, ids = {}, set()
    for item in definitions:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in ('name','category_id')):
            raise ValueError('Invalid category definition')
        if item['category_id'] in ids:
            raise ValueError('Duplicate category ID')
        ids.add(item['category_id'])
        names.setdefault(item['name'], []).append(item['category_id'])
    memberships = coin.get('categories')
    if not isinstance(memberships, list) or any(not isinstance(n,str) for n in memberships):
        raise ValueError('Missing or malformed category memberships')
    selected = []
    for name in sorted(set(memberships)):
        if len(names.get(name, [])) != 1:
            raise ValueError('Missing or ambiguous category mapping: ' + name)
        selected.append((names[name][0], name))
    return timestamp, values, selected


def ingest(connection, directory):
    """Caller owns transaction. Duplicate source paths must retain identical bytes and times."""
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('version') != 1:
        raise ValueError('Unsupported capture manifest')
    bodies = {}
    for name, endpoint in ENDPOINTS.items():
        meta = manifest['responses'][name]
        body = (directory / (name + '.json')).read_bytes()
        if meta['endpoint'] != endpoint or hashlib.sha256(body).hexdigest() != meta['sha256']:
            raise ValueError('Capture checksum or endpoint mismatch')
        if type(meta['retrieved_at_ms']) is not int or meta['retrieved_at_ms'] < 0:
            raise ValueError('Invalid retrieval timestamp')
        bodies[name] = body
    timestamp, values, selected = normalize(bodies['bitcoin'], bodies['categories'])
    mapping = connection.execute("SELECT canonical_id FROM provider_assets WHERE provider='coingecko' AND provider_coin_id='bitcoin'").fetchone()
    if mapping != ('asset:bitcoin',):
        raise ValueError('Verified Bitcoin provider mapping is required')
    sources = {}
    inserted_sources = 0
    for name in ENDPOINTS:
        meta = manifest['responses'][name]
        key = str(directory / (name + '.json'))
        row = connection.execute("SELECT id,sha256,retrieved_at_ms FROM market_sources WHERE provider='coingecko' AND source_key=?", (key,)).fetchone()
        if row:
            if row[1:] != (meta['sha256'], meta['retrieved_at_ms']):
                raise ValueError('Previously indexed source was modified')
            sources[name] = row[0]
        else:
            sources[name] = connection.execute("INSERT INTO market_sources(provider,source_key,retrieved_at_ms,sha256) VALUES ('coingecko',?,?,?)",(key,meta['retrieved_at_ms'],meta['sha256'])).lastrowid
            inserted_sources += 1
    source = sources['bitcoin']
    added = connection.execute("""INSERT INTO market_snapshots VALUES ('coingecko','bitcoin',?,?,'USD',?,?,?,?,?,?,?)
        ON CONFLICT(source_id,provider_coin_id,currency) DO NOTHING""",(source,timestamp,*values)).rowcount
    for category_id, name in selected:
        # Existing category definitions remain historical first-seen rows in this milestone.
        connection.execute("INSERT INTO categories VALUES ('coingecko',?,?,?) ON CONFLICT(provider,category_id) DO NOTHING",(category_id,name,sources['categories']))
        connection.execute("INSERT INTO asset_categories VALUES ('coingecko','bitcoin',?,?) ON CONFLICT DO NOTHING",(category_id,source))
    result = {'sources_added': inserted_sources, 'snapshots_added': added, 'categories':len(selected),
              'source_id':source, 'provider_timestamp_ms':timestamp, 'price_usd':values[0]}
    emit('coingecko_load','processed',**result)
    return result
