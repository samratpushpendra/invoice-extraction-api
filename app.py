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

def parse_date(text):
    m = re.search(r"Date:\s*([^\n]+)", text, re.IGNORECASE)
    if not m:
        return None
    try:
        dt = parser.parse(m.group(1), dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except:
        return None

def parse_money(value):
    if value is None:
        return None
    value = value.replace("Rs.", "").replace("Rs", "").replace(",", "").strip()
    try:
        return float(value)
    except:
        return None

@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    text = req.invoice_text

    invoice_no = None
    m = re.search(r"Invoice No:\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        invoice_no = m.group(1).strip()

    vendor = None
    m = re.search(r"Vendor:\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        vendor = m.group(1).strip()

    date = parse_date(text)

    amount = None
    m = re.search(r"Subtotal:\s*Rs\.?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        amount = parse_money(m.group(1))

    tax = None
    m = re.search(r"GST.*?:\s*Rs\.?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        tax = parse_money(m.group(1))

    currency = "INR" if "Rs." in text or "GST" in text else None

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }