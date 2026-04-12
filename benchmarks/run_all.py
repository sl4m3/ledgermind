import subprocess
import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
import psutil

console = Console()

BENCHMARK_MODES = {
    "full": "LedgerMind Full (Vector + Keyword + RRF)",
    "keyword": "LedgerMind Keyword-only (FTS5)",
    "baseline_sql": "Baseline SQLite FTS5",
}

DATASETS = ["locomo", "longmemeval"]

# Scale limits for each dataset (to avoid excessive runtimes)
DATASET_SCALE_LIMITS = {
    "locomo": 1000,      # Full dataset
    "longmemeval": 500,  # Full dataset (sequential execution avoids contention)
}

# Parallel execution settings
# For high-end workstations (7950X + 32GB), we can run more in parallel
# But memory model loading is the bottleneck, so we limit to avoid OOM
MAX_PARALLEL_WORKERS = 2  # 2 workers = 2 models loaded simultaneously

BENCHMARK_TIMEOUT = {
    # (mode, dataset) -> timeout in seconds
    # Reasonable timeouts for 7950X + 32GB RAM
    ("full", "locomo"): 900,         # 15 min
    ("full", "longmemeval"): 600,    # 10 min (200 items)
    ("keyword", "locomo"): 600,      # 10 min
    ("keyword", "longmemeval"): 400, # 7 min (200 items)
    ("baseline_sql", "locomo"): 300,  # 5 min
    ("baseline_sql", "longmemeval"): 200, # 3 min (200 items)
}

def get_timeout(mode: str, dataset: str) -> int:
    """Get timeout for a specific benchmark configuration."""
    return BENCHMARK_TIMEOUT.get((mode, dataset), 1800)  # Default 30 min

def run_single_benchmark(args: Tuple[str, str, str]) -> Tuple[str, float, bool]:
    """
    Run a single benchmark configuration.
    Returns: (benchmark_name, duration, success)
    """
    mode, dataset, bench_type = args
    
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{os.getcwd()}:{os.getcwd()}/src"
    
    if bench_type == "latency":
        scale_limit = DATASET_SCALE_LIMITS.get(dataset, 1000)
        cmd = [sys.executable, "benchmarks/latency_bench.py", 
               "--mode", mode, "--dataset", dataset, "--fast"]
        name = f"[{mode.upper()}] Latency on {dataset.upper()}"
    else:  # agentic
        scale_limit = DATASET_SCALE_LIMITS.get(dataset, 1000)
        cmd = [sys.executable, "benchmarks/agentic_bench.py",
               "--mode", mode, "--dataset", dataset, "--scale", str(scale_limit), "--output-json"]
        name = f"[{mode.upper()}] Accuracy on {dataset.upper()}"
    
    timeout = get_timeout(mode, dataset)
    
    # For LongMemEval, use sequential execution to avoid model loading contention
    # For others, parallel is fine
    is_long_running = dataset == "longmemeval"
    
    start = time.time()
    try:
        # Suppress all output from subprocess to avoid cluttering the progress bar
        with open(os.devnull, 'w') as devnull:
            result = subprocess.run(cmd, env=env, stdout=devnull, stderr=subprocess.DEVNULL, timeout=timeout)
        duration = time.time() - start
        success = result.returncode == 0
        return (name, duration, success)
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return (f"{name} (timeout {timeout/60:.0f}m)", duration, False)
    except Exception as e:
        duration = time.time() - start
        return (name, duration, False)

def collect_results(res_dir: Path, modes: List[str], datasets: List[str]) -> Dict:
    """Collect all CSV results and return aggregated data."""
    all_results = {}
    
    for mode in modes:
        for dataset in datasets:
            # Find matching files
            pattern = f"scalability_{mode}_{dataset}_*.csv"
            files = list(res_dir.glob(pattern))
            if files:
                latest = max(files, key=lambda f: f.stat().st_mtime)
                all_results[f"{mode}_{dataset}"] = latest
    
    return all_results

def generate_comparative_report(results: Dict, res_dir: Path) -> Path:
    """Generate a markdown report comparing all modes."""
    report_file = res_dir / f"comparative_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 📊 LedgerMind Comparative Benchmark Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 📈 Performance Comparison\n\n")
        f.write("| Mode | Dataset | Operation | Scale | p50 (ms) | p95 (ms) | Throughput (ops/s) | Recall@5 |\n")
        f.write("|------|---------|-----------|-------|----------|----------|-------------------|----------|\n")
        
        # Parse CSV files
        for key, filepath in results.items():
            try:
                import csv
                with open(filepath, 'r') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        f.write(f"| {row['mode']} | {row.get('dataset', 'N/A')} | {row['operation']} | {row['scale']} | ")
                        f.write(f"{float(row['p50_ms']):.2f} | {float(row['p95_ms']):.2f} | ")
                        f.write(f"{float(row['throughput_ops_sec']):.2f} | {float(row['accuracy_recall_5']):.2%} |\n")
            except Exception as e:
                console.print(f"  [yellow]Warning: Could not parse {filepath}: {e}[/yellow]")
        
        f.write("\n## 🔍 Key Insights\n\n")
        f.write("*Full report will be generated after all benchmark runs complete.*\n")
    
    return report_file

def main():
    res_dir = Path("benchmarks/results")
    res_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        "[bold yellow]LEDGERMIND COMPARATIVE BENCHMARK SUITE[/bold yellow]\n"
        "[dim]Parallel Execution | Testing: Full vs Keyword vs Baseline | Datasets: LoCoMo, LongMemEval[/dim]",
        border_style="yellow"
    ))

    # Build task list: separate fast (LoCoMo) and slow (LongMemEval) benchmarks
    fast_tasks = []
    slow_tasks = []
    
    for mode in BENCHMARK_MODES.keys():
        # LoCoMo - parallel
        fast_tasks.append((mode, "locomo", "latency"))
        fast_tasks.append((mode, "locomo", "agentic"))
        # LongMemEval - sequential (to avoid model contention)
        slow_tasks.append((mode, "longmemeval", "latency"))
        slow_tasks.append((mode, "longmemeval", "agentic"))
    
    all_tasks = fast_tasks + slow_tasks
    
    console.print(f"\n📋 [bold]Total tasks:[/bold] {len(all_tasks)}")
    console.print(f"  🚀 Fast (LoCoMo, parallel): {len(fast_tasks)}")
    console.print(f"  🐌 Slow (LongMemEval, sequential): {len(slow_tasks)}")
    console.print(f"🔢 [bold]Max parallel workers:[/bold] {MAX_PARALLEL_WORKERS}\n")

    # Run benchmarks
    results = {}
    total_start = time.time()
    
    # Phase 1: Fast parallel (LoCoMo)
    console.print("[bold cyan]Phase 1: Fast parallel benchmarks (LoCoMo)[/bold cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        main_task = progress.add_task(f"[bold cyan]Running LoCoMo benchmarks...", total=len(fast_tasks))
        
        with ProcessPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            future_to_task = {
                executor.submit(run_single_benchmark, task): task
                for task in fast_tasks
            }
            
            completed = 0
            failed = 0
            
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                mode, dataset, bench_type = task
                
                try:
                    name, duration, success = future.result()
                    completed += 1
                    
                    if success:
                        results[f"{bench_type}_{mode}_{dataset}"] = duration
                    else:
                        failed += 1
                    
                    progress.update(main_task, advance=1)
                    icon = "✅" if success else "❌"
                    memory_gb = psutil.virtual_memory().used / (1024**3)
                    cpu_percent = psutil.cpu_percent(interval=0.1)
                    console.print(f"  {icon} [dim]{name}[/dim] [bold]{duration:.1f}s[/bold] | RAM: {memory_gb:.1f}GB | CPU: {cpu_percent:.0f}%")
                    
                except Exception as e:
                    failed += 1
                    progress.update(main_task, advance=1)
                    console.print(f"[red]  ❌ Task failed: {mode}/{dataset}/{bench_type} - {e}[/red]")

    # Phase 2: Slow sequential (LongMemEval)
    console.print("\n[bold yellow]Phase 2: Sequential benchmarks (LongMemEval)[/bold yellow]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        main_task = progress.add_task(f"[bold yellow]Running LongMemEval benchmarks (sequential)...", total=len(slow_tasks))
        
        for task in slow_tasks:
            mode, dataset, bench_type = task
            
            try:
                name, duration, success = run_single_benchmark(task)
                
                if success:
                    results[f"{bench_type}_{mode}_{dataset}"] = duration
                else:
                    failed = results.get('failed', 0) + 1
                
                progress.update(main_task, advance=1)
                icon = "✅" if success else "❌"
                memory_gb = psutil.virtual_memory().used / (1024**3)
                console.print(f"  {icon} [dim]{name}[/dim] [bold]{duration:.1f}s[/bold] | RAM: {memory_gb:.1f}GB")
                
            except Exception as e:
                failed = results.get('failed', 0) + 1
                progress.update(main_task, advance=1)
                console.print(f"[red]  ❌ Task failed: {mode}/{dataset}/{bench_type} - {e}[/red]")

    total_duration = time.time() - total_start

    console.print(Panel(f"⏱️ [bold]Total Execution Time:[/bold] {total_duration/60:.1f} minutes", border_style="cyan"))
    
    # Collect and analyze results
    result_files = collect_results(res_dir, list(BENCHMARK_MODES.keys()), DATASETS)
    if result_files:
        report_file = generate_comparative_report(result_files, res_dir)
        console.print(Panel(
            f"✨ [bold green]ALL TESTS DONE![/bold green]\n"
            f"Comparative report created: [blue]{report_file}[/blue]",
            border_style="green"
        ))
    else:
        console.print("[yellow]⚠️  No result files generated. Check for errors above.[/yellow]")

    # Print summary table
    console.print("\n[bold]📊 Quick Summary:[/bold]")
    table = Table(box=box.ROUNDED)
    table.add_column("Benchmark", style="cyan")
    table.add_column("Mode", style="magenta")
    table.add_column("Dataset", style="green")
    table.add_column("Duration", justify="right")
    table.add_column("Status", justify="center")
    
    for key, duration in results.items():
        parts = key.split("_", 2)
        if len(parts) == 3:
            bench_type, mode, dataset = parts
            table.add_row(bench_type, mode, dataset, f"{duration:.1f}s", "✅")
    
    console.print(table)

if __name__ == "__main__":
    main()
