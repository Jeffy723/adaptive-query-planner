import React from 'react';
import type { ExecutionStage } from '../types/pipeline';

interface ExecutionViewerProps {
  execution: ExecutionStage;
}

export const ExecutionViewer: React.FC<ExecutionViewerProps> = ({ execution }) => {
  if (execution.status === 'NOT_RUN' || !execution.statistics) {
    return <div style={{ color: 'var(--text-muted)' }}>Physical plan execution has not occurred yet.</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="mono" style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
            Executed Physical Plan: {execution.selected_plan_id}
          </span>
          {execution.baseline_matched && (
            <span className="badge-tag success">
              ✓ Baseline Verified (100% Match)
            </span>
          )}
        </div>
        <span className="badge-tag info">
          Rows Returned: {execution.rows_returned}
        </span>
      </div>

      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '10px' }}>
        Runtime execution metrics recorded by <code className="mono">backend.executor.Executor</code>:
      </div>

      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Operation</th>
              <th style={{ width: '90px' }}>Type</th>
              <th style={{ width: '130px', textAlign: 'right' }}>Estimated Input</th>
              <th style={{ width: '120px', textAlign: 'right' }}>Actual Input</th>
              <th style={{ width: '140px', textAlign: 'right' }}>Estimated Output</th>
              <th style={{ width: '130px', textAlign: 'right' }}>Actual Output</th>
            </tr>
          </thead>
          <tbody>
            {execution.statistics.map((st, i) => (
              <tr key={i}>
                <td>
                  <code className="mono" style={{ color: '#0f172a', fontWeight: 600, fontSize: '12px' }}>
                    {st.operation}
                  </code>
                </td>
                <td>
                  <span className="badge-tag neutral" style={{ fontSize: '10px' }}>
                    {st.operation_type}
                  </span>
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {st.estimated_input}
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: '#0f172a', fontWeight: 600 }}>
                  {st.actual_input}
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {st.estimated_output}
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--accent-mint)', fontWeight: 700 }}>
                  {st.actual_output}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
