import os
import time
import logging
import shutil
import subprocess
from typing import Optional, Any, Protocol
from .config import EnrichmentConfig
from .builder import PromptBuilder
from ledgermind.core.utils.gemini_config import GeminiConfigManager

logger = logging.getLogger("ledgermind-core.enrichment.clients")

class LLMClient(Protocol):
    """Protocol for LLM execution strategies."""
    def call(self, instructions: str, data: str, fid: str = "unknown") -> Optional[str]:
        ...
    def is_available(self) -> bool:
        ...

class CloudLLMClient:
    """Strategy for Gemini/Claude (Cloud) using CLI/SDK."""
    def __init__(self, config: EnrichmentConfig, memory: Any = None):
        self.config = config
        self.memory = memory
        self._bin = "gemini"
        self._mode = "global"
        self._client = "gemini"  # Default client
        self._cli_flags = ["--extensions", "", "--allowed-mcp-server-names", ""]  # Gemini flags

        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            self._bin = meta.get_config("gemini_binary_path") or self._bin
            self._mode = meta.get_config("gemini_config_mode") or self._mode
            # V7.10: Detect client for CLI flags
            self._client = meta.get_config("client") or "gemini"
            
            # Set CLI flags based on client
            if self._client == "claude":
                # Claude CLI flags: disable tools, MCP, session persistence, slash commands
                self._cli_flags = [
                    "-p",  # Print response and exit (non-interactive mode)
                    "--tools", "",  # Disable tool calls
                    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',  # Disable MCP connections
                    "--no-session-persistence",  # Don't save to memory
                    "--disable-slash-commands",  # Disable slash commands
                ]
            else:
                # Gemini CLI flags
                self._cli_flags = ["--extensions", "", "--allowed-mcp-server-names", ""]

    def call(self, instructions: str, data: str, fid: str = "unknown") -> Optional[str]:
        # Try CLI first
        res = self._call_cli(instructions, data, fid)
        if res: return res
        
        # Fallback to SDK
        return self._call_sdk(instructions + "\n\n" + data)

    def _call_cli(self, instructions: str, data: str, fid: str) -> Optional[str]:
        try:
            full_prompt = PromptBuilder.wrap_with_data(instructions, data, self.config)

            # Лаконичное подтверждение отправки
            logger.info(f"{self._client.capitalize()} CLI: Calling model {self.config.model_name} for {fid}...")

            config_path = GeminiConfigManager.get_config_path(mode=self._mode)
            env = GeminiConfigManager.get_environment(config_path)
            env["NODE_OPTIONS"] = "--max-old-space-size=2048"

            for attempt in range(1, self.config.retry_attempts + 1):
                logger.info(f"Attempt {attempt}/{self.config.retry_attempts}: {self._client.capitalize()} CLI call...")
                try:
                    # V7.10: Use client-specific CLI flags
                    cmd = [self._bin] + self._cli_flags + ["--model", self.config.model_name, "Analyze logs and return JSON."]
                    
                    bin_path = shutil.which(self._bin)
                    if not bin_path:
                        raise FileNotFoundError(f"{self._bin} executable not found in PATH")
                    cmd[0] = bin_path
                    proc = subprocess.Popen( # nosec B603
                        cmd,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, env=env
                    )
                    stdout, stderr = proc.communicate(input=full_prompt, timeout=self.config.timeout)
                    if proc.returncode == 0 and stdout:
                        return stdout.strip()

                    logger.error(f"CLI failed: {stderr[:500]}")
                except Exception as e:
                    logger.error(f"Internal CLI error: {e}")

                if attempt < self.config.retry_attempts:
                    time.sleep(self.config.retry_delay)
            return None
        except Exception as e:
            logger.error(f"CLI process error: {e}")
            return None

    def _call_sdk(self, prompt: str) -> Optional[str]:
        try:
            import google.generativeai as genai
            key = os.environ.get("GEMINI_API_KEY")
            if not key: return None
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            return resp.text if resp else None
        except Exception: return None

    def is_available(self) -> bool:
        """Check if Cloud LLM is properly configured."""
        # Set binary based on client
        bin_name = "claude" if self._client == "claude" else "gemini"
        
        # Check if CLI is available
        try:
            bin_path = shutil.which(bin_name)
            if not bin_path:
                raise FileNotFoundError(f"{bin_name} executable not found in PATH")
            result = subprocess.run([bin_path, "--version"], capture_output=True, timeout=5) # nosec B603
            if result.returncode == 0:
                return True
        except Exception:
            pass

        # Check if SDK is available (Gemini only)
        if self._client == "gemini":
            try:
                import google.generativeai as genai
                key = os.environ.get("GEMINI_API_KEY")
                return bool(key)
            except Exception:
                pass
        
        return False


class LocalLLMClient:
    """Strategy for llama-cpp (Local)."""
    def __init__(self, config: EnrichmentConfig, memory: Any = None):
        self.config = config
        self.memory = memory
        self._client = None

    def call(self, instructions: str, data: str, fid: str = "unknown") -> Optional[str]:
        try:
            from llama_cpp import Llama

            if not self._client:
                path = os.environ.get("LEDGERMIND_LOCAL_LLM_PATH")
                if not path and self.memory and hasattr(self.memory, 'vector'):
                    path = getattr(self.memory.vector, 'model_path', None)

                if not path or not os.path.exists(path):
                    return None
                self._client = Llama(model_path=path, n_ctx=2048, verbose=False)

            logger.info(f"Local Enrichment: Processing {fid} via GGUF...")
            prompt = f"System: Technical Expert\nUser: {instructions}\nData: {data}\nAssistant: "
            output = self._client(prompt, max_tokens=1024, stop=["User:", "System:"], echo=False)
            return output['choices'][0]['text']
        except Exception as e:
            logger.error(f"Local LLM failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if Local LLM is properly configured."""
        try:
            from llama_cpp import Llama
            path = os.environ.get("LEDGERMIND_LOCAL_LLM_PATH")
            if not path and self.memory and hasattr(self.memory, 'vector'):
                path = getattr(self.memory.vector, 'model_path', None)
            return bool(path and os.path.exists(path))
        except Exception:
            return False
