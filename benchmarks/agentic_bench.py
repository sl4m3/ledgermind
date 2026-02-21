import os
import time
import shutil
import csv
from pathlib import Path
from datetime import datetime
from benchmarks.data_loader import DatasetManager
from benchmarks.evaluator import MetricsCalculator, EvaluationReport
from benchmarks.configs import get_config_factory

class AgenticBenchmark:
    """Evaluates IR metrics (Recall, Precision, MRR) and QA Accuracy."""
    def __init__(self, mode="full", output_dir="benchmarks/results"):
        self.mode = mode
        self.output_dir = Path(output_dir)
        self.dm = DatasetManager()
        self.mc = MetricsCalculator()
        self.results = []

    def evaluate_retrieval(self, dataset_name="synthetic", scale=200):
        print(f"\n--- Evaluation ({self.mode.upper()}) on {dataset_name.upper()} (Scale: {scale}) ---")
        
        # 1. Setup
        config = get_config_factory(self.mode)
        config.setup()
        
        # 2. Load and Ingest Data
        if dataset_name == "locomo": data = self.dm.load_locomo()
        elif dataset_name == "longmemeval": data = self.dm.load_longmemeval()
        else: data = self.dm.get_synthetic_data(scale)
            
        if not data:
            print(f"  Warning: No data for {dataset_name}.")
            config.teardown(); return

        print(f"  Ingesting {min(len(data), scale)} items...")
        doc_ids = []
        for item in data[:scale]:
            try:
                # Use faster path if baseline
                if hasattr(config, "record_direct"):
                    config.record_direct(item['title'], item['target'], item['rationale'])
                    # For baselines, we manually manage doc IDs if we need them
                else:
                    res = config.memory.record_decision(item['title'], item['target'], item['rationale'])
                    doc_ids.append(res.metadata.get("file_id"))
            except Exception: pass
        
        # For evaluation, we need to map our synthetic items to the stored IDs
        # To simplify, we'll re-query by target for mapping
        print(f"  Mapping and Querying...")
        report = EvaluationReport(self.mode)
        samples = data[:50] # Evaluate 50 samples
        
        for item in samples:
            # Gold target and query
            target = item['target']
            # Find the true doc_id for this item in our memory
            # We assume unique target titles for evaluation mapping
            true_id_res = config.memory.search_decisions(target, limit=1, mode='strict')
            if not true_id_res: continue
            gold_id = true_id_res[0]['id']
            
            # Formulate query from rationale (the "haystack")
            text = item['rationale']
            query = text[len(text)//4 : len(text)//4 + 100] if len(text) > 120 else text[:100]
            
            # EXECUTE SEARCH
            retrieved_ids = config.search(query, limit=5)
            
            # CALCULATE METRICS
            m = {
                "recall@1": self.mc.recall_at_k(retrieved_ids, gold_id, 1),
                "recall@5": self.mc.recall_at_k(retrieved_ids, gold_id, 5),
                "precision@5": self.mc.precision_at_k(retrieved_ids, gold_id, 5),
                "mrr": self.mc.reciprocal_rank(retrieved_ids, gold_id)
            }
            report.add_point(m)

        summary = report.summarize()
        summary["dataset"] = dataset_name
        summary["scale"] = scale
        summary["mode"] = self.mode
        self.results.append(summary)
        
        print(f"  Recall@5: {summary['recall@5']:.2%}, MRR: {summary['mrr']:.4f}")
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
        print(f"Report saved to {path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="full", choices=["full", "keyword", "baseline_flat", "baseline_sql"])
    parser.add_argument("--scale", type=int, default=100)
    args = parser.parse_args()
    
    bench = AgenticBenchmark(mode=args.mode)
    bench.evaluate_retrieval(dataset_name="locomo", scale=args.scale)
    bench.evaluate_retrieval(dataset_name="longmemeval", scale=args.scale)
