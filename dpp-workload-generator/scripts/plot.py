import pandas as pd
import matplotlib.pyplot as plt
import sys
import os
from pathlib import Path

def load_data(csv_path):
    if not os.path.exists(csv_path):
        print(f"Error: File {csv_path} not found.")
        return None
    df = pd.read_csv(csv_path)
    # Filter out warmup runs
    # Some older versions might have True/False as strings or booleans depending on CSV writer
    if df['warmup'].dtype == object:
        df = df[df['warmup'].str.lower() == 'false']
    else:
        df = df[df['warmup'] == False]
    return df

def plot_latency(df, output_path, title, xlabel):
    stats = df.groupby('parameter_value')['latency_ms'].agg(['mean', 'std']).reset_index()
    
    plt.figure(figsize=(10, 6))
    plt.errorbar(stats['parameter_value'], stats['mean'], yerr=stats['std'].fillna(0), fmt='-o', capsize=5, markersize=8, linewidth=2)
    plt.title(title, fontsize=14)
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel('Latency (ms)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Latency plot saved to {output_path}")

def plot_storage(df, output_path, title, xlabel):
    # Sum payload and index bytes
    df['total_bytes'] = df['bytes_payload'] + df['bytes_index']
    stats = df.groupby('parameter_value')['total_bytes'].agg(['mean', 'std']).reset_index()
    
    plt.figure(figsize=(10, 6))
    plt.errorbar(stats['parameter_value'], stats['mean'], yerr=stats['std'].fillna(0), fmt='-s', color='green', capsize=5, markersize=8, linewidth=2)
    plt.title(title, fontsize=14)
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel('Storage Overhead (bytes)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Storage plot saved to {output_path}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python plot.py <csv_path> [output_dir]")
        return

    csv_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(output_dir, exist_ok=True)
    
    df = load_data(csv_path)
    if df is None or df.empty:
        print("No data to plot.")
        return

    kind = df['workload_kind'].iloc[0]
    filename_base = Path(csv_path).stem
    
    if 'depth' in kind:
        plot_latency(df, os.path.join(output_dir, f"{filename_base}_latency.png"), f"Resolution Latency vs Depth ({kind})", "Chain Depth")
    elif 'fanout' in kind:
        plot_latency(df, os.path.join(output_dir, f"{filename_base}_latency.png"), f"Resolution Latency vs Fan-out ({kind})", "Fan-out Count")
    else:
        plot_latency(df, os.path.join(output_dir, f"{filename_base}_latency.png"), f"Operation Latency ({kind})", "Parameter Value")

    if df['bytes_payload'].sum() > 0 or df['bytes_index'].sum() > 0:
        plot_storage(df, os.path.join(output_dir, f"{filename_base}_storage.png"), f"Storage Overhead ({kind})", "Parameter Value")

if __name__ == "__main__":
    main()
