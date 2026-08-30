import React from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useTelemetry } from '../hooks/useTelemetry';
import EdgeCloudPanel from '../components/organisms/EdgeCloudPanel';
import FalconPanel from '../components/organisms/FalconPanel';
import AuGridPanel from '../components/organisms/AuGridPanel';
import SmartPricePanel from '../components/organisms/SmartPricePanel';
import ProsumerTableOverlay from '../components/organisms/ProsumerTableOverlay';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/dashboard';

export default function Dashboard() {
  const { data, status, sequence } = useWebSocket(WS_URL);
  const { cpuHistory, priceHistory, isOffloading, edgeCpuCritical } = useTelemetry(data);
  const [showProsumerTable, setShowProsumerTable] = React.useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* ── Header ──────────────────────────────────────── */}
      <header className="dashboard-header">
        <div className="dashboard-header__title">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect width="20" height="20" rx="4" fill="var(--accent-edge)" fillOpacity="0.15" />
            <path d="M6 10L9 13L14 7" stroke="var(--accent-edge)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          TwinEdgeGrid
          <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.75rem' }}>
            Digital Twin Dashboard
          </span>
        </div>
        <div className="dashboard-header__status">
          <div className={`status-dot status-dot--${status}`} />
          <span>{status === 'connected' ? `Live · seq ${sequence}` : status}</span>
          {data && (
            <span style={{ marginLeft: '8px', color: 'var(--text-muted)' }}>
              {new Date(data.timestamp).toLocaleTimeString()}
            </span>
          )}
          <button 
            className="btn-outline" 
            style={{ marginLeft: 'var(--space-4)' }}
            onClick={() => setShowProsumerTable(true)}
          >
            View Prosumer Ledger
          </button>
        </div>
      </header>

      {/* ── 2×2 Panel Grid ──────────────────────────────── */}
      <main className="dashboard-grid">
        <EdgeCloudPanel
          data={data}
          cpuHistory={cpuHistory}
          isOffloading={isOffloading}
          edgeCpuCritical={edgeCpuCritical}
        />
        <FalconPanel data={data} />
        <AuGridPanel data={data} />
        <SmartPricePanel data={data} priceHistory={priceHistory} />
      </main>

      {showProsumerTable && (
        <ProsumerTableOverlay data={data} onClose={() => setShowProsumerTable(false)} />
      )}
    </div>
  );
}
