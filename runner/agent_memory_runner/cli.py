import argparse
import sys
import os
import time
from agent_memory_runner.pty_driver import PTYDriver
from agent_memory_runner.extractor import MemoryExtractor
from agent_memory_runner.governance import GovernanceEngine

def main():
    parser = argparse.ArgumentParser(description="Agent Memory Runner v2.4.0")
    parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Agent command")
    
    args = parser.parse_args()
    cmd = args.command
    if not cmd:
        cmd = [os.environ.get("SHELL", "sh")]

    # 1. Setup components
    extractor = MemoryExtractor(args.path)
    governance = GovernanceEngine(args.path)

    # 2. Driver
    driver = PTYDriver(cmd)

    def output_observer(data: bytes):
        extractor.process_chunk(data)

    try:
        print(f"🔌 [Agent Memory v2.4.0] Dynamic Retrieval Layer: ACTIVE")
        driver.run(
            on_output=output_observer, 
            on_exit=extractor.flush, 
            on_input=governance.transform_input,
            initial_input=governance.get_init_payload()
        )
    except Exception as e:
        print(f"Runner Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
