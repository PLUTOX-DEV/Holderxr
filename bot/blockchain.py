from __future__ import annotations

import os
import re
import requests
import logging
from typing import Optional, Dict

from .config import (
    ETHERSCAN_API_KEY,
    ALCHEMY_API_KEY,
    SUI_RPC_URL,
    HELIUS_API_KEY,
)

logger = logging.getLogger(__name__)

# ===========================
# Helpers
# ===========================

def _is_valid_evm_address(addr: str) -> bool:
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", addr))


# ===========================
# TOKEN METADATA (ERC20)
# ===========================

def get_token_meta(network: str, contract: str) -> Optional[Dict[str, str]]:
    """
    Fetch ERC20 token name & symbol.
    Returns: { "name": str, "symbol": str } or None
    """
    try:
        network = (network or "eth").lower()

        if network not in ("eth", "base", "bsc"):
            return None

        if not _is_valid_evm_address(contract):
            return None

        # Prefer Alchemy
        alchemy_urls = {
            "eth": f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
            "base": f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
        }

        rpc = alchemy_urls.get(network)
        if rpc and ALCHEMY_API_KEY:
            def eth_call(sig: str) -> str:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [{"to": contract, "data": sig}, "latest"],
                }
                r = requests.post(rpc, json=payload, timeout=10)
                r.raise_for_status()
                return r.json().get("result", "")

            # name() → 0x06fdde03
            # symbol() → 0x95d89b41
            name_hex = eth_call("0x06fdde03")
            symbol_hex = eth_call("0x95d89b41")

            if name_hex and symbol_hex:
                name = bytes.fromhex(name_hex[130:]).decode("utf-8", errors="ignore").strip("\x00")
                symbol = bytes.fromhex(symbol_hex[130:]).decode("utf-8", errors="ignore").strip("\x00")

                if name and symbol:
                    return {"name": name, "symbol": symbol}

        # --------- Fallback: Etherscan-style APIs ---------
        api_map = {
            "eth": ("https://api.etherscan.io/api", ETHERSCAN_API_KEY),
            "base": ("https://api.basescan.org/api", os.getenv("BASESCAN_API_KEY")),
            "bsc": ("https://api.bscscan.com/api", os.getenv("BSCSCAN_API_KEY")),
        }

        base_url, api_key = api_map.get(network, (None, None))
        if not base_url or not api_key:
            return None

        params = {
            "module": "token",
            "action": "tokeninfo",
            "contractaddress": contract,
            "apikey": api_key,
        }

        r = requests.get(base_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("result")

        if isinstance(data, list) and data:
            return {
                "name": data[0].get("tokenName"),
                "symbol": data[0].get("symbol"),
            }

    except Exception as exc:
        logger.exception("get_token_meta failed: %s", exc)

    return None


# ===========================
# HOLDER CHECK — EVM
# ===========================

def _is_holder_evm(address: str, contract: str, min_amount: int = 1, chain: str = "eth") -> bool:
    try:
        if not _is_valid_evm_address(address) or not _is_valid_evm_address(contract):
            return False

        alchemy_map = {
            "eth": f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
            "base": f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
        }

        rpc = alchemy_map.get(chain)
        if rpc and ALCHEMY_API_KEY:
            addr_padded = address.lower().replace("0x", "").rjust(64, "0")
            data = "0x70a08231" + addr_padded

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_call",
                "params": [{"to": contract, "data": data}, "latest"],
            }

            r = requests.post(rpc, json=payload, timeout=10)
            r.raise_for_status()
            result = r.json().get("result")

            if result:
                return int(result, 16) >= int(min_amount)

        api_map = {
            "eth": ("https://api.etherscan.io/api", ETHERSCAN_API_KEY),
            "base": ("https://api.basescan.org/api", os.getenv("BASESCAN_API_KEY")),
            "bsc": ("https://api.bscscan.com/api", os.getenv("BSCSCAN_API_KEY")),
        }

        base_url, key = api_map.get(chain, (None, None))
        if not base_url:
            return False

        params = {
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": contract,
            "address": address,
            "tag": "latest",
            "apikey": key,
        }

        r = requests.get(base_url, params=params, timeout=10)
        r.raise_for_status()

        if r.json().get("status") in ("1", 1):
            return int(r.json().get("result", 0)) >= int(min_amount)

    except Exception as exc:
        logger.exception("_is_holder_evm error: %s", exc)

    return False


# ===========================
# SOLANA (Helius)
# ===========================

def _is_holder_solana(address: str, mint: str, min_amount: int = 1) -> bool:
    try:
        if not HELIUS_API_KEY:
            return False

        url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "id": "check",
            "method": "getTokenAccountsByOwner",
            "params": [address, {"mint": mint}, {"encoding": "jsonParsed"}],
        }

        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()

        for acc in r.json().get("result", {}).get("value", []):
            amount = int(acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
            if amount >= int(min_amount):
                return True

    except Exception as exc:
        logger.exception("_is_holder_solana error: %s", exc)

    return False


# ===========================
# SUI
# ===========================

def _is_holder_sui(address: str, coin_type: str, min_amount: int = 1) -> bool:
    try:
        if not SUI_RPC_URL:
            return False

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "suix_getBalance",
            "params": [address, coin_type],
        }

        r = requests.post(SUI_RPC_URL, json=payload, timeout=10)
        r.raise_for_status()

        total = int(r.json().get("result", {}).get("totalBalance", 0))
        return total >= int(min_amount)

    except Exception as exc:
        logger.exception("_is_holder_sui error: %s", exc)

    return False


# ===========================
# ROUTER
# ===========================

def is_token_holder(network: str, address: str, contract: str, min_amount: int = 1) -> bool:
    network = (network or "").lower()

    if network in ("eth", "base", "bsc"):
        return _is_holder_evm(address, contract, min_amount, chain=network)

    if network in ("sol", "solana", "pumpfun"):
        return _is_holder_solana(address, contract, min_amount)

    if network == "sui":
        return _is_holder_sui(address, contract, min_amount)

    logger.warning("Unsupported network: %s", network)
    return False
