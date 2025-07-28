"""Enhanced text normalization utilities for cleaning SEC filings while aggressively preserving table structure."""

import re
import unicodedata
from typing import List, Set, Tuple
from config.settings import CONTROL_CHAR_REPLACEMENT, MULTIPLE_WHITESPACE_PATTERN
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EnhancedTextNormalizer:
    """Enhanced text cleaning and normalization for SEC filings with superior table preservation."""

    def __init__(self):
        self.control_char_pattern = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]')  # Preserve \t, \n, \r
        self.non_ascii_pattern = re.compile(r'[^\x00-\x7F]+')

        # Enhanced patterns for SEC table detection
        self.table_indicators = {
            # Monetary patterns
            'monetary': re.compile(r'\$\s*\(?[\d,]+(?:\.\d+)?\)?'),
            'percentage': re.compile(r'\d+\.?\d*%'),
            'numeric_columns': re.compile(r'\(?[\d,]+(?:\.\d+)?\)?\s+\(?[\d,]+(?:\.\d+)?\)?'),

            # Date patterns
            'dates': re.compile(
                r'(?:december|january|february|march|april|may|june|july|august|september|october|november)\s+\d{1,2},?\s+\d{4}',
                re.IGNORECASE),
            'year_headers': re.compile(r'\b\d{4}\s+\d{4}\s+\d{4}\b'),

            # Financial keywords
            'financial_terms': re.compile(
                r'\b(?:revenue|income|profit|loss|assets|liabilities|equity|cash|flow|expenses|costs|sales|operating|net|gross|total)\b',
                re.IGNORECASE),

            # Table structure indicators
            'significant_spaces': re.compile(r'\s{4,}'),
            'tabs': re.compile(r'\t'),
            'pipes': re.compile(r'\|.*\|.*\|'),
            'delimiters': re.compile(r'^[-=_+]{3,}$'),
        }

    def normalize_text(self, text: str, preserve_structure: bool = True) -> str:
        """
        Enhanced normalization pipeline optimized for SEC table preservation.

        Args:
            text: Raw text from filing
            preserve_structure: Whether to aggressively preserve table structure

        Returns:
            Normalized text with tables properly preserved
        """
        if not text:
            return ""

        logger.debug("Starting enhanced text normalization")

        # First pass: Remove SEC markers but preserve all structure
        text = self._remove_sec_markers(text)

        # Replace control characters (except tabs and newlines)
        text = self._replace_control_chars(text)

        # Normalize unicode
        text = self._normalize_unicode(text)

        # Fix encoding issues
        text = self._fix_encoding_issues(text)

        if preserve_structure:
            # AGGRESSIVE table structure preservation
            text = self._aggressively_preserve_tables(text)
        else:
            # Standard whitespace normalization
            text = self._normalize_whitespace(text)
            text = self._remove_empty_lines(text)

        logger.debug("Enhanced text normalization completed")
        return text.strip()

    def _aggressively_preserve_tables(self, text: str) -> str:
        """
        Aggressively preserve table structure using enhanced detection.
        """
        lines = text.split('\n')
        processed_lines = []

        logger.debug(f"Processing {len(lines)} lines with aggressive table preservation")

        # First pass: classify all lines
        line_classifications = []
        for i, line in enumerate(lines):
            classification = self._classify_line_enhanced(line, lines, i)
            line_classifications.append(classification)

        # Second pass: process based on classification
        for i, (line, classification) in enumerate(zip(lines, line_classifications)):
            if classification in ['table_header', 'table_content', 'table_delimiter', 'monetary_data']:
                # PRESERVE EVERYTHING for table lines
                processed_lines.append(line.rstrip())  # Only remove trailing spaces
                logger.debug(f"Line {i}: PRESERVED as {classification}: {line[:50]}...")

            elif classification == 'table_continuation':
                # Preserve with minimal formatting
                processed_lines.append(line.strip())

            elif classification == 'potential_table':
                # Cautious preservation
                processed_lines.append(self._cautiously_format_line(line))

            else:
                # Regular text - normalize but preserve indentation
                indent = len(line) - len(line.lstrip())
                cleaned = ' '.join(line.split())
                if cleaned:
                    processed_lines.append(' ' * min(indent, 4) + cleaned)
                elif processed_lines and processed_lines[-1].strip():
                    # Keep one empty line between paragraphs
                    processed_lines.append('')

        # Third pass: clean up excessive empty lines
        result = self._clean_excessive_empty_lines(processed_lines)

        logger.info(f"Aggressive table preservation completed: {len(result)} lines")
        return '\n'.join(result)

    def _classify_line_enhanced(self, line: str, all_lines: List[str], line_index: int) -> str:
        """
        Enhanced line classification for better table detection.
        """
        line_stripped = line.strip()

        if not line_stripped:
            return 'empty'

        # Check for table delimiters first
        if self.table_indicators['delimiters'].search(line_stripped):
            return 'table_delimiter'

        # Check for monetary data (highest priority for SEC filings)
        if self.table_indicators['monetary'].search(line):
            # Check if it has columnar structure
            if (self.table_indicators['significant_spaces'].search(line) or
                    self.table_indicators['tabs'].search(line) or
                    self.table_indicators['numeric_columns'].search(line)):
                return 'monetary_data'

        # Check for financial table headers
        if self._is_enhanced_table_header(line):
            return 'table_header'

        # Check for pipe-delimited content
        if self.table_indicators['pipes'].search(line):
            return 'table_content'

        # Check for multiple monetary/numeric values
        monetary_matches = len(self.table_indicators['monetary'].findall(line))
        percentage_matches = len(self.table_indicators['percentage'].findall(line))

        if monetary_matches >= 2 or percentage_matches >= 2:
            return 'monetary_data'

        # Check for columnar numeric data
        if self.table_indicators['numeric_columns'].search(line):
            # Additional check for context
            if self._has_table_context(all_lines, line_index):
                return 'table_content'

        # Check for significant whitespace with financial terms
        if (self.table_indicators['significant_spaces'].search(line) and
                self.table_indicators['financial_terms'].search(line)):
            return 'potential_table'

        # Check for date headers (common in SEC tables)
        if (self.table_indicators['dates'].search(line) or
                self.table_indicators['year_headers'].search(line)):
            return 'table_header'

        # Check for continuation patterns
        if self._is_table_continuation(line):
            return 'table_continuation'

        return 'regular_text'

    def _is_enhanced_table_header(self, line: str) -> bool:
        """Enhanced table header detection."""
        line_lower = line.lower()

        # Financial statement headers
        financial_headers = [
            'statement of', 'balance sheet', 'income statement', 'cash flow',
            'year ended', 'quarter ended', 'period ended', 'fiscal year',
            'for the year', 'for the quarter', 'for the period',
            'in thousands', 'in millions', 'in billions',
            'unaudited', 'audited', 'consolidated'
        ]

        if any(header in line_lower for header in financial_headers):
            return True

        # Check for year/date patterns
        if (re.search(r'\b\d{4}\b.*\b\d{4}\b', line) or  # Multiple years
                re.search(r'(?:december|march|june|september)\s+\d{1,2}', line_lower)):
            return True

        # Check for column headers with financial terms
        financial_terms = ['revenue', 'income', 'assets', 'liabilities', 'equity', 'cash']
        if (any(term in line_lower for term in financial_terms) and
                self.table_indicators['significant_spaces'].search(line)):
            return True

        return False

    def _has_table_context(self, all_lines: List[str], line_index: int) -> bool:
        """Check if line has table context by examining surrounding lines."""
        # Look at surrounding lines (±3)
        start = max(0, line_index - 3)
        end = min(len(all_lines), line_index + 4)

        context_lines = all_lines[start:end]
        table_indicators = 0

        for context_line in context_lines:
            if (self.table_indicators['monetary'].search(context_line) or
                    self.table_indicators['percentage'].search(context_line) or
                    self.table_indicators['significant_spaces'].search(context_line) or
                    self._is_enhanced_table_header(context_line)):
                table_indicators += 1

        return table_indicators >= 2

    def _is_table_continuation(self, line: str) -> bool:
        """Check if line is a table continuation."""
        line_lower = line.lower().strip()

        continuation_patterns = [
            'total', 'subtotal', 'net', 'gross', 'less:', 'add:', 'deduct:',
            'continued', 'cont.', 'see note', 'refer to', 'as of'
        ]

        return any(pattern in line_lower for pattern in continuation_patterns)

    def _cautiously_format_line(self, line: str) -> str:
        """Cautiously format potential table lines."""
        # Preserve structure but clean up minimally
        # Replace multiple spaces with exactly 4 spaces to maintain columns
        formatted = re.sub(r' {2,}', '    ', line.rstrip())
        return formatted

    def _clean_excessive_empty_lines(self, lines: List[str]) -> List[str]:
        """Clean up excessive empty lines while preserving table structure."""
        result = []
        empty_count = 0

        for line in lines:
            if not line.strip():
                empty_count += 1
                # Allow more empty lines around tables
                if empty_count <= 3:  # Increased from 2
                    result.append(line)
            else:
                empty_count = 0
                result.append(line)

        return result

    def _remove_sec_markers(self, text: str) -> str:
        """Remove SEC-specific markers while preserving document structure."""
        # Remove page markers
        text = re.sub(r'<PAGE>\s*\d+', '', text, flags=re.IGNORECASE)

        # Remove "Table of Contents" headers but keep the structure
        text = re.sub(r'^\s*Table\s+of\s+Contents\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

        # Remove standalone page numbers at line start/end
        text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE)

        # Remove HTML-like tags
        text = re.sub(r'</?[A-Z]+>', '', text)

        return text

    def _replace_control_chars(self, text: str) -> str:
        """Replace control characters except tabs and newlines."""
        return self.control_char_pattern.sub(CONTROL_CHAR_REPLACEMENT, text)

    def _normalize_unicode(self, text: str) -> str:
        """Normalize unicode characters to ASCII equivalents where possible."""
        # Normalize to NFKD form
        text = unicodedata.normalize('NFKD', text)

        # Replace common unicode characters
        replacements = {
            '\u2019': "'",  # Right single quotation mark
            '\u2018': "'",  # Left single quotation mark
            '\u201C': '"',  # Left double quotation mark
            '\u201D': '"',  # Right double quotation mark
            '\u2013': '-',  # En dash
            '\u2014': '--',  # Em dash (use double dash to preserve width)
            '\u2026': '...',  # Ellipsis
            '\u00A0': ' ',  # Non-breaking space
            '\u2022': '*',  # Bullet
            '\u00B7': '*',  # Middle dot
            '\u2212': '-',  # Minus sign
        }

        for unicode_char, ascii_char in replacements.items():
            text = text.replace(unicode_char, ascii_char)

        return text

    def _fix_encoding_issues(self, text: str) -> str:
        """Fix common encoding issues in text."""
        # Fix mojibake patterns
        encoding_fixes = {
            'â€™': "'",
            'â€œ': '"',
            'â€': '"',
            'â€"': '--',
            'â€"': '-',
            'Ã¢': '',
            'Â': '',
            'â\x80\x99': "'",
            'â\x80\x9c': '"',
            'â\x80\x9d': '"',
            'â\x80\x93': '-',
            'â\x80\x94': '--',
        }

        for pattern, replacement in encoding_fixes.items():
            text = text.replace(pattern, replacement)

        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize multiple whitespace to single spaces."""
        # Replace multiple spaces, tabs, etc. with single space
        text = re.sub(r'[ \t]+', ' ', text)

        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        return text

    def _remove_empty_lines(self, text: str) -> str:
        """Remove excessive empty lines while preserving paragraph structure."""
        lines = text.split('\n')
        non_empty_lines = []

        for line in lines:
            if line.strip():
                non_empty_lines.append(line)
            elif non_empty_lines and non_empty_lines[-1].strip():
                # Keep one empty line between paragraphs
                non_empty_lines.append('')

        return '\n'.join(non_empty_lines)

    def clean_for_csv(self, text: str) -> str:
        """Additional cleaning for CSV output."""
        # Remove newlines and extra spaces
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = re.sub(r'\s+', ' ', text)

        # Escape quotes
        text = text.replace('"', '""')

        return text.strip()

    def extract_company_name(self, text: str) -> str:
        """Extract company name from filing header."""
        # Common patterns for company name in SEC filings
        patterns = [
            r"(?:COMPANY\s*CONFORMED\s*NAME|CONFORMED\s*NAME|COMPANY\s*NAME)[\s:]+([^\n]+)",
            r"(?:^|\n)\s*([A-Z][A-Z0-9\s,.\-&]+(?:INC|CORP|LLC|LP|LTD|COMPANY|CO)\.?)\s*\n",
            r"(?:REGISTRANT\s*NAME)[\s:]+([^\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:5000], re.IGNORECASE | re.MULTILINE)
            if match:
                company_name = match.group(1).strip()
                # Clean up the name
                company_name = re.sub(r'\s+', ' ', company_name)
                company_name = company_name.strip(' .')
                if len(company_name) > 3 and len(company_name) < 100:
                    return company_name

        return ""

    def sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use in filenames."""
        # Replace illegal filename characters
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\t']
        for char in illegal_chars:
            name = name.replace(char, ' ')

        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)

        # Remove leading/trailing spaces and periods
        name = name.strip(' .')

        # Limit length
        if len(name) > 50:
            name = name[:50].strip()

        return name