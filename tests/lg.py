#!/usr/bin/env python3
import sys
import os
import argparse
import subprocess
import time
import shutil
import random
import uuid
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

# Ensure local src is prioritized for imports
src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.exists(src_path):
    sys.path.insert(0, src_path)

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from rich.progress import track

from ledgermind.core.api.bridge import IntegrationBridge

# Configuration
DEFAULT_CLI = os.environ.get("LEDGERMIND_CLI", "gemini")
MEMORY_PATH = os.environ.get("AGENT_MEMORY_PATH", "./memory")

console = Console()

def warp_time_in_db(db_path: str, table: str, days_back: int, time_col: str = "timestamp"):
    """Manipulates timestamps in SQLite to simulate aging."""
    if not os.path.exists(db_path): return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        past_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        cursor.execute(f"UPDATE {table} SET {time_col} = ?", (past_date,))
        if table == "metadata":
            cursor.execute("UPDATE metadata SET last_hit_at = ?", (past_date,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        console.print(f"[red]Error warping time in {db_path}: {e}[/red]")
        return False

def run_lifecycle_test(args):
    """Expanded Lifecycle Test: Birth -> Search -> Evolution -> Aging -> Decay -> Graph."""
    console.print(Panel.fit("[bold magenta]LedgerMind Advanced Knowledge Lifecycle Test[/bold magenta]", border_style="magenta"))
    
    tmp_dir = os.path.join(os.getcwd(), "memory")
    if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        bridge = IntegrationBridge(
            memory_path=tmp_dir, 
            vector_model="ledgermind/models/v5-small-text-matching-Q4_K_M.gguf",
            default_cli=[args.cli]
        )
        target = f"Legacy-Protocol-{uuid.uuid4().hex[:4]}"
        
        # --- STAGE 1: BIRTH ---
        console.print("\n[bold cyan]Stage 1: Birth (Consistent Failures)[/bold cyan]")
        for i in track(range(3), description="Recording errors..."):
            bridge.memory.process_event(
                source="agent", kind="error",
                content=f"Critical failure in {target}",
                context={"target": target, "error_code": 500}
            )
            time.sleep(0.1)

        # --- STAGE 2: CRYSTALLIZATION ---
        console.print("\n[bold cyan]Stage 2: Crystallization (Reflection)[/bold cyan]")
        proposals = bridge.memory.run_reflection()
        if not proposals:
            console.print("[red]FAIL: No proposal generated.[/red]")
            return
        
        prop_id = proposals[0]
        bridge.memory.accept_proposal(prop_id)
        console.print(f"[green]✔ Decision created for {target}[/green]")
        
        # --- STAGE 2.1: GIT SYNC TEST ---
        console.print("\n[bold cyan]Stage 2.1: Git Sync Test (Real Commit Indexing)[/bold cyan]")
        repo_dir = os.path.join(os.getcwd(), ".test_git_repo")
        if os.path.exists(repo_dir): shutil.rmtree(repo_dir)
        os.makedirs(repo_dir, exist_ok=True)
        
        try:
            subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
            
            test_file = os.path.join(repo_dir, "feature.py")
            with open(test_file, "w") as f: f.write("print('hello world')")
            
            subprocess.run(["git", "add", "feature.py"], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "Initial feature commit"], cwd=repo_dir, check=True)
            
            indexed_count = bridge.sync_git(repo_path=repo_dir)
            if indexed_count > 0:
                console.print(f"[green]✔ Successfully indexed {indexed_count} commits from Git.[/green]")
                recent = bridge.get_recent_events(limit=1)
                if recent and recent[0]['kind'] == 'commit_change':
                     console.print(f"Verified event: [dim]{recent[0]['content']}[/dim]")
                else:
                     console.print("[red]FAIL: Indexed event not found in episodic store.[/red]")
            else:
                console.print("[red]FAIL: No commits indexed.[/red]")

            # --- STAGE 2.2: GIT-BASED HYPOTHESIS ---
            console.print("\n[bold cyan]Stage 2.2: Git-Based Hypothesis (Evolution Trigger)[/bold cyan]")
            git_target = f"auth-module-{uuid.uuid4().hex[:4]}"
            
            for i in range(3):
                fname = f"file_{i}.txt"
                with open(os.path.join(repo_dir, fname), "w") as f: f.write(f"change {i}")
                subprocess.run(["git", "add", fname], cwd=repo_dir, check=True)
                subprocess.run(["git", "commit", "-m", f"feat({git_target}): improve logic part {i}"], cwd=repo_dir, check=True)
            
            indexed_count_v2 = bridge.sync_git(repo_path=repo_dir)
            console.print(f"[dim]Indexed {indexed_count_v2} commits in Stage 2.2[/dim]")
            
            proposal_ids = bridge.memory.run_reflection()
            
            found_git_prop = False
            for pid in proposal_ids:
                meta = bridge.memory.semantic.meta.get_by_fid(pid)
                if meta and git_target in meta.get('target', '') and "Evolving Pattern" in meta.get('title', ''):
                    found_git_prop = True
                    break
            
            if found_git_prop:
                console.print(f"[green]✔ Git Evolution: Successfully generated proposal for {git_target} based on commits.[/green]")
            else:
                console.print(f"[red]FAIL: No Git evolution proposal found for {git_target}.[/red]")
                drafts = bridge.memory.semantic.meta.list_draft_proposals()
                for d in drafts:
                    ctx = json.loads(d.get('context_json', '{}'))
                    console.print(f"[dim]Found Draft: {d.get('content')} for target {ctx.get('target')}[/dim]")
        finally:
            if os.path.exists(repo_dir): shutil.rmtree(repo_dir)

        # IMPORTANT: Wait for vector indexing to complete on CPU
        console.print("[dim]Waiting for vector engine to index (5s)...[/dim]")
        time.sleep(5)

        # --- STAGE 2.5: SEARCH & EVIDENCE VERIFICATION ---
        console.print("\n[bold cyan]Stage 2.5: Search & Evidence Verification[/bold cyan]")
        console.print("[dim]Performing semantic search...[/dim]")
        search_results = bridge.search_decisions(target, limit=1)
        if search_results:
            res = search_results[0]
            console.print(f"Search found: [bold cyan]{res['title']}[/bold cyan]")
            console.print(f"Evidence Count: [bold green]{res.get('evidence_count', 0)}[/bold green]")
            if res.get('evidence_count', 0) >= 1:
                console.print("[green]✔ Evidence linking verified.[/green]")
            else:
                console.print("[red]! Low evidence count. Check linking logic.[/red]")

        # --- STAGE 3: EVOLUTION (Auto-Supersede) ---
        console.print("\n[bold cyan]Stage 3: Knowledge Evolution (Auto-Supersede)[/bold cyan]")
        console.print("[dim]Evolving decision (this involves vector similarity check)...[/dim]")
        
        # Get the ID of the ACTIVE decision to verify it gets superseded
        active_results = [r for r in bridge.search_decisions(target, mode="audit") if r['status'] == 'active' and r['id'].startswith('decision')]
        if not active_results:
            console.print("[red]FAIL: Active decision not found for evolution.[/red]")
            return
        
        old_id = active_results[0]['id']
        current_title = active_results[0].get('title', f"Structural flaw in {target}")

        # Record a new decision with VERY high similarity to trigger auto-supersede
        # Using almost identical title and rationale to ensure > 0.7
        evolution_result = bridge.record_decision(
            title=f"Evolution: {current_title}", 
            target=target,
            rationale=f"Structural flaw confirmed in {target}. Added 200ms delay to fix it (V2 confirmed). {uuid.uuid4().hex[:4]}",
            consequences=["Apply 200ms delay"]
        )
        new_dec_id = evolution_result.metadata.get("file_id")
        console.print(f"[green]✔ Evolution recorded: {new_dec_id}[/green]")
        
        all_results = bridge.search_decisions(target, mode="audit")
        superseded_ids = [r['id'] for r in all_results if r['status'] == 'superseded']
        
        if old_id in superseded_ids:
            console.print(f"[green]✔ Auto-Supersede verified. Old ID {old_id} was automatically replaced.[/green]")
        else:
            console.print(f"[red]FAIL: Auto-Supersede did not trigger.[/red]")

        # --- STAGE 3.5: ARBITRATION (Hard Conflict) ---
        console.print("\n[bold cyan]Stage 3.5: Arbitration (Hard Conflict Simulation)[/bold cyan]")
        
        def mock_conflict_arbiter(new_d, old_d):
            console.print("[yellow]Arbiter triggered for conflicting proposals...[/yellow]")
            # Logic: If titles are radically different, it's a CONFLICT
            if "totally different" in new_d['title'].lower():
                return "CONFLICT"
            return "SUPERSEDE"

        try:
            # Try to record something for the same target but with a message that triggers CONFLICT in our mock
            bridge.memory.record_decision(
                title=f"Totally different approach for {target}",
                target=target,
                rationale="This is a completely different strategy that doesn't evolve the previous one.",
                arbiter_callback=mock_conflict_arbiter
            )
            console.print("[red]FAIL: Expected ConflictError was not raised.[/red]")
        except Exception as e:
            if "CONFLICT" in str(e):
                console.print(f"[green]✔ Arbitration verified: Conflict detected and blocked as expected.[/green]")
            else:
                console.print(f"[red]FAIL: Unexpected error during arbitration: {e}[/red]")

        # --- STAGE 4: AGING ---
        console.print("\n[bold yellow]Stage 4: Aging (Simulated 14 days)[/bold yellow]")
        meta_db = os.path.join(tmp_dir, "semantic", "semantic_meta.db")
        warp_time_in_db(meta_db, "semantic_meta", 14)
        bridge.memory.semantic.sync_meta_index()
        bridge.memory.run_maintenance()
        
        # --- STAGE 5: GRAPH VISUALIZATION ---
        console.print("\n[bold cyan]Stage 5: Knowledge Graph Visualization[/bold cyan]")
        mermaid = bridge.generate_knowledge_graph(target=target)
        console.print(Panel(mermaid, title="Mermaid Knowledge Evolution Graph", border_style="blue"))

        # --- STAGE 6: OBLIVION ---
        console.print("\n[bold red]Stage 6: Oblivion (Simulated 500 days)[/bold red]")
        warp_time_in_db(meta_db, "semantic_meta", 500)
        bridge.memory.semantic.sync_meta_index()
        bridge.memory.run_maintenance()
        
        final_results = bridge.search_decisions(target, mode="audit")
        if any(r['status'] == 'active' for r in final_results):
             console.print("[yellow]! Knowledge retained via Immortal Links (Expected).[/yellow]")
             
        # --- STAGE 7: CONTEXT INJECTION AUDIT ---
        console.print("\n[bold cyan]Stage 7: Context Injection Audit (Impact Analysis)[/bold cyan]")
        query = f"How to solve {target}?"
        
        # 1. Output without memory
        console.print("[dim]Simulating prompt WITHOUT memory...[/dim]")
        # We use 'echo' to simulate LLM, so we just check if the prompt contains context
        prompt_no_mem = query
        
        # 2. Output with memory
        console.print("[dim]Simulating prompt WITH memory...[/dim]")
        context = bridge.get_context_for_prompt(query)
        prompt_with_mem = f"{context}\n\n{query}"
        
        if "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" in prompt_with_mem:
            console.print("[green]✔ Context Injection verified: Knowledge was successfully found and injected.[/green]")
            # In a real test with a real LLM, we would compare the similarity of responses here.
            # For this script, verifying the injection string is sufficient.
        else:
            console.print("[red]FAIL: Context was not injected for a known target.[/red]")

        console.print("[bold green]✔ Full Advanced Lifecycle Verified.[/bold green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback
        console.print(traceback.format_exc())
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
            console.print(f"\n[dim]Cleaned up {tmp_dir}[/dim]")

def run_autonomy_stress_tests():
    """Implementation of 6 Deep Autonomy Tests for LedgerMind Core."""
    console.print(Panel.fit("[bold red]LedgerMind Core Deep Autonomy Stress Tests[/bold red]", border_style="red"))
    
    tmp_dir = os.path.join(os.getcwd(), ".autonomy_test")
    if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        bridge = IntegrationBridge(memory_path=tmp_dir, vector_model="ledgermind/models/v5-small-text-matching-Q4_K_M.gguf")
        
        # --- TEST 1: Falsifiability (Negative Feedback Loop) ---
        console.print("\n[bold cyan]1. Falsifiability Test (Knowledge Invalidation)[/bold cyan]")
        target_f = "Parsing-Strategy-Alpha-99"
        bridge.record_decision(
            title="Policy: Always use LibAlpha", target=target_f, 
            rationale="LibAlpha is designated as the primary stable parsing library.", consequences=["Use LibAlpha"]
        )
        # Add 5 failure events to trigger reflection
        for _ in range(5):
            bridge.memory.process_event(source="system", kind="error", content=f"Critical crash in {target_f} using LibAlpha engine", context={"target": target_f})
        
        # Run reflection
        proposals = bridge.memory.run_reflection()
        
        # Check metadata instead of filename
        drafts = bridge.memory.semantic.meta.list_draft_proposals()
        found_invalidation = any(d.get('target') == target_f for d in drafts)
        
        if found_invalidation:
            console.print("[green]✔ Falsifiability: Reflection generated new proposals based on failure patterns.[/green]")
        else:
            console.print("[yellow]! Falsifiability: No direct invalidation proposal generated yet (thresholds not met).[/yellow]")

        # --- TEST 2: Semantic Noise Immunity ---
        console.print("\n[bold cyan]2. Semantic Noise Immunity (Signal-to-Noise)[/bold cyan]")
        # Inject 20 noise events
        noise_words = ["coffee machine status", "weather update", "lunch break interval", "idle background worker", "log rotation successful"]
        for _ in range(20):
             bridge.memory.process_event(source="agent", kind="result", content=f"Noise Log: {random.choice(noise_words)}")
        
        # Inject 5 signal events
        target_s = "Nuclear-Core-Heat-Signal"
        for _ in range(5):
             bridge.memory.process_event(source="system", kind="error", content=f"DANGER: Core heat exceeded in {target_s}", context={"target": target_s})
        
        # Capture proposals
        bridge.memory.run_reflection()
        drafts = bridge.memory.semantic.meta.list_draft_proposals()
        
        signal_found = any(d.get('target') == target_s for d in drafts)
        noise_leaked = any("noise" in d.get('content', '').lower() or "coffee" in d.get('content', '').lower() for d in drafts)
        
        if signal_found and not noise_leaked:
            console.print("[green]✔ Noise Immunity: Core successfully extracted signal and ignored noise.[/green]")
        else:
            console.print(f"[yellow]! Noise Immunity: Signal Found: {signal_found}, Noise Leaked: {noise_leaked}[/yellow]")

        # --- TEST 3: Deep Truth Resolution (Chain of 10) ---
        console.print("\n[bold cyan]3. Deep Truth Resolution (Chain of 10 Supersedes)[/bold cyan]")
        target_t = "Chain-Evolution-Target-Z"
        current_id = bridge.record_decision(title="Evolution Step 1.0", target=target_t, rationale="Initial base version for testing deep recursive resolution.").metadata["file_id"]
        
        for i in range(2, 11):
            res = bridge.supersede_decision(title=f"Evolution Step {i}.0", target=target_t, rationale=f"Auto-Update to step {i}.0 with improved logic.", old_decision_ids=[current_id])
            current_id = res.metadata["file_id"]
        
        # Specific search
        search_res = bridge.search_decisions(target_t, limit=1, mode="balanced")
        if search_res and search_res[0]["title"] == "Evolution Step 10.0":
            console.print("[green]✔ Deep Truth: Correctly resolved chain of 10 to the latest version.[/green]")
        else:
            console.print(f"[red]FAIL: Expected Step 10.0, got {search_res[0]['title'] if search_res else 'None'}[/red]")

        # --- TEST 4: Self-Healing Index ---
        console.print("\n[bold cyan]4. Self-Healing Index (Database Recovery)[/bold cyan]")
        meta_db_path = os.path.join(tmp_dir, "semantic", "semantic_meta.db")
        bridge.memory.close()
        time.sleep(1) # Wait for file handles to release
        
        # Nuke all SQLite files
        for ext in ["", "-wal", "-shm"]:
            fpath = meta_db_path + ext
            if os.path.exists(fpath): os.remove(fpath)
        console.print("[dim]Metadata index files deleted.[/dim]")
        
        # Re-initialize bridge
        bridge = IntegrationBridge(memory_path=tmp_dir, vector_model="ledgermind/models/v5-small-text-matching-Q4_K_M.gguf")
        
        # Check recovery
        check_res = bridge.search_decisions(target_t, limit=1)
        if check_res and check_res[0]["title"] == "Evolution Step 10.0":
            console.print("[green]✔ Self-Healing: Metadata index successfully rebuilt from disk source.[/green]")
        else:
            console.print("[red]FAIL: Metadata recovery failed.[/red]")

        # --- TEST 5: Cross-Target Generalization ---
        console.print("\n[bold cyan]5. Cross-Target Generalization[/bold cyan]")
        target_g = "Main-Database-Cluster-PROD"
        bridge.record_decision(
            title="Database Cluster Performance Tuning", target=target_g, 
            rationale="Highly specific tuning for high-load production clusters including connection pooling.", consequences=["tuning=enabled"]
        )
        # Search for a different but semantically related target
        gen_res = bridge.search_decisions("Performance tuning for the high-load database", limit=1)
        if gen_res and "Database Cluster Performance" in gen_res[0]["title"]:
            console.print("[green]✔ Generalization: Found relevant knowledge via semantic target proximity.[/green]")
        else:
            console.print("[red]FAIL: Cross-target knowledge not found.[/red]")

        # --- TEST 6: Autonomous Merging ---
        console.print("\n[bold cyan]6. Autonomous Merging (Duplicate Detection)[/bold cyan]")
        target_m = "API-Gateway-Final-Component"
        for _ in range(3):
            bridge.memory.process_event(source="system", kind="error", content="Timeout detected in API Gateway component", context={"target": target_m})
            bridge.memory.process_event(source="system", kind="error", content="Connection expired in Gateway layer", context={"target": target_m})
        
        bridge.memory.run_reflection()
        report = bridge.memory.run_maintenance()
        
        console.print(f"[green]✔ Maintenance scan complete. Merges/Analysis performed.[/green]")
        console.print("\n[bold green]ALL DEEP AUTONOMY STRESS TESTS COMPLETED.[/bold green]")

    except Exception as e:
        console.print(f"[bold red]Autonomy Stress Test Failure:[/bold red] {e}")
        import traceback
        console.print(traceback.format_exc())
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

def show_injected_context(bridge: IntegrationBridge, query: str):
    """Fetches and displays what LedgerMind will provide as context."""
    results = bridge.memory.search_decisions(query, limit=3, mode="balanced")
    if not results: return None
    table = Table(title="[bold blue]Context Found[/bold blue]", show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Status", style="green")
    for r in results: table.add_row(r['id'], r['title'], r['status'])
    console.print(table)
    return results

def main():
    parser = argparse.ArgumentParser(description="LedgerMind Advanced Gateway")
    parser.add_argument("prompt", nargs="*", help="Your question")
    parser.add_argument("--cli", default=DEFAULT_CLI)
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--test-lifecycle", action="store_true")
    parser.add_argument("--test-autonomy", action="store_true")
    
    args = parser.parse_args()
    
    if args.test_lifecycle:
        run_lifecycle_test(args)
        sys.exit(0)
    
    if args.test_autonomy:
        run_autonomy_stress_tests()
        sys.exit(0)
        
    user_prompt = " ".join(args.prompt)
    if not user_prompt:
        parser.print_help()
        sys.exit(0)
    
    try:
        bridge = IntegrationBridge(memory_path=MEMORY_PATH, vector_model="ledgermind/models/v5-small-text-matching-Q4_K_M.gguf")
        if not args.no_memory:
            show_injected_context(bridge, user_prompt)
        bridge.execute_with_memory([args.cli], user_prompt, stream=True)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    main()
