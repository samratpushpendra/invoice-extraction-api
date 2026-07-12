from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dateutil import parser
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExtractRequest(BaseModel):
    invoice_text: str

class ExtractResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None

def clean_text(value):
    if value is None:
        return None
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value if value else None

def parse_date_field(text):
    patterns = [
        r"Date\s*[:\-]?\s*([A-Za-z0-9,\-/\. ]+)",
        r"Invoice Date\s*[:\-]?\s*([A-Za-z0-9,\-/\. ]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            try:
                dt = parser.parse(raw, dayfirst=True, fuzzy=True)
                return dt.strftime("%Y-%m-%d")
            except:
                pass
    return None

def parse_money(raw):
    if raw is None:
        return None
    raw = raw.replace(",", "")
    raw = raw.replace("Rs.", "").replace("Rs", "")
    raw = raw.replace("INR", "")
    raw = raw.strip()
    try:
        return float(raw)
    except:
        return None

def find_first_match(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_text(m.group(1))
    return None

@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    text = req.invoice_text

    invoice_no = find_first_match(text, [
        r"(?:Invoice\s*No\.?|Invoice\s*#?|Inv\.?\s*No\.?|Inv\.?|Bill\s*No\.?)\s*[:\-]?\s*([A-Z0-9\-\/]+)",
        r"\b([A-Z]{1,5}-\d{2,10})\b",
        r"\b([A-Z]{2,}\d{2,})\b",
    ])

    vendor = find_first_match(text, [
        r"(?:Vendor|Supplier|Billed\s*From|From)\s*[:\-]?\s*(.+)",
    ])

    date = parse_date_field(text)

    amount = None
    amount_patterns = [
        r"(?:Subtotal|Sub\s*Total|Subtotal Amount)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
        r"(?:Amount\s*Before\s*Tax|Taxable\s*Amount)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
    ]
    amount_raw = find_first_match(text, amount_patterns)
    if amount_raw:
        amount = parse_money(amount_raw)

    tax = None
    tax_patterns = [
        r"(?:GST(?:\s*\(\d+%\))?|Tax|VAT)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
    ]
    tax_raw = find_first_match(text, tax_patterns)
    if tax_raw:
        tax = parse_money(tax_raw)

    currency = "INR" if re.search(r"\bRs\.?\b|\bINR\b|\bGST\b", text, re.IGNORECASE) else None

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }
