# Import json for use below.
import json
# Import urllib.request for use below.
import urllib.request
# Import urllib.error for use below.
import urllib.error

# Set the explicit starting value; store the result in URL.
URL = (
    "https://fapi.binance.com/fapi/v1/klines"
    "?symbol=BTCUSDT&interval=30m&limit=2"
)

# Run this operation with the error handling and cleanup defined below.
try:
    # Manage urllib.request.urlopen(URL, timeout=10) with automatic context cleanup on exit.
    with urllib.request.urlopen(URL, timeout=10) as response:
        # Parse the response stream as JSON; store the result in data.
        data = json.load(response)

        # Write the formatted output to the terminal.
        print("HTTP status:", response.status)
        # Write the formatted output to the terminal.
        print("Candles returned:", len(data))
        # Write the formatted output to the terminal.
        print(json.dumps(data, indent=2))

except urllib.error.HTTPError as error:
    # Write the formatted output to the terminal.
    print("HTTP error:", error.code)
    # Write the formatted output to the terminal.
    print(error.read().decode("utf-8", errors="replace"))

except urllib.error.URLError as error:
    # Write the formatted output to the terminal.
    print("Connection error:", error.reason)