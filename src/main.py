"""Modified main entry point with enhanced table preservation."""

import argparse
import sys
import signal
import atexit
from pathlib import Path
import time
import shutil
import zipfile
from typing import Dict
from config.settings import VALID_EXTENSIONS

from src.core.zip_processor import ZipProcessor
from src.core.extractor import MDNAExtractor  # This will be the enhanced version
from src.core.cik_filter import CIKFilter
from src.utils.logger import setup_logging, get_logger, log_summary
from config.settings import INPUT_DIR, OUTPUT_DIR, CIK_INPUT_DIR

logger = get_logger(__name__)

# Global cleanup paths
cleanup_paths = []


def cleanup_temp_files():
    """Clean up temporary files on exit."""
    for path in cleanup_paths:
        try:
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink()
        except Exception:
            pass


def signal_handler(signum, frame):
    """Handle interrupt signals."""
    logger.info("Processing interrupted, cleaning up...")
    cleanup_temp_files()
    sys.exit(130)


# Register cleanup functions
atexit.register(cleanup_temp_files)
signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Main function with enhanced table preservation."""
    parser = argparse.ArgumentParser(
        description="Extract MD&A sections from 10-K filings with perfect table preservation"
    )

    parser.add_argument("-i", "--input", type=Path, default=INPUT_DIR, help="Input directory with ZIP files")
    parser.add_argument("-o", "--output", type=Path, default=OUTPUT_DIR, help="Output directory for MD&A sections")
    parser.add_argument("-c", "--cik-csv", type=Path, required=True, help="CSV file with CIKs and tickers")
    parser.add_argument("-r", "--raw-dir", type=Path, help="Directory to save raw files (temp)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--keep-raw", action="store_true", help="Keep raw files after processing")

    args = parser.parse_args()

    # Set up logging
    setup_logging(verbose=args.verbose)

    # Validate directories
    if not args.input.exists():
        logger.error(f"Input directory does not exist: {args.input}")
        sys.exit(1)

    if not args.cik_csv.exists():
        logger.error(f"CIK CSV file does not exist: {args.cik_csv}")
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)

    # Set up raw file directory
    if args.raw_dir:
        raw_dir = args.raw_dir
    else:
        raw_dir = args.output / "raw_filings"

    raw_dir.mkdir(parents=True, exist_ok=True)

    if not args.keep_raw:
        cleanup_paths.append(raw_dir)

    start_time = time.time()

    # Initialize CIK filter with single CSV file
    logger.info(f"Loading CIK list from: {args.cik_csv}")
    cik_filter = CIKFilter(cik_csv_file=args.cik_csv, input_dir=args.input)

    if cik_filter.has_cik_filters():
        summary = cik_filter.get_summary()
        logger.info(f"Loaded {summary['total_ciks']} CIKs from CSV")
        logger.info(f"Looking for 10-K filings in ZIP files...")
    else:
        logger.error("No CIKs loaded from CSV file")
        sys.exit(1)

    # Register temp directories for cleanup
    cleanup_paths.extend([
        args.output / "temp_extraction",
        args.input / "temp_extraction",
        args.input / "temp_zip_extraction"
    ])

    try:
        logger.info(f"Starting processing: {args.input}")
        logger.info("Table preservation mode: ENABLED")

        # Process ZIP files with table-preserving processor
        processor = TablePreservingZipProcessor(
            output_dir=args.output,
            raw_dir=raw_dir,
            mdna_only=True,
            delete_raw_after_processing=not args.keep_raw
        )

        stats = processor.process_directory(args.input, cik_filter=cik_filter)

        # Calculate timing
        elapsed_time = time.time() - start_time

        # Print final results
        logger.info("=" * 50)
        logger.info("PROCESSING COMPLETE")
        logger.info("=" * 50)
        logger.info(f"Time elapsed: {elapsed_time:.1f} seconds")
        logger.info(f"Total ZIP files: {stats.get('total_zips', 0)}")
        logger.info(f"Total files in ZIPs: {stats.get('total_files', 0)}")
        logger.info(f"Files matching CIK filter: {stats.get('total_files', 0) - stats.get('filtered_out', 0)}")
        logger.info(f"Successfully extracted MD&A: {stats.get('processed', 0)}")
        logger.info(f"Failed: {stats.get('failed', 0)}")

        if not args.keep_raw:
            logger.info(f"Raw files deleted after processing")
        else:
            logger.info(f"Raw files saved in: {raw_dir}")

        if stats.get('processed', 0) > 0:
            logger.info(f"✅ MD&A sections with preserved tables saved to: {args.output}")
            sys.exit(0)
        else:
            logger.error("No MD&A sections were successfully extracted")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        cleanup_temp_files()
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=args.verbose)
        cleanup_temp_files()
        sys.exit(1)


class TablePreservingZipProcessor(ZipProcessor):
    """Modified ZIP processor with enhanced table preservation."""

    def __init__(self, output_dir: Path, raw_dir: Path, mdna_only: bool = True,
                 delete_raw_after_processing: bool = True):
        super().__init__(output_dir)
        self.raw_dir = raw_dir
        self.mdna_only = mdna_only
        self.delete_raw_after_processing = delete_raw_after_processing
        # Use the enhanced extractor
        self.extractor = MDNAExtractor(output_dir)

    def process_zip_file(self, zip_path: Path, cik_filter=None) -> Dict[str, any]:
        """Process ZIP file with table preservation."""
        logger.info(f"Processing ZIP: {zip_path.name}")

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
                # Get all text files
                all_files = zf.namelist()
                text_files = [f for f in all_files if any(f.endswith(ext) for ext in VALID_EXTENSIONS)]

                stats["total_files"] = len(text_files)
                logger.info(f"  Found {stats['total_files']} text files in ZIP")

                if not text_files:
                    return stats

                # Process each file
                for file_name in text_files:
                    try:
                        # Extract to raw directory first
                        raw_file_path = self.raw_dir / Path(file_name).name

                        with zf.open(file_name) as source:
                            content = source.read()

                            # Quick check if this is a 10-K and matches CIK filter
                            content_str = content.decode('utf-8', errors='ignore')

                            # Extract CIK from content
                            import re
                            cik_match = re.search(r'CENTRAL INDEX KEY:\s*(\d+)', content_str)
                            if not cik_match:
                                cik_match = re.search(r'CIK:\s*(\d+)', content_str)

                            if cik_match:
                                cik = cik_match.group(1).zfill(10)

                                # Check if it's a 10-K
                                if '10-K' not in content_str[:5000].upper():
                                    stats["filtered_out"] += 1
                                    continue

                                # Check CIK filter
                                if cik_filter and not cik_filter.should_process_cik(cik):
                                    stats["filtered_out"] += 1
                                    continue

                                # Save raw file
                                with open(raw_file_path, 'wb') as target:
                                    target.write(content)

                                logger.info(f"  Processing: {raw_file_path.name} (CIK: {cik})")

                                # Process for MD&A extraction with table preservation
                                result = self.extractor.extract_from_file(raw_file_path)

                                if result:
                                    stats["processed"] += 1
                                    logger.info(f"  ✅ Extracted MD&A with preserved tables")
                                else:
                                    stats["failed"] += 1
                                    logger.warning(f"  ❌ No MD&A found in: {file_name}")

                                # Delete raw file if requested
                                if self.delete_raw_after_processing:
                                    try:
                                        raw_file_path.unlink()
                                    except:
                                        pass
                            else:
                                stats["filtered_out"] += 1

                    except Exception as e:
                        stats["failed"] += 1
                        stats["errors"].append({"file": file_name, "error": str(e)})
                        logger.error(f"  Error processing {file_name}: {e}")

        except Exception as e:
            stats["errors"].append({"zip_file": str(zip_path), "error": str(e)})
            logger.error(f"Error processing ZIP {zip_path}: {e}")

        logger.info(f"ZIP complete: {stats['processed']} MD&A sections extracted, {stats['filtered_out']} filtered")
        return stats


if __name__ == "__main__":
    main()