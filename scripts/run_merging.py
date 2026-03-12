import os
import sys
import logging
import time
import argparse

# Custom Formatter for better visibility
class ColorFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.levelname = "DEBUG"
        elif record.levelno == logging.INFO:
            record.levelname = "INFO "
        return super().format(record)

# Setup Detailed Logging
logging.basicConfig(
    level=logging.DEBUG, # Set to DEBUG for full visibility
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger("scripts.run_merging")

# Add src to sys.path
sys.path.insert(0, os.path.abspath("src"))

try:
    from ledgermind.core.api.memory import Memory
    from ledgermind.core.reasoning.merging import MergeEngine, MergeConfig
except ImportError as e:
    logger.error(f"Critical Import Error: {e}")
    sys.exit(1)

def main():
    # V7.6: Command-line arguments for flexible configuration
    parser = argparse.ArgumentParser(description='LEDGERMIND Hypothesis Merging')
    parser.add_argument('--threshold', type=float, default=0.85,
                        help='Similarity threshold (default: 0.85, range: 0.7-0.95)')
    parser.add_argument('--storage', type=str, default=None,
                        help='Storage path (default: auto-detect)')
    args = parser.parse_args()
    
    # Validate threshold
    if not 0.5 <= args.threshold <= 0.95:
        logger.error(f"Invalid threshold {args.threshold}. Must be between 0.5 and 0.95")
        sys.exit(1)

    logger.info("="*60)
    logger.info("LEDGERMIND HYPOTHESIS MERGING SESSION START")
    logger.info("="*60)

    # Detect storage path
    storage_path = os.path.abspath(args.storage if args.storage else "../.ledgermind")
    if not os.path.exists(storage_path):
        storage_path = os.path.abspath(".ledgermind")

    logger.info(f"Storage Path: {storage_path}")
    logger.info(f"Merge Threshold: {args.threshold}")

    # 1. Initialize Memory
    logger.info("Initializing Memory components...")
    memory = Memory(storage_path=storage_path)

    try:
        # 2. Configuration
        # Threshold 0.85 is strictly for semantic similarity
        config = MergeConfig(
            threshold=args.threshold,
            max_candidates=100
        )
        # Ensure we use vector_embedding
        config.algorithms['default'] = {'name': 'vector_embedding'}

        logger.debug(f"Merge Configuration: threshold={config.threshold}, algorithm=vector_embedding")
        
        # 3. Initialize Merge Engine
        logger.info("Starting Merge Engine facade...")
        engine = MergeEngine(memory, config=config)
        
        # 4. Run Scan with timing
        logger.info("Initiating global knowledge scan (Deep Semantic Analysis)...")
        start_time = time.time()
        
        # The scan will log individual similarity scores if level is DEBUG
        proposals = engine.scan_for_duplicates()
        
        elapsed = time.time() - start_time
        logger.info("-" * 40)
        logger.info(f"Scan Statistics:")
        logger.info(f"  - Total Elapsed Time: {elapsed:.2f} seconds")
        
        if proposals:
            logger.info(f"  - Merge Proposals Created: {len(proposals)}")
            for i, pid in enumerate(proposals, 1):
                logger.info(f"    [{i}] {pid}")
            logger.info("-" * 40)
            logger.info("RESULT: Merging session SUCCESSFUL. Review proposals in semantic store.")
        else:
            logger.info(f"  - No duplicates detected above threshold {config.threshold}.")
            logger.info("-" * 40)
            logger.info("RESULT: Scan finished with no actions required.")
            
    except Exception as e:
        logger.error(f"CRITICAL FAILURE during merging: {e}", exc_info=True)
    finally:
        # 5. Cleanup
        logger.info("Shutting down memory services...")
        memory.close()
        logger.info("="*60)
        logger.info("SESSION COMPLETE")
        logger.info("="*60)

if __name__ == "__main__":
    main()
