import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_USERNAMES = [u.strip() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()]

# API keys
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "").strip()
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "").strip()
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "").strip()
BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY", "").strip()
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
SUI_RPC_URL = os.getenv("SUI_RPC_URL", "https://fullnode.mainnet.sui.io:443").strip()
CHANNEL_ID = "@YourChannelUsername"
BOT_USERNAME = "holderxrbot"

# Supported networks
NETWORKS = {
    "sol": "Solana",
    "eth": "Ethereum",
    "base": "Base",
    "bsc": "BNB Smart Chain",
    "sui": "Sui",
    "pumpfun": "PumpFun (Solana)",
}

DEFAULT_MIN_AMOUNT = 1
