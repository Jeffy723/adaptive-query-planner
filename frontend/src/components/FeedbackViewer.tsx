import React from 'react';
import type { FeedbackStage } from '../types/pipeline';

interface FeedbackViewerProps {
  feedback: FeedbackStage;
}

export const FeedbackViewer: React.FC<FeedbackViewerProps> = ({ feedback }) => {
  if (feedback.status === 'NOT_RUN' || !feedback.operations) {
    return <div style={{ color: 'var(--text-muted)' }}>Runtime feedback has not been captured yet.</div>;
  }

  // Filter out operations that have selectivity feedback
  const filterFeedbacks = feedback.operations
    .filter((op) => op.selectivity_feedback !== null)
    .map((op) => op.selectivity_feedback!);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '14.5px', fontWeight: 700, color: '#0f172a' }}>
            Empirical Execution Metrics vs Compile-Time Cost Model
          </span>
          <span className={`badge-tag ${feedback.learning_enabled ? 'success' : 'neutral'}`}>
            Learning: {feedback.learning_enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        {feedback.learning_enabled && (
          <span className="badge-tag info">
            Stored Profiles: {feedback.stored_profile_count || 0}
          </span>
        )}
      </div>

      {/* Summary KPI Cards */}
      <div className="metric-cards-row">
        <div className="metric-card">
          <div className="metric-card-label">Total Output Error</div>
          <div className="metric-card-value" style={{ color: feedback.total_absolute_error === 0 ? 'var(--accent-mint)' : 'var(--accent-amber)' }}>
            {feedback.total_absolute_error} <span style={{ fontSize: '13px', fontWeight: 'normal', color: 'var(--text-secondary)' }}>rows</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-label">Max Operator Error</div>
          <div className="metric-card-value" style={{ color: 'var(--accent-amber)' }}>
            {feedback.max_absolute_error} <span style={{ fontSize: '13px', fontWeight: 'normal', color: 'var(--text-secondary)' }}>rows</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-card-label">Average Relative Error</div>
          <div className="metric-card-value" style={{ color: 'var(--accent-violet-dark)' }}>
            {feedback.average_relative_error?.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Operator Accuracy Table */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '10px', letterSpacing: '0.6px' }}>
          Operator Cardinality Accuracy Comparison:
        </div>
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Operation</th>
                <th style={{ width: '90px' }}>Type</th>
                <th style={{ width: '140px', textAlign: 'right' }}>ESTIMATED Output</th>
                <th style={{ width: '130px', textAlign: 'right' }}>ACTUAL Output</th>
                <th style={{ width: '120px', textAlign: 'right' }}>Difference</th>
                <th style={{ width: '130px', textAlign: 'right' }}>Relative Error</th>
              </tr>
            </thead>
            <tbody>
              {feedback.operations.map((op, i) => {
                const diffColor = op.difference === 0 ? 'var(--text-muted)' : op.difference > 0 ? 'var(--accent-mint)' : 'var(--accent-rose)';
                return (
                  <tr key={i}>
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
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--accent-violet-dark)' }}>
                      {op.estimated_output}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: '#0f172a', fontWeight: 600 }}>
                      {op.actual_output}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: diffColor, fontWeight: 600 }}>
                      {op.difference > 0 ? `+${op.difference}` : op.difference}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: op.absolute_error === 0 ? 'var(--accent-mint)' : 'var(--accent-amber)' }}>
                      {op.relative_error_percentage.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Adaptive Selectivity Updates Table */}
      {filterFeedbacks.length > 0 && (
        <div style={{ marginBottom: '18px' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '10px', letterSpacing: '0.6px' }}>
            Adaptive Statistics Learning & Selectivity Updates:
          </div>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Filter Predicate</th>
                  <th style={{ width: '150px', textAlign: 'right' }}>ESTIMATED Prior</th>
                  <th style={{ width: '150px', textAlign: 'right' }}>ACTUAL Observed</th>
                  <th style={{ width: '160px', textAlign: 'right' }}>UPDATED Learned</th>
                  <th style={{ width: '120px', textAlign: 'center' }}>Smoothing α</th>
                </tr>
              </thead>
              <tbody>
                {filterFeedbacks.map((sf, idx) => (
                  <tr key={idx}>
                    <td>
                      <code className="mono" style={{ color: 'var(--accent-amber)', fontWeight: 600, fontSize: '12px' }}>
                        {sf.predicate}
                      </code>
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--accent-violet-dark)' }}>
                      {sf.previous_selectivity.toFixed(4)}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: '#0f172a', fontWeight: 600 }}>
                      {sf.observed_selectivity.toFixed(4)}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--accent-mint)', fontWeight: 700 }}>
                      {sf.updated_selectivity.toFixed(4)}
                    </td>
                    <td style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                      {sf.alpha.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {feedback.explain_text && (
        <details style={{ marginTop: '16px' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '12px' }}>
            View Full Feedback Text Report
          </summary>
          <pre className="code-block" style={{ marginTop: '8px', fontSize: '12px' }}>
            {feedback.explain_text}
          </pre>
        </details>
      )}
    </div>
  );
};
