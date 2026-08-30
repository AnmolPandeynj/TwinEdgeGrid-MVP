"""AuGrid LSTM model for edge-based load prediction.

Architecture matches the AuGrid paper specification:
- Lookback window: 2 timesteps (t-2, t-1)
- Input size: 1 (aggregated load value)
- Hidden size: 64
- Layers: 2
- Output: 1 (predicted load L̂(t+1))
- Time complexity: O(W) per iteration where W = hidden_size * num_layers

The model is intentionally lightweight to prove edge-deployability
on constrained hardware (the paper benchmarks on Raspberry Pi 3B+).
"""

from __future__ import annotations

import os
from functools import lru_cache

import torch
import torch.nn as nn


class AuGridLSTM(nn.Module):
    """LSTM recurrent network for hourly load prediction.

    Configured to process a lookback window of 2 timesteps,
    predicting the aggregated load for the next hour.
    """

    def __init__(
        self,
        input_size: int = 1,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, lookback=2, features=1).

        Returns:
            Predictions of shape (batch, 1).
        """
        # Initialize hidden and cell states with zeros
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size, device=x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size, device=x.device)

        # LSTM forward: out shape = (batch, lookback, hidden_size)
        out, _ = self.lstm(x, (h0, c0))

        # Use only the last timestep's output
        out = self.fc(out[:, -1, :])
        return out


_MODEL_PATH = os.path.join(os.path.dirname(__file__), "weights", "augrid_lstm.pt")


@lru_cache(maxsize=1)
def load_model() -> AuGridLSTM:
    """Load the AuGrid LSTM model, using pre-trained weights if available.

    Falls back to a randomly initialized model for MVP demonstration.
    The random model still proves the offloading pipeline end-to-end.
    """
    model = AuGridLSTM()

    if os.path.exists(_MODEL_PATH):
        state_dict = torch.load(_MODEL_PATH, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
    # else: use random weights — predictions will be noisy but pipeline works

    model.eval()
    return model
