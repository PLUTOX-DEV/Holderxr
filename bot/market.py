from __future__ import annotations
import requests

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/"
COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/token_price/{platform}?contract_addresses={contract}&vs_currencies=usd&include_market_cap=true"

def get_dexscreener_info(contract: str) -> dict | None:
    try:
        r = requests.get(DEXSCREENER_URL + contract, timeout=10)
        if r.ok:
            data = r.json()
            pairs = data.get("pairs") or []
            if pairs:
                top = pairs[0]
                return {
                    "token": top.get("baseToken", {}).get("name"),
                    "symbol": top.get("baseToken", {}).get("symbol"),
                    "priceUsd": top.get("priceUsd"),
                    "fdv": top.get("fdv"),
                    "liquidity": top.get("liquidity", {}).get("usd"),
                    "chain": top.get("chainId"),
                    "dex": top.get("dexId"),
                }
    except Exception:
        pass
    return None

def get_coingecko_info(platform: str, contract: str) -> dict | None:
    try:
        url = COINGECKO_SIMPLE.format(platform=platform, contract=contract)
        r = requests.get(url, timeout=10)
        if r.ok:
            data = r.json()
            obj = data.get(contract.lower())
            if obj:
                return {
                    "priceUsd": obj.get("usd"),
                    "marketCap": obj.get("usd_market_cap"),
                }
    except Exception:
        pass
    return None
