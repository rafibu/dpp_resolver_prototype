import pytest
import pandas as pd
import os
import sys
from pathlib import Path
from workload.measurement import MeasurementRecorder

# Add scripts directory to sys.path to import plot.py
scripts_dir = str(Path(__file__).parent.parent / "scripts")
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)

import plot

@pytest.fixture
def temp_output(tmp_path):
    return tmp_path

def test_csv_structure_and_values(temp_output):
    recorder = MeasurementRecorder(output_dir=str(temp_output))
    recorder.start_run("test-run", "depth")
    
    # Record success
    recorder.record("resolve", 1, 10.5, bytes_payload=100, bytes_index=10, success=True, warmup=False)
    # Record warmup
    recorder.record("resolve", 1, 5.0, success=True, warmup=True)
    # Record failure
    recorder.record("resolve", 2, 0.0, success=False, error="Connection refused", warmup=False)
    
    csv_path = recorder.end_run()
    
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    
    # Check columns
    expected_cols = ["run_id", "workload_kind", "parameter_value", "operation", 
                     "latency_ms", "bytes_payload", "bytes_index", "success", "error", "warmup"]
    assert all(col in df.columns for col in expected_cols)
    
    # Check row count
    assert len(df) == 3
    
    # Check values
    assert df.loc[0, 'latency_ms'] == 10.5
    assert df.loc[0, 'success'] == True
    assert df.loc[1, 'warmup'] == True
    assert df.loc[2, 'success'] == False
    assert df.loc[2, 'error'] == "Connection refused"
    
    # Latency non-negative
    assert (df['latency_ms'] >= 0).all()

def test_plot_loading_and_filtering(temp_output):
    csv_path = temp_output / "test.csv"
    df_raw = pd.DataFrame({
        "run_id": ["r1", "r1"],
        "workload_kind": ["depth", "depth"],
        "parameter_value": [1, 1],
        "operation": ["op", "op"],
        "latency_ms": [10, 5],
        "bytes_payload": [100, 100],
        "bytes_index": [10, 10],
        "success": [True, True],
        "error": [None, None],
        "warmup": [False, True]
    })
    df_raw.to_csv(csv_path, index=False)
    
    df_loaded = plot.load_data(str(csv_path))
    assert len(df_loaded) == 1
    assert df_loaded.iloc[0]['warmup'] == False

def test_plot_generation(temp_output, monkeypatch):
    # Mock plt.show/savefig to avoid GUI issues
    import matplotlib.pyplot as plt
    monkeypatch.setattr(plt, 'savefig', lambda *args, **kwargs: None)
    
    csv_path = temp_output / "depth-test.csv"
    df = pd.DataFrame({
        "run_id": ["r1"] * 5,
        "workload_kind": ["depth"] * 5,
        "parameter_value": [1, 1, 2, 2, 3],
        "operation": ["resolve"] * 5,
        "latency_ms": [10, 12, 20, 22, 30],
        "bytes_payload": [100] * 5,
        "bytes_index": [10] * 5,
        "success": [True] * 5,
        "error": [None] * 5,
        "warmup": [False] * 5
    })
    df.to_csv(csv_path, index=False)
    
    # Test plot_latency directly
    plot.plot_latency(df, str(temp_output / "lat.png"), "Title", "X")
    # Test plot_storage directly
    plot.plot_storage(df, str(temp_output / "store.png"), "Title", "X")

def test_plot_missing_columns(temp_output):
    csv_path = temp_output / "bad.csv"
    df = pd.DataFrame({"wrong": [1, 2]})
    df.to_csv(csv_path, index=False)
    
    with pytest.raises(KeyError):
        plot.load_data(str(csv_path))

def test_plot_empty_csv(temp_output):
    csv_path = temp_output / "empty.csv"
    df = pd.DataFrame(columns=["warmup"])
    df.to_csv(csv_path, index=False)
    
    df_loaded = plot.load_data(str(csv_path))
    assert df_loaded.empty
