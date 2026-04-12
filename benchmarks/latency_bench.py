import time
import statistics
import shutil
import tempfile
import os
import sys
import csv
import numpy as np
from pathlib import Path
from datetime import datetime
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.data_loader import DatasetManager
from benchmarks.utils import ResourceTracker, ResultVisualizer
from benchmarks.configs import get_config_factory
from benchmarks.evaluator import MetricsCalculator, EvaluationReport

console = Console()

class ScalabilityBenchmark:
    """Measures Latency and Accuracy degradation across various scales (100, 1k, 10k)."""
    def __init__(self, mode="full", output_dir="benchmarks/results"):
        self.mode = mode
        self.output_dir = Path(output_dir)
        self.results = []
        self.tracker = ResourceTracker()
        self.dm = DatasetManager()
        self.mc = MetricsCalculator()
        self.visualizer = ResultVisualizer(output_dir)

    def run_suite(self, scales=[1000, 5000, 10000, 20000], dataset="synthetic"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_name = dataset if dataset != "synthetic" else "synthetic"

        for scale in scales:
            console.print(f"\n[bold blue]>>> SCALE: {scale} records[/bold blue] (Mode: {self.mode}, Dataset: {dataset_name})")
            config = get_config_factory(self.mode)
            config.setup()

            # 1. INGESTION (WRITE LATENCY)
            if dataset == "locomo":
                data = self.dm.load_locomo()
            elif dataset == "longmemeval":
                data = self.dm.load_longmemeval()
            else:
                data = self.dm.get_synthetic_data(scale)
            
            if not data:
                console.print(f"  [yellow]Warning: Dataset {dataset} not available, falling back to synthetic[/yellow]")
                data = self.dm.get_synthetic_data(scale)
            
            # Use scale to limit dataset size if needed
            data = data[:scale]
            actual_scale = len(data)
            latencies = []
            self.tracker.start()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Ingesting {actual_scale} items...", total=actual_scale)
                for item in data:
                    start = time.perf_counter()
                    try:
                        config.memory.record_decision(item['title'], item['target'], item['rationale'])
                    except: pass
                    latencies.append((time.perf_counter() - start) * 1000)
                    progress.advance(task)

            usage = self.tracker.stop()
            self._record("write", scale, latencies, usage, dataset=dataset_name)

            # 2. RETRIEVAL (ACCURACY + SEARCH LATENCY)
            report = EvaluationReport(self.mode)
            search_latencies = []
            sample_count = min(len(data), 100)
            samples = data[:sample_count]
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Evaluating accuracy...", total=sample_count)
                for item in samples:
                    true_id_res = config.memory.search_decisions(item['target'], limit=1, mode='strict')
                    if not true_id_res: 
                        progress.advance(task)
                        continue
                    gold_id = true_id_res[0]['id']
                    
                    query = item['rationale'][:100]
                    
                    start = time.perf_counter()
                    retrieved_ids = config.search(query, limit=5)
                    search_latencies.append((time.perf_counter() - start) * 1000)
                    
                    report.add_point({
                        "recall@5": self.mc.recall_at_k(retrieved_ids, gold_id, 5),
                        "mrr": self.mc.reciprocal_rank(retrieved_ids, gold_id)
                    })
                    progress.advance(task)
            
            summary = report.summarize()
            self._record("search", scale, search_latencies, usage, accuracy=summary.get("recall@5", 0), dataset=dataset_name)

            config.teardown()

        report_path = self._save_report(timestamp, dataset_name)
        self.visualizer.generate_plots(report_path)

    def _record(self, op, scale, lats, usage, accuracy=None, dataset="synthetic"):
        res = {
            "operation": op,
            "scale": scale,
            "mode": self.mode,
            "dataset": dataset,
            "p50_ms": statistics.median(lats) if lats else 0,
            "p95_ms": sorted(lats)[int(len(lats) * 0.95)] if len(lats) > 1 else (lats[0] if lats else 0),
            "throughput_ops_sec": len(lats) / usage['duration_sec'] if usage['duration_sec'] > 0 else 0,
            "accuracy_recall_5": accuracy if accuracy is not None else 0
        }
        self.results.append(res)
        color = "green" if op == "write" else "cyan"
        console.print(f"  [{color}]{op.upper()}[/{color}]: p95=[bold]{res['p95_ms']:.2f}ms[/bold], Acc=[bold]{res.get('accuracy_recall_5', 0):.2%}[/bold]")
        return res  # Return for later aggregation

    def _save_report(self, timestamp, dataset_name):
        path = self.output_dir / f"scalability_{self.mode}_{dataset_name}_{timestamp}.csv"
        keys = self.results[0].keys()
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.results)
        return str(path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="full", choices=["full", "keyword", "baseline_flat", "baseline_sql"])
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--dataset", default="synthetic", choices=["synthetic", "locomo", "longmemeval"],
                        help="Dataset to use for benchmarking (default: synthetic)")
    args = parser.parse_args()

    scales = [1000, 5000] if args.fast else [1000, 5000, 10000, 20000]
    bench = ScalabilityBenchmark(mode=args.mode)
    bench.run_suite(scales=scales, dataset=args.dataset)
