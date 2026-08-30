/**
 * TypeScript interfaces mirroring backend Pydantic V2 models.
 * Kept in sync with backend/app/models/ schemas.
 */

// ── Enums ───────────────────────────────────────────────
export type TrafficType = 'video' | 'voip' | 'data';
export type ProsumerStatus = 'cooperative' | 'hoarding' | 'selling' | 'idle';

// ── Telemetry ───────────────────────────────────────────
export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  is_offloading: boolean;
  active_celery_tasks: number;
  node_type: 'edge' | 'cloud';
}

// ── FALCON SDN ──────────────────────────────────────────
export interface MeterSlice {
  name: string;
  allocated_bandwidth: number;
  current_usage: number;
  packet_drop_count: number;
}

export interface ReallocationEvent {
  timestamp: string;
  from_slice: string;
  to_slice: string;
  amount_mbps: number;
}

export interface BandwidthAllocation {
  global_limit: number;
  slices: MeterSlice[];
  recent_reallocations: ReallocationEvent[];
  total_drops: number;
}

// ── AuGrid ──────────────────────────────────────────────
export interface LoadPrediction {
  predicted_load: number;
  actual_load: number | null;
  execution_location: 'edge' | 'cloud';
  cpu_at_decision: number;
  latency_ms: number;
  timestamp: string;
}

export interface AuGridState {
  current_prediction: LoadPrediction | null;
  prediction_history: LoadPrediction[];
  running_rmse: number;
  total_predictions: number;
  edge_predictions: number;
  cloud_predictions: number;
}

// ── SmartPrice ──────────────────────────────────────────
export interface Prosumer {
  prosumer_id: string;
  cooperation_index: number;
  reward_factor: number;
  variable_price: number;
  stored_energy_kwh: number;
  status: ProsumerStatus;
  total_energy_sold: number;
  rounds_participated: number;
}

export interface PricingResult {
  base_price: number;
  deviation_metric: number;
  purchase_price: number | null;
  total_energy_supplied: number;
  total_energy_demanded: number;
  deficit: number;
  prosumers_served: number;
  cooperative_count: number;
  hoarding_count: number;
  timestamp: string;
}

export interface MarketState {
  prosumers: Prosumer[];
  current_pricing: PricingResult | null;
  avg_cooperative_price: number;
  avg_hoarding_price: number;
  price_reduction_pct: number;
  total_revenue: number;
  round_number: number;
}

// ── Dashboard (composite) ───────────────────────────────
export interface DashboardUpdate {
  timestamp: string;
  edge_metrics: SystemMetrics;
  cloud_metrics: SystemMetrics;
  falcon: BandwidthAllocation;
  augrid: AuGridState;
  smartprice: MarketState;
  pipeline_active: boolean;
}

export interface WSMessage {
  type: 'update' | 'error' | 'status';
  sequence: number;
  data: DashboardUpdate | string;
}
