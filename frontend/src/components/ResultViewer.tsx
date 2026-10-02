import React from 'react';
import type { ResultStage } from '../types/pipeline';

interface ResultViewerProps {
  result: ResultStage;
}

export const ResultViewer: React.FC<ResultViewerProps> = ({ result }) => {
  if (result.status === 'NOT_RUN' || !result.rows) {
    return <div style={{ color: 'var(--text-muted)' }}>No query results available yet.</div>;
  }

  const columns = result.columns || [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            Physical plan execution completed successfully:
          </span>
          <span className="badge-tag success">
            Execution Verified
          </span>
        </div>
        <span className="badge-tag info">
          Rows Returned: {result.row_count}
        </span>
      </div>

      {result.rows.length === 0 ? (
        <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-secondary)', background: 'var(--inset-bg)', border: '1px solid var(--inset-border)', borderRadius: 'var(--radius-md)' }}>
          (0 matching rows found)
        </div>
      ) : (
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '50px' }}>#</th>
                {columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, idx) => (
                <tr key={idx}>
                  <td style={{ color: 'var(--text-muted)' }}>{idx + 1}</td>
                  {columns.map((col) => {
                    const val = row[col];
                    return (
                      <td key={col} style={{ fontFamily: typeof val === 'number' ? 'var(--font-mono)' : 'inherit' }}>
                        {val !== null && val !== undefined ? String(val) : <span style={{ color: 'var(--text-muted)' }}>NULL</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
