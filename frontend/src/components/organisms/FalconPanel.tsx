import React, { memo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import type { DashboardUpdate } from '../../types/telemetry';

interface FalconPanelProps {
  data: DashboardUpdate | null;
}

const SLICE_COLORS: Record<string, string> = {
  video: '#EF4444',
  voip: '#3B82F6',
  data: '#10B981',
};

const FalconPanel = memo(function FalconPanel({ data }: FalconPanelProps) {
  const falcon = data?.falcon;
  const slices = falcon?.slices ?? [];

  const chartData = slices.map((s) => ({
    name: s.name.toUpperCase(),
    allocated: s.allocated_bandwidth,
    used: s.current_usage,
    drops: s.packet_drop_count,
  }));

  const recentEvents = falcon?.recent_reallocations?.slice(0, 5) ?? [];

  return (
    <div className="panel">
      <div className="panel__header">
        <span className="panel__title">FALCON SDN Slicing</span>
        <span className="badge badge--danger" style={{ fontSize: '0.625rem' }}>
          {falcon?.total_drops ?? 0} DROPS
        </span>
      </div>

      <div className="panel__body">
        <div className="panel__kpis">
          {slices.map((s) => (
            <div className="kpi-card" key={s.name}>
              <span
                className="kpi-card__value data-value"
                style={{ color: SLICE_COLORS[s.name] ?? 'var(--text-primary)' }}
              >
                {s.allocated_bandwidth}
              </span>
              <span className="kpi-card__label">{s.name} Mbps</span>
            </div>
          ))}
          <div className="kpi-card">
            <span className="kpi-card__value data-value">
              {falcon?.global_limit ?? 1000}
            </span>
            <span className="kpi-card__label">Global B</span>
          </div>
        </div>

        <div className="chart-container" style={{ minHeight: '160px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis width={45} />
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
              />
              <Bar dataKey="allocated" name="Allocated" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-alloc-${index}`}
                    fill={SLICE_COLORS[slices[index]?.name] ?? '#888'}
                    fillOpacity={0.3}
                  />
                ))}
              </Bar>
              <Bar dataKey="used" name="Used" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-used-${index}`}
                    fill={SLICE_COLORS[slices[index]?.name] ?? '#888'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {recentEvents.length > 0 && (
          <div style={{ marginTop: 'var(--space-3)' }}>
            <span className="label">Recent Reallocations</span>
            <div style={{ marginTop: 'var(--space-2)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {recentEvents.map((evt, i) => (
                <div
                  key={i}
                  style={{
                    fontFamily: 'var(--font-data)',
                    fontSize: '0.6875rem',
                    color: 'var(--text-secondary)',
                    padding: '4px 8px',
                    background: 'var(--bg-card)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  {evt.from_slice.toUpperCase()} → {evt.to_slice.toUpperCase()}: {evt.amount_mbps} Mbps
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

export default FalconPanel;
