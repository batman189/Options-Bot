"""ThetaData v3 real-time snapshot client (Standard plan).
All returned values validated. v3 only (v2 deprecated)."""

import logging
import requests
from data.data_validation import validate_field, DataValidationError

logger = logging.getLogger("options-bot.data.theta_snapshot")

BASE_URL = "http://127.0.0.1:25503/v3"
TIMEOUT = 10


def _get(endpoint: str, params: dict) -> dict:
    """Make a GET request to ThetaData v3 and return parsed JSON."""
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    if resp.status_code == 403:
        raise DataValidationError(
            f"[ThetaData] {endpoint}: subscription insufficient ({resp.text[:100]})"
        )
    if resp.status_code == 472:
        raise DataValidationError(f"[ThetaData] {endpoint}: no data found")
    if resp.status_code != 200:
        raise DataValidationError(
            f"[ThetaData] {endpoint}: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    return resp.json()


class ThetaSnapshotClient:
    """Real-time option snapshots from ThetaData Terminal v3."""

    def get_first_order_greeks(self, symbol: str, expiration: str,
                                strike: float, right: str) -> dict:
        """Fetch delta, theta, vega, rho, IV for a single contract.

        Returns dict with validated fields: delta, theta, vega, rho,
        implied_vol, underlying_price.
        """
        data = _get("option/snapshot/greeks/first_order", {
            "symbol": symbol, "expiration": expiration,
            "strike": f"{strike:.2f}", "right": right, "format": "json",
        })
        rows = data.get("response", [])
        if not rows or not rows[0].get("data"):
            raise DataValidationError(
                f"[ThetaData] No Greeks for {symbol} {right} ${strike} exp={expiration}"
            )
        d = rows[0]["data"][0]

        return {
            "delta": validate_field(d.get("delta"), "delta", "ThetaData"),
            "theta": validate_field(d.get("theta"), "theta", "ThetaData"),
            "vega": d.get("vega", 0) or 0,  # Can be near-zero for 0DTE
            "rho": d.get("rho", 0) or 0,
            "implied_vol": validate_field(d.get("implied_vol"), "implied_vol", "ThetaData", nonzero=True),
            "underlying_price": validate_field(d.get("underlying_price"), "underlying_price", "ThetaData", nonzero=True),
        }

    def get_implied_volatility(self, symbol: str, expiration: str,
                                strike: float, right: str) -> dict:
        """Fetch IV + bid/ask for a single contract.

        Returns dict with validated fields: implied_vol, bid, ask,
        underlying_price.
        """
        data = _get("option/snapshot/greeks/implied_volatility", {
            "symbol": symbol, "expiration": expiration,
            "strike": f"{strike:.2f}", "right": right, "format": "json",
        })
        rows = data.get("response", [])
        if not rows or not rows[0].get("data"):
            raise DataValidationError(
                f"[ThetaData] No IV for {symbol} {right} ${strike} exp={expiration}"
            )
        d = rows[0]["data"][0]

        return {
            "implied_vol": validate_field(d.get("implied_vol"), "implied_vol", "ThetaData", nonzero=True),
            "bid": validate_field(d.get("bid"), "bid", "ThetaData", min_val=0),
            "ask": validate_field(d.get("ask"), "ask", "ThetaData", min_val=0),
            "underlying_price": validate_field(d.get("underlying_price"), "underlying_price", "ThetaData", nonzero=True),
        }

    def get_expirations(self, symbol: str) -> list[str]:
        """Fetch all available expiration dates for a symbol.
        Returns sorted list of date strings (YYYY-MM-DD)."""
        data = _get("option/list/expirations", {
            "symbol": symbol, "format": "json",
        })
        return sorted(r["expiration"] for r in data.get("response", []))

    def get_open_interest_bulk(self, symbol: str, expiration: str) -> list[dict]:
        """Fetch OI for all contracts on an expiration.

        Returns list of dicts with: strike, right, open_interest.
        Each OI value is validated (must be non-negative).
        """
        data = _get("option/snapshot/open_interest", {
            "symbol": symbol, "expiration": expiration, "format": "json",
        })
        rows = data.get("response", [])
        results = []
        for row in rows:
            contract = row.get("contract", {})
            oi_data = row.get("data", [{}])
            oi = oi_data[0].get("open_interest", 0) if oi_data else 0
            validate_field(oi, f"OI {contract.get('right','')} ${contract.get('strike','')}", "ThetaData", min_val=0)
            results.append({
                "strike": contract.get("strike"),
                "right": contract.get("right", "").upper(),
                "open_interest": oi,
            })
        return results

    def get_quotes_bulk(self, symbol: str, expiration: str) -> list[dict]:
        """Fetch bid/ask + volume for all contracts. Quote endpoint for bid/ask, OHLC for volume."""
        # Get real bid/ask from quote endpoint
        quote_data = _get("option/snapshot/quote", {
            "symbol": symbol, "expiration": expiration, "format": "json",
        })
        # Get volume from OHLC endpoint (quote doesn't include volume)
        ohlc_data = _get("option/snapshot/ohlc", {
            "symbol": symbol, "expiration": expiration, "format": "json",
        })

        # Build volume lookup
        vol_map = {}
        for row in ohlc_data.get("response", []):
            c = row.get("contract", {})
            d = row.get("data", [{}])
            vol = d[0].get("volume", 0) if d else 0
            vol_map[(c.get("strike"), c.get("right", "").upper())] = vol

        rows = quote_data.get("response", [])
        results = []
        for row in rows:
            contract = row.get("contract", {})
            qdata = row.get("data", [{}])
            d = qdata[0] if qdata else {}
            strike = contract.get("strike")
            right = contract.get("right", "").upper()
            bid = validate_field(d.get("bid"), f"bid {right} ${strike}", "ThetaData", min_val=0)
            ask = validate_field(d.get("ask"), f"ask {right} ${strike}", "ThetaData", min_val=0)
            volume = vol_map.get((strike, right), 0)
            results.append({
                "strike": strike,
                "right": right,
                "bid": bid,
                "ask": ask,
                "volume": volume,
            })
        return results
