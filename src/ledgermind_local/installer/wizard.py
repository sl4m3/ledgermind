"""Guided terminal installer backed by the same strict config model."""

from __future__ import annotations

import getpass
import os
import select
import shutil
import sys
import termios
import textwrap
import tty
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO, cast

from .errors import UserCancelledError
from .models import (
    AdvancedConfig,
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
    IntegrationConfig,
    LocalEmbeddingConfig,
    RerankerApiConfig,
    RerankerConfig,
    RerankerLocalConfig,
    RuntimeConfig,
)
from .openrouter import OpenRouterEndpoint, list_openrouter_model_endpoints
from .provider_profiles import GenerationProviderProfileId

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
REFERENCE_GENERATION_MODEL = "deepseek/deepseek-v4-flash-0731"
REFERENCE_NVIDIA_GENERATION_MODEL = "nvidia/nemotron-3-super-120b-a12b"
REFERENCE_EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b:free"
REFERENCE_EMBEDDING_DIMENSIONS = 2048
REFERENCE_LOCAL_EMBEDDING_CATALOG_ID = "nemotron-3-embed-1b-bf16"


@dataclass(frozen=True, slots=True)
class _Choice:
    value: str
    label: str
    detail: str = ""


class _TerminalWizard:
    def __init__(
        self,
        *,
        input_fn: Callable[[str], str],
        secret_fn: Callable[[str], str],
        output: TextIO,
    ) -> None:
        self.input_fn = input_fn
        self.secret_fn = secret_fn
        self.output = output
        self.color = bool(getattr(output, "isatty", lambda: False)())
        self.navigation = self.color and input_fn is input and sys.stdin.isatty()
        self._brand_visible = False
        columns = shutil.get_terminal_size((80, 24)).columns
        self.panel_width = max(44, min(96, columns - 4))

    def _style(self, text: str, code: str) -> str:
        if not self.color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def line(self, text: str = "") -> None:
        print(text, file=self.output)

    def _clear_screen(self) -> None:
        if self.navigation:
            self.output.write("\033[2J\033[H")

    def _brand(self) -> None:
        inside = self.panel_width - 2
        brand = "  LEDGERMIND SETUP"
        self.line("  ╭" + "─" * inside + "╮")
        self.line(
            "  │" + self._style(brand, "1;36") + " " * (inside - len(brand)) + "│"
        )
        self.line("  │" + "  Private memory for your local agents".ljust(inside) + "│")
        self.line("  ╰" + "─" * inside + "╯")

    def _panel(self, title: str, lines: Sequence[str]) -> None:
        inside = self.panel_width - 2
        label = f" {title} "
        label = label[:inside]
        self.line("  ╭" + label + "─" * (inside - len(label)) + "╮")
        for raw in lines:
            wrapped = textwrap.wrap(
                raw,
                width=max(1, inside - 4),
                replace_whitespace=False,
                drop_whitespace=True,
            ) or [""]
            for part in wrapped:
                self.line("  │  " + part.ljust(inside - 4) + "  │")
        self.line("  ╰" + "─" * inside + "╯")

    def _choice_panel_lines(
        self,
        prompt: str,
        choices: Sequence[_Choice],
        *,
        selected: int,
        footer: str,
    ) -> list[str]:
        inside = self.panel_width - 2
        label = f" {prompt} "[:inside]
        rows = ["  ╭" + label + "─" * (inside - len(label)) + "╮"]
        for index, choice in enumerate(choices):
            pointer = "›" if index == selected else " "
            primary = f"  {pointer} {choice.label}"
            primary = primary[: inside - 2].ljust(inside)
            if index == selected:
                primary = primary.replace("›", self._style("›", "1;36"), 1)
            rows.append("  │" + primary + "│")
            if choice.detail:
                detail = textwrap.shorten(
                    choice.detail,
                    width=max(8, inside - 7),
                    placeholder="…",
                )
                rows.append("  │     " + detail.ljust(inside - 5) + "│")
        rows.append("  ╰" + "─" * inside + "╯")
        rows.append(self._style(f"  {footer}", "2"))
        return rows

    def banner(self) -> None:
        self._clear_screen()
        if not self.navigation:
            self.line()
        self._brand()
        self._brand_visible = True
        self.line(
            self._style("  Esc/Q cancels menus · Ctrl+C or :q exits anytime", "2")
        )

    def section(self, number: int, title: str, detail: str, *, total: int = 8) -> None:
        if self.navigation:
            self._clear_screen()
            self._brand()
            width = 32
            filled = min(width, max(0, round(width * number / max(total, 1))))
            progress = "━" * filled + "─" * (width - filled)
            self.line()
            self.line(self._style(f"  {progress}  STEP {number} OF {total}", "36"))
            self._brand_visible = True
        elif not self._brand_visible:
            self.banner()
        self.line()
        if self.navigation:
            self._panel(title, (detail,))
        else:
            self.line(self._style(f"  {number}/{total}  {title}", "1;34"))
            self.line(f"  {detail}")

    def token_preview(self, token: str) -> str:
        if len(token) <= 8:
            return "*" * len(token)
        return f"{token[:4]}{'*' * min(12, len(token) - 8)}{token[-4:]}"

    def _navigation_choice(
        self, prompt: str, choices: Sequence[_Choice], *, default: int
    ) -> str:
        selected = max(0, min(default - 1, len(choices) - 1))
        descriptor = sys.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        try:
            tty.setraw(descriptor)
            while True:
                self.output.write("\033[?25l")
                rows = self._choice_panel_lines(
                    prompt,
                    choices,
                    selected=selected,
                    footer="↑/↓ move   Enter select   Esc/Q cancel",
                )
                for row in rows:
                    self._menu_line(row)
                self.output.flush()
                key = os.read(descriptor, 1)
                if key == b"\x1b":
                    tail = self._escape_tail(descriptor)
                    if tail == b"[A":
                        selected = (selected - 1) % len(choices)
                    elif tail == b"[B":
                        selected = (selected + 1) % len(choices)
                    else:
                        raise UserCancelledError("installation cancelled by user")
                elif key in {b"\r", b"\n"}:
                    return choices[selected].value
                elif key in {b"q", b"Q"}:
                    raise UserCancelledError("installation cancelled by user")
                elif key == b"\x03":
                    raise KeyboardInterrupt
                # Redraw only this compact selector.
                self.output.write(f"\r\033[{len(rows)}A\033[J")
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
            self.output.write("\033[?25h")
            self.output.flush()

    def _menu_line(self, text: str) -> None:
        """Render a selector row independently of raw-terminal newline rules."""

        self.output.write(f"\r\033[2K{text}\r\n")

    @staticmethod
    def _escape_tail(descriptor: int) -> bytes:
        """Read a bounded arrow-key suffix without blocking on a bare Escape."""

        tail = bytearray()
        for _ in range(2):
            readable, _, _ = select.select((descriptor,), (), (), 0.05)
            if not readable:
                break
            tail.extend(os.read(descriptor, 1))
        return bytes(tail)

    def ask(self, prompt: str, *, default: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        if self.navigation:
            self.line()
            self.line(self._style(f"  {prompt}{suffix}", "1"))
            self.line(self._style("  Type a value, then press Enter · :q cancel", "2"))
            value = self.input_fn("  > ").strip()
        else:
            value = self.input_fn(f"  {prompt}{suffix}: ").strip()
        if value.lower() in {":q", ":quit", ":exit"}:
            raise UserCancelledError("installation cancelled by user")
        return value or (default or "")

    def required(self, prompt: str, *, default: str | None = None) -> str:
        while True:
            value = self.ask(prompt, default=default)
            if value:
                return value
            self.line(self._style("  A value is required.", "31"))

    def secret(self, prompt: str) -> str:
        while True:
            if self.navigation:
                self.line()
                self.line(self._style(f"  {prompt}", "1"))
                self.line(
                    self._style(
                        "  Input is hidden · Enter confirm · type :q to cancel",
                        "2",
                    )
                )
                value = self.secret_fn("  > ").strip()
            else:
                value = self.secret_fn(f"  {prompt}: ").strip()
            if value.lower() in {":q", ":quit", ":exit"}:
                raise UserCancelledError("installation cancelled by user")
            if value:
                return value
            self.line(self._style("  A token is required.", "31"))

    def choose(
        self,
        prompt: str,
        choices: Sequence[_Choice],
        *,
        default: int = 1,
    ) -> str:
        if self.navigation:
            return self._navigation_choice(prompt, choices, default=default)
        self.line(f"  {prompt}")
        for index, choice in enumerate(choices, start=1):
            marker = self._style(str(index), "1;36")
            detail = f" — {choice.detail}" if choice.detail else ""
            self.line(f"    {marker}. {choice.label}{detail}")
        while True:
            raw = self.ask("Select", default=str(default)).lower()
            if raw in {"q", "quit", "exit"}:
                raise UserCancelledError("installation cancelled by user")
            if raw.isdigit() and 1 <= int(raw) <= len(choices):
                return choices[int(raw) - 1].value
            for choice in choices:
                if raw == choice.value.lower():
                    return choice.value
            self.line(self._style("  Select one of the listed options.", "31"))

    def confirm(self, prompt: str, *, default: bool = True) -> bool:
        if self.navigation:
            answer = self.choose(
                prompt,
                (_Choice("yes", "Yes"), _Choice("no", "No")),
                default=1 if default else 2,
            )
            return answer == "yes"
        answer = self.ask(prompt, default="yes" if default else "no").lower()
        while answer not in {"yes", "no", "y", "n"}:
            self.line(self._style("  Enter yes or no.", "31"))
            answer = self.ask(prompt, default="yes" if default else "no").lower()
        return answer in {"yes", "y"}

    def integrations(self, discovered: Sequence[tuple[str, str]]) -> tuple[str, ...]:
        if not discovered:
            self.line("  No supported agent installations were detected.")
            return ()
        if self.navigation:
            selected = set(range(len(discovered)))
            cursor = 0
            descriptor = sys.stdin.fileno()
            previous = termios.tcgetattr(descriptor)
            try:
                tty.setraw(descriptor)
                while True:
                    self.output.write("\033[?25l")
                    choices = tuple(
                        _Choice(
                            identifier,
                            f"{'[x]' if index in selected else '[ ]'} {label}",
                        )
                        for index, (identifier, label) in enumerate(discovered)
                    )
                    rows = self._choice_panel_lines(
                        "Select agents",
                        choices,
                        selected=cursor,
                        footer=(
                            "↑/↓ move   Space toggle   Enter continue   Esc/Q cancel"
                        ),
                    )
                    for row in rows:
                        self._menu_line(row)
                    self.output.flush()
                    key = os.read(descriptor, 1)
                    if key == b"\x1b":
                        tail = self._escape_tail(descriptor)
                        if tail == b"[A":
                            cursor = (cursor - 1) % len(discovered)
                        elif tail == b"[B":
                            cursor = (cursor + 1) % len(discovered)
                        else:
                            raise UserCancelledError("installation cancelled by user")
                    elif key == b" ":
                        if cursor in selected:
                            selected.remove(cursor)
                        else:
                            selected.add(cursor)
                    elif key in {b"\r", b"\n"}:
                        return tuple(
                            identifier
                            for index, (identifier, _) in enumerate(discovered)
                            if index in selected
                        )
                    elif key in {b"q", b"Q"}:
                        raise UserCancelledError("installation cancelled by user")
                    elif key == b"\x03":
                        raise KeyboardInterrupt
                    self.output.write(f"\r\033[{len(rows)}A\033[J")
            finally:
                termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
                self.output.write("\033[?25h")
                self.output.flush()
        self.line("  Detected agents")
        for index, (_, label) in enumerate(discovered, start=1):
            self.line(f"    {self._style(str(index), '1;36')}. {label}")
        self.line("  Enter comma-separated numbers, 'all', or 'none'.")
        while True:
            raw = self.ask("Connect", default="all").lower()
            if raw in {"q", "quit", "exit"}:
                raise UserCancelledError("installation cancelled by user")
            if raw == "all":
                return tuple(identifier for identifier, _ in discovered)
            if raw == "none":
                return ()
            try:
                indexes = {int(item.strip()) for item in raw.split(",") if item.strip()}
            except ValueError:
                indexes = set()
            if indexes and all(1 <= index <= len(discovered) for index in indexes):
                return tuple(
                    identifier
                    for index, (identifier, _) in enumerate(discovered, start=1)
                    if index in indexes
                )
            self.line(
                self._style("  Use numbers such as 1,3, or choose all/none.", "31")
            )


def build_interactive_config(
    *,
    input_fn: Callable[[str], str] = input,
    secret_fn: Callable[[str], str] = getpass.getpass,
    output: TextIO = sys.stderr,
    existing_config: InstallerConfig | None = None,
    openrouter_endpoint_loader: Callable[
        [str, str], tuple[OpenRouterEndpoint, ...]
    ] = lambda model, token: list_openrouter_model_endpoints(model, token=token),
    embedding_dimension_loader: Callable[[EmbeddingApiConfig, str], int] | None = None,
    preflight_home: Path | None = None,
    embedding_catalog: Sequence[dict[str, object]] = (),
) -> InstallerConfig:
    ui = _TerminalWizard(input_fn=input_fn, secret_fn=secret_fn, output=output)
    try:
        ui.section(0, "PREFLIGHT", "Linux host and installed agents", total=8)
        from .hardware import detect_devices
        from .paths import InstallerPaths
        from .preflight import check_preflight
        from .targets.registry import get_target_adapter, target_ids

        preflight = check_preflight(InstallerPaths(home_override=preflight_home))
        ui.line(f"  Platform: {preflight['platform']} (glibc {preflight['libc']})")
        ui.line(
            "  Sandbox:  "
            + (
                "bubblewrap available"
                if preflight["bubblewrap"]
                else "bubblewrap missing"
            )
        )
        ui.line(f"  Free disk: {int(preflight['free_bytes']) // (1024**3)} GiB")
        devices = detect_devices()
        ui.line("  Compute:  " + ", ".join(device.kind for device in devices))
        discovered: list[tuple[str, str]] = []
        for target_id in target_ids():
            adapter = get_target_adapter(target_id)
            if adapter.discover().detected:
                discovered.append((target_id, adapter.label))
        ui.line(
            "  Agents:   "
            + (", ".join(label for _, label in discovered) or "none detected")
        )

        if existing_config is None:
            ui.section(1, "LANGUAGE", "Language used to write semantic memory")
            semantic_language = ui.choose(
                "Choose a semantic language",
                (
                    _Choice("en", "English"),
                    _Choice("es", "Spanish"),
                    _Choice("de", "German"),
                    _Choice("fr", "French"),
                    _Choice("ru", "Russian"),
                    _Choice("custom", "Custom", "any BCP-47 language tag"),
                ),
                default=1,
            )
            if semantic_language == "custom":
                semantic_language = ui.required(
                    "Language tag (for example pt, uk, ja, or zh-Hans)"
                )

            ui.section(2, "AGENTS", "Select installed agents to connect")
            selected = ui.integrations(discovered)
            integrations = tuple(
                IntegrationConfig.model_validate({"id": target_id, "enabled": True})
                for target_id in selected
            )

            ui.section(3, "MEMORY", "Choose whether connected agents share knowledge")
            memory_mode = ui.choose(
                "Memory layout",
                (
                    _Choice("per_agent", "Separate per agent", "strong isolation"),
                    _Choice("shared", "Shared by all agents", "one knowledge space"),
                ),
            )
            runtime = RuntimeConfig()
        else:
            semantic_language = existing_config.semantic_language
            memory_mode = existing_config.memory_mode
            runtime = existing_config.runtime
            integrations = existing_config.integrations
            ui.line(
                "  Reconfiguring providers; memory layout and agents are preserved."
            )

        ui.section(4, "GENERATION", "One model for the complete knowledge pipeline")
        generation_provider = ui.choose(
            "Generation provider",
            (
                _Choice("openrouter", "OpenRouter", "provider routing is pinned"),
                _Choice("nvidia_nim", "NVIDIA NIM", "native guided JSON"),
                _Choice("custom", "Custom OpenAI-compatible endpoint"),
            ),
        )
        if generation_provider == "openrouter":
            endpoint = OPENROUTER_BASE_URL
            ui.line(f"  API base: {endpoint}")
            route = None
            fallback_routes: tuple[str, ...] = ()
            default_generation_model = REFERENCE_GENERATION_MODEL
        elif generation_provider == "nvidia_nim":
            endpoint = NVIDIA_NIM_BASE_URL
            route = None
            fallback_routes = ()
            default_generation_model = REFERENCE_NVIDIA_GENERATION_MODEL
            ui.line(f"  API base: {endpoint}")
        else:
            endpoint = ui.required("API base URL (for example https://host.example/v1)")
            route = None
            fallback_routes = ()
            default_generation_model = None
        token = ui.secret("Generation token")
        ui.line(f"  Token accepted: {ui.token_preview(token)}")
        model = ui.required("Generation model", default=default_generation_model)
        if generation_provider == "openrouter":
            discovered_endpoints: tuple[OpenRouterEndpoint, ...] = ()
            try:
                ui.line("  Discovering providers with strict JSON Schema support...")
                discovered_endpoints = openrouter_endpoint_loader(model, token)
            except Exception as exc:  # noqa: BLE001 - converted to a recoverable wizard path
                ui.line(ui._style(f"  Discovery unavailable: {exc}", "33"))
            route_source = "discovered" if discovered_endpoints else "manual"
            if discovered_endpoints:
                route_source = ui.choose(
                    "Provider routes",
                    (
                        _Choice("discovered", "Choose discovered providers"),
                        _Choice(
                            "manual",
                            "Enter routes manually",
                            "strict probe still required",
                        ),
                    ),
                )
            route_count = ui.choose(
                "Routing policy",
                (
                    _Choice("one", "Primary only", "no hidden fallback"),
                    _Choice("two", "Primary + one fallback", "ordered and restricted"),
                ),
            )
            if route_source == "discovered":
                endpoint_choices = tuple(
                    _Choice(item.route, item.label, item.detail)
                    for item in discovered_endpoints
                )
                route = ui.choose("Primary provider", endpoint_choices)
                if route_count == "two":
                    fallbacks = tuple(
                        item for item in endpoint_choices if item.value != route
                    )
                    if not fallbacks:
                        ui.line(
                            ui._style(
                                "  Only one compatible provider was found; using no fallback.",
                                "33",
                            )
                        )
                    else:
                        fallback_routes = (ui.choose("Fallback provider", fallbacks),)
            else:
                route = ui.required(
                    "Primary OpenRouter provider (for example provider/variant)"
                )
                if route_count == "two":
                    while True:
                        fallback = ui.required(
                            "Fallback OpenRouter provider (for example provider/variant)"
                        )
                        if fallback != route:
                            fallback_routes = (fallback,)
                            break
                        ui.line(
                            ui._style(
                                "  Fallback provider must differ from the primary provider.",
                                "31",
                            )
                        )

        ui.section(5, "EMBEDDINGS", "API service or signed local Nemotron")
        approved_local = next(
            (
                entry
                for entry in embedding_catalog
                if entry.get("id") == REFERENCE_LOCAL_EMBEDDING_CATALOG_ID
            ),
            None,
        )
        embedding_choices = [_Choice("api", "API endpoint", "quickest setup")]
        if approved_local is not None:
            embedding_choices.append(
                _Choice(
                    "local",
                    "Local signed model",
                    "Nemotron 3 Embed 1B; private and offline",
                )
            )
        else:
            ui.line(
                "  Local embeddings are hidden because this signed release has no approved runtime."
            )
        embedding_mode = ui.choose(
            "Embedding source",
            tuple(embedding_choices),
        )
        if embedding_mode == "api":
            embedding_endpoint = ui.required("Embedding API base", default=endpoint)
            reuse_token = embedding_endpoint.rstrip("/") == endpoint.rstrip(
                "/"
            ) and ui.confirm("Reuse the generation token", default=True)
            embedding_token = token if reuse_token else ui.secret("Embedding token")
            default_embedding_model = (
                REFERENCE_EMBEDDING_MODEL
                if "openrouter.ai" in embedding_endpoint
                else None
            )
            embedding_model = ui.required(
                "Embedding model", default=default_embedding_model
            )
            provisional_dimensions = (
                REFERENCE_EMBEDDING_DIMENSIONS
                if embedding_model.removesuffix(":free")
                == REFERENCE_EMBEDDING_MODEL.removesuffix(":free")
                else 1536
            )
            provisional = EmbeddingApiConfig(
                endpoint=embedding_endpoint,
                token=embedding_token,
                model=embedding_model,
                dimensions=provisional_dimensions,
            )
            while True:
                try:
                    if embedding_dimension_loader is None:
                        from .profiles.probes import discover_embedding_dimensions

                        dimensions = discover_embedding_dimensions(
                            provisional, token=embedding_token
                        )
                    else:
                        dimensions = embedding_dimension_loader(
                            provisional, embedding_token
                        )
                    break
                except Exception as exc:  # noqa: BLE001 - interactive recovery boundary
                    ui.line(ui._style(f"  Embedding check failed: {exc}", "31"))
                    recovery = ui.choose(
                        "What next?",
                        (
                            _Choice("retry", "Retry the check"),
                            _Choice(
                                "restart", "Start over", "change endpoint or token"
                            ),
                            _Choice("cancel", "Cancel"),
                        ),
                    )
                    if recovery == "retry":
                        continue
                    if recovery == "cancel":
                        raise UserCancelledError("installation cancelled by user")
                    return build_interactive_config(
                        input_fn=input_fn,
                        secret_fn=secret_fn,
                        output=output,
                        existing_config=existing_config,
                        openrouter_endpoint_loader=openrouter_endpoint_loader,
                        embedding_dimension_loader=embedding_dimension_loader,
                        preflight_home=preflight_home,
                        embedding_catalog=embedding_catalog,
                    )
            ui.line(f"  Detected vector dimensions: {dimensions}")
            embedding = EmbeddingConfig(
                mode="api",
                api=EmbeddingApiConfig(
                    endpoint=embedding_endpoint,
                    token=embedding_token,
                    model=embedding_model,
                    dimensions=dimensions,
                ),
            )
        else:
            assert approved_local is not None
            ui.line("  Recommended: NVIDIA Nemotron-3-Embed-1B-BF16 (2048d)")
            catalog_id = str(approved_local["id"])
            supported_devices = {
                str(item) for item in approved_local.get("devices", [])
            }
            device = ui.choose(
                "Compute device",
                tuple(
                    [_Choice("auto", "Automatic", "prefer GPU, then CPU")]
                    + [
                        _Choice(
                            device.kind,
                            {
                                "cpu": "CPU",
                                "cuda": "NVIDIA CUDA",
                                "rocm": "AMD ROCm",
                            }.get(device.kind, device.kind),
                            device.name,
                        )
                        for device in devices
                        if device.available and device.kind in supported_devices
                    ]
                ),
            )
            embedding = EmbeddingConfig(
                mode="local",
                local=LocalEmbeddingConfig(
                    catalog_id=catalog_id,
                    device=cast(Literal["auto", "cpu", "cuda", "rocm"], device),
                ),
            )

        ui.line("  Optional reranking improves the order of retrieved knowledge")
        reranker_mode = ui.choose(
            "Reranker",
            (
                _Choice("disabled", "Disabled", "use deterministic Core ranking"),
                _Choice(
                    "api", "API", "send admitted candidates to a reranking endpoint"
                ),
                _Choice("local", "Local", "Qwen3 0.6B on CPU or GPU"),
            ),
        )
        if reranker_mode == "api":
            existing_api = existing_config.reranker.api if existing_config else None
            reranker_endpoint = ui.required(
                "Reranker API operation URL",
                default=existing_api.endpoint if existing_api else None,
            )
            reuse_token = reranker_endpoint.startswith(
                endpoint.rstrip("/")
            ) and ui.confirm("Reuse the generation token", default=True)
            reranker_token = token if reuse_token else ui.secret("Reranker API token")
            reranker_model = ui.required(
                "Reranker model", default=existing_api.model if existing_api else None
            )
            reranker = RerankerConfig(
                mode="api",
                api=RerankerApiConfig(
                    endpoint=reranker_endpoint,
                    token=reranker_token,
                    model=reranker_model,
                ),
            )
        elif reranker_mode == "local":
            from ledgermind_local.inference.retrieval_reranker import MODEL_REVISION

            existing_local = existing_config.reranker.local if existing_config else None
            runtime_path = ui.required(
                "Installed reranker runtime directory",
                default=existing_local.runtime_path if existing_local else None,
            )
            reranker_device = ui.choose(
                "Reranker compute device",
                (
                    _Choice("cpu", "CPU"),
                    _Choice("cuda", "NVIDIA CUDA"),
                    _Choice("rocm", "AMD ROCm"),
                ),
            )
            reranker = RerankerConfig(
                mode="local",
                local=RerankerLocalConfig(
                    model_path=str(
                        Path(runtime_path).expanduser()
                        / "model"
                        / "snapshots"
                        / MODEL_REVISION
                    ),
                    runtime_path=runtime_path,
                    device=cast(Literal["cpu", "cuda", "rocm"], reranker_device),
                ),
            )
        else:
            reranker = RerankerConfig()

        if existing_config is None:
            ui.line("  Choose how long local embedding and reranker models stay loaded")
            residency_mode = ui.choose(
                "Local model residency",
                (
                    _Choice(
                        "session",
                        "Session (recommended)",
                        "keep models loaded until the agent turn finishes",
                    ),
                    _Choice(
                        "idle",
                        "Idle timeout",
                        "keep models warm for a period after the last request",
                    ),
                    _Choice(
                        "always_on",
                        "Always on",
                        "keep models resident for minimum recall latency",
                    ),
                ),
            )
            idle_timeout_seconds = 900.0
            if residency_mode == "idle":
                idle_minutes = ui.choose(
                    "Unload after idle time",
                    (
                        _Choice("5", "5 minutes"),
                        _Choice("10", "10 minutes"),
                        _Choice("15", "15 minutes (recommended)"),
                        _Choice("30", "30 minutes"),
                    ),
                    default=3,
                )
                idle_timeout_seconds = float(idle_minutes) * 60.0
            runtime = RuntimeConfig(
                residency_mode=cast(
                    Literal["session", "idle", "always_on"], residency_mode
                ),
                idle_timeout_seconds=idle_timeout_seconds,
            )

        draft = InstallerConfig(
            semantic_language=semantic_language,
            integrations=integrations,
            memory_mode=cast(Literal["shared", "per_agent"], memory_mode),
            generation=GenerationConfig(
                provider_profile=cast(
                    GenerationProviderProfileId,
                    "openai_compatible"
                    if generation_provider == "custom"
                    else generation_provider,
                ),
                endpoint=endpoint,
                route=route,
                fallback_routes=fallback_routes,
                token=token,
                model=model,
            ),
            embedding=embedding,
            reranker=reranker,
            runtime=runtime,
            memory_data_path=(
                existing_config.memory_data_path
                if existing_config is not None
                else None
            ),
            advanced=(
                existing_config.advanced
                if existing_config is not None
                else AdvancedConfig()
            ),
        )

        ui.section(6, "REVIEW", "Nothing is installed until you confirm")
        ui.line(f"  Language:   {semantic_language}")
        ui.line(f"  Provider:   {generation_provider}")
        ui.line(f"  Generation: {model}")
        ui.line(f"  Token:      {ui.token_preview(token)}")
        if route:
            route_chain = " → ".join((route, *fallback_routes))
            ui.line(f"  Routes:     {route_chain} (restricted)")
        ui.line(f"  Embeddings:  {embedding.mode}")
        if embedding.api is not None:
            ui.line(
                f"               {embedding.api.model} ({embedding.api.dimensions}d)"
            )
        elif embedding.local is not None:
            ui.line(
                f"               {embedding.local.catalog_id} ({embedding.local.device})"
            )
        if reranker.mode == "local":
            ui.line(
                f"  Reranker:    local Qwen3 0.6B on {reranker.device} "
                f"({reranker.runtime_path})"
            )
        elif reranker.mode == "api" and reranker.api is not None:
            ui.line(f"  Reranker:    API · {reranker.api.model}")
        else:
            ui.line("  Reranker:    disabled · Core ranking")
        residency_labels = {
            "session": "session · unload after the agent turn",
            "idle": f"idle · unload after {runtime.idle_timeout_seconds / 60:g} min",
            "always_on": "always on · keep local models resident",
        }
        ui.line(f"  Residency:   {residency_labels[runtime.residency_mode]}")
        ui.line(f"  Memory:      {memory_mode}")
        ui.line(
            "  Agents:      " + (", ".join(item.id for item in integrations) or "none")
        )
        review_action = ui.choose(
            "Continue",
            (
                _Choice(
                    "apply",
                    "Apply configuration"
                    if existing_config is not None
                    else "Start installation",
                ),
                _Choice("edit", "Edit providers", "keep language, memory, and agents"),
                _Choice("restart", "Start over", "review every choice again"),
                _Choice("cancel", "Cancel", "make no changes"),
            ),
        )
        if review_action == "cancel":
            raise UserCancelledError("installation cancelled by user")
        if review_action == "edit":
            return build_interactive_config(
                input_fn=input_fn,
                secret_fn=secret_fn,
                output=output,
                existing_config=draft,
                openrouter_endpoint_loader=openrouter_endpoint_loader,
                embedding_dimension_loader=embedding_dimension_loader,
                preflight_home=preflight_home,
                embedding_catalog=embedding_catalog,
            )
        if review_action == "restart":
            return build_interactive_config(
                input_fn=input_fn,
                secret_fn=secret_fn,
                output=output,
                openrouter_endpoint_loader=openrouter_endpoint_loader,
                embedding_dimension_loader=embedding_dimension_loader,
                preflight_home=preflight_home,
                embedding_catalog=embedding_catalog,
            )

        ui.section(7, "READY", "Provider checks run before any host changes")
        ui.line("  Strict generation schema: required")
        ui.line("  Release and local model assets: signed and verified")
        ui.line("  Detailed progress and recovery diagnostics will follow.")

        return draft
    except (EOFError, KeyboardInterrupt) as exc:
        raise UserCancelledError("installation cancelled by user") from exc


def choose_existing_install_action(
    *, input_fn: Callable[[str], str] = input, output: TextIO = sys.stderr
) -> str:
    """Select one safe operation when the installer finds an existing deployment."""

    ui = _TerminalWizard(input_fn=input_fn, secret_fn=getpass.getpass, output=output)
    ui.section(
        1,
        "EXISTING INSTALLATION",
        "Your memory and provider settings are preserved",
        total=1,
    )
    return ui.choose(
        "What would you like to do?",
        (
            _Choice("add-agent", "Add an agent", "does not change model profiles"),
            _Choice("update", "Update LedgerMind", "preserves config and memory"),
            _Choice("repair", "Repair installation", "restores runtime and hooks"),
            _Choice("reconfigure", "Reconfigure providers", "keeps memory and agents"),
            _Choice("exit", "Exit", "make no changes"),
        ),
    )


def choose_integrations_to_connect(
    config: InstallerConfig,
    *,
    input_fn: Callable[[str], str] = input,
    output: TextIO = sys.stderr,
) -> tuple[str, ...]:
    """Choose detected agents that are not already connected."""

    from .targets.registry import get_target_adapter, target_ids

    connected = {item.id for item in config.integrations}
    available: list[tuple[str, str]] = []
    for target_id in target_ids():
        adapter = get_target_adapter(target_id)
        if target_id not in connected and adapter.discover().detected:
            available.append((target_id, adapter.label))
    ui = _TerminalWizard(input_fn=input_fn, secret_fn=getpass.getpass, output=output)
    ui.section(
        1,
        "AGENTS",
        "Existing integrations and inference profiles stay unchanged",
        total=1,
    )
    return ui.integrations(available)


__all__ = [
    "NVIDIA_NIM_BASE_URL",
    "OPENROUTER_BASE_URL",
    "REFERENCE_EMBEDDING_DIMENSIONS",
    "REFERENCE_EMBEDDING_MODEL",
    "REFERENCE_GENERATION_MODEL",
    "REFERENCE_NVIDIA_GENERATION_MODEL",
    "build_interactive_config",
    "choose_existing_install_action",
    "choose_integrations_to_connect",
]
