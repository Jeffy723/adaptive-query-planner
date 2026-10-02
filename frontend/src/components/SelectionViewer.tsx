import React from 'react';
import type { SelectorStage } from '../types/pipeline';

interface SelectionViewerProps {
  selector: SelectorStage;
}

export const SelectionViewer: React.FC<SelectionViewerProps> = ({ selector }) => {
  if (selector.status === 'NOT_RUN' || !selector.selected_plan_id) {
    return <div style={{ color: 'var(--text-muted)' }}>Plan selection has not occurred yet.</div>;
  }

  return (
    <div>
      {/* Selected Strategy Card */}
      <div
        style={{
          background: 'rgba(124, 58, 237, 0.06)',
          border: '1px solid rgba(124, 58, 237, 0.22)',
          borderRadius: 'var(--radius-md)',
          padding: '20px 22px',
          marginBottom: '22px',
          boxShadow: '0 4px 16px rgba(124, 58, 237, 0.06)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '18px', fontWeight: 800, color: 'var(--accent-violet-dark)', fontFamily: 'var(--font-mono)' }}>
              Selected Execution Plan: {selector.selected_plan_id}
            </span>
            <span className="badge-tag info">Optimal Strategy</span>
          </div>
          <span style={{ fontSize: '16px', fontWeight: 700, color: 'var(--accent-amber)', fontFamily: 'var(--font-mono)' }}>
            Estimated Cost: {selector.selected_cost?.toFixed(2)}
          </span>
        </div>
        <p style={{ color: 'var(--text-body)', fontSize: '13.5px', marginBottom: '8px', lineHeight: 1.6 }}>
          <strong>Decision Rationale:</strong> {selector.reason}
        </p>
        <p style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>
          <em>Rule: Selected according to the deterministic cost model (lowest estimated total processing cost).</em>
        </p>
      </div>

      {/* Candidate Ranking Table */}
      {selector.ranked_candidates && selector.ranked_candidates.length > 0 && (
        <div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '10px', letterSpacing: '0.6px' }}>
            Candidate Plans Ranked by Cost:
          </div>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '70px', textAlign: 'center' }}>Rank</th>
                  <th>Candidate Plan</th>
                  <th style={{ width: '150px', textAlign: 'right' }}>Estimated Cost</th>
                  <th style={{ width: '180px', textAlign: 'center' }}>Decision Status</th>
                </tr>
              </thead>
              <tbody>
                {selector.ranked_candidates.map((cand) => (
                  <tr
                    key={cand.plan_id}
                    style={cand.is_selected ? { backgroundColor: 'rgba(124, 58, 237, 0.05)' } : {}}
                  >
                    <td style={{ textAlign: 'center', fontWeight: 700, color: cand.is_selected ? 'var(--accent-violet-dark)' : 'var(--text-secondary)' }}>
                      #{cand.rank}
                    </td>
                    <td>
                      <code className="mono" style={{ fontWeight: 600, color: cand.is_selected ? '#0f172a' : 'var(--text-secondary)' }}>
                        {cand.plan_id}
                      </code>
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--accent-amber)' }}>
                      {cand.cost.toFixed(2)}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {cand.is_selected ? (
                        <span className="badge-tag info">Selected Plan</span>
                      ) : (
                        <span className="badge-tag neutral">Candidate</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
