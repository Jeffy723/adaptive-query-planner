import React from 'react';
import type { CostStage } from '../types/pipeline';

interface CostViewerProps {
  cost: CostStage;
  selectedPlanId?: string;
}

export const CostViewer: React.FC<CostViewerProps> = ({ cost, selectedPlanId }) => {
  if (cost.status === 'NOT_RUN' || !cost.estimates || cost.estimates.length === 0) {
    return <div style={{ color: 'var(--text-muted)' }}>Cost estimates have not been computed yet.</div>;
  }

  // Calculate max cost for horizontal bar chart scaling
  const maxCost = Math.max(...cost.estimates.map((e) => e.total_cost), 1);

  return (
    <div>
      <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '18px' }}>
        Cost Estimator calculates intermediate cardinalities and cumulative processing costs using dataset statistics.
      </p>

      {/* Bar Chart Comparison */}
      <div style={{ background: 'var(--inset-bg)', border: '1px solid var(--inset-border)', borderRadius: 'var(--radius-md)', padding: '18px 20px', marginBottom: '24px' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '14px', letterSpacing: '0.6px' }}>
          Estimated Total Cost Comparison:
        </div>
        <div className="bar-chart-container">
          {cost.estimates.map((est) => {
            const isSelected = est.plan_id === selectedPlanId;
            const widthPct = Math.max(10, (est.total_cost / maxCost) * 100);
            return (
              <div key={est.plan_id} className="bar-row">
                <span className="bar-label">{est.plan_id}</span>
                <div className="bar-track">
                  <div
                    className={`bar-fill ${isSelected ? 'selected' : ''}`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                <span className="bar-value">
                  {est.total_cost.toFixed(2)} cost
                </span>
                {isSelected && (
                  <span className="badge-tag info" style={{ padding: '2px 8px', fontSize: '10px' }}>
                    Lowest
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Per-Plan Cost Breakdown Tables */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
        {cost.estimates.map((est) => (
          <div key={est.plan_id} style={{ background: 'var(--inset-bg)', border: '1px solid var(--inset-border)', borderRadius: 'var(--radius-md)', padding: '18px 20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="mono" style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  {est.plan_id} Detailed Cost Breakdown
                </span>
                {est.plan_id === selectedPlanId && (
                  <span className="badge-tag info">Selected</span>
                )}
              </div>
              <span className="mono" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--accent-amber)' }}>
                Total Cost: {est.total_cost.toFixed(2)}
              </span>
            </div>

            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Operation</th>
                    <th style={{ width: '90px' }}>Type</th>
                    <th style={{ width: '90px', textAlign: 'right' }}>Input Rows</th>
                    <th style={{ width: '100px', textAlign: 'right' }}>Output Rows</th>
                    <th style={{ width: '90px', textAlign: 'right' }}>Cost</th>
                    <th style={{ width: '100px', textAlign: 'right' }}>Selectivity</th>
                    <th>Formula / Description</th>
                  </tr>
                </thead>
                <tbody>
                  {est.operations.map((op, opI) => (
                    <tr key={opI}>
                      <td>
                        <code className="mono" style={{ color: '#0f172a', fontWeight: 600, fontSize: '12px' }}>
                          {op.operation}
                        </code>
                      </td>
                      <td>
                        <span className="badge-tag neutral" style={{ fontSize: '10px' }}>
                          {op.operation_type}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{op.input_rows}</td>
                      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{op.output_rows}</td>
                      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--accent-amber)', fontWeight: 600 }}>
                        {op.cost.toFixed(2)}
                      </td>
                      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                        {op.selectivity !== null && op.selectivity !== undefined
                          ? op.selectivity.toFixed(4)
                          : '—'}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{op.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
