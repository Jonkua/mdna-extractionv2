"""Configuration settings for MD&A Extractor."""

import os
from pathlib import Path

# Base directories
# Resolve project root two levels up from this file
BASE_DIR = Path(__file__).resolve().parent.parent

# Absolute input/output paths
INPUT_DIR  = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
CIK_INPUT_DIR = BASE_DIR / "cik_input"  # New directory for CIK filter CSV files

# Create directories if they don't exist
for dir_path in [INPUT_DIR, OUTPUT_DIR, LOG_DIR, CIK_INPUT_DIR]:
    dir_path.mkdir(exist_ok=True, parents=True)

# File patterns
VALID_EXTENSIONS = {".txt", ".TXT"}
ZIP_EXTENSIONS = {".zip", ".ZIP"}
CIK_CSV_EXTENSIONS = {".csv", ".CSV"}

# CIK filtering settings
CIK_CSV_PATTERN = r".*(\d{4}).*\.csv$"  # Pattern to extract year from CSV filename
FORM_TYPE_FILTER = {"10-K"}  # Only process 10-K filings when CIK filtering is enabled

# Temporary file settings (to avoid filling internal drive)
USE_EXTERNAL_TEMP = True  # Use output directory for temp files instead of system temp
CLEANUP_IMMEDIATELY = True  # Clean up temp files immediately after processing each file
TEMP_DIR_NAME = "temp_extraction"  # Name of temp subdirectory

# Processing limits
MAX_FILE_SIZE_MB = 250
MAX_CROSS_REFERENCE_DEPTH = 3
TABLE_MIN_COLUMNS = 2
TABLE_MIN_ROWS = 2

# Text normalization
ENCODING_PREFERENCES = ["utf-8", "latin-1", "cp1252", "ascii"]
CONTROL_CHAR_REPLACEMENT = " "
MULTIPLE_WHITESPACE_PATTERN = r"\s+"

# Filing priority order (for fallback logic when not using CIK filtering)
FILING_PRIORITY = ["10-K/A", "10-K", "10-Q/A", "10-Q"]

# Logging
LOG_FILENAME = "mdna_extraction_errors.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Error handling
CONTINUE_ON_ERROR = True
MAX_ERRORS_PER_FILE = 10

# Performance
CHUNK_SIZE = 2048 * 2048  # 4MB chunks for reading large files