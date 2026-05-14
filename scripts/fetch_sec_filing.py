#!/usr/bin/env python3
"""
fetch_sec_filing.py — 自动从 SEC EDGAR 获取美股财报原始文件(10-Q/10-K/6-K/20-F)
用法:
    python3 fetch_sec_filing.py <SYMBOL> <PERIOD> [--output-dir DIR] [--download]
示例:
    python3 fetch_sec_filing.py AMD 2026Q1
    python3 fetch_sec_filing.py AMD 2026Q1 --download --output-dir /path/to/YoungStockDaily/earnings-filings
"""

import argparse
import json
import os
import re
import sys
import time
import requests

# SEC requires a proper User-Agent
SEC_UA = "YoungStockDaily/1.0 (research@youngstockdaily.com)"
HEADERS = {"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"}

# Ticker -> CIK mapping (all watchlist stocks)
TICKER_CIK = {
    "MU": "723125",
    "AMD": "2488",
    "INTC": "50863",
    "GOOG": "1652044",
    "NVDA": "1045810",
    "NBIS": "1513845",
    "CRWV": "1769628",
    "CRCL": "1876042",
    "MSTR": "1050446",
    "TSLA": "1318605",
    "XPEV": "1810997",
}

# Filing types that contain quarterly/annual reports
# US companies: 10-Q (quarterly), 10-K (annual)
# Foreign companies: 6-K (interim), 20-F (annual)
REPORT_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "6-K", "20-F", "20-F/A"}


def get_cik(ticker: str) -> str | None:
    """Get CIK for a ticker, first from local map, then from SEC."""
    if ticker.upper() in TICKER_CIK:
        return TICKER_CIK[ticker.upper()]

    # Fallback: search SEC company tickers file
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        for _, v in r.json().items():
            if v["ticker"].upper() == ticker.upper():
                return str(v["cik_str"])
    except Exception as e:
        print(f"[WARN] Failed to search SEC tickers: {e}", file=sys.stderr)
    return None


def find_filing(cik: str, period: str) -> dict | None:
    """
    Find the SEC filing for a given CIK and period (e.g., '2026Q1').
    Returns dict with: form, filing_date, accession, primary_doc, sec_url, period_ending
    """
    # Parse period: 2026Q1 -> year=2026, quarter=1
    m = re.match(r"(\d{4})Q(\d)", period)
    if not m:
        print(f"[ERROR] Invalid period format: {period}. Expected YYYYQN.", file=sys.stderr)
        return None
    year, quarter = int(m.group(1)), int(m.group(2))

    # Determine expected fiscal quarter end date range
    # Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec
    quarter_end_months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
    start_month, end_month = quarter_end_months[quarter]

    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[ERROR] Failed to fetch SEC submissions: {e}", file=sys.stderr)
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    report_dates = recent.get("reportDate", [])

    best_match = None
    for i in range(min(50, len(forms))):
        if forms[i] not in REPORT_FORMS:
            continue

        rd = report_dates[i] if i < len(report_dates) else ""
        if not rd:
            continue

        # Parse report date
        try:
            rd_parts = rd.split("-")
            rd_year = int(rd_parts[0])
            rd_month = int(rd_parts[1])
        except (ValueError, IndexError):
            continue

        # Match: same year, month within quarter range (with some tolerance)
        # For fiscal year-end companies, quarters may shift slightly
        if rd_year == year and start_month <= rd_month <= end_month + 1:
            acc_clean = accessions[i].replace("-", "")
            sec_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{primary_docs[i]}"
            sec_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"

            best_match = {
                "form": forms[i],
                "filing_date": dates[i],
                "accession": accessions[i],
                "primary_doc": primary_docs[i],
                "sec_url": sec_url,
                "sec_index_url": sec_index_url,
                "period_ending": rd,
            }
            # Prefer 10-Q/10-K over 6-K/20-F, prefer exact quarter match
            if forms[i] in ("10-Q", "10-K"):
                break
        
        # For 20-F (annual), check if it covers the fiscal year
        if forms[i] == "20-F" and rd_year in (year, year - 1):
            acc_clean = accessions[i].replace("-", "")
            sec_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{primary_docs[i]}"
            sec_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
            if best_match is None:
                best_match = {
                    "form": forms[i],
                    "filing_date": dates[i],
                    "accession": accessions[i],
                    "primary_doc": primary_docs[i],
                    "sec_url": sec_url,
                    "sec_index_url": sec_index_url,
                    "period_ending": rd,
                }

    # For 6-K filings, they may be filed around the earnings date
    # and the reportDate may be the filing date itself
    if best_match is None:
        for i in range(min(50, len(forms))):
            if forms[i] != "6-K":
                continue
            fd = dates[i] if i < len(dates) else ""
            if not fd:
                continue
            try:
                fd_parts = fd.split("-")
                fd_year = int(fd_parts[0])
                fd_month = int(fd_parts[1])
            except (ValueError, IndexError):
                continue
            # 6-K for Q1 2026 would be filed around May 2026
            if fd_year == year and end_month <= fd_month <= end_month + 3:
                acc_clean = accessions[i].replace("-", "")
                sec_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{primary_docs[i]}"
                sec_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
                best_match = {
                    "form": forms[i],
                    "filing_date": dates[i],
                    "accession": accessions[i],
                    "primary_doc": primary_docs[i],
                    "sec_url": sec_url,
                    "sec_index_url": sec_index_url,
                    "period_ending": report_dates[i] if i < len(report_dates) else fd,
                }
                break

    return best_match


def download_filing(sec_url: str, output_dir: str, symbol: str, period: str) -> str | None:
    """Download the filing HTML to local directory. Returns local file path."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{symbol}-{period}-sec-filing.htm"
    filepath = os.path.join(output_dir, filename)

    try:
        r = requests.get(sec_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"[OK] Downloaded {len(r.content)} bytes -> {filepath}")
        return filepath
    except Exception as e:
        print(f"[ERROR] Failed to download filing: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch SEC EDGAR filing for a stock")
    parser.add_argument("symbol", help="Stock ticker (e.g., AMD)")
    parser.add_argument("period", help="Fiscal period (e.g., 2026Q1)")
    parser.add_argument("--output-dir", default=".", help="Directory to save downloaded filing")
    parser.add_argument("--download", action="store_true", help="Download the filing HTML")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    period = args.period.upper()

    cik = get_cik(symbol)
    if not cik:
        print(f"[ERROR] Could not find CIK for {symbol}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Searching SEC EDGAR for {symbol} (CIK: {cik}) {period}...")
    filing = find_filing(cik, period)

    if not filing:
        print(f"[WARN] No filing found for {symbol} {period}", file=sys.stderr)
        result = {"symbol": symbol, "period": period, "found": False}
        if args.json:
            print(json.dumps(result, indent=2))
        sys.exit(1)

    print(f"[OK] Found: {filing['form']} filed {filing['filing_date']}, period ending {filing['period_ending']}")
    print(f"     SEC URL: {filing['sec_url']}")

    local_path = None
    if args.download:
        local_path = download_filing(filing["sec_url"], args.output_dir, symbol, period)

    result = {
        "symbol": symbol,
        "period": period,
        "found": True,
        "form": filing["form"],
        "filing_date": filing["filing_date"],
        "period_ending": filing["period_ending"],
        "accession": filing["accession"],
        "sec_url": filing["sec_url"],
        "sec_index_url": filing["sec_index_url"],
        "local_path": local_path,
    }

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
