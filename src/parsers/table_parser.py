"""Improved parser for detecting and preserving tables within MD&A sections."""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from config.patterns import COMPILED_PATTERNS
from config.settings import TABLE_MIN_COLUMNS, TABLE_MIN_ROWS
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Table:
    """Represents a detected table."""
    content: List[List[str]]  # Table as list of rows
    start_pos: int
    end_pos: int
    start_line: int
    end_line: int
    title: Optional[str]
    confidence: float
    table_type: str  # 'delimited', 'aligned', 'mixed', 'financial'
    original_text: str  # Preserve original formatting
    raw_lines: List[str]  # Raw lines for perfect preservation


class TableParser:
    """Detects and preserves tables within text."""

    def __init__(self):
        self.patterns = COMPILED_PATTERNS

    def identify_tables(self, text: str) -> List[Table]:
        """
        Identify tables in text while preserving their original formatting.

        Args:
            text: Text containing potential tables

        Returns:
            List of Table objects with position information
        """
        tables = []
        lines = text.split('\n')

        # Track which lines are part of tables
        table_lines = set()

        # Try different detection methods
        tables.extend(self._identify_financial_tables(lines, table_lines))
        tables.extend(self._identify_delimited_tables(lines, table_lines))
        tables.extend(self._identify_aligned_tables(lines, table_lines))

        # Remove duplicates and overlaps
        tables = self._deduplicate_tables(tables)

        # Sort by position
        tables.sort(key=lambda t: t.start_line)

        return tables

    def preserve_tables_in_text(self, text: str, tables: List[Table]) -> str:
        """
        Return text with tables perfectly preserved in their original formatting.

        Args:
            text: Original text
            tables: List of identified tables

        Returns:
            Text with tables properly formatted and preserved
        """
        if not tables:
            return text

        lines = text.split('\n')
        result_lines = []
        current_line = 0

        for table in sorted(tables, key=lambda t: t.start_line):
            # Add lines before table
            while current_line < table.start_line:
                if current_line < len(lines):
                    result_lines.append(lines[current_line])
                current_line += 1

            # Add table title if exists
            if table.title:
                result_lines.append("")  # Empty line before title
                result_lines.append(table.title)
                result_lines.append("")  # Empty line after title

            # Add the preserved table lines
            if hasattr(table, 'raw_lines') and table.raw_lines:
                # Use the exact original lines
                for raw_line in table.raw_lines:
                    result_lines.append(raw_line)
            else:
                # Fallback to original_text
                table_text_lines = table.original_text.split('\n')
                for line in table_text_lines:
                    result_lines.append(line)

            # Skip the original table lines in source
            current_line = table.end_line + 1

            # Add spacing after table
            if current_line < len(lines) and lines[current_line].strip():
                result_lines.append("")  # Empty line after table

        # Add remaining lines
        while current_line < len(lines):
            result_lines.append(lines[current_line])
            current_line += 1

        return '\n'.join(result_lines)

    def _identify_financial_tables(self, lines: List[str], table_lines: Set[int]) -> List[Table]:
        """Specifically identify financial statement tables."""
        tables = []
        i = 0

        while i < len(lines):
            if i in table_lines:
                i += 1
                continue

            # Look for financial table indicators
            if self._is_financial_table_header(lines[i]):
                table = self._extract_financial_table(lines, i, table_lines)
                if table:
                    tables.append(table)
                    for line_num in range(table.start_line, table.end_line + 1):
                        table_lines.add(line_num)
                    i = table.end_line + 1
                else:
                    i += 1
            else:
                i += 1

        return tables

    def _is_financial_table_header(self, line: str) -> bool:
        """Check if line is a financial table header."""
        # Common financial table headers
        financial_patterns = [
            r'(?:Consolidated|Condensed)?\s*(?:Statements?|Schedule)\s*of',
            r'(?:Year|Three|Six|Nine)\s+Months?\s+Ended',
            r'(?:December|March|June|September)\s+\d{1,2},?\s+\d{4}',
            r'(?:in\s+)?(?:millions|thousands|billions)(?:\s+of\s+dollars)?',
            r'(?:Revenue|Income|Assets|Liabilities|Cash\s+Flow)',
            r'(?:Balance\s+Sheet|Income\s+Statement|Statement\s+of\s+Operations)',
        ]

        for pattern in financial_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True

        # Check for date columns
        date_pattern = r'\b(?:19|20)\d{2}\b'
        dates = re.findall(date_pattern, line)
        if len(dates) >= 2:
            return True

        return False

    def _extract_financial_table(self, lines: List[str], start_idx: int,
                                table_lines: Set[int]) -> Optional[Table]:
        """Extract a financial table with special handling."""
        table_start = start_idx
        table_raw_lines = []

        # Look for title above header
        title = None
        if start_idx > 0 and not self._is_table_line(lines[start_idx - 1]):
            potential_title = lines[start_idx - 1].strip()
            if potential_title and len(potential_title) < 200:
                title = potential_title
                table_start = start_idx - 1

        # Collect all table lines
        current = start_idx
        consecutive_empty = 0
        has_numeric_data = False

        while current < len(lines):
            line = lines[current]

            if not line.strip():
                consecutive_empty += 1
                if consecutive_empty > 2:
                    break
                table_raw_lines.append(line)
            else:
                consecutive_empty = 0

                # Check if line contains numeric data
                if re.search(r'\d', line):
                    has_numeric_data = True

                # Check if line looks like part of table
                if (self._is_table_line(line) or
                    self._is_financial_data_line(line) or
                    self._is_table_continuation(line)):
                    table_raw_lines.append(line)
                else:
                    # Check if it's a note or total line
                    if self._is_table_note_or_total(line):
                        table_raw_lines.append(line)
                    else:
                        break

            current += 1

        # Validate table
        if len(table_raw_lines) < TABLE_MIN_ROWS or not has_numeric_data:
            return None

        # Create table object
        table_end = start_idx + len(table_raw_lines) - 1

        return Table(
            content=[],  # Will be filled if needed
            start_pos=0,
            end_pos=0,
            start_line=table_start,
            end_line=table_end,
            title=title,
            confidence=0.95,
            table_type='financial',
            original_text='\n'.join(lines[table_start:table_end + 1]),
            raw_lines=lines[table_start:table_end + 1]
        )

    def _is_financial_data_line(self, line: str) -> bool:
        """Check if line contains financial data."""
        # Look for currency amounts
        currency_pattern = r'\$\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand))?'
        if re.search(currency_pattern, line, re.IGNORECASE):
            return True

        # Look for percentages
        if re.search(r'\d+(?:\.\d+)?\s*%', line):
            return True

        # Look for parenthetical numbers (negative values)
        if re.search(r'\(\s*[\d,]+(?:\.\d+)?\s*\)', line):
            return True

        # Look for columnar numeric data
        numbers = re.findall(r'(?<!\w)[\d,]+(?:\.\d+)?(?!\w)', line)
        if len(numbers) >= 2:
            # Check if numbers are spaced apart
            first_num_pos = line.find(numbers[0])
            last_num_pos = line.rfind(numbers[-1])
            if last_num_pos - first_num_pos > len(numbers[0]) + 10:
                return True

        return False

    def _is_table_note_or_total(self, line: str) -> bool:
        """Check if line is a table note or total line."""
        note_total_patterns = [
            r'^\s*\([a-z0-9]\)',  # (a), (1), etc.
            r'^\s*\*',  # Asterisk notes
            r'(?:total|subtotal|net|gross)\s*:?\s*\$?[\d,]',
            r'(?:see|refer\s+to)\s+(?:note|accompanying)',
        ]

        for pattern in note_total_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True

        return False

    def _identify_delimited_tables(self, lines: List[str], table_lines: Set[int]) -> List[Table]:
        """Identify tables with clear delimiters."""
        tables = []
        i = 0

        while i < len(lines):
            # Skip lines already identified as part of tables
            if i in table_lines:
                i += 1
                continue

            # Check for horizontal delimiter
            if self._is_horizontal_delimiter(lines[i]):
                table = self._extract_delimited_table(lines, i, table_lines)
                if table:
                    tables.append(table)
                    # Mark lines as part of table
                    for line_num in range(table.start_line, table.end_line + 1):
                        table_lines.add(line_num)
                    i = table.end_line + 1
                else:
                    i += 1
            # Check for pipe-delimited table
            elif '|' in lines[i] and lines[i].count('|') >= 2:
                table = self._extract_pipe_table(lines, i, table_lines)
                if table:
                    tables.append(table)
                    for line_num in range(table.start_line, table.end_line + 1):
                        table_lines.add(line_num)
                    i = table.end_line + 1
                else:
                    i += 1
            else:
                i += 1

        return tables

    def _identify_aligned_tables(self, lines: List[str], table_lines: Set[int]) -> List[Table]:
        """Identify space-aligned tables."""
        tables = []
        i = 0

        while i < len(lines):
            # Skip lines already identified as part of tables
            if i in table_lines:
                i += 1
                continue

            # Look for potential table headers
            if self._looks_like_table_header(lines[i]):
                table = self._extract_aligned_table(lines, i, table_lines)
                if table:
                    tables.append(table)
                    for line_num in range(table.start_line, table.end_line + 1):
                        table_lines.add(line_num)
                    i = table.end_line + 1
                else:
                    i += 1
            else:
                i += 1

        return tables

    def _is_horizontal_delimiter(self, line: str) -> bool:
        """Check if line is a horizontal delimiter."""
        stripped = line.strip()
        if len(stripped) < 3:
            return False

        # Check for lines made of dashes, equals, or underscores
        delimiter_chars = {'-', '=', '_'}
        unique_chars = set(stripped.replace(' ', ''))

        return len(unique_chars) == 1 and unique_chars.issubset(delimiter_chars)

    def _is_table_line(self, line: str) -> bool:
        """Check if a line appears to be part of a table."""
        # Has multiple segments separated by significant spaces
        if re.search(r'\s{3,}', line):
            segments = re.split(r'\s{3,}', line.strip())
            if len(segments) >= 2:
                # Check if at least some segments have content
                non_empty = [s for s in segments if s.strip()]
                if len(non_empty) >= 2:
                    return True

        # Has tabs (often used in tables)
        if '\t' in line and line.count('\t') >= 1:
            segments = line.split('\t')
            non_empty = [s for s in segments if s.strip()]
            if len(non_empty) >= 2:
                return True

        # Has pipe delimiters
        if '|' in line and line.count('|') >= 2:
            return True

        # Is a delimiter line
        if self._is_horizontal_delimiter(line):
            return True

        # Has financial data in columns
        if self._is_financial_data_line(line):
            return True

        return False

    def _looks_like_table_header(self, line: str) -> bool:
        """Check if line looks like a table header."""
        # Check for date headers
        if re.search(r'(?:Year|Period|Quarter|Month)\s+End(?:ed|ing)', line, re.IGNORECASE):
            return True

        # Check for financial statement headers
        if re.search(r'(?:December|June|March|September)\s+\d{1,2},?\s+20\d{2}', line, re.IGNORECASE):
            return True

        # Check for columnar structure with common headers
        segments = re.split(r'\s{3,}|\t', line.strip())
        if len(segments) >= TABLE_MIN_COLUMNS:
            header_keywords = ['total', 'year', 'quarter', 'revenue', 'income', 'assets',
                             'change', 'increase', 'decrease', '%', '$', '2019', '2020',
                             '2021', '2022', '2023', '2024', 'actual', 'budget']
            matches = sum(1 for seg in segments
                         if any(keyword in seg.lower() for keyword in header_keywords))
            if matches >= 1:
                return True

        return False

    def _extract_delimited_table(self, lines: List[str], delimiter_line: int,
                                table_lines: Set[int]) -> Optional[Table]:
        """Extract a table with horizontal delimiter."""
        # Look for header above delimiter
        if delimiter_line > 0 and not lines[delimiter_line - 1].strip():
            return None

        # Find table bounds
        table_start = delimiter_line - 1 if delimiter_line > 0 else delimiter_line
        table_raw_lines = []

        # Add header if exists
        if delimiter_line > 0:
            table_raw_lines.append(lines[delimiter_line - 1])

        # Add delimiter
        table_raw_lines.append(lines[delimiter_line])

        # Collect data rows
        current_line = delimiter_line + 1
        consecutive_empty = 0

        while current_line < len(lines) and consecutive_empty < 2:
            line = lines[current_line]

            if not line.strip():
                consecutive_empty += 1
                if consecutive_empty == 1:
                    table_raw_lines.append(line)
            else:
                consecutive_empty = 0
                # Check if line looks like table data
                if self._looks_like_table_data(line) or self._is_table_continuation(line):
                    table_raw_lines.append(line)
                else:
                    break

            current_line += 1

        if len(table_raw_lines) < TABLE_MIN_ROWS:
            return None

        # Find title
        title = self._extract_table_title(lines, table_start)

        # Calculate end line
        end_line = table_start + len(table_raw_lines) - 1

        return Table(
            content=[],  # Not parsing content, preserving raw
            start_pos=0,
            end_pos=0,
            start_line=table_start,
            end_line=end_line,
            title=title,
            confidence=0.9,
            table_type='delimited',
            original_text='\n'.join(table_raw_lines),
            raw_lines=lines[table_start:end_line + 1]
        )

    def _extract_pipe_table(self, lines: List[str], start_line: int,
                           table_lines: Set[int]) -> Optional[Table]:
        """Extract a pipe-delimited table."""
        table_raw_lines = []
        current_line = start_line

        while current_line < len(lines):
            line = lines[current_line]
            if '|' in line:
                table_raw_lines.append(line)
                current_line += 1
            else:
                # Check if it's a continuation
                if line.strip() and self._is_table_continuation(line):
                    table_raw_lines.append(line)
                    current_line += 1
                else:
                    break

        if len(table_raw_lines) < TABLE_MIN_ROWS:
            return None

        # Find title
        title = self._extract_table_title(lines, start_line)

        # Calculate end line
        end_line = start_line + len(table_raw_lines) - 1

        return Table(
            content=[],  # Not parsing, preserving raw
            start_pos=0,
            end_pos=0,
            start_line=start_line,
            end_line=end_line,
            title=title,
            confidence=0.95,
            table_type='delimited',
            original_text='\n'.join(table_raw_lines),
            raw_lines=lines[start_line:end_line + 1]
        )

    def _extract_aligned_table(self, lines: List[str], start_line: int,
                              table_lines: Set[int]) -> Optional[Table]:
        """Extract a space-aligned table."""
        table_raw_lines = [lines[start_line]]  # Start with header
        current_line = start_line + 1
        consecutive_empty = 0
        has_numeric_data = False

        while current_line < len(lines) and consecutive_empty < 2:
            line = lines[current_line]

            if not line.strip():
                consecutive_empty += 1
                if consecutive_empty == 1:
                    table_raw_lines.append(line)
                current_line += 1
                continue
            else:
                consecutive_empty = 0

            # Check for numeric data
            if re.search(r'\d', line):
                has_numeric_data = True

            # Check if line looks like table data
            if (self._is_table_line(line) or
                self._is_financial_data_line(line) or
                self._is_table_continuation(line)):
                table_raw_lines.append(line)
            else:
                break

            current_line += 1

        # Validate
        if len(table_raw_lines) < TABLE_MIN_ROWS or not has_numeric_data:
            return None

        # Find title
        title = self._extract_table_title(lines, start_line)

        # Calculate end line
        end_line = start_line + len(table_raw_lines) - 1

        return Table(
            content=[],  # Not parsing, preserving raw
            start_pos=0,
            end_pos=0,
            start_line=start_line,
            end_line=end_line,
            title=title,
            confidence=0.8,
            table_type='aligned',
            original_text='\n'.join(table_raw_lines),
            raw_lines=lines[start_line:end_line + 1]
        )

    def _looks_like_table_data(self, line: str) -> bool:
        """Check if line looks like table data."""
        # Contains numbers
        if re.search(r'\d', line):
            # Check for multiple numbers separated by spaces
            numbers = re.findall(r'[\d,]+(?:\.\d+)?', line)
            if len(numbers) >= 2:
                return True
            # Single number might be OK if it's financial data
            if self._is_financial_data_line(line):
                return True

        # Has columnar structure
        if re.search(r'\s{3,}|\t', line):
            segments = re.split(r'\s{3,}|\t', line.strip())
            non_empty = [s for s in segments if s.strip()]
            if len(non_empty) >= 2:
                return True

        return False

    def _is_table_continuation(self, line: str) -> bool:
        """Check if line is a table continuation (like totals, notes)."""
        continuation_keywords = [
            'total', 'subtotal', 'net', 'gross', 'sum',
            'see note', 'see accompanying', 'continued',
            'includes', 'excludes', 'consists of',
            'represents', 'related to', 'primarily'
        ]
        line_lower = line.lower()

        # Check for keywords
        if any(keyword in line_lower for keyword in continuation_keywords):
            return True

        # Check for note markers
        if re.match(r'^\s*\([a-z0-9]\)', line, re.IGNORECASE):
            return True

        # Check for footnote markers
        if re.match(r'^\s*\*+\s*', line):
            return True

        return False

    def _extract_table_title(self, lines: List[str], table_start: int) -> Optional[str]:
        """Extract table title from preceding lines."""
        # Look at previous 3 lines
        for i in range(1, min(4, table_start + 1)):
            line_idx = table_start - i
            if line_idx < 0:
                break

            line = lines[line_idx].strip()

            # Skip empty lines
            if not line:
                continue

            # Check if it looks like a title
            if (len(line) < 200 and
                not self._is_table_line(line) and
                not self._is_financial_data_line(line) and
                not line.endswith('.') and
                not re.match(r'^\d+$', line)):  # Not just a number

                # Additional title indicators
                title_indicators = [
                    'table', 'schedule', 'summary', 'consolidated',
                    'condensed', 'statement', 'analysis'
                ]

                if any(ind in line.lower() for ind in title_indicators):
                    return line

                # Even without indicators, might still be a title
                if len(line) > 10:  # Reasonable length
                    return line

        return None

    def _deduplicate_tables(self, tables: List[Table]) -> List[Table]:
        """Remove duplicate and overlapping tables."""
        if not tables:
            return tables

        # Sort by start position
        tables.sort(key=lambda t: t.start_line)

        deduped = []
        for table in tables:
            # Check if overlaps with existing tables
            overlap = False
            for existing in deduped:
                if (table.start_line >= existing.start_line and
                    table.start_line <= existing.end_line):
                    # Check confidence - keep higher confidence table
                    if table.confidence > existing.confidence:
                        deduped.remove(existing)
                        deduped.append(table)
                    overlap = True
                    break

            if not overlap:
                deduped.append(table)

        return deduped