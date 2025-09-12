# blockchain.py
from __future__ import annotations

import os
import re
import requests
import logging
from typing import Optional

from .config import ETHERSCAN_API_KEY, ALCHEMY_API_KEY, SUI_RPC_URL, HELIUS_API_KEY

logger = logging.getLogger(__name__)

# --------- Helpers ---------
def _is_valid_evm_address(addr: str) -> bool:
    """Check if a string is a valid Ethereum-style 0x... address"""
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", addr))


# --------- EVM balance check (ERC-20) ---------
def _is_holder_evm(address: str, contract: str, min_amount: int = 1, chain: str = "eth") -> bool:
    """Check if an EVM wallet holds at least `min_amount` tokens of a given ERC20 contract"""
    try:
        if not _is_valid_evm_address(address) or not _is_valid_evm_address(contract):
            logger.debug("Invalid EVM address or contract: %s %s", address, contract)
            return False

        # First: try Alchemy JSON-RPC if available for the chain
        alchemy_map = {
            "eth": f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else None,
            "base": f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else None,
            # add other alchemy-supported chains if needed
        }
        rpc = alchemy_map.get(chain)
        if rpc:
            # ERC20 balanceOf(address) selector: 70a08231
            addr_padded = address.lower().replace("0x", "").rjust(64, "0")
            data = "0x70a08231" + addr_padded
            payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": contract, "data": data}, "latest"]}
            logger.debug("Calling Alchemy RPC %s for contract %s address %s", rpc, contract, address)
            r = requests.post(rpc, json=payload, timeout=10)
            r.raise_for_status()
            res = r.json().get("result")
            if res:
                balance = int(res, 16)
                logger.debug("Alchemy returned balance %s for %s on %s", balance, address, chain)
                return balance >= int(min_amount)

        # Fallback: Etherscan-style tokenbalance endpoint
        apis = {
            "eth": ("https://api.etherscan.io/api", ETHERSCAN_API_KEY or os.getenv("ETHERSCAN_API_KEY", "")),
            "base": ("https://api.basescan.org/api", os.getenv("BASESCAN_API_KEY", "")),
            "bsc": ("https://api.bscscan.com/api", os.getenv("BSCSCAN_API_KEY", "")),
        }
        base_url, key = apis.get(chain, (None, None))
        if not base_url:
            logger.warning("No API configured for chain %s", chain)
            return False
        params = {
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": contract,
            "address": address,
            "tag": "latest",
            "apikey": key
        }
        logger.debug("Querying %s tokenbalance for %s", base_url, address)
        r = requests.get(base_url, params=params, timeout=10)
        r.raise_for_status()
        resp_json = r.json()
        status = resp_json.get("status")
        if status in ("1", 1):
            balance = int(resp_json.get("result", "0"))
            logger.debug("API returned balance %s", balance)
            return balance >= int(min_amount)
        else:
            logger.debug("API response status not success: %s %s", status, resp_json.get("message"))
    except Exception as exc:
        logger.exception("Error in _is_holder_evm: %s", exc)
    return False


# --------- Solana SPL via Helius ---------
def _is_holder_solana(address: str, mint: str, min_amount: int = 1) -> bool:
    """Check if Solana address holds SPL token using Helius RPC"""
    try:
        if not HELIUS_API_KEY:
            logger.warning("HELIUS_API_KEY not configured")
            return False
        url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "id": "check",
            "method": "getTokenAccountsByOwner",
            "params": [address, {"mint": mint}, {"encoding": "jsonParsed"}]
        }
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        res = r.json().get("result", {}).get("value", [])
        for acc in res:
            amount = int(acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
            if amount >= int(min_amount):
                logger.debug("Solana account %s has amount %s for mint %s", address, amount, mint)
                return True
    except Exception as exc:
        logger.exception("Error in _is_holder_solana: %s", exc)
    return False


# --------- Sui via RPC ---------
def _is_holder_sui(address: str, coin_type: str, min_amount: int = 1) -> bool:
    """Check if Sui address holds at least `min_amount` tokens of a given coin type"""
    try:
        if not SUI_RPC_URL:
            logger.warning("SUI_RPC_URL not configured")
            return False
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "suix_getBalance",
            "params": [address, coin_type]
        }
        r = requests.post(SUI_RPC_URL, json=payload, timeout=10)
        r.raise_for_status()
        total = int(r.json().get("result", {}).get("totalBalance", 0))
        logger.debug("Sui totalBalance=%s for %s coin_type=%s", total, address, coin_type)
        return total >= int(min_amount)
    except Exception as exc:
        logger.exception("Error in _is_holder_sui: %s", exc)
    return False


# --------- Router ---------
def is_token_holder(network: str, address: str, contract: str, min_amount: int = 1) -> bool:
    """Main router to check token holder status across networks"""
    network = (network or "").lower()
    if network in ("eth", "base", "bsc"):
        return _is_holder_evm(address, contract, min_amount, chain=network)
    if network in ("sol", "solana"):
        return _is_holder_solana(address, contract, min_amount)
    if network == "sui":
        return _is_holder_sui(address, contract, min_amount)
    if network == "pumpfun":
        # PumpFun tokens live on Solana; reuse SPL logic
        return _is_holder_solana(address, contract, min_amount)
    logger.warning("Unsupported network: %s", network)
    return False
