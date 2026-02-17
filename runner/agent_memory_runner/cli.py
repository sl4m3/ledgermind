import argparse
import sys
import os
import re
import time
from agent_memory_core.api.memory import Memory
from agent_memory_runner.pty_driver import PTYDriver
from agent_memory_runner.extractor import MemoryExtractor

SYSTEM_PROTOCOL = """
--- [KNOWLEDGE PERSISTENCE PROTOCOL] ---
Operational Context: ACTIVE. Storage: Git-backed Semantic Store.

You are an AI agent operating in a terminal environment with persistent memory.
Rules for this session:
1. FORMALIZE all strategic decisions, rules, and constraints using the marker:
   MEMORY: {{"title": "...", "target": "...", "rationale": "...", "consequences": []}}
2. The environment observer will automatically capture and commit these to Git.
3. PRESERVE consistency with existing context provided below.

Established Context:
{context}
----------------------------------------
"""

def fetch_memory_context(path: str) -> str:
    try:
        mem = Memory(storage_path=path)
        results = mem.search_decisions(" ", limit=20, mode="strict")
        if not results:
            return "No previous records. Environment is fresh."
        return "\n".join([f"- {item.preview} (ID: {item.id})" for item in results])
    except Exception:
        return "Memory system not initialized."

def main():
    parser = argparse.ArgumentParser(
        description="Agent Memory Runner (Universal PTY Wrapper)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  am-run gemini chat
  am-run aichat
  am-run open-interpreter
  am-run python3 agent.py
  am-run --path ./custom_mem bash
        """
    )
    parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    parser.add_argument("--no-protocol", action="store_true", help="Only inject context without system rules")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Agent command to execute")
    
    args = parser.parse_args()
    
    cmd = args.command
    if not cmd:
        shell = os.environ.get("SHELL", "sh")
        cmd = [shell]

    # 1. Prepare Memory & Protocol
    extractor = MemoryExtractor(args.path)
    context = fetch_memory_context(args.path)
    
    if args.no_protocol:
        injection = f"\n[PERSISTENT CONTEXT]\n{context}\n"
    else:
        injection = SYSTEM_PROTOCOL.format(context=context)

    injection_bytes = injection.encode('utf-8')

    # 2. Setup Driver
    driver = PTYDriver(cmd)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def output_observer(data: bytes):
        try:
            chunk = data.decode('utf-8', errors='ignore')
            clean_text = ansi_escape.sub('', chunk)
            extractor.process_chunk(clean_text)
        except Exception:
            pass

    try:
        print(f"🔌 [Agent Memory] Attaching to: {' '.join(cmd)}")
        # Small sleep before injection to let the child app settle
        time.sleep(0.1) 
        driver.run(on_output=output_observer, initial_input=injection_bytes)
    except Exception as e:
        print(f"Runner Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
