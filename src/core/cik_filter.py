"""Simplified CIK filter for processing a single CSV file with CIKs."""

import csv
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CIKFilter:
    """Filter filings based on CIK list from CSV file."""

    def __init__(self, cik_csv_file: Optional[Path] = None, input_dir: Optional[Path] = None):
        """
        Initialize CIK filter with a single CSV file.

        Args:
            cik_csv_file: Path to CSV file containing CIKs
            input_dir: Input directory (for compatibility)
        """
        self.cik_csv_file = cik_csv_file
        self.input_dir = input_dir
        self.ciks: Set[str] = set()
        self._loaded = False

    def _load_ciks(self):
        """Load CIKs from CSV file."""
        if self._loaded:
            return

        self._loaded = True

        if not self.cik_csv_file or not self.cik_csv_file.exists():
            logger.warning(f"CIK CSV file not found: {self.cik_csv_file}")
            return

        try:
            with open(self.cik_csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)

                # Try to detect header
                first_row = next(reader, None)
                if not first_row:
                    logger.warning(f"Empty CSV file: {self.cik_csv_file}")
                    return

                # Check if first row is header (non-numeric)
                if first_row and not first_row[0].isdigit():
                    # Skip header, process remaining rows
                    logger.debug(f"Detected header row: {first_row}")
                else:
                    # First row is data, process it
                    self._process_csv_row(first_row)

                # Process remaining rows
                for row in reader:
                    self._process_csv_row(row)

            logger.info(f"Loaded {len(self.ciks)} CIKs from {self.cik_csv_file.name}")

        except Exception as e:
            logger.error(f"Error loading CIK CSV file: {e}")

    def _process_csv_row(self, row: List[str]):
        """Process a single CSV row to extract CIK."""
        if not row:
            return

        # CIK should be in first column
        cik_str = row[0].strip()

        # Remove any non-numeric characters
        cik_str = re.sub(r'\D', '', cik_str)

        if cik_str:
            # Pad with zeros to make 10 digits
            cik = cik_str.zfill(10)
            self.ciks.add(cik)

            # Also add version without leading zeros for flexible matching
            self.ciks.add(str(int(cik)))

    def has_cik_filters(self) -> bool:
        """Check if any CIK filters are loaded."""
        self._load_ciks()
        return bool(self.ciks)

    def should_process_cik(self, cik: str) -> bool:
        """
        Check if a CIK should be processed.

        Args:
            cik: Central Index Key

        Returns:
            True if CIK is in filter list
        """
        self._load_ciks()

        if not self.ciks:
            return True  # No filter means process all

        # Normalize CIK
        cik_normalized = cik.strip().zfill(10)
        cik_no_zeros = str(int(cik_normalized))

        # Check both versions
        return cik_normalized in self.ciks or cik_no_zeros in self.ciks

    def should_process_filing(self, cik: str, form_type: str, year: int) -> bool:
        """
        Check if a filing should be processed.

        Args:
            cik: Central Index Key
            form_type: Type of filing (e.g., "10-K")
            year: Year of filing

        Returns:
            True if filing should be processed
        """
        # Only process 10-K filings
        if form_type != "10-K":
            return False

        return self.should_process_cik(cik)

    def get_cik_list(self) -> List[str]:
        """Get list of all CIKs in filter."""
        self._load_ciks()
        return sorted(list(self.ciks))

    def get_summary(self) -> Dict[str, any]:
        """Get summary of loaded CIKs."""
        self._load_ciks()

        return {
            "enabled": bool(self.ciks),
            "total_ciks": len(self.ciks),
            "csv_file": str(self.cik_csv_file) if self.cik_csv_file else None,
            "sample_ciks": list(self.ciks)[:5] if self.ciks else []
        }

    def reload(self):
        """Force reload of CIK data."""
        self._loaded = False
        self.ciks.clear()
        self._load_ciks()