#!/usr/bin/env python3
"""
Comparative analysis script for LedgerMind benchmark results.
Parses all CSV/JSON result files and generates comparison tables and plots.
"""

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
import matplotlib.pyplot as plt
import numpy as np

console = Console()

def parse_scalability_csv(filepath: Path) -> List[Dict]:
    """Parse a scalability CSV file and return list of results."""
    results = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                'mode': row['mode'],
                'dataset': row.get('dataset', 'unknown'),
                'operation': row['operation'],
                'scale': int(row['scale']),
                'p50_ms': float(row['p50_ms']),
                'p95_ms': float(row['p95_ms']),
                'throughput_ops_sec': float(row['throughput_ops_sec']),
                'recall@5': float(row.get('accuracy_recall_5', 0)),
                'source_file': filepath.name
            })
    return results

def parse_agentic_json(filepath: Path) -> List[Dict]:
    """Parse an agentic benchmark JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    results = []
    for entry in data:
        results.append({
            'mode': entry.get('mode', 'unknown'),
            'dataset': entry.get('dataset', 'unknown'),
            'scale': entry.get('scale', 0),
            'recall@1': entry.get('recall@1', 0),
            'recall@5': entry.get('recall@5', 0),
            'precision@5': entry.get('precision@5', 0),
            'mrr': entry.get('mrr', 0),
            'source_file': filepath.name
        })
    return results

def collect_all_results(results_dir: Path) -> Dict:
    """Collect all benchmark results from the directory."""
    all_scalability = []
    all_agentic = []
    
    for csv_file in results_dir.glob("scalability_*.csv"):
        try:
            all_scalability.extend(parse_scalability_csv(csv_file))
        except Exception as e:
            console.print(f"[yellow]⚠️  Warning: Could not parse {csv_file.name}: {e}[/yellow]")
    
    for json_file in results_dir.glob("agentic_*.json"):
        try:
            all_agentic.extend(parse_agentic_json(json_file))
        except Exception as e:
            console.print(f"[yellow]⚠️  Warning: Could not parse {json_file.name}: {e}[/yellow]")
    
    return {
        'scalability': all_scalability,
        'agentic': all_agentic
    }

def print_comparison_table(results: Dict):
    """Print rich comparison tables."""
    
    # Scalability table
    if results['scalability']:
        console.print("\n[bold blue]📈 Scalability & Latency Comparison[/bold blue]")
        table = Table(box=box.ROUNDED, show_lines=True)
        table.add_column("Mode", style="cyan", no_wrap=True)
        table.add_column("Dataset", style="green")
        table.add_column("Operation", style="magenta")
        table.add_column("Scale", justify="right")
        table.add_column("p50 (ms)", justify="right")
        table.add_column("p95 (ms)", justify="right")
        table.add_column("Throughput\n(ops/s)", justify="right")
        table.add_column("Recall@5", justify="right")
        
        # Sort by mode, dataset, scale
        sorted_results = sorted(results['scalability'], 
                                key=lambda x: (x['mode'], x['dataset'], x['scale'], x['operation']))
        
        for r in sorted_results:
            table.add_row(
                r['mode'],
                r['dataset'],
                r['operation'],
                str(r['scale']),
                f"{r['p50_ms']:.2f}",
                f"{r['p95_ms']:.2f}",
                f"{r['throughput_ops_sec']:.2f}",
                f"{r['recall@5']:.2%}"
            )
        
        console.print(table)
    
    # Agentic table
    if results['agentic']:
        console.print("\n[bold magenta]🎯 Retrieval Accuracy Comparison[/bold magenta]")
        table = Table(box=box.ROUNDED)
        table.add_column("Mode", style="cyan", no_wrap=True)
        table.add_column("Dataset", style="green")
        table.add_column("Scale", justify="right")
        table.add_column("Recall@1", justify="right")
        table.add_column("Recall@5", justify="right")
        table.add_column("Precision@5", justify="right")
        table.add_column("MRR", justify="right")
        
        sorted_results = sorted(results['agentic'],
                                key=lambda x: (x['mode'], x['dataset'], x['scale']))
        
        for r in sorted_results:
            table.add_row(
                r['mode'],
                r['dataset'],
                str(r['scale']),
                f"{r['recall@1']:.2%}",
                f"{r['recall@5']:.2%}",
                f"{r['precision@5']:.4f}",
                f"{r['mrr']:.4f}"
            )
        
        console.print(table)

def calculate_overhead(results: Dict):
    """Calculate overhead of full mode vs baseline."""
    console.print("\n[bold yellow]⚖️  Overhead Analysis[/bold yellow]")
    
    scalability = results['scalability']
    if not scalability:
        console.print("  [yellow]No scalability data available[/yellow]")
        return
    
    # Group by dataset and scale
    groups = {}
    for r in scalability:
        key = (r['dataset'], r['scale'], r['operation'])
        if key not in groups:
            groups[key] = {}
        groups[key][r['mode']] = r
    
    for (dataset, scale, op), modes in groups.items():
        if 'full' in modes and 'baseline_sql' in modes:
            full = modes['full']
            baseline = modes['baseline_sql']
            
            console.print(f"\n  [bold]{dataset.upper()} - {op.upper()} (Scale: {scale})[/bold]")
            
            # Latency overhead
            if baseline['p50_ms'] > 0:
                latency_overhead = ((full['p50_ms'] - baseline['p50_ms']) / baseline['p50_ms']) * 100
                console.print(f"    Latency p50 overhead: [bold red]+{latency_overhead:.1f}%[/bold red] "
                              f"({baseline['p50_ms']:.2f}ms → {full['p50_ms']:.2f}ms)")
            
            # Throughput overhead
            if baseline['throughput_ops_sec'] > 0:
                throughput_overhead = ((full['throughput_ops_sec'] - baseline['throughput_ops_sec']) / 
                                      baseline['throughput_ops_sec']) * 100
                console.print(f"    Throughput overhead: [bold red]{throughput_overhead:.1f}%[/bold red] "
                              f"({baseline['throughput_ops_sec']:.2f} → {full['throughput_ops_sec']:.2f} ops/s)")
            
            # Recall improvement
            if baseline['recall@5'] > 0:
                recall_improvement = ((full['recall@5'] - baseline['recall@5']) / baseline['recall@5']) * 100
                console.print(f"    Recall@5 improvement: [bold green]+{recall_improvement:.1f}%[/bold green] "
                              f"({baseline['recall@5']:.2%} → {full['recall@5']:.2%})")
            else:
                console.print(f"    Recall@5: baseline=0%, full={full['recall@5']:.2%} "
                              f"[bold green](+∞%)[/bold green]")

def generate_comparison_plots(results: Dict, output_dir: Path):
    """Generate comparison plots for all modes."""
    if not results['scalability']:
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Group data for plotting
    modes = sorted(set(r['mode'] for r in results['scalability']))
    datasets = sorted(set(r['dataset'] for r in results['scalability']))
    
    for dataset in datasets:
        dataset_data = [r for r in results['scalability'] if r['dataset'] == dataset]
        
        # Plot 1: Latency comparison
        fig, ax = plt.subplots(figsize=(12, 6))
        x_pos = np.arange(len(modes))
        width = 0.35
        
        write_data = [r for r in dataset_data if r['operation'] == 'write' and r['scale'] == max(r['scale'] for r in dataset_data)]
        search_data = [r for r in dataset_data if r['operation'] == 'search' and r['scale'] == max(r['scale'] for r in dataset_data)]
        
        if write_data or search_data:
            modes_present = sorted(set([r['mode'] for r in write_data + search_data]))
            write_p95 = [next((r['p95_ms'] for r in write_data if r['mode'] == m), 0) for m in modes_present]
            search_p95 = [next((r['p95_ms'] for r in search_data if r['mode'] == m), 0) for m in modes_present]
            
            x = np.arange(len(modes_present))
            ax.bar(x - width/2, write_p95, width, label='Write p95', color='#FF6B6B')
            ax.bar(x + width/2, search_p95, width, label='Search p95', color='#4ECDC4')
            
            ax.set_xlabel('Mode')
            ax.set_ylabel('Latency (ms)')
            ax.set_title(f'Latency Comparison - {dataset.upper()}')
            ax.set_xticks(x)
            ax.set_xticklabels(modes_present, rotation=45, ha='right')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(output_dir / f'latency_comparison_{dataset}.png', dpi=150)
            plt.close()
            console.print(f"  [green]✓[/green] Saved latency_comparison_{dataset}.png")
        
        # Plot 2: Throughput comparison
        fig, ax = plt.subplots(figsize=(12, 6))
        
        write_throughput = [r['throughput_ops_sec'] for r in write_data]
        search_throughput = [r['throughput_ops_sec'] for r in search_data]
        
        if write_throughput or search_throughput:
            ax.bar(x - width/2, write_throughput, width, label='Write throughput', color='#95E1D3')
            ax.bar(x + width/2, search_throughput, width, label='Search throughput', color='#F38181')
            
            ax.set_xlabel('Mode')
            ax.set_ylabel('Operations/sec')
            ax.set_title(f'Throughput Comparison - {dataset.upper()}')
            ax.set_xticks(x)
            ax.set_xticklabels(modes_present, rotation=45, ha='right')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(output_dir / f'throughput_comparison_{dataset}.png', dpi=150)
            plt.close()
            console.print(f"  [green]✓[/green] Saved throughput_comparison_{dataset}.png")
        
        # Plot 3: Recall comparison (if available)
        recall_data = [r for r in dataset_data if r['recall@5'] > 0]
        if recall_data:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            modes_recall = sorted(set(r['mode'] for r in recall_data))
            recall_values = [next((r['recall@5'] for r in recall_data if r['mode'] == m), 0) for m in modes_recall]
            
            colors = ['#2ECC71' if v > 0.8 else '#F39C12' if v > 0.5 else '#E74C3C' for v in recall_values]
            ax.bar(modes_recall, recall_values, color=colors, alpha=0.8)
            ax.set_xlabel('Mode')
            ax.set_ylabel('Recall@5')
            ax.set_title(f'Recall@5 Comparison - {dataset.upper()}')
            ax.set_ylim(0, 1.0)
            ax.grid(True, alpha=0.3, axis='y')
            
            for i, v in enumerate(recall_values):
                ax.text(i, v + 0.02, f'{v:.2%}', ha='center', fontweight='bold')
            
            plt.tight_layout()
            plt.savefig(output_dir / f'recall_comparison_{dataset}.png', dpi=150)
            plt.close()
            console.print(f"  [green]✓[/green] Saved recall_comparison_{dataset}.png")

def main():
    results_dir = Path("benchmarks/results")
    
    if not results_dir.exists():
        console.print(f"[red]❌ Results directory not found: {results_dir}[/red]")
        console.print("Run benchmarks first: python benchmarks/run_all.py")
        sys.exit(1)
    
    console.print(Panel.fit(
        "[bold cyan]LEDGERMIND BENCHMARK ANALYSIS[/bold cyan]\n"
        "[dim]Comparing: Full vs Keyword vs Baseline[/dim]",
        border_style="cyan"
    ))
    
    # Collect results
    console.print("\n🔍 Collecting results...")
    all_results = collect_all_results(results_dir)
    
    scalability_count = len(all_results['scalability'])
    agentic_count = len(all_results['agentic'])
    
    if scalability_count == 0 and agentic_count == 0:
        console.print("[yellow]⚠️  No benchmark results found. Run benchmarks first.[/yellow]")
        sys.exit(1)
    
    console.print(f"  [green]✓[/green] Found {scalability_count} scalability results")
    console.print(f"  [green]✓[/green] Found {agentic_count} agentic results")
    
    # Print comparison tables
    print_comparison_table(all_results)
    
    # Calculate overhead
    calculate_overhead(all_results)
    
    # Generate plots
    console.print("\n📊 Generating comparison plots...")
    generate_comparison_plots(all_results, results_dir)
    
    console.print(Panel.fit(
        "[bold green]✅ Analysis Complete![/bold green]\n"
        f"Results directory: [blue]{results_dir.absolute()}[/blue]",
        border_style="green"
    ))

if __name__ == "__main__":
    main()
