import React, { memo, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { DashboardUpdate, Prosumer } from '../../types/telemetry';
import type { SmartPriceChartPoint } from '../../hooks/useTelemetry';

interface SmartPricePanelProps {
  data: DashboardUpdate | null;
  priceHistory: SmartPriceChartPoint[];
}

const STATUS_COLORS: Record<string, string> = {
  cooperative: 'var(--accent-edge)',
  selling: 'var(--accent-edge)',
  hoarding: 'var(--accent-warning)',
  idle: 'var(--text-muted)',
};

const SmartPricePanel = memo(function SmartPricePanel({ data, priceHistory }: SmartPricePanelProps) {
  const market = data?.smartprice;
  const pricing = market?.current_pricing;

  return (
    <div className="panel">
      <div className="panel__header">
        <span className="panel__title">SmartPrice Market</span>
        <span className="label" style={{ color: 'var(--text-secondary)' }}>
          Round {market?.round_number ?? 0}
        </span>
      </div>

      <div className="panel__body">
        <div className="panel__kpis">
          <div className="kpi-card">
            <span className="kpi-card__value kpi-card__value--edge data-value">
              {market?.price_reduction_pct?.toFixed(1) ?? '—'}%
            </span>
            <span className="kpi-card__label">Price Reduction</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value data-value">
              ${pricing?.base_price?.toFixed(4) ?? '—'}
            </span>
            <span className="kpi-card__label">Base Price</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value kpi-card__value--edge data-value">
              {pricing?.cooperative_count ?? 0}
            </span>
            <span className="kpi-card__label">Cooperating</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value kpi-card__value--warning data-value">
              {pricing?.hoarding_count ?? 0}
            </span>
            <span className="kpi-card__label">Hoarding</span>
          </div>
        </div>

        {pricing?.deficit != null && pricing.deficit > 0 && (
          <div
            className="offload-banner"
            style={{
              borderLeftColor: 'var(--accent-danger)',
              color: 'var(--accent-danger)',
              background: 'var(--accent-danger-dim)',
              marginBottom: 'var(--space-3)',
            }}
          >
            ENERGY DEFICIT: {pricing.deficit.toFixed(1)} kWh — Purchase price: ${pricing.purchase_price?.toFixed(4) ?? '—'}
          </div>
        )}

        <div className="chart-container" style={{ minHeight: '140px', flex: 1, marginBottom: 'var(--space-4)' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={priceHistory} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={false} />
              <YAxis width={45} tickFormatter={(v) => `$${v.toFixed(2)}`} />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-md)',
                  fontFamily: 'var(--font-data)',
                  fontSize: '12px',
                }}
                itemStyle={{ color: 'var(--text-primary)' }}
                labelStyle={{ color: 'var(--text-primary)', fontWeight: 'bold', marginBottom: '4px' }}
                labelFormatter={() => ''}
                formatter={(val: number) => `$${val.toFixed(4)}`}
              />
              <Line
                type="monotone"
                dataKey="basePrice"
                stroke="var(--text-secondary)"
                strokeWidth={2}
                dot={false}
                name="Base Price"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="hoardPrice"
                stroke="var(--accent-warning)"
                strokeWidth={2}
                dot={false}
                name="Avg Hoard"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="coopPrice"
                stroke="var(--accent-edge)"
                strokeWidth={2}
                dot={false}
                name="Avg Coop"
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>



        <div style={{ display: 'flex', gap: 'var(--space-4)', marginTop: 'var(--space-3)' }}>
          <span className="label">
            Avg Coop: <span className="data-value" style={{ color: 'var(--accent-edge)' }}>
              ${market?.avg_cooperative_price?.toFixed(4) ?? '—'}
            </span>
          </span>
          <span className="label">
            Avg Hoard: <span className="data-value" style={{ color: 'var(--accent-warning)' }}>
              ${market?.avg_hoarding_price?.toFixed(4) ?? '—'}
            </span>
          </span>
          <span className="label">
            Revenue: <span className="data-value">
              ${market?.total_revenue?.toFixed(2) ?? '—'}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
});

export default SmartPricePanel;
