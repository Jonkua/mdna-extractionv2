"""ZIP archive processor for handling compressed SEC filings with CIK filtering and 10-Q fallback logic, now integrating FilingManager registration."""

import zipfile
import tempfile
from pathlib import Path
from typing import Dict, Optional

from src.core.extractor import MDNAExtractor
from src.core.file_handler import FileHandler
from src.core.filing_manager import FilingManager
from src.core.cik_filter import CIKFilter
from src.utils.logger import get_logger, log_error
from config.settings import VALID_EXTENSIONS, ZIP_EXTENSIONS

logger = get_logger(__name__)


class ZipProcessor:
    """Handles processing of ZIP archives containing SEC filings, integrated with CIK filtering and FilingManager registration."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.extractor = MDNAExtractor(output_dir)
        self.file_handler = FileHandler()
        self.filing_manager = FilingManager()

    def process_zip_file(
        self,
        zip_path: Path,
        cik_filter: Optional[CIKFilter] = None
    ) -> Dict[str, any]:
        """
        Process a single ZIP file, applying CIK filtering, registering filings, and selecting via FilingManager.

        Args:
            zip_path: Path to ZIP file
            cik_filter: Optional CIKFilter instance

        Returns:
            Processing statistics
        """
        logger.info(f"Processing ZIP file: {zip_path}")

        stats = {
            "zip_file": str(zip_path),
            "total_files": 0,
            "processed": 0,
            "failed": 0,
            "filtered_out": 0,
            "errors": []
        }

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                members = zf.namelist()
                # filter only valid text extensions
                text_members = [f for f in members if any(f.endswith(ext) for ext in VALID_EXTENSIONS)]
                stats["total_files"] = len(text_members)
                logger.info(f"Found {len(text_members)} text files in archive")

                # 1) Extract all to temp and collect candidates
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    candidates = []
                    for member in text_members:
                        try:
                            zf.extract(member, temp_path)
                            file_path = temp_path / member

                            # apply CIK filter pre-check
                            if cik_filter and cik_filter.has_cik_filters():
                                cik, year, form_type = self.extractor._parse_file_metadata_simple(file_path)
                                if not cik_filter.should_process_filing(cik, form_type, year):
                                    stats["filtered_out"] += 1
                                    logger.debug(f"Filtered out by CIK filter: {member} (CIK: {cik})")
                                    continue

                            # register with FilingManager for selection logic
                            cik, year, form_type = self.extractor._parse_file_metadata_simple(file_path)
                            if cik and year and form_type:
                                self.filing_manager.add_filing(file_path, cik, year, form_type)
                                candidates.append(file_path)
                            else:
                                logger.debug(f"Metadata parse failed, skipping registration: {member}")

                        except Exception as e:
                            stats["failed"] += 1
                            stats["errors"].append({"file": member, "error": str(e)})
                            log_error(f"Error extracting {member} from {zip_path}: {e}")

                    # 2) Select which filings to process based on priority
                    selection = self.filing_manager._select_filings_to_process()
                    to_process = set(selection.get("process", []))

                    # 3) Extract MD&A for selected filings
                    for file_path in to_process:
                        try:
                            result = self.extractor.extract_from_file(file_path)
                            if result:
                                stats["processed"] += 1
                            else:
                                stats["failed"] += 1
                                stats["errors"].append({"file": file_path.name, "error": "Extraction failed"})
                        except Exception as e:
                            stats["failed"] += 1
                            stats["errors"].append({"file": file_path.name, "error": str(e)})
                            log_error(f"Error processing {file_path.name} from {zip_path}: {e}")

        except zipfile.BadZipFile:
            log_error(f"Invalid ZIP file: {zip_path}")
            stats["errors"].append({"file": str(zip_path), "error": "Invalid ZIP file"})
        except Exception as e:
            log_error(f"Error processing ZIP file {zip_path}: {e}")
            stats["errors"].append({"file": str(zip_path), "error": str(e)})

        logger.info(f"ZIP complete: {stats['processed']} processed, {stats['filtered_out']} filtered, {stats['failed']} failed")
        return stats

    def process_directory(
        self,
        input_dir: Path,
        cik_filter: Optional[CIKFilter] = None
    ) -> Dict[str, any]:
        """
        Process all ZIP files in a directory with optional CIK filtering.

        Args:
            input_dir: Directory containing ZIP files
            cik_filter: Optional CIKFilter instance

        Returns:
            Overall processing statistics
        """
        overall_stats = {
            "total_zips": 0,
            "total_files": 0,
            "processed": 0,
            "failed": 0,
            "filtered_out": 0,
            "zip_stats": []
        }

        zip_files = []
        for ext in ZIP_EXTENSIONS:
            zip_files.extend(input_dir.glob(f"*{ext}"))
        zip_files = list(set(zip_files))
        overall_stats["total_zips"] = len(zip_files)

        logger.info(f"Found {len(zip_files)} ZIP files to process in {input_dir}")

        for zip_path in sorted(zip_files):
            stats = self.process_zip_file(zip_path, cik_filter=cik_filter)
            overall_stats["zip_stats"].append(stats)
            overall_stats["total_files"] += stats.get("total_files", 0)
            overall_stats["processed"] += stats.get("processed", 0)
            overall_stats["failed"] += stats.get("failed", 0)
            overall_stats["filtered_out"] += stats.get("filtered_out", 0)

        return overall_stats
