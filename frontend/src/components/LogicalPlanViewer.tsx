import React from 'react';
import type { LogicalIRStage } from '../types/pipeline';

interface LogicalPlanViewerProps {
  logicalIr: LogicalIRStage;
}

export const LogicalPlanViewer: React.FC<LogicalPlanViewerProps> = ({ logicalIr }) => {
  if (logicalIr.status === 'NOT_RUN' || !logicalIr.operations) {
    return <div style={{ color: 'var(--text-muted)' }}>Logical IR has not been generated yet.</div>;
  }

  const getOpBadgeColor = (type: string) => {
    switch (type) {
      case 'SCAN':
        return 'var(--accent-violet-dark)';
      case 'FILTER':
        return 'var(--accent-amber)';
      case 'PROJECT':
        return 'var(--accent-magenta)';
      case 'SORT':
        return 'var(--accent-violet)';
      default:
        return 'var(--text-secondary)';
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
        <div>
          <span className="badge-tag info">LOGICAL PLAN</span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '13px', marginLeft: '10px' }}>
            Syntax-independent intermediate representation (describes <strong>WHAT</strong> to compute, not how)
          </span>
        </div>
        <span style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
          Source Table: <code className="mono" style={{ color: '#0f172a', fontWeight: 600 }}>{logicalIr.source_table}</code>
        </span>
      </div>

      <div className="flow-diagram-container">
        {logicalIr.operations.map((op, idx) => (
          <React.Fragment key={op.index}>
            <div className="flow-op-node">
              <span style={{ color: getOpBadgeColor(op.type), fontWeight: 700, marginRight: '10px' }}>
                [{op.type}]
              </span>
              <span>{op.description}</span>
            </div>
            {idx < (logicalIr.operations?.length || 0) - 1 && (
              <span className="flow-op-arrow">↓</span>
            )}
          </React.Fragment>
        ))}
      </div>

      {logicalIr.explain_text && (
        <details style={{ marginTop: '18px' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '12px' }}>
            View Textual IR Explain Representation
          </summary>
          <pre className="code-block" style={{ marginTop: '8px', fontSize: '12px' }}>
            {logicalIr.explain_text}
          </pre>
        </details>
      )}
    </div>
  );
};
