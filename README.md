# MD&A Extractor for SEC 10-K Filings with CIK Filtering

A Python tool for extracting Management's Discussion and Analysis (MD&A) sections from SEC 10-K filings in ZIP archives, filtered by a list of CIKs (Central Index Keys) provided in a CSV file. The extractor processes only filings matching the CIK list, normalizes the text to remove HTML/XBRL markup, extracts the MD&A section, and outputs clean text files.

## Key Features

- **CIK-Based Filtering**  
  - Process only 10-K filings for companies in your CIK list
  - Accept CSV files with CIK, ticker, and company information
  - Flexible CIK matching (with or without leading zeros)
  - Only extracts files from ZIP that match the filter (efficient disk usage)

- **HTML/XBRL Normalization**  
  - Removes HTML tags, XBRL markup, and SEC-specific formatting
  - Normalizes text BEFORE searching for MD&A sections
  - Preserves table structures and formatting

- **Smart Section Detection**  
  - Comprehensive regex patterns for Item 7 identification
  - Handles variations in section headers
  - Validates extracted content

- **Efficient Processing**  
  - Processes files directly from ZIP archives
  - Temporary raw file storage with automatic cleanup
  - Memory-efficient batch processing

## Installation

```bash
git clone <repository-url>
cd mdna-extractor
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Basic Command

```bash
python -m src.main --cik-csv cik_list.csv --input ./input --output ./output
```

### Command Line Options

```
  -i, --input PATH       Input directory containing ZIP files (default: ./input)
  -o, --output PATH      Output directory for MD&A sections (default: ./output)
  -c, --cik-csv PATH     CSV file with CIKs to filter (REQUIRED)
  -r, --raw-dir PATH     Directory for temporary raw files (default: ./output/raw_filings)
  -v, --verbose          Enable verbose logging
  --keep-raw             Keep raw filing files after processing
  -h, --help             Show help message
```

### Examples

```bash
# Basic usage with CIK filtering
python -m src.main --cik-csv sp500_ciks.csv

# Keep raw files for inspection
python -m src.main --cik-csv sp500_ciks.csv --keep-raw

# Custom directories with verbose output
python -m src.main --cik-csv ciks.csv --input /data/sec_zips --output /data/mdna --verbose

# Specify raw file directory
python -m src.main --cik-csv ciks.csv --raw-dir ./temp_raw
```

## CIK CSV File Format

The CIK filter CSV file should contain CIKs in the first column. Additional columns are optional:

### Minimal format:
```csv
0000320193
0000789019
0001018724
```

### With header:
```csv
CIK
0000320193
0000789019
0001018724
```

### Full format with additional info:
```csv
CIK,Ticker,Company_Name
0000320193,AAPL,Apple Inc.
0000789019,MSFT,Microsoft Corporation
0001018724,AMZN,Amazon.com Inc.
```

## Directory Structure

```
mdna-extractor/
├── input/                  # Place ZIP files here
│   └── filings_2024.zip
├── output/                 # Extracted MD&A sections
│   ├── CIK_0000320193_20240315_MD&A.txt
│   └── raw_filings/        # Temporary (deleted unless --keep-raw)
├── cik_input/             # Place CIK CSV files here
│   └── sp500_ciks.csv
└── logs/                  # Error logs
```

## Output Format

Each extracted MD&A section is saved as a text file with the following:
- **Filename**: `CIK_{cik}_{date}_MD&A.txt`
- **Content**: Clean MD&A text with minimal header
- **Size**: Typically 2-10 KB (much smaller than original filing)

Example output file header:
```
EXTRACTED MD&A SECTION
CIK: 0000320193
Company: Apple Inc.
Filing Date: 2024-03-15
Form Type: 10-K
============================================================

[MD&A content follows...]
```

## Processing Flow

1. **Load CIK list** from CSV file
2. **Scan ZIP files** in input directory
3. **For each file in ZIP**:
   - Read file header to extract CIK
   - Check if CIK matches filter list
   - Check if file is a 10-K (not 10-Q)
   - If matches: extract to temporary location
4. **Normalize text** (remove HTML/XBRL)
5. **Find MD&A section** using patterns
6. **Extract and save** MD&A content only
7. **Delete raw file** (unless --keep-raw)

## Statistics Output

The extractor provides detailed statistics:
```
Processing complete:
- Total ZIP files: 5
- Total files in ZIPs: 1,247
- Files matching CIK filter: 125
- Successfully extracted MD&A: 123
- Failed: 2
- Time elapsed: 145.3 seconds
```

## Troubleshooting

### No files processed
- Verify ZIP files contain 10-K filings (not 10-Q)
- Check CIK format in CSV (can be with or without leading zeros)
- Ensure ZIP files contain text files (.txt extension)

### MD&A not found
- Some older filings use different section headers
- Check logs for specific error messages
- Try --keep-raw to inspect the normalized text

### Encoding errors
- The extractor handles multiple encodings automatically
- Check logs for specific file issues

### Memory issues
- Process smaller batches of ZIP files
- Ensure sufficient disk space for temporary files

## Performance Tips

- **Large datasets**: Process in batches of 10-20 ZIP files
- **Disk space**: Temporary raw files can be large; ensure adequate space
- **Speed**: ~1-2 seconds per filing on modern hardware
- **Memory**: Uses streaming for large files

## Advanced Usage

### Python Script Example
```python
from pathlib import Path
import subprocess
import sys

# Configuration
cik_csv = Path("sp500_ciks.csv")
input_dir = Path("./sec_filings")
output_dir = Path("./extracted_mdna")

# Run extraction
cmd = [
    sys.executable, "-m", "src.main",
    "--cik-csv", str(cik_csv),
    "--input", str(input_dir),
    "--output", str(output_dir),
    "--verbose"
]

subprocess.run(cmd)
```

## Requirements

- Python 3.8+
- 8GB+ RAM recommended
- Sufficient disk space for temporary files
- See requirements.txt for Python packages

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly with sample data
4. Submit a pull request

## Acknowledgments

Built for efficient extraction of MD&A sections from SEC EDGAR filings with CIK-based filtering for targeted analysis.