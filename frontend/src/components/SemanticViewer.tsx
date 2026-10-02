import React from 'react';
import type { SemanticStage } from '../types/pipeline';

interface SemanticViewerProps {
  semantic: SemanticStage;
}

export const SemanticViewer: React.FC<SemanticViewerProps> = ({ semantic }) => {
  if (semantic.status === 'ERROR') {
    return (
      <div>
        <div style={{ marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="badge-tag danger">Status: FAILED</span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            SemanticAnalyzer detected {semantic.errors?.length || 1} semantic violation(s):
          </span>
        </div>

        {semantic.errors && semantic.errors.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {semantic.errors.map((err, i) => (
              <div key={i} className="error-banner" style={{ margin: 0 }}>
                <div className="error-banner-title">
                  <span>✗ [{err.code}]</span>
                  <span>Line {err.line}, Column {err.col}</span>
                </div>
                <p>{err.message}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="error-banner">
            <div className="error-banner-title">✗ Semantic Error</div>
            <p>Query failed semantic validation checks against registered schema.</p>
          </div>
        )}
      </div>
    );
  }

  if (semantic.status === 'NOT_RUN') {
    return <div style={{ color: 'var(--text-muted)' }}>Semantic analysis has not run yet.</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="badge-tag success">Status: PASSED</span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            Validated against Schema Registry (<code className="mono" style={{ color: '#0f172a', fontWeight: 600 }}>{semantic.table}</code>)
          </span>
        </div>
        {semantic.resolved_columns && (
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Resolved columns:</span>
            {semantic.resolved_columns.map((col) => (
              <span key={col} className="badge-tag neutral mono">
                {col}
              </span>
            ))}
          </div>
        )}
      </div>

      <div style={{ background: 'var(--inset-bg)', border: '1px solid var(--inset-border)', borderRadius: 'var(--radius-md)', padding: '16px 20px' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '12px', letterSpacing: '0.6px' }}>
          Verified Language Rules & Schema Constraints:
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {semantic.checks?.map((chk, idx) => (
            <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', fontSize: '13px' }}>
              <span style={{ color: 'var(--accent-mint)', fontWeight: 'bold' }}>✓</span>
              <div>
                <span style={{ color: '#0f172a', fontWeight: 600 }}>{chk.name}: </span>
                <span style={{ color: 'var(--text-body)' }}>{chk.description}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
