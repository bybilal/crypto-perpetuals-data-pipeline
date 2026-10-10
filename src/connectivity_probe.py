import json
import urllib.request
import urllib.error

URL = (
    "https://fapi.binance.com/fapi/v1/klines"
    "?symbol=BTCUSDT&interval=30m&limit=2"
)

try:
    with urllib.request.urlopen(URL, timeout=10) as response:
        data = json.load(response)

        print("HTTP status:", response.status)
        print("Candles returned:", len(data))
        print(json.dumps(data, indent=2))

except urllib.error.HTTPError as error:
    print("HTTP error:", error.code)
    print(error.read().decode("utf-8", errors="replace"))

except urllib.error.URLError as error:
    print("Connection error:", error.reason)