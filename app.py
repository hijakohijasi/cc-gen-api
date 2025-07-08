from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import random
import aiohttp
import os
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import Response


app = FastAPI(
    title="Public CC Generator API",
    description="API for generating valid credit card numbers with BIN information (No Authentication Required)",
    version="1.0",
    contact={
        "name": "API Support",
        "url": "https://t.me/TheSmartDev",
    },
    license_info={
        "name": "MIT",
    },
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MAX_GEN_LIMIT = 50  # Maximum cards per request
DEFAULT_GEN_LIMIT = 5  # Default cards if limit not specified

# Models
class CardInfo(BaseModel):
    number: str
    expiry: str
    cvv: str
    brand: Optional[str] = None
    type: Optional[str] = None

class BinInfo(BaseModel):
    bin: str
    bank: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    flag: Optional[str] = None
    scheme: Optional[str] = None
    type: Optional[str] = None
    prepaid: Optional[bool] = None
    tier: Optional[str] = None
    currency: Optional[str] = None

class GenerateResponse(BaseModel):
    cards: List[CardInfo]
    bin_info: BinInfo
    generated_at: str

# Helper Functions
def luhn_checksum(card_number: str) -> bool:
    """Validate card number using Luhn algorithm with double verification"""
    if not card_number.isdigit():
        return False

    total = 0
    reverse_digits = card_number[::-1]

    for i, digit in enumerate(reverse_digits):
        digit = int(digit)
        if i % 2 == 1:  # Double every second digit
            digit *= 2
            if digit > 9:
                digit = (digit // 10) + (digit % 10)
        total += digit

    return total % 10 == 0

def generate_card_number(bin: str) -> str:
    """Generate valid card number from BIN with triple Luhn verification"""
    # Clean the BIN (remove non-digits)
    clean_bin = re.sub(r'[^\d]', '', bin)

    # Validate BIN length
    if len(clean_bin) < 6 or len(clean_bin) > 15:
        raise ValueError("BIN must be between 6-15 digits")

    # Generate the base number (BIN + random digits, leaving room for check digit)
    missing_digits = 15 - len(clean_bin)
    if missing_digits < 0:
        raise ValueError("BIN too long")

    # Generate random middle digits
    middle_digits = ''.join([str(random.randint(0, 9)) for _ in range(missing_digits)])
    partial_number = clean_bin + middle_digits

    # Calculate Luhn check digit
    total = 0
    for i, digit in enumerate(partial_number[::-1]):
        digit = int(digit)
        if i % 2 == 0:  # Double every second digit from right (0-indexed)
            digit *= 2
            if digit > 9:
                digit = (digit // 10) + (digit % 10)
        total += digit

    check_digit = (10 - (total % 10)) % 10
    full_number = partial_number + str(check_digit)

    # Triple verification
    if not luhn_checksum(full_number):
        # If failed, regenerate (should theoretically never happen)
        return generate_card_number(bin)

    # Additional format check
    if len(full_number) not in (15, 16) or not full_number.isdigit():
        return generate_card_number(bin)

    return full_number

def generate_expiry() -> tuple:
    """Generate random future expiry date"""
    expiry_date = datetime.now() + timedelta(days=random.randint(365, 365*5))
    return (expiry_date.strftime("%m"), expiry_date.strftime("%y"))

def generate_cvv(card_type: Optional[str]) -> str:
    """Generate random CVV with correct length for card type"""
    if card_type and "amex" in card_type.lower():
        return str(random.randint(1000, 9999))  # Amex has 4-digit CVV
    return str(random.randint(100, 999))  # Others have 3-digit CVV

async def get_bin_info(bin: str) -> Optional[dict]:
    """Fetch BIN information from multiple public APIs"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    bin_to_use = bin[:6]

    # 1. Try HandyAPI first
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://data.handyapi.com/bin/{bin_to_use}",
                headers={**headers, "x-api-key": "handyapi-pub-4c5376b7b41649ce93d4b7f93984f088"}
            ) as res:
                if res.status == 200:
                    data = await res.json()
                    if data.get("Status") == "SUCCESS":
                        country = data.get("Country", {}).get("Name", "").upper()
                        return {
                            "type": data.get("Type"),
                            "scheme": data.get("Scheme"),
                            "tier": data.get("CardTier"),
                            "bank": data.get("Issuer"),
                            "country": country,
                            "currency": "N/A",
                            "country_code": data.get("Country", {}).get("A2", "N/A"),
                            "flag": get_flag_emoji(data.get("Country", {}).get("A2")),
                            "prepaid": data.get("Prepaid") == "Yes",
                            "luhn": True
                        }
    except Exception as e:
        print("HandyAPI error:", e)

    # 2. Fallback to binlist.net
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://lookup.binlist.net/{bin_to_use}", 
                headers=headers
            ) as res:
                if res.status == 200:
                    data = await res.json()
                    country = data.get("country", {}).get("name", "").upper()
                    return {
                        "type": data.get("type"),
                        "scheme": data.get("scheme"),
                        "tier": data.get("brand"),
                        "bank": data.get("bank", {}).get("name"),
                        "country": country,
                        "currency": data.get("country", {}).get("currency"),
                        "country_code": data.get("country", {}).get("alpha2"),
                        "flag": data.get("country", {}).get("emoji", "🏳️"),
                        "prepaid": data.get("prepaid", False),
                        "luhn": data.get("number", {}).get("luhn", True)
                    }
    except Exception as e:
        print("binlist.net error:", e)

    return None

def get_flag_emoji(country_code: str) -> str:
    """Get flag emoji from country code"""
    if not country_code or len(country_code) != 2:
        return "🏳️"
    try:
        return chr(0x1F1E6 + ord(country_code[0].upper())-65) + chr(0x1F1E6 + ord(country_code[1].upper())-65)
    except:
        return "🏳️"

# API Endpoints
@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "Public CC Generator API",
        "endpoints": {
            "/generate": "Generate CCs (JSON)",
            "/generate/file": "Download CCs as file",
            "/bin/{bin}": "Get BIN info"
        }
    }

@app.get("/generate", response_model=GenerateResponse)
async def generate_cards(
    bin: str = Query(..., min_length=6, max_length=16, description="First 6+ digits of card number"),
    limit: int = Query(DEFAULT_GEN_LIMIT, ge=1, le=MAX_GEN_LIMIT, description="Number of cards to generate (max 50)"),
    month: Optional[str] = Query(None, pattern="^(0[1-9]|1[0-2])$", description="Expiry month (MM)"),
    year: Optional[str] = Query(None, pattern="^(2[3-9]|[3-9][0-9])$", description="Expiry year (YY)"),
    cvv: Optional[str] = Query(None, pattern="^[0-9]{3,4}$", description="CVV (3 or 4 digits)")
):
    try:
        # Get BIN info from multiple sources
        bin_info = await get_bin_info(bin)
        if not bin_info:
            raise HTTPException(400, "Couldn't fetch BIN details from any source")

        # Generate cards with unique expiry dates and proper CVV lengths
        cards = []
        for _ in range(limit):
            expiry_month, expiry_year = month or generate_expiry()[0], year or generate_expiry()[1]
            card_cvv = cvv or generate_cvv(bin_info.get("type"))

            # Generate card with triple validation
            card_number = generate_card_number(bin)

            # Final verification
            if not luhn_checksum(card_number):
                raise HTTPException(500, "Failed to generate valid card number")

            cards.append(CardInfo(
                number=card_number,
                expiry=f"{expiry_month}/{expiry_year}",
                cvv=card_cvv,
                brand=bin_info.get("scheme"),
                type=bin_info.get("type")
            ))

        # Prepare response
        return GenerateResponse(
            cards=cards,
            bin_info=BinInfo(
                bin=bin[:6],
                bank=bin_info.get("bank"),
                country=bin_info.get("country"),
                country_code=bin_info.get("country_code"),
                flag=bin_info.get("flag"),
                scheme=bin_info.get("scheme"),
                type=bin_info.get("type"),
                prepaid=bin_info.get("prepaid"),
                tier=bin_info.get("tier"),
                currency=bin_info.get("currency")
            ),
            generated_at=datetime.utcnow().isoformat()
        )
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/generate/view")
async def generate_view(
    bin: str = Query(..., min_length=6, max_length=16),
    limit: int = Query(DEFAULT_GEN_LIMIT, ge=1, le=MAX_GEN_LIMIT),
    month: Optional[str] = Query(None, pattern="^(0[1-9]|1[0-2])$"),
    year: Optional[str] = Query(None, pattern="^(2[3-9]|[3-9][0-9])$"),
    cvv: Optional[str] = Query(None, pattern="^[0-9]{3,4}$"),
):
    bin_info = await get_bin_info(bin)
    if not bin_info:
        raise HTTPException(400, "Couldn't fetch BIN details")

    cards = []
    for _ in range(limit):
        expiry_month, expiry_year = month or generate_expiry()[0], year or generate_expiry()[1]
        card_cvv = cvv or generate_cvv(bin_info.get("type"))
        card_number = generate_card_number(bin)

        if not luhn_checksum(card_number):
            raise HTTPException(500, "Failed to generate valid card number")

        cards.append(f"{card_number}|{expiry_month}|{expiry_year}|{card_cvv}")

    content = (
        f"BIN: {bin[:6]}\n"
        f"SCHEME: {bin_info.get('scheme')}\n"
        f"TYPE: {bin_info.get('type')}\n"
        f"TIER: {bin_info.get('tier')}\n"
        f"PREPAID: {bin_info.get('prepaid')}\n"
        f"BANK: {bin_info.get('bank')}\n"
        f"COUNTRY: {bin_info.get('country')} ({bin_info.get('country_code')}) {bin_info.get('flag')}\n"
        f"CURRENCY: {bin_info.get('currency')}\n"
        f"==============================\n" +
        "\n".join(cards)
    )

    filename = f"cards_{bin[:6]}.txt"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "text/plain; charset=utf-8"
    }

    return Response(content=content, headers=headers)


@app.get("/bin/{bin}", response_model=BinInfo)
async def bin_lookup(bin: str):
    bin_info = await get_bin_info(bin)
    if not bin_info:
        raise HTTPException(404, "BIN not found in any source")

    return BinInfo(
        bin=bin[:6],
        bank=bin_info.get("bank"),
        country=bin_info.get("country"),
        country_code=bin_info.get("country_code"),
        flag=bin_info.get("flag"),
        scheme=bin_info.get("scheme"),
        type=bin_info.get("type"),
        prepaid=bin_info.get("prepaid"),
        tier=bin_info.get("tier"),
        currency=bin_info.get("currency")
    )

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
