import React from 'react';
import type { PlannerStage } from '../types/pipeline';

interface PhysicalPlanViewerProps {
  planner: PlannerStage;
}

export const PhysicalPlanViewer: React.FC<PhysicalPlanViewerProps> = ({ planner }) => {
  if (planner.status === 'NOT_RUN' || !planner.plans) {
    return <div style={{ color: 'var(--text-muted)' }}>Physical plans have not been generated yet.</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
          Physical Execution Plan Generator produced {planner.candidate_count} semantically equivalent candidate plan(s) by permuting filter ordering.
        </p>
        <span className="badge-tag info">
          Candidates: {planner.plans.length}
        </span>
      </div>

      <div className="physical-plans-grid">
        {planner.plans.map((plan) => (
          <div
            key={plan.plan_id}
            className={`plan-card ${plan.is_selected ? 'selected' : ''}`}
          >
            <div className="plan-card-header">
              <span className="plan-card-title">{plan.plan_id}</span>
              {plan.is_selected ? (
                <span className="badge-tag info">Selected Strategy</span>
              ) : (
                <span className="badge-tag neutral">Candidate</span>
              )}
            </div>

            {plan.filter_order && plan.filter_order.length > 0 && (
              <div className="plan-filter-order">
                <div className="plan-filter-order-title">Filter Evaluation Order:</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {plan.filter_order.map((pred, i) => (
                    <div key={i} className="mono" style={{ color: 'var(--accent-amber)', fontSize: '12px', fontWeight: 600 }}>
                      {i + 1}. {pred}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'stretch' }}>
              {plan.operations.map((op, opIdx) => (
                <React.Fragment key={opIdx}>
                  <div
                    style={{
                      background: 'rgba(255, 255, 255, 0.9)',
                      border: '1px solid rgba(0, 0, 0, 0.07)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '8px 12px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      boxShadow: '0 1px 3px rgba(0, 0, 0, 0.02)',
                    }}
                  >
                    <span
                      style={{
                        color:
                          op.type === 'FILTER'
                            ? 'var(--accent-amber)'
                            : op.type === 'SCAN'
                            ? 'var(--accent-violet-dark)'
                            : op.type === 'PROJECT'
                            ? 'var(--accent-magenta)'
                            : 'var(--accent-violet)',
                        fontWeight: 700,
                      }}
                    >
                      [{op.type}]
                    </span>
                    <span style={{ color: '#0f172a', fontWeight: 500 }}>{op.description}</span>
                  </div>
                  {opIdx < plan.operations.length - 1 && (
                    <div style={{ textAlign: 'center', color: 'var(--accent-violet)', opacity: 0.7, fontSize: '11px', margin: '-2px 0' }}>
                      ↓
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>

            <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', borderTop: '1px solid rgba(0, 0, 0, 0.06)', paddingTop: '10px' }}>
              {plan.description}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
