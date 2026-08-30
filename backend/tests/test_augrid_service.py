"""Tests for AuGrid LSTM service."""

from __future__ import annotations

import pytest

from app.models.augrid import LSTMInput, LoadPrediction, AuGridState


class TestLSTMInputValidation:
    """Test LSTM input schema enforcement."""

    def test_valid_lookback_2(self):
        inp = LSTMInput(historical_loads=[100.0, 120.0])
        assert len(inp.historical_loads) == 2

    def test_rejects_lookback_1(self):
        with pytest.raises(Exception):
            LSTMInput(historical_loads=[100.0])

    def test_rejects_lookback_3(self):
        with pytest.raises(Exception):
            LSTMInput(historical_loads=[100.0, 120.0, 130.0])


class TestLoadPrediction:
    """Test LoadPrediction deviation metric."""

    def test_deviation_calculation(self):
        p = LoadPrediction(
            predicted_load=110.0,
            actual_load=100.0,
            execution_location="edge",
            cpu_at_decision=50.0,
        )
        assert p.deviation is not None
        assert abs(p.deviation - 0.1) < 1e-6

    def test_deviation_none_without_actual(self):
        p = LoadPrediction(
            predicted_load=110.0,
            actual_load=None,
            execution_location="cloud",
            cpu_at_decision=90.0,
        )
        assert p.deviation is None

    def test_deviation_none_zero_actual(self):
        p = LoadPrediction(
            predicted_load=110.0,
            actual_load=0.0,
            execution_location="edge",
            cpu_at_decision=50.0,
        )
        assert p.deviation is None


class TestAuGridLSTMModel:
    """Test the PyTorch LSTM model shape and output."""

    def test_model_output_shape(self):
        import torch
        from lstm.model import AuGridLSTM

        model = AuGridLSTM()
        model.eval()

        # Input: (batch=1, lookback=2, features=1)
        x = torch.randn(1, 2, 1)
        with torch.no_grad():
            out = model(x)

        assert out.shape == (1, 1), f"Expected (1, 1), got {out.shape}"

    def test_model_batch_processing(self):
        import torch
        from lstm.model import AuGridLSTM

        model = AuGridLSTM()
        model.eval()

        # Batch of 8
        x = torch.randn(8, 2, 1)
        with torch.no_grad():
            out = model(x)

        assert out.shape == (8, 1), f"Expected (8, 1), got {out.shape}"

    def test_load_model_caches(self):
        from lstm.model import load_model

        m1 = load_model()
        m2 = load_model()
        assert m1 is m2, "load_model should return cached instance"
