import os
import sys
import time
import shutil
import csv
from pathlib import Path
from datetime import datetime
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.data_loader import DatasetManager
from benchmarks.evaluator import MetricsCalculator, EvaluationReport
from benchmarks.configs import get_config_factory

console = Console()

class AgenticBenchmark:
    """Evaluates IR metrics (Recall, Precision, MRR) and QA Accuracy."""
    def __init__(self, mode="full", output_dir="benchmarks/results"):
        self.mode = mode
        self.output_dir = Path(output_dir)
        self.dm = DatasetManager()
        self.mc = MetricsCalculator()
        self.results = []

    def evaluate_retrieval(self, dataset_name="synthetic", scale=1000):
        console.print(f"\n[bold magenta]--- Evaluation ({self.mode.upper()}) on {dataset_name.upper()} ---[/bold magenta]")
        
        # 1. Setup
        config = get_config_factory(self.mode)
        config.setup()
        
        # 2. Load and Ingest Data
        if dataset_name == "locomo": data = self.dm.load_locomo()
        elif dataset_name == "longmemeval": data = self.dm.load_longmemeval()
        else: data = self.dm.get_synthetic_data(scale)
            
        if not data:
            console.print(f"  [yellow]Warning: No data for {dataset_name}.[/yellow]")
            config.teardown(); return

        actual_scale = min(len(data), scale)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"Ingesting {actual_scale} items...", total=actual_scale)
            for item in data[:actual_scale]:
                try:
                    if hasattr(config, "record_direct"):
                        config.record_direct(item['title'], item['target'], item['rationale'])
                    else:
                        config.memory.record_decision(item['title'], item['target'], item['rationale'])
                except: pass
                progress.advance(task)
        
        # 3. Evaluation
        sample_count = min(len(data), 200)
        samples = data[:sample_count]
        report = EvaluationReport(self.mode)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"Mapping and Querying...", total=sample_count)
            for item in samples:
                target = item['target']
                true_id_res = config.memory.search_decisions(target, limit=1, mode='strict')
                if not true_id_res: 
                    progress.advance(task)
                    continue
                gold_id = true_id_res[0]['id']
                
                text = item['rationale']
                query = text[len(text)//4 : len(text)//4 + 100] if len(text) > 120 else text[:100]
                
                retrieved_ids = config.search(query, limit=5)
                
                m = {
                    "recall@1": self.mc.recall_at_k(retrieved_ids, gold_id, 1),
                    "recall@5": self.mc.recall_at_k(retrieved_ids, gold_id, 5),
                    "precision@5": self.mc.precision_at_k(retrieved_ids, gold_id, 5),
                    "mrr": self.mc.reciprocal_rank(retrieved_ids, gold_id)
                }
                report.add_point(m)
                progress.advance(task)

        summary = report.summarize()
        summary["dataset"] = dataset_name
        summary["scale"] = actual_scale
        summary["mode"] = self.mode
        self.results.append(summary)
        
        console.print(f"  [bold green]Results:[/bold green] Recall@5: [bold]{summary['recall@5']:.2%}[/bold], MRR: [bold]{summary['mrr']:.4f}[/bold]")
        config.teardown()

    def run_suite(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        datasets = ["synthetic", "locomo", "longmemeval"]
        
        for ds in datasets:
            self.evaluate_retrieval(dataset_name=ds)
            
        self._save_report(timestamp)

    def _save_report(self, timestamp):
        path = self.output_dir / f"agentic_metrics_{self.mode}_{timestamp}.csv"
        if not self.results: return
        keys = self.results[0].keys()
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.results)
        console.print(f"Report saved to [blue]{path}[/blue]")

    def _save_json_report(self, timestamp):
        import json
        path = self.output_dir / f"agentic_metrics_{self.mode}_{timestamp}.json"
        if not self.results: return
        with open(path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        console.print(f"JSON report saved to [blue]{path}[/blue]")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="full", choices=["full", "keyword", "baseline_flat", "baseline_sql"])
    parser.add_argument("--scale", type=int, default=1000)
    parser.add_argument("--dataset", default="locomo", choices=["synthetic", "locomo", "longmemeval"])
    parser.add_argument("--output-json", action="store_true",
                        help="Also save results in JSON format for machine reading")
    args = parser.parse_args()

    bench = AgenticBenchmark(mode=args.mode)
    bench.evaluate_retrieval(dataset_name=args.dataset, scale=args.scale)
    
    if args.output_json and bench.results:
        bench._save_json_report(datetime.now().strftime("%Y%m%d_%H%M%S"))
