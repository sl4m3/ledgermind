import os
import psutil
import time
from typing import List
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
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

    def generate_comparison_plots(self, all_csv_files: List[str]):
        """Generate comparison plots from multiple benchmark runs."""
        import glob
        
        all_data = []
        for csv_file in all_csv_files:
            try:
                df = pd.read_csv(csv_file)
                if 'dataset' not in df.columns:
                    # Try to infer dataset from filename
                    import re
                    match = re.search(r'scalability_(\w+)_(\w+)_', csv_file)
                    if match:
                        df['dataset'] = match.group(2)
                    else:
                        df['dataset'] = 'unknown'
                all_data.append(df)
            except Exception as e:
                print(f"Warning: Could not read {csv_file}: {e}")
        
        if not all_data:
            return
        
        combined_df = pd.concat(all_data, ignore_index=True)
        
        if combined_df.empty:
            return
        
        # Grouped bar chart for latency comparison
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        
        # 1. Latency comparison
        if 'mode' in combined_df.columns and 'p95_ms' in combined_df.columns:
            modes = combined_df['mode'].unique()
            datasets = combined_df['dataset'].unique()
            
            x = np.arange(len(datasets))
            width = 0.25
            
            for i, mode in enumerate(modes):
                mode_data = combined_df[combined_df['mode'] == mode]
                latencies = []
                for dataset in datasets:
                    subset = mode_data[mode_data['dataset'] == dataset]
                    write_data = subset[subset['operation'] == 'write']
                    if not write_data.empty:
                        latencies.append(write_data['p95_ms'].mean())
                    else:
                        latencies.append(0)
                
                axes[0].bar(x + i * width, latencies, width, label=mode)
            
            axes[0].set_xlabel('Dataset')
            axes[0].set_ylabel('Latency p95 (ms)')
            axes[0].set_title('Write Latency Comparison by Mode')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(datasets, rotation=45, ha='right')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)
        
        # 2. Recall comparison
        if 'accuracy_recall_5' in combined_df.columns:
            recall_data = combined_df[combined_df['accuracy_recall_5'] > 0]
            if not recall_data.empty and 'mode' in recall_data.columns:
                fig2, ax2 = plt.subplots(figsize=(10, 6))
                
                modes = recall_data['mode'].unique()
                datasets = recall_data['dataset'].unique() if 'dataset' in recall_data.columns else ['unknown']
                
                x = np.arange(len(modes))
                width = 0.8 / len(datasets)
                
                for i, dataset in enumerate(datasets):
                    ds_data = recall_data[recall_data['dataset'] == dataset] if 'dataset' in recall_data.columns else recall_data
                    recalls = [ds_data[ds_data['mode'] == mode]['accuracy_recall_5'].mean() 
                              for mode in modes]
                    
                    ax2.bar(x + i * width, recalls, width, label=dataset, alpha=0.8)
                
                ax2.set_xlabel('Mode')
                ax2.set_ylabel('Recall@5')
                ax2.set_title('Recall@5 Comparison by Mode')
                ax2.set_xticks(x + width * (len(datasets) - 1) / 2)
                ax2.set_xticklabels(modes, rotation=45, ha='right')
                ax2.legend()
                ax2.set_ylim(0, 1.0)
                ax2.grid(True, alpha=0.3, axis='y')
                
                plt.tight_layout()
                plt.savefig(self.output_dir / 'comparison_recall.png', dpi=150)
                plt.close()
                print(f"Comparison recall plot saved to {self.output_dir / 'comparison_recall.png'}")
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'comparison_latency.png', dpi=150)
        plt.close()
        print(f"Comparison latency plot saved to {self.output_dir / 'comparison_latency.png'}")
