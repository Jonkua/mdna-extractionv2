"""Enhanced regex patterns for MD&A section detection and table parsing, optimized for SEC filings."""

import re

# Enhanced table detection patterns specifically for SEC financial filings
SEC_TABLE_PATTERNS = [
    # Financial statement headers with years/quarters
    r"(?i)^\s*(?:year|quarter|period)\s+ended?\s+(?:december|march|june|september|\d{1,2}[,\s]+\d{4})",
    r"(?i)^\s*(?:for\s+the\s+)?(?:year|quarter|period)\s+ended?\s+",
    r"(?i)^\s*(?:fiscal\s+)?(?:year|quarter)\s+\d{4}",

    # Multi-column date headers (common in SEC filings)
    r"^\s*(?:december|january|february|march|april|may|june|july|august|september|october|november)\s+\d{1,2},?\s+\d{4}\s+",
    r"^\s*\d{4}\s+\d{4}\s+\d{4}",  # Three or more years in a row
    r"^\s*\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\s+\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}",  # Multiple dates

    # Financial line items with monetary values
    r"(?i)^\s*(?:revenue|income|expenses?|assets?|liabilities|equity|cash)\s+.*?\$",
    r"(?i)^\s*(?:total|net|gross|operating)\s+(?:revenue|income|profit|loss)\s+.*?\$",
    r"(?i)^\s*(?:cost of|selling|general|administrative)\s+.*?\$",

    # Dollar amounts in columns (with potential parentheses for negatives)
    r"^\s*\$\s*\(?[\d,]+(?:\.\d+)?\)?\s+\$\s*\(?[\d,]+(?:\.\d+)?\)?",
    r"^\s*\(?[\d,]+(?:\.\d+)?\)?\s+\(?[\d,]+(?:\.\d+)?\)?\s+\(?[\d,]+(?:\.\d+)?\)?",

    # Table separators common in SEC filings
    r"^\s*[-=_]{5,}\s*$",
    r"^\s*\|\s*[-=_]{3,}\s*\|",
    r"^\s*\+[-=_]+\+",

    # Monetary units indicators
    r"(?i)^\s*\((?:in\s+)?(?:thousands|millions|billions)(?:\s+except|\s+of|\s+unless)?\)",
    r"(?i)^\s*(?:amounts?\s+in\s+)?(?:thousands|millions|billions)",
    r"(?i)^\s*\$\s*in\s+(?:thousands|millions|billions)",

    # Common SEC table structures
    r"^\s*(?:\d+\.?\s+)?[A-Z][a-z\s]+\s{3,}[\d\$\(\),.-]+",  # Label followed by numbers
    r"^\s*[A-Z][A-Z\s]+\s{2,}[\d\$\(\),.-]+",  # ALL CAPS headers with numbers

    # Multiple columns of numbers (financial data)
    r"^\s*(?:\$?\s*\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?\s*){2,}$",
    r"^\s*(?:\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?\s*){3,}$",

    # Percentage columns (common in SEC filings)
    r"^\s*(?:\d+\.?\d*%\s*){2,}$",
    r"^\s*.*?\d+\.?\d*%.*?\d+\.?\d*%",

    # Statement titles (balance sheet, income statement, etc.)
    r"(?i)^\s*(?:consolidated\s+)?(?:balance\s+sheet|statement\s+of|income\s+statement)",
    r"(?i)^\s*(?:consolidated\s+)?(?:cash\s+flow|stockholder|shareholder)",
]

# Enhanced patterns for financial statement components
FINANCIAL_STATEMENT_PATTERNS = [
    # Balance Sheet items
    r"(?i)^\s*(?:current\s+)?assets?\s*:?\s*$",
    r"(?i)^\s*(?:current\s+)?liabilities\s*:?\s*$",
    r"(?i)^\s*(?:stockholder|shareholder)s?\s+equity\s*:?\s*$",
    r"(?i)^\s*total\s+(?:assets?|liabilities|equity)\s*$",

    # Income Statement items
    r"(?i)^\s*(?:total\s+)?(?:revenue|sales)\s*:?\s*$",
    r"(?i)^\s*(?:cost\s+of\s+)?(?:sales|revenue|goods\s+sold)\s*:?\s*$",
    r"(?i)^\s*gross\s+(?:profit|margin)\s*:?\s*$",
    r"(?i)^\s*operating\s+(?:income|expenses?)\s*:?\s*$",
    r"(?i)^\s*net\s+(?:income|loss)\s*:?\s*$",

    # Cash Flow items
    r"(?i)^\s*(?:net\s+)?cash\s+(?:provided|used)\s+by\s*:?\s*$",
    r"(?i)^\s*operating\s+activities\s*:?\s*$",
    r"(?i)^\s*investing\s+activities\s*:?\s*$",
    r"(?i)^\s*financing\s+activities\s*:?\s*$",
]

# Patterns for table continuation and formatting
TABLE_CONTINUATION_PATTERNS = [
    r"(?i)^\s*(?:continued|cont\.|see\s+note)",
    r"(?i)^\s*(?:subtotal|total|less|add|deduct)\s*:?\s*",
    r"^\s*(?:\.\.\.|---|\*\*\*)\s*$",  # Continuation markers
]

# Enhanced column detection patterns
COLUMN_DETECTION_PATTERNS = [
    # Multiple years/quarters
    r"(\d{4})\s+(\d{4})\s+(\d{4})",
    r"(Q[1-4]\s+\d{4})\s+(Q[1-4]\s+\d{4})",

    # Dollar amounts in columns
    r"(\$\s*[\d,]+(?:\.\d+)?)\s+(\$\s*[\d,]+(?:\.\d+)?)",
    r"(\([\d,]+(?:\.\d+)?\))\s+(\([\d,]+(?:\.\d+)?\))",  # Negative amounts in parentheses

    # Mixed number formats
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)",
]

# Patterns to identify table boundaries more accurately
TABLE_BOUNDARY_PATTERNS = [
    # Table starts
    r"(?i)^\s*(?:the\s+following\s+table|table\s+\d+|see\s+table)",
    r"(?i)^\s*(?:as\s+of|for\s+the\s+(?:year|quarter|period))",

    # Table ends
    r"(?i)^\s*(?:see\s+accompanying|refer\s+to|note\s+\d+)",
    r"(?i)^\s*(?:end\s+of\s+table|table\s+ends)",
    r"^\s*(?:={3,}|-{3,}|_{3,})\s*$",  # Separator lines
]


# Compile enhanced patterns for better performance
def compile_enhanced_patterns():
    """Compile enhanced regex patterns for SEC table detection."""
    compiled = {
        "sec_tables": [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in SEC_TABLE_PATTERNS],
        "financial_statements": [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in FINANCIAL_STATEMENT_PATTERNS],
        "table_continuation": [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in TABLE_CONTINUATION_PATTERNS],
        "column_detection": [re.compile(p, re.MULTILINE) for p in COLUMN_DETECTION_PATTERNS],
        "table_boundaries": [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in TABLE_BOUNDARY_PATTERNS],
    }
    return compiled


ENHANCED_PATTERNS = compile_enhanced_patterns()

# Updated original patterns with SEC-specific enhancements
ITEM_7_START_PATTERNS = [
    # Standard "Management's Discussion and Analysis"
    r"(?:^|\n)\s*ITEM\s*7\.?\s*MANAGEMENT['']?S\s*DISCUSSION\s*AND\s*ANALYSIS",
    r"(?:^|\n)\s*ITEM\s*7\.?\s*MANAGEMENT['']?S\s*DISCUSSION\s*&\s*ANALYSIS",
    # Abbreviated MD&A forms
    r"(?:^|\n)\s*ITEM\s*7[\-:\s]+MD&A",
    r"(?:^|\n)\s*ITEM\s*7[\-:\s]+M\s*D\s*&?\s*A",
    r"(?:^|\n)\s*ITEM\s*7[\-:\s]+MDA",
    # Enhanced patterns for variations
    r"(?:^|\n)\s*ITEM\s*7\.?\s*MANAGEMENT['']?S\s*DISCUSSION\s*AND\s*ANALYSIS\s*OF\s*FINANCIAL\s*CONDITION\s*AND\s*RESULTS\s*OF\s*OPERATIONS",
    r"(?:^|\n)\s*ITEM\s*7\.?\s*MD&A\s*-\s*FINANCIAL\s*CONDITION\s*AND\s*RESULTS",
]

# Enhanced table delimiters for SEC filings
TABLE_DELIMITER_PATTERNS = [
    r"^\s*[-=_]{3,}\s*$",  # Standard separators
    r"^\s*\|.*\|.*\|",  # Pipe-delimited
    r"(?:\s{3,}|\t)",  # Multiple spaces or tabs
    r"^\s*(?:\d+\s+){2,}",  # Rows of numeric columns
    r"^\s*[A-Za-z]+\s+(?:[-–]\s+)?\$\(?\d",  # Label followed by number
    r"^\s*\(?\$?\d[\d,\.]+\)?\s+(?:\(?\$?\d[\d,\.]+\)?\s+)+$",  # Numeric entries
    # Enhanced SEC-specific patterns
    r"^\s*\$\s*\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?\s+\$\s*\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?",  # Dollar columns
    r"^\s*\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?\s+\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?\s+\(?",  # Multi-number columns
    r"^\s*\d+\.?\d*%\s+\d+\.?\d*%",  # Percentage columns
]

# Enhanced table headers for SEC filings
TABLE_HEADER_PATTERNS = [
    r"^\s*(?:Year|Period|Quarter|Month)\s+End(?:ed|ing)",
    r"^\s*(?:December|June|March|September)\s+\d{1,2},?\s+20\d{2}",
    r"^\s*\$?\s*(?:in\s+)?(?:thousands|millions|billions)",
    r"^\s*(?:Revenue|Income|Assets|Liabilities|Equity)",
    r"^\s*Statements?\s+of\s+(?:Operations|Cash\s+Flows|Income)",
    r"^\s*(?:Unaudited|Audited)\s+Financial\s+Statements?",
    r"^\s*(?:Balance\s+Sheets?|Cash\s+Flows?|Stockholders['']?\s+Equity)",
    r"^\s*(?:Total|Net|Gross|Operating)\s+(?:Income|Loss|Profit)",
    # Enhanced SEC-specific headers
    r"^\s*(?:For\s+the\s+)?(?:Year|Quarter|Period)\s+Ended\s+",
    r"^\s*(?:Fiscal\s+)?(?:Year|Quarter)\s+\d{4}",
    r"^\s*(?:Three|Six|Nine|Twelve)\s+Months?\s+Ended",
    r"^\s*\((?:in\s+)?(?:thousands|millions|billions)(?:\s+except|\s+of|\s+unless)?\)",
]