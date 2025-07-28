"""Fixed MD&A extractor that normalizes text before searching for sections and properly formats tables."""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple

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


class MDNAExtractor:
    """Fixed extractor that normalizes before section detection and properly formats tables."""

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
        Extract MD&A section from a filing file with normalization first and proper table formatting.

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

            # 2) Normalize text
            logger.debug("Normalizing text content...")
            normalized = self._normalize_filing_content(content)
            if not normalized:
                logger.error("Text normalization failed")
                return None

            # 3) Build Filing object
            filing = self._create_filing_from_text(file_path, normalized)
            if filing is None:
                logger.error("Could not create filing object")
                return None

            # 4) Find MD&A in normalized text
            logger.debug("Searching for MD&A section...")
            bounds = self.section_parser.find_mdna_section(normalized, filing.form_type)
            if not bounds:
                # Try incorporation by reference
                inc = self.section_parser.check_incorporation_by_reference(
                    normalized, 0, len(normalized)
                )
                if inc:
                    logger.warning(f"MD&A incorporated by reference: {inc.document_type}")
                    resolved = self.reference_resolver.resolve_reference(inc, filing)
                    if resolved:
                        normalized = resolved
                        bounds = (0, len(resolved))
                    else:
                        log_error("Could not resolve incorporation by reference", file_path)
                        return None
                else:
                    log_error("MD&A section not found", file_path)
                    return None

            start_pos, end_pos = bounds

            # 5) Validate section
            validation = self.section_parser.validate_section(
                normalized, start_pos, end_pos, filing.form_type
            )
            if not validation["is_valid"]:
                for w in validation["warnings"]:
                    logger.warning(f"Validation warning: {w}")

            # 6) Slice out MD&A text
            mdna_text = normalized[start_pos:end_pos]

            # 7) Sub-sections, tables, cross-refs - CRITICAL TABLE PROCESSING
            subsections = self.section_parser.extract_subsections(mdna_text)

            # Identify tables in the MD&A text
            logger.debug("Identifying tables in MD&A text...")
            tables = self.table_parser.identify_tables(mdna_text)
            if tables:
                logger.info(f"Found {len(tables)} tables in MD&A")

                # CRITICAL FIX: Apply table formatting to preserve table structure
                logger.debug("Applying table formatting to preserve structure...")
                mdna_text = self.table_parser.preserve_tables_in_text(mdna_text, tables)
                logger.info("Table formatting applied successfully")
            else:
                logger.debug("No tables found in MD&A text")

            # Process cross-references
            cross_refs = self.cross_ref_parser.find_cross_references(mdna_text)
            if cross_refs:
                logger.info(f"Found {len(cross_refs)} cross-references")
                resolved_refs = self.cross_ref_parser.resolve_references(
                    cross_refs, normalized, self.text_normalizer
                )
                if resolved_refs:
                    cross_ref_text = self.cross_ref_parser.format_resolved_references(resolved_refs)
                    mdna_text += cross_ref_text

            # 8) Assemble result and write out
            result = ExtractionResult(
                filing=filing,
                mdna_text=mdna_text,  # Now contains properly formatted tables
                start_pos=start_pos,
                end_pos=end_pos,
                word_count=validation["word_count"],
                subsections=subsections,
                tables=tables,
                cross_references=cross_refs
            )
            self._save_extraction_result(result, filing, file_path)

            logger.info(f"✓ Successfully extracted MD&A ({validation['word_count']} words)")
            if tables:
                logger.info(f"✓ Preserved {len(tables)} tables with proper formatting")
            return result

        except Exception as e:
            log_error(f"Extraction failed: {e}", file_path)
            logger.exception("Detailed error:")
            return None

    def _normalize_filing_content(self, raw_content: str) -> Optional[str]:
        """
        Normalize filing content by removing HTML, XBRL, and other markup.

        Args:
            raw_content: Raw filing content

        Returns:
            Normalized text content
        """
        try:
            # Remove HTML tags
            content = self._remove_html_tags(raw_content)

            # Remove XBRL tags
            content = self._remove_xbrl_tags(content)

            # Apply standard text normalization WITH STRUCTURE PRESERVATION
            # This is critical for tables
            content = self.text_normalizer.normalize_text(content, preserve_structure=True)

            # Additional SEC-specific cleaning
            content = self._clean_sec_specific_content(content)

            return content

        except Exception as e:
            logger.error(f"Error normalizing content: {e}")
            return None

    def _remove_html_tags(self, text: str) -> str:
        """Remove HTML tags while preserving text content."""
        # First, replace common block tags with newlines to preserve structure
        block_tags = ['p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr']
        for tag in block_tags:
            text = re.sub(f'</{tag}>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(f'<{tag}[^>]*>', '\n', text, flags=re.IGNORECASE)

        # Replace &nbsp; with space
        text = re.sub(r'&nbsp;?', ' ', text, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        import html
        text = html.unescape(text)

        return text

    def _remove_xbrl_tags(self, text: str) -> str:
        """Remove XBRL tags and namespaces."""
        # Remove XBRL instance documents
        text = re.sub(r'<xbrl:.*?>.*?</xbrl:.*?>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove inline XBRL tags
        text = re.sub(r'<ix:.*?>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</ix:.*?>', '', text, flags=re.IGNORECASE)

        # Remove other XBRL-related tags
        text = re.sub(r'<[^>]*:[^>]+>', '', text)

        return text

    def _clean_sec_specific_content(self, text: str) -> str:
        """Remove SEC-specific artifacts."""
        # Remove EDGAR headers
        text = re.sub(r'<SEC-DOCUMENT>.*?</SEC-DOCUMENT>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<SEC-HEADER>.*?</SEC-HEADER>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove TYPE tags
        text = re.sub(r'<TYPE>[^<]+', '', text, flags=re.IGNORECASE)

        # Remove SEQUENCE tags
        text = re.sub(r'<SEQUENCE>[^<]+', '', text, flags=re.IGNORECASE)

        # Remove FILENAME tags
        text = re.sub(r'<FILENAME>[^<]+', '', text, flags=re.IGNORECASE)

        # Remove excessive newlines
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        return text

    def _create_filing_from_text(self, file_path: Path, content: str) -> Optional[Filing]:
        """
        Create Filing object from normalized text content.

        Args:
            file_path: Path to filing file
            content: Normalized text content

        Returns:
            Filing object or None
        """
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
        """Parse metadata from filename formatted as YYYYMMDD_FormType_edgar_data_CIK_AccessionNumber.txt"""
        filename = file_path.name
        cik = None
        filing_date = None
        form_type = None

        pattern = r'(\d{8})_(10-[KQ](?:/A)?)_edgar_data_(\d{1,10})_([0-9\-]+)\.txt'
        match = re.search(pattern, filename, re.IGNORECASE)

        if match:
            date_str = match.group(1)
            form_type = match.group(2).upper()
            cik = match.group(3).zfill(10)  # Pad to 10 digits

            try:
                filing_date = datetime.strptime(date_str, '%Y%m%d')
            except Exception as e:
                logger.warning(f"Could not parse date from {date_str}: {e}")

        return cik, filing_date, form_type

    def _extract_cik(self, content: str) -> Optional[str]:
        """Extract CIK from normalized content."""
        patterns = [
            r'CENTRAL INDEX KEY:\s*(\d+)',
            r'CIK:\s*(\d+)',
            r'C\.I\.K\.\s*NO\.\s*(\d+)',
            r'COMMISSION FILE NUMBER:\s*\d+-(\d+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                cik = match.group(1).strip()
                # Pad to 10 digits
                return cik.zfill(10)

        return None

    def _extract_form_type(self, content: str) -> Optional[str]:
        """Extract form type from normalized content."""
        # Look in first 1000 characters
        header = content[:1000]

        patterns = [
            r'FORM\s+(10-[KQ])(?:/A)?',
            r'FORM\s+TYPE:\s*(10-[KQ])(?:/A)?',
            r'ANNUAL REPORT PURSUANT TO SECTION 13'  # Indicates 10-K
        ]

        for pattern in patterns:
            match = re.search(pattern, header, re.IGNORECASE)
            if match:
                if 'ANNUAL REPORT' in pattern:
                    return '10-K'
                form_type = match.group(1).upper()
                # Check for amendment
                if '/A' in match.group(0).upper():
                    form_type += '/A'
                return form_type

        # Default based on content
        if 'FORM 10-Q' in header.upper():
            return '10-Q'
        elif 'FORM 10-K' in header.upper():
            return '10-K'

        return '10-K'  # Default assumption

    def _extract_filing_date(self, content: str) -> Optional[datetime]:
        """Extract filing date from normalized content."""
        patterns = [
            r'FILED AS OF DATE:\s*(\d{8})',
            r'DATE OF REPORT[^:]*:\s*(\d{4}-\d{2}-\d{2})',
            r'For the period ended\s+(\w+\s+\d{1,2},?\s+\d{4})'
        ]

        for pattern in patterns:
            match = re.search(pattern, content[:2000], re.IGNORECASE)
            if match:
                date_str = match.group(1)

                # Try different date formats
                for fmt in ['%Y%m%d', '%Y-%m-%d', '%B %d, %Y', '%B %d %Y']:
                    try:
                        return datetime.strptime(date_str.replace(',', ''), fmt)
                    except:
                        continue

        return None

    def _extract_company_name(self, content: str) -> str:
        """Extract company name from normalized content."""
        company_name = self.text_normalizer.extract_company_name(content)
        return company_name or "Unknown Company"

    def _save_extraction_result(self, result: ExtractionResult, filing: Filing, file_path: Path):
        """Save extraction result to file."""
        # Generate output filename in format: cik#_CoNameSanitized_FormType_YYYY.txt
        year_str = filing.filing_date.strftime('%Y') if filing.filing_date else 'unknown'
        company_safe = self.text_normalizer.sanitize_filename(filing.company_name)
        form_type_safe = filing.form_type.replace('/', '')  # 10-K/A becomes 10-KA

        output_filename = f"{filing.cik}_{company_safe}_{form_type_safe}_{year_str}.txt"
        output_path = self.output_dir / output_filename

        # Format output content
        output_content = self._format_output(result)

        # Save file
        self.file_handler.write_file(output_path, output_content)
        logger.info(f"Saved extraction to: {output_path}")

    def _format_output(self, result: ExtractionResult) -> str:
        """Format extraction result for output with proper table formatting."""
        output = []

        # Header
        output.append("=" * 80)
        output.append(f"CIK: {result.filing.cik}")
        output.append(f"Company: {result.filing.company_name}")
        output.append(f"Form Type: {result.filing.form_type}")
        output.append(f"Filing Date: {result.filing.filing_date}")
        output.append(f"Extraction Date: {datetime.now().isoformat()}")
        output.append(f"Word Count: {result.word_count}")
        if result.tables:
            output.append(f"Tables Found: {len(result.tables)}")
        output.append("=" * 80)
        output.append("")

        # MD&A content - this now contains properly formatted tables
        output.append(result.mdna_text)

        # Add table summary if tables were found
        if result.tables:
            output.append("\n\n" + "=" * 40)
            output.append("TABLE SUMMARY")
            output.append("=" * 40)
            for i, table in enumerate(result.tables, 1):
                output.append(f"Table {i}:")
                output.append(f"  Type: {table.table_type}")
                output.append(f"  Rows: {len(table.content)}")
                output.append(f"  Columns: {len(table.content[0]) if table.content else 0}")
                if table.title:
                    output.append(f"  Title: {table.title}")
                output.append("")

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