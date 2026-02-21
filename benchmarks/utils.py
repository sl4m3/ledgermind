import os
import psutil
import time
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

class ResourceTracker:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.start_memory = 0
        self.start_time = 0

    def start(self):
        self.start_memory = self.process.memory_info().rss / (1024 * 1024) # MB
        self.start_time = time.perf_counter()

    def stop(self):
        end_memory = self.process.memory_info().rss / (1024 * 1024)
        end_time = time.perf_counter()
        return {
            "ram_usage_mb": end_memory - self.start_memory,
            "duration_sec": end_time - self.start_time,
            "current_ram_mb": end_memory
        }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Simple heuristic: 1 token ~= 4 chars for English, or use tiktoken if needed
        # Since tiktoken might not be available or slow to load, we use a heuristic
        return len(text) // 4

class ResultVisualizer:
    def __init__(self, output_dir="benchmarks/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_plots(self, csv_path: str):
        df = pd.read_csv(csv_path)
        if df.empty:
            return

        # 1. Latency vs Scale
        plt.figure(figsize=(10, 6))
        for op in df['operation'].unique():
            subset = df[df['operation'] == op]
            plt.plot(subset['scale'], subset['p95_ms'], marker='o', label=f'{op} p95')
        
        plt.title('Latency (p95) vs Scale')
        plt.xlabel('Number of records')
        plt.ylabel('Latency (ms)')
        plt.xscale('log')
        plt.legend()
        plt.grid(True)
        plt.savefig(self.output_dir / 'latency_scaling.png')
        plt.close()

        # 2. Throughput vs Scale
        plt.figure(figsize=(10, 6))
        for op in df['operation'].unique():
            subset = df[df['operation'] == op]
            plt.plot(subset['scale'], subset['throughput_ops_sec'], marker='s', label=f'{op}')
        
        plt.title('Throughput vs Scale')
        plt.xlabel('Number of records')
        plt.ylabel('Ops/sec')
        plt.xscale('log')
        plt.legend()
        plt.grid(True)
        plt.savefig(self.output_dir / 'throughput_scaling.png')
        plt.close()
        
        print(f"Plots generated in {self.output_dir}")
