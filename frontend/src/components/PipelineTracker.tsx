import React from 'react';
import type { PipelineStages, StageStatus } from '../types/pipeline';

interface PipelineTrackerProps {
  stages: PipelineStages;
  onSelectStage: (stageKey: string) => void;
}

interface StepConfig {
  key: keyof PipelineStages;
  label: string;
}

const STEPS: StepConfig[] = [
  { key: 'lexer', label: 'Lexer' },
  { key: 'parser', label: 'Parser' },
  { key: 'semantic', label: 'Semantic' },
  { key: 'logical_ir', label: 'Logical IR' },
  { key: 'planner', label: 'Planner' },
  { key: 'cost', label: 'Cost Model' },
  { key: 'selector', label: 'Selector' },
  { key: 'execution', label: 'Execution' },
  { key: 'feedback', label: 'Feedback' },
  { key: 'result', label: 'Result' },
];

export const PipelineTracker: React.FC<PipelineTrackerProps> = ({ stages, onSelectStage }) => {
  const getStatusIcon = (status: StageStatus) => {
    switch (status) {
      case 'PASSED':
        return '✓';
      case 'ERROR':
        return '✗';
      case 'RUNNING':
        return '⟳';
      default:
        return '●';
    }
  };

  const getStatusClass = (status: StageStatus) => {
    switch (status) {
      case 'PASSED':
        return 'passed';
      case 'ERROR':
        return 'error';
      case 'RUNNING':
        return 'running';
      default:
        return 'not-run';
    }
  };

  return (
    <div className="pipeline-tracker">
      <div className="pipeline-tracker-title">Compiler & Planning Pipeline Tracker</div>
      <div className="pipeline-steps-flow">
        {STEPS.map((step, idx) => {
          const stageState = stages[step.key];
          const status = stageState?.status || 'NOT_RUN';
          return (
            <React.Fragment key={step.key}>
              <div
                className={`pipeline-step-node ${getStatusClass(status)}`}
                onClick={() => onSelectStage(step.key)}
                title={`Click to inspect ${step.label} (${status})`}
              >
                <span className="step-icon">{getStatusIcon(status)}</span>
                <span>{step.label}</span>
              </div>
              {idx < STEPS.length - 1 && <span className="flow-arrow">→</span>}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
