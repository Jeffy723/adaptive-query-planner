import React from 'react';
import type { ExampleQuery } from '../types/pipeline';

interface QueryEditorProps {
  query: string;
  setQuery: (q: string) => void;
  onExecute: () => void;
  isLoading: boolean;
  examples: ExampleQuery[];
  enableLearning: boolean;
  setEnableLearning: (v: boolean) => void;
  alpha: number;
  setAlpha: (v: number) => void;
  onResetStats: () => void;
}

export const QueryEditor: React.FC<QueryEditorProps> = ({
  query,
  setQuery,
  onExecute,
  isLoading,
  examples,
  enableLearning,
  setEnableLearning,
  alpha,
  setAlpha,
  onResetStats,
}) => {
  const handleSelectExample = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selectedId = e.target.value;
    if (!selectedId) return;
    const found = examples.find((ex) => ex.id === selectedId);
    if (found) {
      setQuery(found.query);
    }
  };

  return (
    <div className="query-editor-card">
      <div className="query-editor-header">
        <span className="query-editor-heading">
          QUERY SPECIFICATION (SQL-like DML)
        </span>
        <div className="examples-select-group">
          <label htmlFor="example-select">Benchmark Presets:</label>
          <select
            id="example-select"
            className="form-select"
            onChange={handleSelectExample}
            defaultValue=""
          >
            <option value="" disabled>
              Select a benchmark query...
            </option>
            {examples.map((ex) => (
              <option key={ex.id} value={ex.id}>
                {ex.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      <textarea
        className="query-textarea"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Enter SQL-like query (e.g., SELECT name FROM students WHERE marks > 80;)"
        spellCheck={false}
        rows={5}
      />

      <div className="query-editor-actions">
        <div className="learning-toggle-group">
          <label title="When enabled, runtime feedback updates future cost estimator selectivity statistics">
            <input
              type="checkbox"
              checked={enableLearning}
              onChange={(e) => setEnableLearning(e.target.checked)}
            />
            <span>Enable Adaptive Learning</span>
          </label>
          {enableLearning && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Smoothing α:</span>
              <input
                type="number"
                min="0.1"
                max="1.0"
                step="0.1"
                className="alpha-input"
                value={alpha}
                onChange={(e) => setAlpha(parseFloat(e.target.value) || 0.5)}
              />
            </div>
          )}
          <button
            type="button"
            className="btn-secondary"
            onClick={onResetStats}
            title="Reset in-memory learned selectivity profiles"
          >
            Reset Learned Statistics
          </button>
        </div>

        <button
          type="button"
          className="btn-primary"
          onClick={onExecute}
          disabled={isLoading || !query.trim()}
        >
          {isLoading ? 'Compiling & Executing...' : '▶ Execute Query'}
        </button>
      </div>
    </div>
  );
};
