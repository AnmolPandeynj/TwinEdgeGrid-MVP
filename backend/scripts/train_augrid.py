"""AuGrid LSTM Training Script.

Trains the AuGridLSTM model on UMass Smart* dataset for hourly load prediction.
Produces trained weights compatible with the TwinEdgeGrid inference pipeline.

Usage:
    # Train on the Apartment dataset (recommended):
    python backend/scripts/train_augrid.py --data backend/lstm/data/apartment.csv

    # Train on the Microgrid dataset (quick test):
    python backend/scripts/train_augrid.py --data backend/lstm/data/microgrid.csv

    # Custom parameters:
    python backend/scripts/train_augrid.py \\
        --data backend/lstm/data/apartment.csv \\
        --epochs 150 \\
        --batch-size 128 \\
        --lr 0.0005 \\
        --split 0.8

Architecture (from AuGrid paper):
    - Lookback: 2 timesteps
    - Input size: 1 (aggregated load kW)
    - Hidden size: 64
    - Layers: 2
    - Output: 1 (predicted load)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# Add backend to path so we can import the exact same model class
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from lstm.model import AuGridLSTM  # noqa: E402

# ── Constants ────────────────────────────────────────────
LOOKBACK = 2
WEIGHTS_DIR = BACKEND_DIR / "lstm" / "weights"
WEIGHTS_PATH = WEIGHTS_DIR / "augrid_lstm.pt"
SCALER_PATH = WEIGHTS_DIR / "scaler_params.json"


def load_and_preprocess(data_path: str) -> pd.DataFrame:
    """Load UMass Smart* data and resample to hourly aggregated community load in kW.

    Handles two input modes:
      1. A directory path (e.g., apartment-electrical/apartment/) containing
         year subfolders (2014/, 2015/, 2016/) each with per-apartment CSVs.
         All apartments are aggregated into a single community load signal,
         matching AuGrid's privacy-preserving edge aggregation methodology.
      2. A single CSV file path for simpler datasets (e.g., microgrid).

    The UMass apartment CSVs have no header row. Columns are:
        datetime_string, power_kw
    Recorded at 15-minute intervals, already in kW.
    """
    data_path = Path(data_path)
    print(f"Loading data from: {data_path}")

    if data_path.is_dir():
        return _load_apartment_directory(data_path)
    elif data_path.is_file() and data_path.suffix == ".csv":
        return _load_single_csv(data_path)
    else:
        raise FileNotFoundError(
            f"Path '{data_path}' is not a valid directory or CSV file."
        )


def _load_apartment_directory(dir_path: Path) -> pd.DataFrame:
    """Aggregate all apartment CSVs across all years into one community load series.

    AuGrid's core thesis: predict aggregated community load at the edge,
    never exposing individual consumer profiles. This function physically
    sums all apartment readings at each timestamp to create that signal.
    """
    all_frames: list[pd.DataFrame] = []
    csv_count = 0

    # Scan for year subdirectories (2014, 2015, 2016) or CSVs directly
    year_dirs = sorted([d for d in dir_path.iterdir() if d.is_dir()])
    search_dirs = year_dirs if year_dirs else [dir_path]

    for search_dir in search_dirs:
        csv_files = sorted(search_dir.glob("Apt*_*.csv"))
        if not csv_files:
            csv_files = sorted(search_dir.glob("*.csv"))

        for csv_file in csv_files:
            try:
                df = pd.read_csv(
                    csv_file,
                    header=None,
                    names=["datetime", "power_kw"],
                    parse_dates=["datetime"],
                )
                df.set_index("datetime", inplace=True)
                # Drop rows where power is NaN
                df.dropna(subset=["power_kw"], inplace=True)
                if len(df) > 0:
                    all_frames.append(df)
                    csv_count += 1
            except Exception as e:
                print(f"  Skipping {csv_file.name}: {e}")

    if not all_frames:
        raise ValueError(f"No valid CSV files found in {dir_path}")

    print(f"  Loaded {csv_count} apartment CSV files")

    # Concatenate all apartments and aggregate by summing at each timestamp
    # This creates the community-level aggregated load signal
    combined = pd.concat(all_frames)
    community_load = combined.groupby(combined.index)["power_kw"].sum()

    print(f"  Raw aggregated samples: {len(community_load)}")
    print(f"  Date range: {community_load.index.min()} to {community_load.index.max()}")

    # Resample from 15-minute intervals to hourly mean
    hourly = community_load.resample("1h").mean()
    hourly = hourly.dropna()

    result = pd.DataFrame({"load_kw": hourly.values}, index=hourly.index)

    print(f"  Hourly samples: {len(result)}")
    print(f"  Load range: {result['load_kw'].min():.4f} to {result['load_kw'].max():.4f} kW")

    return result


def _load_single_csv(csv_path: Path) -> pd.DataFrame:
    """Load a single CSV file (e.g., microgrid dataset)."""
    print(f"  Loading single CSV: {csv_path.name}")
    df = pd.read_csv(csv_path)
    print(f"  Raw shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")

    # ── Detect and parse the timestamp column ────────────
    ts_col = None
    for candidate in ["timestamp", "time", "datetime", "date", "Timestamp", "Time"]:
        if candidate in df.columns:
            ts_col = candidate
            break

    if ts_col is None:
        # Check for headerless format (2 columns)
        if len(df.columns) == 2:
            df.columns = ["datetime", "power_kw"]
            ts_col = "datetime"
        else:
            ts_col = df.columns[0]
            print(f"  Warning: No known timestamp column found. Using '{ts_col}'.")

    # Try Unix epoch first, then datetime string
    sample_val = df[ts_col].iloc[0]
    if isinstance(sample_val, (int, float, np.integer, np.floating)):
        df["dt"] = pd.to_datetime(df[ts_col], unit="s", utc=True)
    else:
        df["dt"] = pd.to_datetime(df[ts_col], utc=True)
    df.set_index("dt", inplace=True)

    # ── Detect and extract the power column ──────────────
    power_col = None
    for candidate in ["power_kw", "power", "use", "usage", "load", "watts", "kw",
                       "Power", "Use", "Usage", "Load", "Watts", "kW",
                       "use [kW]", "gen [kW]", "Grid [kW]"]:
        if candidate in df.columns:
            power_col = candidate
            break

    if power_col is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            power_col = numeric_cols[0]
            print(f"  Warning: No known power column found. Using '{power_col}'.")
        else:
            raise ValueError("No numeric columns found in the CSV.")

    print(f"  Using timestamp column: '{ts_col}'")
    print(f"  Using power column: '{power_col}'")

    power_series = pd.to_numeric(df[power_col], errors="coerce")

    # Convert to kW if values seem to be in Watts
    median_val = power_series.median()
    if median_val > 100:
        print(f"  Median value ({median_val:.1f}) suggests Watts. Converting to kW.")
        power_series = power_series / 1000.0
    else:
        print(f"  Median value ({median_val:.4f}) suggests already in kW.")

    # Resample to hourly mean
    hourly = power_series.resample("1h").mean()
    hourly = hourly.dropna()

    result = pd.DataFrame({"load_kw": hourly.values}, index=hourly.index)

    print(f"  Hourly samples: {len(result)}")
    print(f"  Load range: {result['load_kw'].min():.4f} to {result['load_kw'].max():.4f} kW")

    return result


def normalize(data: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Min-Max normalize data to [0, 1]. Returns (scaled_data, data_min, data_max)."""
    data_min = float(data.min())
    data_max = float(data.max())

    if data_max - data_min < 1e-8:
        raise ValueError(
            f"Data has near-zero range (min={data_min}, max={data_max}). "
            "Check that the power column contains valid readings."
        )

    scaled = (data - data_min) / (data_max - data_min)
    return scaled, data_min, data_max


def create_sequences(data: np.ndarray, lookback: int = LOOKBACK) -> tuple[np.ndarray, np.ndarray]:
    """Create lookback-2 input/target pairs from the time-series.

    For each timestep t >= lookback:
        X[i] = [data[t-2], data[t-1]]   (shape: (lookback,))
        y[i] = data[t]                   (shape: scalar)
    """
    X, y = [], []
    for i in range(lookback, len(data)):
        X.append(data[i - lookback:i, 0])
        y.append(data[i, 0])
    return np.array(X), np.array(y)


def train(
    X_train: torch.Tensor,
    y_train: torch.Tensor,
    model: AuGridLSTM,
    epochs: int,
    batch_size: int,
    lr: float,
) -> list[float]:
    """Train the LSTM model. Returns list of epoch losses."""
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    dataset = TensorDataset(X_train, y_train)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    model.train()
    loss_history = []

    print(f"\n{'='*60}")
    print(f"  Training AuGrid LSTM")
    print(f"  Epochs: {epochs} | Batch Size: {batch_size} | LR: {lr}")
    print(f"  Samples: {len(X_train)} | Batches/epoch: {len(loader)}")
    print(f"{'='*60}\n")

    start_time = time.time()

    for epoch in range(epochs):
        epoch_loss = 0.0
        for batch_X, batch_y in loader:
            optimizer.zero_grad()
            predictions = model(batch_X)
            loss = criterion(predictions, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        avg_loss = epoch_loss / len(loader)
        loss_history.append(avg_loss)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            elapsed = time.time() - start_time
            print(
                f"  Epoch [{epoch+1:>4d}/{epochs}]  "
                f"Loss: {avg_loss:.6f}  "
                f"Elapsed: {elapsed:.1f}s"
            )

    total_time = time.time() - start_time
    print(f"\n  Training complete in {total_time:.1f}s")
    print(f"  Final loss: {loss_history[-1]:.6f}")

    return loss_history


def evaluate(
    model: AuGridLSTM,
    X_test: torch.Tensor,
    y_test: torch.Tensor,
    data_min: float,
    data_max: float,
) -> float:
    """Evaluate model on test set. Returns RMSE in original kW scale."""
    model.eval()

    with torch.no_grad():
        predictions = model(X_test)

    # Inverse transform: scaled_val * (max - min) + min
    scale_range = data_max - data_min
    pred_kw = predictions.numpy() * scale_range + data_min
    actual_kw = y_test.numpy() * scale_range + data_min

    mse = np.mean((pred_kw - actual_kw) ** 2)
    rmse = math.sqrt(mse)
    mae = np.mean(np.abs(pred_kw - actual_kw))

    print(f"\n{'='*60}")
    print(f"  Evaluation Results")
    print(f"{'='*60}")
    print(f"  RMSE: {rmse:.4f} kW")
    print(f"  MAE:  {mae:.4f} kW")
    print(f"  MSE:  {mse:.6f}")
    print(f"{'='*60}\n")

    return rmse


def save_weights(model: AuGridLSTM, data_min: float, data_max: float) -> None:
    """Save trained weights and scaler parameters."""
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    # Save model state dict
    torch.save(model.state_dict(), WEIGHTS_PATH)
    size_kb = WEIGHTS_PATH.stat().st_size / 1024
    print(f"  Weights saved: {WEIGHTS_PATH} ({size_kb:.1f} KB)")

    # Save scaler parameters for inference normalization
    scaler_params = {
        "data_min": data_min,
        "data_max": data_max,
        "feature": "load_kw",
        "method": "min-max",
        "range": [0.0, 1.0],
    }
    with open(SCALER_PATH, "w") as f:
        json.dump(scaler_params, f, indent=2)
    print(f"  Scaler saved: {SCALER_PATH}")
    print(f"    min={data_min:.4f}, max={data_max:.4f}")


def save_validation_plot(
    model: AuGridLSTM,
    X_test: torch.Tensor,
    y_test: torch.Tensor,
    data_min: float,
    data_max: float,
    loss_history: list[float],
) -> None:
    """Generate and save a validation plot (predicted vs actual)."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend for headless environments
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not installed. Skipping validation plot.")
        return

    model.eval()
    with torch.no_grad():
        predictions = model(X_test)

    scale_range = data_max - data_min
    pred_kw = predictions.numpy().flatten() * scale_range + data_min
    actual_kw = y_test.numpy().flatten() * scale_range + data_min

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))

    # Plot 1: Predicted vs Actual (first 200 hours)
    n_show = min(200, len(pred_kw))
    axes[0].plot(actual_kw[:n_show], label="Actual Load", color="#00ff88", linewidth=1.5)
    axes[0].plot(pred_kw[:n_show], label="Predicted Load", color="#ff6b6b", linewidth=1.5, linestyle="--")
    axes[0].set_title("AuGrid LSTM - Predicted vs Actual (Test Set)")
    axes[0].set_xlabel("Hour")
    axes[0].set_ylabel("Load (kW)")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    # Plot 2: Training loss curve
    axes[1].plot(loss_history, color="#6bb5ff", linewidth=1.5)
    axes[1].set_title("Training Loss Curve")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("MSE Loss")
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plot_path = BACKEND_DIR / "lstm" / "validation_plot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Validation plot saved: {plot_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the AuGrid LSTM model on UMass Smart* data."
    )
    parser.add_argument(
        "--data", type=str, required=True,
        help="Path to the apartment directory (e.g., .../apartment-electrical/apartment/) "
             "or a single CSV file."
    )
    parser.add_argument(
        "--epochs", type=int, default=100,
        help="Number of training epochs (default: 100)."
    )
    parser.add_argument(
        "--batch-size", type=int, default=64,
        help="Training batch size (default: 64)."
    )
    parser.add_argument(
        "--lr", type=float, default=0.001,
        help="Learning rate for Adam optimizer (default: 0.001)."
    )
    parser.add_argument(
        "--split", type=float, default=0.8,
        help="Train/test split ratio (default: 0.8)."
    )
    parser.add_argument(
        "--no-plot", action="store_true",
        help="Skip generating the validation plot."
    )
    args = parser.parse_args()

    # ── Step 1: Load and preprocess ──────────────────────
    print("\n[1/5] Loading and preprocessing data...")
    hourly_df = load_and_preprocess(args.data)

    if len(hourly_df) < 100:
        print(f"  WARNING: Only {len(hourly_df)} hourly samples. "
              "Results may be unreliable. Consider using a larger dataset.")

    # ── Step 2: Normalize and create sequences ───────────
    print("\n[2/5] Normalizing and creating lookback-2 sequences...")
    raw_values = hourly_df[["load_kw"]].values
    scaled_data, data_min, data_max = normalize(raw_values)
    print(f"  Scaler: min={data_min:.4f}, max={data_max:.4f}")

    X, y = create_sequences(scaled_data, LOOKBACK)
    print(f"  Total sequences: {len(X)}")

    # Chronological train/test split
    split_idx = int(len(X) * args.split)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    print(f"  Train: {len(X_train)} | Test: {len(X_test)}")

    # Convert to PyTorch tensors: (N, 2) -> (N, 2, 1)
    X_train_t = torch.tensor(X_train, dtype=torch.float32).unsqueeze(-1)
    y_train_t = torch.tensor(y_train, dtype=torch.float32).unsqueeze(-1)
    X_test_t = torch.tensor(X_test, dtype=torch.float32).unsqueeze(-1)
    y_test_t = torch.tensor(y_test, dtype=torch.float32).unsqueeze(-1)

    print(f"  X_train shape: {X_train_t.shape}")  # (N, 2, 1)
    print(f"  y_train shape: {y_train_t.shape}")  # (N, 1)

    # ── Step 3: Train ────────────────────────────────────
    print("\n[3/5] Training...")
    model = AuGridLSTM(input_size=1, hidden_size=64, num_layers=2, dropout=0.1)
    loss_history = train(X_train_t, y_train_t, model, args.epochs, args.batch_size, args.lr)

    # ── Step 4: Evaluate ─────────────────────────────────
    print("\n[4/5] Evaluating on test set...")
    rmse = evaluate(model, X_test_t, y_test_t, data_min, data_max)

    # ── Step 5: Save ─────────────────────────────────────
    print("\n[5/5] Saving trained model...")
    save_weights(model, data_min, data_max)

    if not args.no_plot:
        save_validation_plot(model, X_test_t, y_test_t, data_min, data_max, loss_history)

    print(f"\n{'='*60}")
    print(f"  DONE! Model ready for deployment.")
    print(f"  RMSE: {rmse:.4f} kW")
    print(f"  Weights: {WEIGHTS_PATH}")
    print(f"  Scaler:  {SCALER_PATH}")
    print(f"{'='*60}")
    print(f"\n  Next steps:")
    print(f"    1. Rebuild containers: docker compose build edge_node cloud_server")
    print(f"    2. Restart services:  docker compose up -d edge_node cloud_server")
    print(f"    3. Run traffic gen:   python backend/scripts/traffic_generator.py --rate 100 --duration 300")
    print(f"    4. Open dashboard:    http://localhost:5173\n")


if __name__ == "__main__":
    main()
