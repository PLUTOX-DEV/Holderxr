from __future__ import annotations
import requests
import logging

logger = logging.getLogger(__name__)

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/"
COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/token_price/{platform}?contract_addresses={contract}&vs_currencies=usd&include_market_cap=true"


def get_dexscreener_info(contract: str) -> dict | None:
    """Fetch token info from Dexscreener API"""
    try:
        r = requests.get(DEXSCREENER_URL + contract, timeout=10)
        r.raise_for_status()
        data = r.json()
        pairs = data.get("pairs") or []
        if not pairs:
            return None

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

    except Exception as e:
        logger.warning("Dexscreener fetch failed for %s: %s", contract, e)
        return None


def get_coingecko_info(platform: str, contract: str) -> dict | None:
    """Fetch token price and market cap from CoinGecko"""
    try:
        url = COINGECKO_SIMPLE.format(platform=platform, contract=contract)
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        obj = data.get(contract.lower())
        if not obj:
            return None

        return {
            "priceUsd": obj.get("usd"),
            "marketCap": obj.get("usd_market_cap"),
        }

    except Exception as e:
        logger.warning("CoinGecko fetch failed for %s on %s: %s", contract, platform, e)
        return None
