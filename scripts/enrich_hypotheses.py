import logging
import sys
import os
import time
import sqlite3

# Setup silent logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("enrichment-tool")

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table

console = Console()

def main():
    console.print(Panel.fit(
        "[bold green]LedgerMind Hypotheses Enrichment[/bold green]\n"
        "[dim]Version 3.1.0-rich | Optimization: On[/dim]", 
        border_style="green"
    ))
    
    storage_path = os.path.abspath("../.ledgermind")
    
    try:
        # 1. Initialization
        with console.status("[bold cyan]Waking up engines...[/bold cyan]"):
            memory = Memory(storage_path=storage_path)
            mode = memory.semantic.meta.get_config("arbitration_mode", "lite")
            client = memory.semantic.meta.get_config("client", "none")
            model = memory.semantic.meta.get_config("enrichment_model", "default")
        
        if mode == "lite":
            console.print("\n[yellow]! System is in 'lite' mode. Enrichment is disabled.[/yellow]")
            return

        # 2. Query pending tasks
        db_path = os.path.join(memory.semantic.repo_path, "semantic_meta.db")
        conn = sqlite3.connect(db_path)
        query = "SELECT fid, target FROM semantic_meta WHERE kind = 'proposal' AND context_json LIKE '%\"enrichment_status\": \"pending\"%'"
        pending_tasks = conn.execute(query).fetchall()
        conn.close()

        if not pending_tasks:
            console.print("\n[green]✓ Knowledge base is fully crystallized. No pending tasks.[/green]")
            return

        console.print(f"• [bold]Mode:[/bold] {mode} | [bold]Client:[/bold] {client} | [bold]Model:[/bold] {model}")
        console.print(f"• [bold]Queue:[/bold] {len(pending_tasks)} proposals\n")

        # 3. Process with UI
        enricher = LLMEnricher(mode=mode, client_name=client, model_name=model)
        
        results_table = Table(title="Enrichment Results", box=None, header_style="bold magenta")
        results_table.add_column("Proposal ID", style="dim", width=30)
        results_table.add_column("Target", style="cyan")
        results_table.add_column("Status", justify="center")
        results_table.add_column("Compression", justify="right")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            main_task = progress.add_task("[cyan]Crystallizing...", total=len(pending_tasks))
            
            for fid, target in pending_tasks:
                progress.update(main_task, description=f"[cyan]Processing {target}...")
                
                try:
                    # Logic directly calling core enricher
                    from ledgermind.core.stores.semantic_store.loader import MemoryLoader
                    from ledgermind.core.core.schemas import ProposalContent, DecisionStream
                    
                    file_path = os.path.join(memory.semantic.repo_path, fid)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        raw_content = f.read()
                    
                    data, _ = MemoryLoader.parse(raw_content)
                    p_data = data.get('context', {})
                    
                    # Create object
                    p_obj = DecisionStream(**p_data) if 'decision_id' in p_data else ProposalContent(**p_data)
                    orig_rationale = p_obj.rationale
                    orig_evidence_len = len(p_obj.evidence_event_ids) if p_obj.evidence_event_ids else 0

                    # 1. Call LLM
                    enriched = enricher.enrich_proposal(p_obj)
                    
                    # 2. Check if changed
                    if enriched.rationale != orig_rationale:
                        # 3. Apply Compression (Counter)
                        final_ids = []
                        if p_obj.evidence_event_ids:
                            total_count = len(p_obj.evidence_event_ids)
                            final_ids = p_obj.evidence_event_ids[-5:] # Tail only
                            
                            # Updates dictionary for saving
                            updates = {
                                "rationale": str(enriched.rationale),
                                "enrichment_status": "completed",
                                "evidence_event_ids": final_ids,
                                "total_evidence_count": total_count # New field!
                            }
                            
                            # If it was procedural, we can also clear the raw steps 
                            # because we have a better text now
                            if hasattr(p_obj, 'procedural') and p_obj.procedural:
                                updates["procedural"] = None
                        
                        # 4. Persistence
                        with memory.semantic.transaction():
                            memory.semantic.update_decision(
                                fid, updates, f"Enriched and Compressed {target}"
                            )
                        
                        results_table.add_row(
                            fid[:28] + "..", 
                            target, 
                            "[green]Done[/green]", 
                            f"{orig_evidence_len} -> {len(final_ids)}"
                        )
                    else:
                        results_table.add_row(fid[:28] + "..", target, "[yellow]Skipped[/yellow]", "-")
                        
                except Exception as e:
                    results_table.add_row(fid[:28] + "..", target, f"[red]Error: {str(e)[:15]}[/red]", "-")
                
                progress.advance(main_task)

        console.print(results_table)
        console.print("\n[bold green]✓ Enrichment cycle finished.[/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]FATAL:[/bold red] {e}")

if __name__ == "__main__":
    main()
