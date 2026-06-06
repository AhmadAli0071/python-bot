# Polymarket Trading Bot - Setup Guide

## Bot kya karta hai?
- Polymarket ke saare active markets scan karta hai
- Web UI se settings change kar sakte ho (price, side, amount)
- Jab chosen side ka price target pe pahunche, automatically trade open hoti hai
- Example: Target = 97 cents, Side = NO → Jab NO price 97 cents ho, NO buy karo

## Step 1: Python Install Karo

Python 3.10+ install karo (agar nahi hai)
- Download: https://www.python.org/downloads/
- Install karte waqt **"Add Python to PATH"** checkbox zaroor tick karo

## Step 2: Dependencies Install Karo

```bash
cd E:\Poly
pip install -r requirements.txt
```

## Step 3: Polymarket Wallet Setup

1. MetaMask wallet install karo (browser extension)
2. Polygon network add karo MetaMask mein
3. Wallet mein **pUSD** (trading ke liye) aur **POL** (gas ke liye) deposit karo
4. Polymarket.com pe jaake wallet connect karo
5. MetaMask > Account Details > Export Private Key se private key copy karo

## Step 4: .env File Setup

`.env` file kholo aur apni details dalo:

```
PRIVATE_KEY=0x_your_private_key_here
WALLET_ADDRESS=0x_your_meta_mask_address
API_KEY=leave_empty_for_now
API_SECRET=leave_empty_for_now
API_PASSPHRASE=leave_empty_for_now
```

## Step 5: API Keys Generate Karo

```bash
python -c "from bot import TradingBot; TradingBot.setup_api_keys()"
```

Ye command API keys print karegi. Jo values aayengi unko `.env` file mein paste karo.

## Step 6: Bot Chalao

```bash
python app.py
```

Browser mein open karo: **http://127.0.0.1:5000**

## Web UI Features

| Feature | Description |
|---------|-------------|
| Target Price | Cents mein set karo (1-99), trade is threshold pe trigger hogi |
| Trade Side | YES ya NO toggle karo |
| Trade Amount | Fixed USDT per trade |
| Scan Interval | Kitne seconds mein scan kare |
| Start/Stop | Bot on/off karo |
| Live Logs | Real-time bot activity dekho |
| Trade History | Saari trades ki list |

## Files

| File | Description |
|------|-------------|
| `app.py` | Flask web server (ye chalao) |
| `bot.py` | Bot engine (background) |
| `config.py` | Settings management |
| `config.json` | Saved settings (auto-generated) |
| `templates/index.html` | Web UI |
| `.env` | Your credentials (PRIVATE!) |
| `traded_markets.json` | Trade history (auto-generated) |

## Important Notes

- `.env` file **kabhi share mat karo** - isme private key hai
- Pehle chhote amount ($1-2) se test karo
- Trading mein risk hai - sirf woh paise lagao jo lose ho sakein
- Bot ko computer ya VPS pe chalte rehne do continuous trading ke liye
- UI se settings change karne ka faayda ye hai ki bot restart ki zaroorat nahi
