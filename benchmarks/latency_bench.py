import time
import statistics
import shutil
import tempfile
import os
import csv
import numpy as np
from pathlib import Path
from datetime import datetime
from benchmarks.data_loader import DatasetManager
from benchmarks.utils import ResourceTracker, ResultVisualizer
from benchmarks.configs import get_config_factory
from benchmarks.evaluator import MetricsCalculator, EvaluationReport

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

    def run_suite(self, scales=[100, 500, 1000, 5000]):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for scale in scales:
            print(f"\n>>> SCALE: {scale} records (Mode: {self.mode})")
            config = get_config_factory(self.mode)
            config.setup()
            
            # 1. INGESTION (WRITE LATENCY)
            data = self.dm.get_synthetic_data(scale)
            latencies = []
            self.tracker.start()
            for item in data:
                start = time.perf_counter()
                try:
                    config.memory.record_decision(item['title'], item['target'], item['rationale'])
                except: pass
                latencies.append((time.perf_counter() - start) * 1000)
            
            usage = self.tracker.stop()
            self._record("write", scale, latencies, usage)

            # 2. RETRIEVAL (ACCURACY + SEARCH LATENCY)
            report = EvaluationReport(self.mode)
            search_latencies = []
            samples = data[:30] # Evaluate 30 samples for accuracy at each scale
            
            for item in samples:
                # Setup gold standard
                true_id_res = config.memory.search_decisions(item['target'], limit=1, mode='strict')
                if not true_id_res: continue
                gold_id = true_id_res[0]['id']
                
                query = item['rationale'][:100]
                
                start = time.perf_counter()
                retrieved_ids = config.search(query, limit=5)
                search_latencies.append((time.perf_counter() - start) * 1000)
                
                # Calculate accuracy for degradation curve
                report.add_point({
                    "recall@5": self.mc.recall_at_k(retrieved_ids, gold_id, 5),
                    "mrr": self.mc.reciprocal_rank(retrieved_ids, gold_id)
                })
            
            summary = report.summarize()
            self._record("search", scale, search_latencies, usage, accuracy=summary.get("recall@5", 0))

            config.teardown()

        report_path = self._save_report(timestamp)
        self.visualizer.generate_plots(report_path)

    def _record(self, op, scale, lats, usage, accuracy=None):
        res = {
            "operation": op,
            "scale": scale,
            "mode": self.mode,
            "p50_ms": statistics.median(lats) if lats else 0,
            "p95_ms": sorted(lats)[int(len(lats) * 0.95)] if len(lats) > 1 else (lats[0] if lats else 0),
            "throughput_ops_sec": len(lats) / usage['duration_sec'] if usage['duration_sec'] > 0 else 0,
            "accuracy_recall_5": accuracy if accuracy is not None else 0
        }
        self.results.append(res)
        print(f"  {op.upper()}: p95={res['p95_ms']:.2f}ms, Acc={res.get('accuracy_recall_5', 0):.2%}")

    def _save_report(self, timestamp):
        path = self.output_dir / f"scalability_{self.mode}_{timestamp}.csv"
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
    args = parser.parse_args()
    
    scales = [100, 500] if args.fast else [100, 1000, 5000]
    bench = ScalabilityBenchmark(mode=args.mode)
    bench.run_suite(scales=scales)
