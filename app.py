from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dateutil import parser
import re

app = FastAPI()

# CORS: allow_credentials MUST be False when allow_origins is "*"
# (allow_origins=["*"] + allow_credentials=True is invalid per the CORS
# spec and browsers/Workers will reject the response.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
        r"Invoice Date\s*[:\-]?\s*([A-Za-z0-9,\-/\. ]+)",
        r"Date\s*[:\-]?\s*([A-Za-z0-9,\-/\. ]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # cut off at newline-ish trailing junk that regex may over-grab
            raw = raw.splitlines()[0]
            try:
                dt = parser.parse(raw, dayfirst=True, fuzzy=True)
                return dt.strftime("%Y-%m-%d")
            except Exception:
                continue
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
    except Exception:
        return None


def find_first_match(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_text(m.group(1))
    return None


# Note: re.IGNORECASE on the label pattern also makes the captured
# character class match lowercase letters, which lets a loose label
# like "Invoice" (matched via the optional "#" in "Invoice\s*#?")
# accidentally swallow the next plain word (e.g. "Ref" in
# "Invoice Ref: QN-2220") instead of the real code. We guard against
# this by requiring the captured value to contain at least one digit
# before accepting it -- a genuine invoice/reference number always
# has digits, a stray label word never does. If no labeled match
# passes that check, fall back to scanning for a bare code shape
# (e.g. "QN-2220") anywhere in the text.
def find_invoice_no(text):
    label_pattern = (
        r"(?:Invoice\s*No\.?|Invoice\s*#?|Inv\.?\s*No\.?|Inv\.?|Bill\s*No\.?"
        r"|Ref(?:erence)?\.?\s*(?:No\.?)?|Quote\s*No\.?|Quotation\s*No\.?)"
        r"\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/]*)"
    )
    for m in re.finditer(label_pattern, text, re.IGNORECASE):
        candidate = m.group(1)
        if re.search(r"\d", candidate):
            return clean_text(candidate)

    # Fallback: a bare code-shape scan, case-sensitive so it only
    # matches genuine-looking codes (not random capitalized words).
    for pattern in [r"\b([A-Z]{1,6}-\d{2,10})\b", r"\b([A-Z]{2,}\d{2,})\b"]:
        m = re.search(pattern, text)
        if m:
            return clean_text(m.group(1))
    return None


@app.get("/")
def root():
    return {"status": "ok", "message": "POST invoice_text to /extract"}


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    text = req.invoice_text

    invoice_no = find_invoice_no(text)

    vendor = find_first_match(text, [
        r"(?:Vendor|Supplier|Billed\s*From|From)\s*[:\-]?\s*(.+)",
    ])

    date = parse_date_field(text)

    amount_patterns = [
        r"(?:Subtotal|Sub\s*Total|Subtotal Amount)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
        r"(?:Amount\s*Before\s*Tax|Taxable\s*Amount)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
    ]
    amount_raw = find_first_match(text, amount_patterns)
    amount = parse_money(amount_raw) if amount_raw else None

    # GST/VAT is checked before the generic "Tax" pattern so that phrases
    # like "Amount Before Tax" (which contain the substring "Tax:") don't
    # get matched instead of the real tax-amount line.
    tax_patterns = [
        r"(?:GST(?:\s*\(\d+%\))?|VAT)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
        r"(?<!Before\s)(?<!Before)\bTax\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+\.\d{2})",
    ]
    tax_raw = find_first_match(text, tax_patterns)
    tax = parse_money(tax_raw) if tax_raw else None

    currency = "INR" if re.search(r"\bRs\.?\b|\bINR\b|\bGST\b", text, re.IGNORECASE) else None

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
