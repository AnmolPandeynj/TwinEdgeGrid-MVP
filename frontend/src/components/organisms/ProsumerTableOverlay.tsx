import React, { memo, useMemo } from 'react';
import type { DashboardUpdate, Prosumer } from '../../types/telemetry';

interface ProsumerTableOverlayProps {
  data: DashboardUpdate | null;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  cooperative: 'var(--accent-edge)',
  selling: 'var(--accent-edge)',
  hoarding: 'var(--accent-warning)',
  idle: 'var(--text-muted)',
};

const ProsumerTableOverlay = memo(function ProsumerTableOverlay({ data, onClose }: ProsumerTableOverlayProps) {
  const market = data?.smartprice;
  const prosumers = market?.prosumers ?? [];

  // Sort by cooperation index descending for visual clarity
  const sortedProsumers = useMemo(() => {
    return [...prosumers].sort((a, b) => b.cooperation_index - a.cooperation_index);
  }, [prosumers]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem' }}>Prosumer Market Ledger</h2>
          <button className="btn-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <table className="prosumer-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Cooperation Index</th>
                <th>Reward Factor</th>
                <th>Variable Price</th>
                <th>Stored Energy (kWh)</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedProsumers.map((p) => (
                <ProsumerRow key={p.prosumer_id} prosumer={p} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
});

const ProsumerRow = memo(function ProsumerRow({ prosumer }: { prosumer: Prosumer }) {
  const rowClass =
    prosumer.status === 'cooperative' || prosumer.status === 'selling'
      ? 'cooperative'
      : prosumer.status === 'hoarding'
        ? 'hoarding'
        : '';

  return (
    <tr className={rowClass}>
      <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        {prosumer.prosumer_id.replace('prosumer_', '#')}
      </td>
      <td>{prosumer.cooperation_index.toFixed(3)}</td>
      <td>{prosumer.reward_factor.toFixed(3)}</td>
      <td>${prosumer.variable_price.toFixed(4)}</td>
      <td>{prosumer.stored_energy_kwh.toFixed(1)}</td>
      <td>
        <span
          className="badge"
          style={{
            background: `${STATUS_COLORS[prosumer.status]}22`,
            color: STATUS_COLORS[prosumer.status],
          }}
        >
          {prosumer.status}
        </span>
      </td>
    </tr>
  );
});

export default ProsumerTableOverlay;
