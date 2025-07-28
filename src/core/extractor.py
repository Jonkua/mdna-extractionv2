"""Enhanced MD&A extractor that perfectly preserves table formatting."""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, List, Set

from src.models.filing import Filing, ExtractionResult
from src.parsers.section_parser import SectionParser
from src.parsers.table_parser import TableParser
from src.parsers.cross_reference_parser import CrossReferenceParser
from src.parsers.text_normalizer import TextNormalizer
from src.parsers.reference_resolver import ReferenceResolver
from src.core.file_handler import FileHandler
from src.utils.logger import get_logger, log_error
from config.settings import OUTPUT_DIR

logger = get_logger(__name__)


class TableRegion:
    """Represents a region of text that contains a table."""
    def __init__(self, start_line: int, end_line: int, lines: List[str]):
        self.start_line = start_line
        self.end_line = end_line
        self.lines = lines
        self.original_text = '\n'.join(lines)


class MDNAExtractor:
    """Enhanced extractor that perfectly preserves table formatting."""

    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.file_handler = FileHandler()
        self.section_parser = SectionParser()
        self.table_parser = TableParser()
        self.cross_ref_parser = CrossReferenceParser()
        self.text_normalizer = TextNormalizer()
        self.reference_resolver = ReferenceResolver(output_dir.parent)

    def extract_from_file(self, file_path: Path) -> Optional[ExtractionResult]:
        """
        Extract MD&A section from a filing file with perfect table preservation.

        Args:
            file_path: Path to filing file

        Returns:
            ExtractionResult or None if extraction failed
        """
        logger.info(f"Processing file: {file_path.name}")

        try:
            # 1) Read raw content
            content = self.file_handler.read_file(file_path)
            if not content:
                logger.error(f"Could not read file: {file_path}")
                return None

            # 2) Create two versions: one for parsing, one for preservation
            logger.debug("Creating parsing and preservation versions...")

            # For parsing: light HTML removal but keep structure
            parsing_content = self._create_parsing_version(content)

            # For preservation: minimal changes, keep exact formatting
            preservation_content = self._create_preservation_version(content)

            # 3) Build Filing object from parsing content
            filing = self._create_filing_from_text(file_path, parsing_content)
            if filing is None:
                logger.error("Could not create filing object")
                return None

            # 4) Find MD&A section boundaries in parsing content
            logger.debug("Searching for MD&A section...")
            bounds = self.section_parser.find_mdna_section(parsing_content, filing.form_type)
            if not bounds:
                # Try incorporation by reference
                inc = self.section_parser.check_incorporation_by_reference(
                    parsing_content, 0, len(parsing_content)
                )
                if inc:
                    logger.warning(f"MD&A incorporated by reference: {inc.document_type}")
                    resolved = self.reference_resolver.resolve_reference(inc, filing)
                    if resolved:
                        parsing_content = resolved
                        preservation_content = resolved
                        bounds = (0, len(resolved))
                    else:
                        log_error("Could not resolve incorporation by reference", file_path)
                        return None
                else:
                    log_error("MD&A section not found", file_path)
                    return None

            start_pos, end_pos = bounds

            # 5) Map character positions to line numbers
            start_line, end_line = self._map_positions_to_lines(parsing_content, start_pos, end_pos)

            # 6) Extract MD&A from preservation content using line numbers
            preservation_lines = preservation_content.split('\n')
            mdna_lines = preservation_lines[start_line:end_line + 1]

            # 7) Process the MD&A content with table preservation
            processed_mdna = self._process_mdna_content(mdna_lines)

            # 8) Validate section
            validation = self.section_parser.validate_section(
                parsing_content, start_pos, end_pos, filing.form_type
            )
            if not validation["is_valid"]:
                for w in validation["warnings"]:
                    logger.warning(f"Validation warning: {w}")

            # 9) Extract subsections (from parsing version)
            mdna_text_for_parsing = parsing_content[start_pos:end_pos]
            subsections = self.section_parser.extract_subsections(mdna_text_for_parsing)

            # 10) Find cross-references (from parsing version)
            cross_refs = self.cross_ref_parser.find_cross_references(mdna_text_for_parsing)
            if cross_refs:
                logger.info(f"Found {len(cross_refs)} cross-references")

            # 11) Create result
            result = ExtractionResult(
                filing=filing,
                mdna_text=processed_mdna,
                start_pos=start_pos,
                end_pos=end_pos,
                word_count=validation["word_count"],
                subsections=subsections,
                tables=[],  # Tables are preserved inline
                cross_references=cross_refs
            )

            self._save_extraction_result(result, filing, file_path)

            logger.info(f"✓ Successfully extracted MD&A ({validation['word_count']} words)")
            return result

        except Exception as e:
            log_error(f"Extraction failed: {e}", file_path)
            logger.exception("Detailed error:")
            return None

    def _create_parsing_version(self, content: str) -> str:
        """Create a version suitable for parsing (finding sections, etc.)."""
        # Remove obvious HTML/XML tags but preserve structure
        parsing = content

        # Remove SEC document tags
        parsing = re.sub(r'<SEC-DOCUMENT>.*?</SEC-DOCUMENT>', '', parsing, flags=re.DOTALL | re.IGNORECASE)
        parsing = re.sub(r'<SEC-HEADER>.*?</SEC-HEADER>', '', parsing, flags=re.DOTALL | re.IGNORECASE)
        parsing = re.sub(r'<TYPE>[^<]+', '', parsing, flags=re.IGNORECASE)
        parsing = re.sub(r'<SEQUENCE>[^<]+', '', parsing, flags=re.IGNORECASE)
        parsing = re.sub(r'<FILENAME>[^<]+', '', parsing, flags=re.IGNORECASE)

        # Remove HTML tags but preserve line breaks
        parsing = re.sub(r'<br\s*/?\s*>', '\n', parsing, flags=re.IGNORECASE)
        parsing = re.sub(r'</p>', '\n', parsing, flags=re.IGNORECASE)
        parsing = re.sub(r'<p[^>]*>', '\n', parsing, flags=re.IGNORECASE)

        # Remove remaining tags
        parsing = re.sub(r'<[^>]+>', '', parsing)

        # Decode HTML entities
        import html
        parsing = html.unescape(parsing)

        # Replace &nbsp; with space
        parsing = re.sub(r'&nbsp;?', ' ', parsing, flags=re.IGNORECASE)

        return parsing

    def _create_preservation_version(self, content: str) -> str:
        """Create a version that preserves exact formatting."""
        preservation = content

        # Only remove the most egregious tags that would interfere
        preservation = re.sub(r'<SEC-DOCUMENT>.*?</SEC-DOCUMENT>', '', preservation, flags=re.DOTALL | re.IGNORECASE)
        preservation = re.sub(r'<SEC-HEADER>.*?</SEC-HEADER>', '', preservation, flags=re.DOTALL | re.IGNORECASE)
        preservation = re.sub(r'<TYPE>[^<]+', '', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'<SEQUENCE>[^<]+', '', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'<FILENAME>[^<]+', '', preservation, flags=re.IGNORECASE)

        # For HTML tables, try to preserve structure
        preservation = self._convert_html_tables(preservation)

        # Handle other HTML more carefully
        preservation = re.sub(r'<br\s*/?\s*>', '\n', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'</tr>', '\n', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'<tr[^>]*>', '', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'</td>', '\t', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'<td[^>]*>', '', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'</th>', '\t', preservation, flags=re.IGNORECASE)
        preservation = re.sub(r'<th[^>]*>', '', preservation, flags=re.IGNORECASE)

        # Remove remaining tags
        preservation = re.sub(r'<[^>]+>', '', preservation)

        # Decode HTML entities
        import html
        preservation = html.unescape(preservation)

        # Replace &nbsp; with actual space
        preservation = re.sub(r'&nbsp;?', ' ', preservation, flags=re.IGNORECASE)

        return preservation

    def _convert_html_tables(self, content: str) -> str:
        """Convert HTML tables to text while preserving structure."""
        # Find all HTML tables
        table_pattern = re.compile(r'<table[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)

        def convert_single_table(match):
            table_html = match.group(0)

            # Extract rows
            rows = []
            row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)

            for row_match in row_pattern.finditer(table_html):
                row_content = row_match.group(1)

                # Extract cells
                cells = []
                cell_pattern = re.compile(r'<t[hd][^>]*>(.*?)</t[hd]>', re.DOTALL | re.IGNORECASE)

                for cell_match in cell_pattern.finditer(row_content):
                    cell_text = cell_match.group(1)
                    # Clean cell content
                    cell_text = re.sub(r'<[^>]+>', '', cell_text)
                    cell_text = cell_text.strip()
                    cells.append(cell_text)

                if cells:
                    # Join cells with tabs
                    rows.append('\t'.join(cells))

            # Join rows with newlines
            return '\n' + '\n'.join(rows) + '\n'

        # Replace all tables
        content = table_pattern.sub(convert_single_table, content)

        return content

    def _map_positions_to_lines(self, content: str, start_pos: int, end_pos: int) -> Tuple[int, int]:
        """Map character positions to line numbers."""
        lines = content.split('\n')
        current_pos = 0
        start_line = 0
        end_line = len(lines) - 1

        for i, line in enumerate(lines):
            line_start = current_pos
            line_end = current_pos + len(line)

            if line_start <= start_pos <= line_end:
                start_line = i

            if line_start <= end_pos <= line_end:
                end_line = i
                break

            current_pos = line_end + 1  # +1 for newline

        return start_line, end_line

    def _process_mdna_content(self, lines: List[str]) -> str:
        """Process MD&A content with intelligent table preservation."""
        processed_lines = []
        i = 0

        while i < len(lines):
            # Check if we're at the start of a table
            table_region = self._identify_table_region(lines, i)

            if table_region:
                # Add spacing before table
                if processed_lines and processed_lines[-1].strip():
                    processed_lines.append('')

                # Add table with exact formatting
                processed_lines.append('--- BEGIN TABLE ---')
                processed_lines.extend(table_region.lines)
                processed_lines.append('--- END TABLE ---')
                processed_lines.append('')

                i = table_region.end_line + 1
            else:
                # Process regular text line
                line = lines[i]

                # Only normalize if it's clearly not part of a table
                if self._is_regular_text_line(line):
                    # Light normalization for regular text
                    normalized = self._normalize_text_line(line)
                    processed_lines.append(normalized)
                else:
                    # Keep as-is (might be table-related)
                    processed_lines.append(line)

                i += 1

        return '\n'.join(processed_lines)

    def _identify_table_region(self, lines: List[str], start_idx: int) -> Optional[TableRegion]:
        """Identify a complete table region starting at the given index."""
        if start_idx >= len(lines):
            return None

        # Check if this line starts a table
        if not self._line_starts_table(lines, start_idx):
            return None

        # Find the extent of the table
        table_lines = []
        current_idx = start_idx
        consecutive_empty = 0
        has_numeric_data = False

        while current_idx < len(lines):
            line = lines[current_idx]

            # Check for numeric data
            if re.search(r'\d', line):
                has_numeric_data = True

            if not line.strip():
                consecutive_empty += 1
                if consecutive_empty > 2:
                    break
                table_lines.append(line)
            else:
                consecutive_empty = 0

                if self._is_table_line(line) or self._is_table_continuation(line):
                    table_lines.append(line)
                else:
                    # Check if it's the end of table
                    if len(table_lines) > 2 and has_numeric_data:
                        break
                    else:
                        # Not a table after all
                        return None

            current_idx += 1

        if len(table_lines) >= 2 and has_numeric_data:
            return TableRegion(start_idx, start_idx + len(table_lines) - 1, table_lines)

        return None

    def _line_starts_table(self, lines: List[str], idx: int) -> bool:
        """Check if the line at the given index starts a table."""
        if idx >= len(lines):
            return False

        line = lines[idx]

        # Check for table headers
        if self._is_table_header(line):
            # Look ahead to confirm it's followed by data
            if idx + 1 < len(lines):
                next_line = lines[idx + 1]
                if self._is_separator_line(next_line) or self._is_table_line(next_line):
                    return True

        # Check for separator followed by data
        if self._is_separator_line(line):
            if idx + 1 < len(lines) and self._is_table_line(lines[idx + 1]):
                return True

        return False

    def _is_table_header(self, line: str) -> bool:
        """Check if line is a table header."""
        # Financial table headers
        if re.search(r'\b(?:Year|Quarter|Period|Month)s?\s+Ended?\b', line, re.IGNORECASE):
            return True

        # Date headers
        if re.search(r'(?:December|March|June|September)\s+\d{1,2},?\s+\d{4}', line, re.IGNORECASE):
            return True

        # Column headers with years
        if re.search(r'\b20\d{2}\b.*\b20\d{2}\b', line):
            return True

        # Financial metrics headers
        header_terms = ['Revenue', 'Income', 'Assets', 'Liabilities', 'Equity', 'Cash']
        if any(term in line for term in header_terms):
            # Check if it has columnar structure
            if re.search(r'\s{3,}|\t', line):
                return True

        return False

    def _is_separator_line(self, line: str) -> bool:
        """Check if line is a table separator."""
        stripped = line.strip()
        if len(stripped) < 3:
            return False

        # Lines made of dashes, equals, underscores
        if re.match(r'^[-=_\s]+$', stripped):
            return True

        return False

    def _is_table_line(self, line: str) -> bool:
        """Check if line is part of a table."""
        # Has tabs or multiple spaces (columnar data)
        if '\t' in line or re.search(r'\s{3,}', line):
            # Check if it has multiple segments
            segments = re.split(r'\t|\s{3,}', line)
            non_empty = [s.strip() for s in segments if s.strip()]
            if len(non_empty) >= 2:
                return True

        # Has financial data
        if self._contains_financial_data(line):
            return True

        # Pipe-delimited
        if line.count('|') >= 2:
            return True

        return False

    def _is_table_continuation(self, line: str) -> bool:
        """Check if line is a table continuation (notes, totals, etc.)."""
        line_lower = line.lower()

        # Total lines
        if re.search(r'\b(?:total|subtotal|net|gross)\b', line_lower):
            return True

        # Note references
        if re.match(r'^\s*\([0-9a-z]\)', line_lower):
            return True

        # Footnote markers
        if re.match(r'^\s*\*+', line):
            return True

        # Note text
        if re.search(r'^\s*(?:see|refer to|includes|excludes|represents)', line_lower):
            return True

        return False

    def _contains_financial_data(self, line: str) -> bool:
        """Check if line contains financial data."""
        # Currency amounts
        if re.search(r'\$\s*[\d,]+', line):
            return True

        # Percentages
        if re.search(r'\d+\.?\d*\s*%', line):
            return True

        # Numbers in parentheses (negative values)
        if re.search(r'\(\s*[\d,]+\.?\d*\s*\)', line):
            return True

        # Multiple numbers separated by spaces
        numbers = re.findall(r'\b[\d,]+\.?\d*\b', line)
        if len(numbers) >= 2:
            # Check if they're spread across the line
            first_pos = line.find(numbers[0])
            last_pos = line.rfind(numbers[-1])
            if last_pos - first_pos > 20:
                return True

        return False

    def _is_regular_text_line(self, line: str) -> bool:
        """Check if line is regular text (not table-related)."""
        # Empty lines are neutral
        if not line.strip():
            return False

        # Lines with table characteristics are not regular text
        if self._is_table_line(line) or self._is_table_continuation(line):
            return False

        # Lines that are mostly text with proper sentences
        if re.search(r'[.!?]\s*$', line.strip()):
            return True

        # Lines with multiple words but no table structure
        words = line.split()
        if len(words) > 5 and not re.search(r'\s{3,}|\t', line):
            return True

        return False

    def _normalize_text_line(self, line: str) -> str:
        """Apply light normalization to a regular text line."""
        # Remove excessive spaces but preserve some indentation
        indent_match = re.match(r'^(\s{0,4})', line)
        indent = indent_match.group(1) if indent_match else ''

        # Normalize the content
        content = ' '.join(line.strip().split())

        return indent + content if content else ''

    def _create_filing_from_text(self, file_path: Path, content: str) -> Optional[Filing]:
        """Create Filing object from normalized text content."""
        try:
            # Try to parse from filename first
            cik, filing_date, form_type = self._parse_filename_metadata(file_path)

            # Extract additional metadata from content
            if not cik:
                cik = self._extract_cik(content)

            if not filing_date:
                filing_date = self._extract_filing_date(content)

            if not form_type:
                form_type = self._extract_form_type(content)

            # Extract company name
            company_name = self._extract_company_name(content)

            if not all([cik, form_type]):
                logger.error(f"Missing required metadata: CIK={cik}, Form={form_type}")
                return None

            # Create filing object
            filing = Filing(
                file_path=file_path,
                cik=cik,
                company_name=company_name,
                form_type=form_type,
                filing_date=filing_date,
                file_size=file_path.stat().st_size if file_path.exists() else 0
            )

            return filing

        except Exception as e:
            logger.error(f"Error creating filing object: {e}")
            return None

    def _parse_filename_metadata(self, file_path: Path) -> Tuple[Optional[str], Optional[datetime], Optional[str]]:
        """Parse metadata from filename."""
        filename = file_path.name
        cik = None
        filing_date = None
        form_type = None

        pattern = r'(\d{8})_(10-[KQ](?:/A)?)_edgar_data_(\d{1,10})_([0-9\-]+)\.txt'
        match = re.search(pattern, filename, re.IGNORECASE)

        if match:
            date_str = match.group(1)
            form_type = match.group(2).upper()
            cik = match.group(3).zfill(10)

            try:
                filing_date = datetime.strptime(date_str, '%Y%m%d')
            except Exception as e:
                logger.warning(f"Could not parse date from {date_str}: {e}")

        return cik, filing_date, form_type

    def _extract_cik(self, content: str) -> Optional[str]:
        """Extract CIK from content."""
        patterns = [
            r'CENTRAL INDEX KEY:\s*(\d+)',
            r'CIK:\s*(\d+)',
            r'C\.I\.K\.\s*NO\.\s*(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content[:5000], re.IGNORECASE)
            if match:
                cik = match.group(1).strip()
                return cik.zfill(10)

        return None

    def _extract_form_type(self, content: str) -> Optional[str]:
        """Extract form type from content."""
        header = content[:2000]

        patterns = [
            r'FORM\s+(10-[KQ])(?:/A)?',
            r'FORM\s+TYPE:\s*(10-[KQ])(?:/A)?',
        ]

        for pattern in patterns:
            match = re.search(pattern, header, re.IGNORECASE)
            if match:
                form_type = match.group(1).upper()
                if '/A' in match.group(0).upper():
                    form_type += '/A'
                return form_type

        # Default based on content
        if 'FORM 10-Q' in header.upper():
            return '10-Q'
        elif 'FORM 10-K' in header.upper():
            return '10-K'

        return '10-K'

    def _extract_filing_date(self, content: str) -> Optional[datetime]:
        """Extract filing date from content."""
        patterns = [
            r'FILED AS OF DATE:\s*(\d{8})',
            r'DATE OF REPORT[^:]*:\s*(\d{4}-\d{2}-\d{2})',
        ]

        for pattern in patterns:
            match = re.search(pattern, content[:2000], re.IGNORECASE)
            if match:
                date_str = match.group(1)

                for fmt in ['%Y%m%d', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except:
                        continue

        return None

    def _extract_company_name(self, content: str) -> str:
        """Extract company name from content."""
        patterns = [
            r'COMPANY\s*CONFORMED\s*NAME:\s*([^\n]+)',
            r'CONFORMED\s*NAME:\s*([^\n]+)',
            r'REGISTRANT\s*NAME:\s*([^\n]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content[:5000], re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'\s+', ' ', name)
                if 3 < len(name) < 100:
                    return name

        return "Unknown Company"

    def _save_extraction_result(self, result: ExtractionResult, filing: Filing, file_path: Path):
        """Save extraction result to file."""
        # Generate output filename
        date_str = filing.filing_date.strftime('%Y-%m-%d') if filing.filing_date else 'unknown'
        company_safe = re.sub(r'[^\w\s-]', '', filing.company_name)[:50]

        output_filename = f"({filing.cik})_({company_safe})_({date_str})_({filing.form_type.replace('/', '_')}).txt"
        output_path = self.output_dir / output_filename

        # Format output content
        output_content = self._format_output(result)

        # Save file
        self.file_handler.write_file(output_path, output_content)
        logger.info(f"Saved extraction to: {output_path}")

    def _format_output(self, result: ExtractionResult) -> str:
        """Format extraction result for output."""
        output = []

        # Header
        output.append("=" * 80)
        output.append(f"CIK: {result.filing.cik}")
        output.append(f"Company: {result.filing.company_name}")
        output.append(f"Form Type: {result.filing.form_type}")
        output.append(f"Filing Date: {result.filing.filing_date}")
        output.append(f"Extraction Date: {datetime.now().isoformat()}")
        output.append(f"Word Count: {result.word_count}")
        output.append("=" * 80)
        output.append("")

        # MD&A content with preserved tables
        output.append(result.mdna_text)

        return '\n'.join(output)

    def _parse_file_metadata_simple(self, file_path: Path) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """Simple metadata parsing for compatibility."""
        cik, filing_date, form_type = self._parse_filename_metadata(file_path)
        year = filing_date.year if filing_date else None
        return cik, year, form_type

    def process_directory(self, input_dir: Path, cik_filter=None) -> Dict[str, int]:
        """Process directory of text files."""
        stats = {
            "total_files": 0,
            "successful": 0,
            "failed": 0,
            "filtered_out": 0
        }

        # Find text files
        text_files = list(input_dir.glob("*.txt")) + list(input_dir.glob("*.TXT"))
        stats["total_files"] = len(text_files)

        logger.info(f"Found {len(text_files)} text files to process")

        for file_path in text_files:
            # Check CIK filter if provided
            if cik_filter and cik_filter.has_cik_filters():
                cik, year, form_type = self._parse_file_metadata_simple(file_path)

                if not cik_filter.should_process_filing(cik, form_type, year):
                    stats["filtered_out"] += 1
                    logger.info(f"Filtered out: {file_path.name}")
                    continue

            # Process file
            result = self.extract_from_file(file_path)
            if result:
                stats["successful"] += 1
            else:
                stats["failed"] += 1

        return stats