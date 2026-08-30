/**
 * Derived telemetry state from WebSocket stream.
 *
 * Maintains rolling history for charts and computes derived values
 * during render (not in effects) per rerender-derived-state-no-effect.
 */

import { useMemo, useRef, useCallback } from 'react';
import type { DashboardUpdate, SystemMetrics, LoadPrediction } from '../types/telemetry';

const MAX_HISTORY = 60; // ~30 seconds at 2 Hz

export interface ChartDataPoint {
  time: number;
  edgeCpu: number;
  cloudCpu: number;
  isOffloading: boolean;
}

export interface FalconChartPoint {
  time: number;
  video: number;
  voip: number;
  data: number;
}

export interface SmartPriceChartPoint {
  time: number;
  basePrice: number;
  coopPrice: number;
  hoardPrice: number;
}

export function useTelemetry(data: DashboardUpdate | null) {
  const cpuHistoryRef = useRef<ChartDataPoint[]>([]);
  const falconHistoryRef = useRef<FalconChartPoint[]>([]);
  const priceHistoryRef = useRef<SmartPriceChartPoint[]>([]);
  const tickRef = useRef(0);
  const lastDataRef = useRef<DashboardUpdate | null>(null);

  // Append new data to rolling histories ONLY if it's a new message
  if (data && data !== lastDataRef.current) {
    lastDataRef.current = data;
    tickRef.current += 1;

    const cpuPoint: ChartDataPoint = {
      time: tickRef.current,
      edgeCpu: data.edge_metrics.cpu_percent,
      cloudCpu: data.cloud_metrics.cpu_percent,
      isOffloading: data.edge_metrics.is_offloading,
    };
    cpuHistoryRef.current = [
      ...cpuHistoryRef.current.slice(-(MAX_HISTORY - 1)),
      cpuPoint,
    ];

    if (data.falcon.slices.length >= 3) {
      const falconPoint: FalconChartPoint = {
        time: tickRef.current,
        video: data.falcon.slices[0]?.allocated_bandwidth ?? 0,
        voip: data.falcon.slices[1]?.allocated_bandwidth ?? 0,
        data: data.falcon.slices[2]?.allocated_bandwidth ?? 0,
      };
      falconHistoryRef.current = [
        ...falconHistoryRef.current.slice(-(MAX_HISTORY - 1)),
        falconPoint,
      ];
    }

    if (data.smartprice) {
      const pricePoint: SmartPriceChartPoint = {
        time: tickRef.current,
        basePrice: data.smartprice.current_pricing?.base_price ?? 0,
        coopPrice: data.smartprice.avg_cooperative_price ?? 0,
        hoardPrice: data.smartprice.avg_hoarding_price ?? 0,
      };
      priceHistoryRef.current = [
        ...priceHistoryRef.current.slice(-(MAX_HISTORY - 1)),
        pricePoint,
      ];
    }
  }

  // Derived values computed during render (not in useEffect)
  const isOffloading = data?.edge_metrics.is_offloading ?? false;
  const edgeCpuCritical = (data?.edge_metrics.cpu_percent ?? 0) >= 80;

  const predictionHistory = data?.augrid.prediction_history ?? [];
  const chartPredictions = useMemo(() => {
    return predictionHistory.map((p: LoadPrediction, i: number) => ({
      time: i,
      predicted: p.predicted_load,
      actual: p.actual_load ?? 0,
      location: p.execution_location,
    }));
  }, [predictionHistory]);

  return {
    cpuHistory: cpuHistoryRef.current,
    falconHistory: falconHistoryRef.current,
    priceHistory: priceHistoryRef.current,
    chartPredictions,
    isOffloading,
    edgeCpuCritical,
  };
}
