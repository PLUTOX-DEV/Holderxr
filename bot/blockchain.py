from __future__ import annotations
import os, requests, re
from .config import ETHERSCAN_API_KEY, ALCHEMY_API_KEY, SUI_RPC_URL, HELIUS_API_KEY

# --------- EVM balance check (ERC-20) ---------
def _is_holder_evm(address: str, contract: str, min_amount: int = 1, chain: str = "eth") -> bool:
    try:
        # Try Alchemy first when supported
        alchemy_map = {
            "eth": f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else None,
            "base": f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else None,
            "bsc": None,  # Not on Alchemy standard
        }
        rpc = alchemy_map.get(chain)
        if rpc:
            if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address) or not re.fullmatch(r"0x[a-fA-F0-9]{40}", contract):
                return False
            payload = {
                "jsonrpc":"2.0",
                "id":1,
                "method":"eth_call",
                "params":[
                    {
                        "to": contract,
                        "data": "0x70a08231" + "0"*24 + address.lower().replace("0x","").rjust(40, "0")
                    },
                    "latest"
                ]
            }
            r = requests.post(rpc, json=payload, timeout=10)
            if r.ok:
                res = r.json().get("result")
                if res:
                    balance = int(res, 16)
                    return balance > 0
        # Etherscan-style APIs
        apis = {
            "eth": ("https://api.etherscan.io/api", os.getenv("ETHERSCAN_API_KEY","")),
            "base": ("https://api.basescan.org/api", os.getenv("BASESCAN_API_KEY","")),
            "bsc": ("https://api.bscscan.com/api", os.getenv("BSCSCAN_API_KEY","")),
        }
        base_url, key = apis[chain]
        params = {
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": contract,
            "address": address,
            "tag": "latest",
            "apikey": key
        }
        r = requests.get(base_url, params=params, timeout=10)
        if r.ok and r.json().get("status") in ("1", 1):
            balance = int(r.json().get("result","0"))
            return balance > 0
    except Exception:
        pass
    return False

# --------- Solana SPL via Helius ---------
def _is_holder_solana(address: str, mint: str, min_amount: int = 1) -> bool:
    try:
        if not HELIUS_API_KEY:
            return False
        url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "id": "check",
            "method": "getTokenAccountsByOwner",
            "params": [
                address,
                {"mint": mint},
                {"encoding": "jsonParsed"}
            ]
        }
        r = requests.post(url, json=payload, timeout=10)
        if r.ok:
            res = r.json().get("result", {}).get("value", [])
            for acc in res:
                amount = int(acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
                if amount > 0:
                    return True
    except Exception:
        pass
    return False

# --------- Sui via RPC ---------
def _is_holder_sui(address: str, coin_type: str, min_amount: int = 1) -> bool:
    try:
        payload = {
            "jsonrpc":"2.0",
            "id":1,
            "method":"suix_getBalance",
            "params":[address, coin_type]
        }
        r = requests.post(SUI_RPC_URL, json=payload, timeout=10)
        if r.ok:
            total = int(r.json().get("result", {}).get("totalBalance", 0))
            return total > 0
    except Exception:
        pass
    return False

# --------- Router ---------
def is_token_holder(network: str, address: str, contract: str, min_amount: int = 1) -> bool:
    network = network.lower()
    if network in ("eth", "base", "bsc"):
        return _is_holder_evm(address, contract, min_amount, chain=network)
    if network == "sol":
        return _is_holder_solana(address, contract, min_amount)
    if network == "sui":
        return _is_holder_sui(address, contract, min_amount)
    if network == "pumpfun":
        # PumpFun tokens live on Solana; reuse SPL logic
        return _is_holder_solana(address, contract, min_amount)
    return False
