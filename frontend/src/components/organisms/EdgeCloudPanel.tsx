import React, { memo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import type { DashboardUpdate } from '../../types/telemetry';
import type { ChartDataPoint } from '../../hooks/useTelemetry';

interface EdgeCloudPanelProps {
  data: DashboardUpdate | null;
  cpuHistory: ChartDataPoint[];
  isOffloading: boolean;
  edgeCpuCritical: boolean;
}

const EdgeCloudPanel = memo(function EdgeCloudPanel({
  data,
  cpuHistory,
  isOffloading,
  edgeCpuCritical,
}: EdgeCloudPanelProps) {
  const edge = data?.edge_metrics;
  const cloud = data?.cloud_metrics;
  const augrid = data?.augrid;

  return (
    <div className={`panel ${edgeCpuCritical ? 'panel--critical' : ''}`}>
      <div className="panel__header">
        <span className="panel__title">Edge-Cloud Continuum</span>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span className={`badge ${isOffloading ? 'badge--warning' : 'badge--edge'}`}>
            {isOffloading ? '⚡ OFFLOADING' : '● LOCAL'}
          </span>
        </div>
      </div>

      {isOffloading && (
        <div className="offload-banner">
          ⚡ CPU THRESHOLD BREACHED — TASKS OFFLOADING → CLOUD
        </div>
      )}

      <div className="panel__body">
        <div className="panel__kpis">
          <div className="kpi-card">
            <span className={`kpi-card__value ${edgeCpuCritical ? 'kpi-card__value--warning' : 'kpi-card__value--edge'}`}>
              {edge?.cpu_percent?.toFixed(1) ?? '—'}%
            </span>
            <span className="kpi-card__label">Edge CPU</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value kpi-card__value--cloud">
              {cloud?.cpu_percent?.toFixed(1) ?? '—'}%
            </span>
            <span className="kpi-card__label">Cloud CPU</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value">
              {edge?.memory_percent?.toFixed(1) ?? '—'}%
            </span>
            <span className="kpi-card__label">Edge RAM</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-card__value data-value">
              {augrid?.total_predictions ?? 0}
            </span>
            <span className="kpi-card__label">Predictions</span>
          </div>
        </div>

        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={cpuHistory} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={false} />
              <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} width={45} />
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
              <ReferenceLine
                y={80}
                stroke="var(--accent-warning)"
                strokeDasharray="6 4"
                label={{ value: '80% Threshold', position: 'right', fill: 'var(--accent-warning)', fontSize: 10 }}
              />
              <Line
                type="monotone"
                dataKey="edgeCpu"
                stroke="var(--accent-edge)"
                strokeWidth={2}
                dot={false}
                name="Edge CPU"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="cloudCpu"
                stroke="var(--accent-cloud)"
                strokeWidth={2}
                dot={false}
                name="Cloud CPU"
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
});

export default EdgeCloudPanel;
