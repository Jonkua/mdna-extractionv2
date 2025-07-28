"""Enhanced parser for detecting and preserving tables within MD&A sections, optimized for SEC filings."""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from config.settings import TABLE_MIN_COLUMNS, TABLE_MIN_ROWS
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Table:
    """Represents a detected table with enhanced metadata."""
    content: List[List[str]]  # Table as list of rows
    start_pos: int
    end_pos: int
    start_line: int
    end_line: int
    title: Optional[str]
    confidence: float
    table_type: str  # 'financial', 'delimited', 'aligned', 'mixed'
    original_text: str  # Preserve original formatting
    column_count: int
    row_count: int
    has_monetary_data: bool
    has_percentage_data: bool


class EnhancedTableParser:
    """Enhanced table detection and preservation for SEC filings."""

    def __init__(self):
        # Import enhanced patterns
        from improved_table_patterns import ENHANCED_PATTERNS
        self.enhanced_patterns = ENHANCED_PATTERNS

        # Financial keywords for better detection
        self.financial_keywords = {
            'revenue', 'income', 'profit', 'loss', 'assets', 'liabilities', 'equity',
            'cash', 'flow', 'expenses', 'costs', 'sales', 'operating', 'net', 'gross',
            'total', 'current', 'non-current', 'stockholder', 'shareholder'
        }

    def identify_tables(self, text: str) -> List[Table]:
        """
        Enhanced table identification optimized for SEC filing formats.

        Args:
            text: Text containing potential tables

        Returns:
            List of Table objects with position information
        """
        tables = []
        lines = text.split('\n')

        # Track which lines are part of tables
        table_lines = set()

        logger.debug(f"Starting enhanced table detection on {len(lines)} lines")

        # Try different detection methods in order of specificity
        tables.extend(self._identify_financial_tables(lines, table_lines))
        tables.extend(self._identify_delimited_tables(lines, table_lines))
        tables.extend(self._identify_aligned_tables(lines, table_lines))
        tables.extend(self._identify_mixed_format_tables(lines, table_lines))

        # Remove duplicates and overlaps
        tables = self._deduplicate_tables(tables)

        # Sort by position and confidence
        tables.sort(key=lambda t: (t.start_line, -t.confidence))

        logger.info(f"Enhanced table detection found {len(tables)} tables")
        for i, table in enumerate(tables):
            logger.debug(f"Table {i + 1}: {table.table_type}, lines {table.start_line}-{table.end_line}, "
                         f"confidence {table.confidence:.2f}")

        return tables

    def preserve_tables_in_text(self, text: str, tables: List[Table]) -> str:
        """
        Enhanced table preservation with better formatting for SEC tables.

        Args:
            text: Original text
            tables: List of identified tables

        Returns:
            Text with tables properly formatted and preserved
        """
        if not tables:
            return text

        lines = text.split('\n')
        enhanced_lines = lines.copy()

        logger.debug(f"Applying enhanced table formatting to {len(tables)} tables")

        # Process tables in reverse order to avoid line number shifts
        for table in reversed(sorted(tables, key=lambda t: t.start_line)):
            enhanced_lines = self._format_table_in_lines(enhanced_lines, table)

        result = '\n'.join(enhanced_lines)
        logger.info("Enhanced table formatting completed")
        return result

    def _identify_financial_tables(self, lines: List[str], table_lines: Set[int]) -> List[Table]:
        """Identify financial statement tables using SEC-specific patterns."""
        tables = []
        i = 0

        while i < len(lines):
            if i in table_lines:
                i += 1
                continue

            # Check for financial statement headers
            if self._is_financial_statement_header(lines[i]):
                table = self._extract_financial_table(lines, i, table_lines)
                if table:
                    tables.append(table)
                    # Mark lines as processed
                    for line_num in range(table.start_line, table.end_line + 1):
                        table_lines.add(line_num)
                    i = table.end_line + 1
                else:
                    i += 1
            else:
                i += 1

        return tables

    def _identify_delimited_tables(self, lines: List[str], table_lines: Set[int]) -> List[Table]:
        """Enhanced delimited table detection."""
        tables = []
        i = 0

        while i < len(lines):
            if i in table_lines:
                i += 1
                continue

            # Check for various delimiter patterns
            if self._is_enhanced_delimiter(lines[i]):
                table = self._extract_enhanced_delimited_table(lines, i, table_lines)
                if table:
                    tables.append(table)
                    for line_num in range(table.start_line, table.end_line + 1):
                        table_lines.add(line_num)
                    i = table.end_line + 1
                else:
                    i += 1
            elif self._is_pipe_delimited_line(lines[i]):
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
        """Enhanced space-aligned table detection."""
        tables = []
        i = 0

        while i < len(lines):
            if i in table_lines:
                i += 1
                continue

            if self._is_enhanced_table_header(lines[i]):
                table = self._extract_enhanced_aligned_table(lines, i, table_lines)
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

    def _identify_mixed_format_tables(self, lines: List[str], table_lines: Set[int]) -> List[Table]:
        """Identify tables with mixed formatting common in SEC filings."""
        tables = []
        i = 0

        while i < len(lines):
            if i in table_lines:
                i += 1
                continue

            # Look for lines with multiple monetary values
            if self._has_multiple_monetary_values(lines[i]):
                table = self._extract_monetary_table(lines, i, table_lines)
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

    def _is_financial_statement_header(self, line: str) -> bool:
        """Check if line is a financial statement header."""
        for pattern in self.enhanced_patterns["financial_statements"]:
            if pattern.search(line):
                return True
        return False

    def _is_enhanced_delimiter(self, line: str) -> bool:
        """Enhanced delimiter detection."""
        stripped = line.strip()
        if len(stripped) < 3:
            return False

        # Check enhanced patterns
        for pattern in self.enhanced_patterns["table_boundaries"]:
            if pattern.search(line):
                return True

        # Traditional delimiter check
        delimiter_chars = {'-', '=', '_', '+', '|'}
        unique_chars = set(stripped.replace(' ', ''))

        if len(unique_chars) <= 2 and unique_chars.issubset(delimiter_chars):
            return True

        return False

    def _is_enhanced_table_header(self, line: str) -> bool:
        """Enhanced table header detection for SEC filings."""
        # Check against enhanced patterns
        for pattern in self.enhanced_patterns["sec_tables"]:
            if pattern.search(line):
                return True

        # Check for financial keywords with columnar structure
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in self.financial_keywords):
            # Check if it has columnar structure
            if self._has_columnar_structure(line):
                return True

        return False

    def _has_multiple_monetary_values(self, line: str) -> bool:
        """Check if line contains multiple monetary values (common in SEC tables)."""
        # Pattern for monetary values including parentheses for negatives
        money_pattern = re.compile(r'\$?\s*\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?')
        matches = money_pattern.findall(line)

        # Also check for percentage values
        percent_pattern = re.compile(r'\d+\.?\d*%')
        percent_matches = percent_pattern.findall(line)

        return len(matches) >= 2 or len(percent_matches) >= 2

    def _has_columnar_structure(self, line: str) -> bool:
        """Enhanced columnar structure detection."""
        # Check for multiple significant spaces
        if re.search(r'\s{4,}', line):
            segments = re.split(r'\s{4,}', line.strip())
            if len(segments) >= 2:
                return True

        # Check for tab-separated content
        if '\t' in line:
            segments = line.split('\t')
            if len(segments) >= 2:
                return True

        # Check for multiple numbers or dollar signs
        number_pattern = re.compile(r'[\d$%]')
        segments = re.split(r'\s{2,}', line.strip())
        numeric_segments = sum(1 for seg in segments if number_pattern.search(seg))

        return len(segments) >= 2 and numeric_segments >= 1

    def _extract_financial_table(self, lines: List[str], start_line: int, table_lines: Set[int]) -> Optional[Table]:
        """Extract a financial statement table."""
        table_content = []
        current_line = start_line
        has_monetary = False
        has_percentage = False

        # Include header
        header_line = lines[start_line].strip()
        if header_line:
            table_content.append([header_line])

        current_line += 1

        # Look for table content
        consecutive_empty = 0
        while current_line < len(lines) and consecutive_empty < 3:
            line = lines[current_line]

            if not line.strip():
                consecutive_empty += 1
                current_line += 1
                continue
            else:
                consecutive_empty = 0

            # Check if this line looks like financial data
            if (self._is_financial_data_line(line) or
                    self._has_columnar_structure(line) or
                    self._has_multiple_monetary_values(line)):

                # Parse the line into columns
                parsed_row = self._parse_financial_line(line)
                table_content.append(parsed_row)

                # Check for monetary/percentage data
                if '$' in line or re.search(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', line):
                    has_monetary = True
                if '%' in line:
                    has_percentage = True
            else:
                # Check if we should stop here
                if (self._is_section_break(line) or
                        current_line - start_line > 50):  # Reasonable limit
                    break

            current_line += 1

        if len(table_content) < TABLE_MIN_ROWS:
            return None

        # Find title
        title = self._extract_enhanced_table_title(lines, start_line)

        # Calculate metrics
        column_count = max(len(row) for row in table_content) if table_content else 0
        row_count = len(table_content)

        # Create original text
        end_line = current_line - 1
        original_text = '\n'.join(lines[start_line:end_line + 1])

        return Table(
            content=table_content,
            start_pos=0,  # Will be calculated later if needed
            end_pos=0,
            start_line=start_line,
            end_line=end_line,
            title=title,
            confidence=0.95,  # High confidence for financial tables
            table_type='financial',
            original_text=original_text,
            column_count=column_count,
            row_count=row_count,
            has_monetary_data=has_monetary,
            has_percentage_data=has_percentage
        )

    def _parse_financial_line(self, line: str) -> List[str]:
        """Parse a financial data line into columns."""
        # Try different parsing strategies

        # Strategy 1: Split on significant whitespace
        if re.search(r'\s{4,}', line):
            columns = re.split(r'\s{4,}', line.strip())
            return [col.strip() for col in columns if col.strip()]

        # Strategy 2: Split on tabs
        if '\t' in line:
            columns = line.split('\t')
            return [col.strip() for col in columns if col.strip()]

        # Strategy 3: Pattern-based parsing for monetary data
        # Look for label followed by monetary values
        match = re.match(r'^(.+?)\s+(\$?\s*\(?[\d,]+(?:\.\d+)?\)?.*)', line.strip())
        if match:
            label = match.group(1).strip()
            values_part = match.group(2)

            # Split values part on whitespace
            values = re.findall(r'\$?\s*\(?[\d,]+(?:\.\d+)?\)?', values_part)

            result = [label] + values
            return result

        # Strategy 4: Simple whitespace split as fallback
        return [col.strip() for col in line.split() if col.strip()]

    def _is_financial_data_line(self, line: str) -> bool:
        """Check if line contains financial data."""
        line_lower = line.lower()

        # Check for financial keywords
        financial_indicators = any(keyword in line_lower for keyword in self.financial_keywords)

        # Check for monetary patterns
        has_money = bool(re.search(r'\$\s*\(?[\d,]+(?:\.\d+)?\)?', line))

        # Check for numeric patterns
        has_numbers = bool(re.search(r'\(?[\d,]+(?:\.\d+)?\)?', line))

        return financial_indicators or has_money or (has_numbers and self._has_columnar_structure(line))

    def _is_section_break(self, line: str) -> bool:
        """Check if line represents a section break."""
        line_lower = line.lower().strip()

        # Common section breaks in SEC filings
        section_breaks = [
            'notes to', 'see note', 'refer to note', 'accompanying notes',
            'see accompanying', 'end of table', 'continued on', 'see page'
        ]

        return any(break_phrase in line_lower for break_phrase in section_breaks)

    def _format_table_in_lines(self, lines: List[str], table: Table) -> List[str]:
        """Enhanced table formatting within the text."""
        result_lines = lines.copy()

        # Add table markers for better visibility
        if table.start_line > 0:
            # Add spacing before table
            result_lines[table.start_line] = f"\n{result_lines[table.start_line]}"

        # Add table header comment
        if table.title:
            title_line = f"\n[TABLE: {table.title}]"
            result_lines.insert(table.start_line, title_line)

        # Format table content for better readability
        for i in range(table.start_line, min(table.end_line + 1, len(result_lines))):
            if i < len(result_lines):
                line = result_lines[i]

                # Preserve significant whitespace in table lines
                if self._is_table_content_line(line, table):
                    # Ensure consistent spacing for monetary values
                    formatted_line = self._format_table_line(line)
                    result_lines[i] = formatted_line

        # Add spacing after table
        if table.end_line + 1 < len(result_lines):
            result_lines[table.end_line + 1] = f"{result_lines[table.end_line + 1]}\n"

        return result_lines

    def _is_table_content_line(self, line: str, table: Table) -> bool:
        """Check if line is part of table content."""
        return (self._has_columnar_structure(line) or
                self._has_multiple_monetary_values(line) or
                table.table_type == 'financial' and self._is_financial_data_line(line))

    def _format_table_line(self, line: str) -> str:
        """Format individual table line for better readability."""
        # Preserve the line largely as-is, but ensure consistent spacing
        # This is crucial for maintaining table structure

        # Remove excessive spaces but preserve columnar structure
        # Replace multiple spaces with exactly 4 spaces to maintain columns
        formatted = re.sub(r'\s{2,}', '    ', line.strip())

        return formatted

    def _extract_enhanced_table_title(self, lines: List[str], table_start: int) -> Optional[str]:
        """Enhanced table title extraction."""
        # Look at previous 5 lines for title
        for i in range(1, min(6, table_start + 1)):
            line_idx = table_start - i
            if line_idx < 0:
                break

            line = lines[line_idx].strip()

            # Skip empty lines
            if not line:
                continue

            # Enhanced title detection
            if (len(line) < 200 and  # Reasonable title length
                    not self._is_table_content_line(line, None) and
                    not re.match(r'^\d+$', line) and  # Not just a number
                    not self._is_section_break(line)):

                # Check if it looks like a title
                if (any(keyword in line.lower() for keyword in
                        ['table', 'statement', 'schedule', 'summary']) or
                        re.search(r'^[A-Z][A-Za-z\s]+$', line)):
                    return line

        return None

    def _extract_enhanced_delimited_table(self, lines: List[str], delimiter_line: int,
                                          table_lines: Set[int]) -> Optional[Table]:
        """Enhanced delimited table extraction."""
        # Similar to original but with enhanced parsing
        return self._extract_financial_table(lines, delimiter_line, table_lines)

    def _extract_pipe_table(self, lines: List[str], start_line: int,
                            table_lines: Set[int]) -> Optional[Table]:
        """Enhanced pipe-delimited table extraction."""
        table_content = []
        current_line = start_line

        while current_line < len(lines):
            line = lines[current_line]
            if '|' in line and line.count('|') >= 2:
                # Parse pipe-delimited content
                cells = [cell.strip() for cell in line.split('|')]
                # Remove empty cells at start/end
                if cells and not cells[0]:
                    cells = cells[1:]
                if cells and not cells[-1]:
                    cells = cells[:-1]
                if cells:
                    table_content.append(cells)
                current_line += 1
            else:
                break

        if len(table_content) < TABLE_MIN_ROWS:
            return None

        # Enhanced table creation
        title = self._extract_enhanced_table_title(lines, start_line)
        end_line = start_line + len(table_content) - 1
        original_text = '\n'.join(lines[start_line:end_line + 1])

        has_monetary = any('$' in str(cell) for row in table_content for cell in row)
        has_percentage = any('%' in str(cell) for row in table_content for cell in row)

        return Table(
            content=table_content,
            start_pos=0,
            end_pos=0,
            start_line=start_line,
            end_line=end_line,
            title=title,
            confidence=0.90,
            table_type='delimited',
            original_text=original_text,
            column_count=max(len(row) for row in table_content) if table_content else 0,
            row_count=len(table_content),
            has_monetary_data=has_monetary,
            has_percentage_data=has_percentage
        )

    def _extract_enhanced_aligned_table(self, lines: List[str], start_line: int,
                                        table_lines: Set[int]) -> Optional[Table]:
        """Enhanced aligned table extraction."""
        return self._extract_financial_table(lines, start_line, table_lines)

    def _extract_monetary_table(self, lines: List[str], start_line: int,
                                table_lines: Set[int]) -> Optional[Table]:
        """Extract table based on monetary value patterns."""
        return self._extract_financial_table(lines, start_line, table_lines)

    def _is_pipe_delimited_line(self, line: str) -> bool:
        """Check if line is pipe-delimited."""
        return '|' in line and line.count('|') >= 2

    def _deduplicate_tables(self, tables: List[Table]) -> List[Table]:
        """Enhanced table deduplication."""
        if not tables:
            return tables

        # Sort by start position and confidence
        tables.sort(key=lambda t: (t.start_line, -t.confidence))

        deduped = []
        for table in tables:
            # Check for overlaps with existing tables
            overlap = False
            for existing in deduped:
                # Check for line overlap
                if (table.start_line <= existing.end_line and
                        table.end_line >= existing.start_line):
                    # Keep the higher confidence table
                    if table.confidence <= existing.confidence:
                        overlap = True
                        break

            if not overlap:
                deduped.append(table)

        return deduped