import React, { memo, useMemo } from 'react';
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ComposedChart,
} from 'recharts';
import type { DashboardUpdate } from '../../types/telemetry';

interface AuGridPanelProps {
  data: DashboardUpdate | null;
}

const AuGridPanel = memo(function AuGridPanel({ data }: AuGridPanelProps) {
  const augrid = data?.augrid;
  const history = augrid?.prediction_history ?? [];
  const current = augrid?.current_prediction;

  const chartData = useMemo(() => {
    return history.map((p, i) => ({
      time: i,
      predicted: Number(p.predicted_load.toFixed(2)),
      actual: p.actual_load != null ? Number(p.actual_load.toFixed(2)) : null,
      location: p.execution_location,
    }));
  }, [history]);

  // Derive deviation from current prediction (during render, not in effect)
  const deviation = current?.actual_load != null && current.actual_load > 0
    ? Math.abs(current.predicted_load - current.actual_load) / current.actual_load
    : null;

  return (
    <div className="panel">
      <div className="panel__header">
        <span className="panel__title">AuGrid Forecasting</span>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {current && (
            <span className={`badge badge--${current.execution_location === 'edge' ? 'edge' : 'cloud'}`}>
              {current.execution_location.toUpperCase()}
            </span>
          )}
          {deviation != null && (
            <span className={`badge ${deviation > 0.2 ? 'badge--warning' : 'badge--edge'}`}>
              Δ {(deviation * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </div>

      <div className="panel__body">
        <div className="panel__kpis">
          <div className="kpi-card">
            <span className="kpi-card__value kpi-card__value--edge data-value">
              {current?.predicted_load?.toFixed(2) ?? '—'}
            </span>
            <span className="kpi-card__label">Predicted kW</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value data-value">
              {current?.actual_load?.toFixed(2) ?? '—'}
            </span>
            <span className="kpi-card__label">Actual kW</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value data-value">
              {augrid?.running_rmse?.toFixed(3) ?? '—'}
            </span>
            <span className="kpi-card__label">RMSE</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value data-value">
              {current?.latency_ms?.toFixed(1) ?? '—'}ms
            </span>
            <span className="kpi-card__label">Latency</span>
          </div>
        </div>

        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={false} />
              <YAxis width={50} tickFormatter={(v) => `${v}`} />
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
              />
              <Area
                type="monotone"
                dataKey="predicted"
                stroke="var(--accent-edge)"
                fill="var(--accent-edge-dim)"
                strokeWidth={2}
                name="Predicted Load"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="var(--accent-cloud)"
                strokeWidth={2}
                strokeDasharray="5 3"
                dot={false}
                name="Actual Load"
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-4)', marginTop: 'var(--space-3)' }}>
          <span className="label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 12, height: 3, background: 'var(--accent-edge)', display: 'inline-block', borderRadius: 2 }} />
            Edge: {augrid?.edge_predictions ?? 0}
          </span>
          <span className="label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 12, height: 3, background: 'var(--accent-cloud)', display: 'inline-block', borderRadius: 2 }} />
            Cloud: {augrid?.cloud_predictions ?? 0}
          </span>
        </div>
      </div>
    </div>
  );
});

export default AuGridPanel;
