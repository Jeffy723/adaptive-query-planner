import React from 'react';

interface HeaderProps {
  serverStatus: string;
  datasetRows: number;
}

export const Header: React.FC<HeaderProps> = ({ serverStatus, datasetRows }) => {
  const isConnected = serverStatus === 'connected';

  return (
    <header className="app-header">
      <div className="app-title-group">
        <h1 className="app-main-heading">
          ADAPTIVE QUERY EXECUTION PLANNER
        </h1>
        <p className="app-subtitle">
          End-to-End Query Compilation · Cost-Based Physical Optimisation & Adaptive Runtime Feedback
        </p>
      </div>
      <div className="header-meta-badges">
        <span className="glass-pill meta-pill">
          <span className="pill-dot neutral"></span>
          TABLE: STUDENTS · {datasetRows} ROWS
        </span>
        <span className={`glass-pill meta-pill ${isConnected ? 'status-connected' : 'status-disconnected'}`}>
          <span className={`pill-dot ${isConnected ? 'mint' : 'rose'}`}></span>
          BACKEND: {serverStatus.toUpperCase()}
        </span>
      </div>
    </header>
  );
};
