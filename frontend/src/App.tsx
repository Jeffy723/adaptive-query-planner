import React, { useEffect, useState } from 'react';
import { executeQuery, fetchExamples, fetchHealth, resetAdaptiveStats } from './api/client';
import { ASTViewer } from './components/ASTViewer';
import { CollapsibleSection } from './components/CollapsibleSection';
import { CostViewer } from './components/CostViewer';
import { ExecutionViewer } from './components/ExecutionViewer';
import { FeedbackViewer } from './components/FeedbackViewer';
import { Header } from './components/Header';
import { LogicalPlanViewer } from './components/LogicalPlanViewer';
import { PhysicalPlanViewer } from './components/PhysicalPlanViewer';
import { PipelineTracker } from './components/PipelineTracker';
import { QueryEditor } from './components/QueryEditor';
import { ResultViewer } from './components/ResultViewer';
import { SelectionViewer } from './components/SelectionViewer';
import { SemanticViewer } from './components/SemanticViewer';
import { TokenViewer } from './components/TokenViewer';
import type { ExampleQuery, PipelineResponse, PipelineStages } from './types/pipeline';

const DEFAULT_QUERY = `SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;`;

const INITIAL_STAGES: PipelineStages = {
  lexer: { status: 'NOT_RUN' },
  parser: { status: 'NOT_RUN' },
  semantic: { status: 'NOT_RUN' },
  logical_ir: { status: 'NOT_RUN' },
  planner: { status: 'NOT_RUN' },
  cost: { status: 'NOT_RUN' },
  selector: { status: 'NOT_RUN' },
  execution: { status: 'NOT_RUN' },
  feedback: { status: 'NOT_RUN' },
  result: { status: 'NOT_RUN' },
};

export const App: React.FC = () => {
  const [query, setQuery] = useState<string>(DEFAULT_QUERY);
  const [examples, setExamples] = useState<ExampleQuery[]>([]);
  const [serverStatus, setServerStatus] = useState<string>('connecting...');
  const [datasetRows, setDatasetRows] = useState<number>(200);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [enableLearning, setEnableLearning] = useState<boolean>(false);
  const [alpha, setAlpha] = useState<number>(0.5);

  const [stages, setStages] = useState<PipelineStages>(INITIAL_STAGES);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  // Collapsible section states (by default: selector and result are expanded)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    lexer: false,
    parser: false,
    semantic: false,
    logical_ir: false,
    planner: false,
    cost: false,
    selector: true,
    execution: false,
    feedback: false,
    result: true,
  });

  useEffect(() => {
    // Initial health check and examples fetch
    fetchHealth()
      .then((h) => {
        setServerStatus('connected');
        setDatasetRows(h.dataset_rows || 200);
      })
      .catch(() => setServerStatus('disconnected'));

    fetchExamples()
      .then((exs) => setExamples(exs))
      .catch((err) => console.warn('Could not load examples:', err));
  }, []);

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleSelectStageFromTracker = (stageKey: string) => {
    // Expand the stage and scroll to it
    setExpandedSections((prev) => ({
      ...prev,
      [stageKey]: true,
    }));
    const el = document.getElementById(`section-${stageKey}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const setAllSections = (expand: boolean) => {
    const updated: Record<string, boolean> = {};
    Object.keys(expandedSections).forEach((k) => {
      updated[k] = expand;
    });
    setExpandedSections(updated);
  };

  const handleExecute = async () => {
    if (!query.trim()) return;
    setIsLoading(true);
    setPipelineError(null);

    // Set tracker running state
    setStages((prev) => {
      const runningState: PipelineStages = { ...prev };
      Object.keys(runningState).forEach((k) => {
        runningState[k as keyof PipelineStages] = { status: 'RUNNING' };
      });
      return runningState;
    });

    try {
      const response: PipelineResponse = await executeQuery(
        query,
        enableLearning,
        alpha,
        false
      );

      setStages(response.stages);

      if (!response.success && response.error) {
        setPipelineError(`[${response.error.stage.toUpperCase()}] ${response.error.message}`);
        // Auto-expand the error stage
        if (response.error.stage) {
          setExpandedSections((prev) => ({
            ...prev,
            [response.error!.stage]: true,
          }));
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown execution error';
      setPipelineError(`Pipeline execution failed: ${msg}`);
      setStages(INITIAL_STAGES);
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetStats = async () => {
    try {
      await resetAdaptiveStats();
      alert('Learned adaptive statistics have been reset.');
    } catch (e) {
      alert(`Reset failed: ${e}`);
    }
  };

  return (
    <div className="app-container">
      <Header serverStatus={serverStatus} datasetRows={datasetRows} />

      <QueryEditor
        query={query}
        setQuery={setQuery}
        onExecute={handleExecute}
        isLoading={isLoading}
        examples={examples}
        enableLearning={enableLearning}
        setEnableLearning={setEnableLearning}
        alpha={alpha}
        setAlpha={setAlpha}
        onResetStats={handleResetStats}
      />

      <PipelineTracker
        stages={stages}
        onSelectStage={handleSelectStageFromTracker}
      />

      {pipelineError && (
        <div className="error-banner" style={{ marginBottom: '24px' }}>
          <div className="error-banner-title">✗ Compilation / Execution Halt</div>
          <p>{pipelineError}</p>
        </div>
      )}

      {/* Global Section Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
          Pipeline Stage Inspector
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setAllSections(true)}
          >
            Expand All Stages
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setAllSections(false)}
          >
            Collapse All Stages
          </button>
        </div>
      </div>

      {/* Stage 1: Lexical Analysis */}
      <CollapsibleSection
        id="section-lexer"
        stageNumber={1}
        title="Lexical Analysis (Lexer)"
        subtitle="Token Stream Decomposition"
        status={stages.lexer.status}
        statusText={stages.lexer.token_count !== undefined ? `${stages.lexer.token_count} Tokens` : undefined}
        isExpanded={expandedSections.lexer}
        onToggle={() => toggleSection('lexer')}
      >
        <TokenViewer lexer={stages.lexer} />
      </CollapsibleSection>

      {/* Stage 2: Syntax Analysis / Parser */}
      <CollapsibleSection
        id="section-parser"
        stageNumber={2}
        title="Syntax Analysis (Parser)"
        subtitle="Abstract Syntax Tree (AST)"
        status={stages.parser.status}
        isExpanded={expandedSections.parser}
        onToggle={() => toggleSection('parser')}
      >
        <ASTViewer parser={stages.parser} />
      </CollapsibleSection>

      {/* Stage 3: Semantic Analysis */}
      <CollapsibleSection
        id="section-semantic"
        stageNumber={3}
        title="Semantic Analysis"
        subtitle="Schema Verification & Type Compatibility"
        status={stages.semantic.status}
        statusText={stages.semantic.valid === true ? 'Valid' : stages.semantic.valid === false ? 'Invalid' : undefined}
        isExpanded={expandedSections.semantic}
        onToggle={() => toggleSection('semantic')}
      >
        <SemanticViewer semantic={stages.semantic} />
      </CollapsibleSection>

      {/* Stage 4: Logical Query IR */}
      <CollapsibleSection
        id="section-logical_ir"
        stageNumber={4}
        title="Logical Intermediate Representation"
        subtitle="Query IR (WHAT to execute)"
        status={stages.logical_ir.status}
        isExpanded={expandedSections.logical_ir}
        onToggle={() => toggleSection('logical_ir')}
      >
        <LogicalPlanViewer logicalIr={stages.logical_ir} />
      </CollapsibleSection>

      {/* Stage 5: Physical Plan Generation */}
      <CollapsibleSection
        id="section-planner"
        stageNumber={5}
        title="Physical Execution Plan Generator"
        subtitle="Candidate Plan Permutations"
        status={stages.planner.status}
        statusText={stages.planner.candidate_count !== undefined ? `${stages.planner.candidate_count} Plans` : undefined}
        isExpanded={expandedSections.planner}
        onToggle={() => toggleSection('planner')}
      >
        <PhysicalPlanViewer planner={stages.planner} />
      </CollapsibleSection>

      {/* Stage 6: Cost Estimation */}
      <CollapsibleSection
        id="section-cost"
        stageNumber={6}
        title="Cost Estimator"
        subtitle="Intermediate Cardinalities & Plan Cost Model"
        status={stages.cost.status}
        isExpanded={expandedSections.cost}
        onToggle={() => toggleSection('cost')}
      >
        <CostViewer cost={stages.cost} selectedPlanId={stages.selector.selected_plan_id} />
      </CollapsibleSection>

      {/* Stage 7: Plan Selection */}
      <CollapsibleSection
        id="section-selector"
        stageNumber={7}
        title="Plan Selector"
        subtitle="Cost-Based Optimization Decision"
        status={stages.selector.status}
        statusText={stages.selector.selected_plan_id ? `Selected: ${stages.selector.selected_plan_id}` : undefined}
        isExpanded={expandedSections.selector}
        onToggle={() => toggleSection('selector')}
      >
        <SelectionViewer selector={stages.selector} />
      </CollapsibleSection>

      {/* Stage 8: Selected Plan Execution */}
      <CollapsibleSection
        id="section-execution"
        stageNumber={8}
        title="Selected Plan Execution"
        subtitle="Runtime Execution Engine & Verification"
        status={stages.execution.status}
        statusText={stages.execution.baseline_matched ? '100% Match' : undefined}
        isExpanded={expandedSections.execution}
        onToggle={() => toggleSection('execution')}
      >
        <ExecutionViewer execution={stages.execution} />
      </CollapsibleSection>

      {/* Stage 9: Runtime Adaptive Feedback */}
      <CollapsibleSection
        id="section-feedback"
        stageNumber={9}
        title="Runtime Adaptive Feedback"
        subtitle="Estimate vs Actual Cardinality & Learned Selectivity"
        status={stages.feedback.status}
        statusText={stages.feedback.learning_enabled ? 'Learning ON' : 'Learning OFF'}
        isExpanded={expandedSections.feedback}
        onToggle={() => toggleSection('feedback')}
      >
        <FeedbackViewer feedback={stages.feedback} />
      </CollapsibleSection>

      {/* Final Stage: Query Result */}
      <CollapsibleSection
        id="section-result"
        stageNumber={10}
        title="Query Result"
        subtitle="Final Result Relation"
        status={stages.result.status}
        statusText={stages.result.row_count !== undefined ? `${stages.result.row_count} Rows` : undefined}
        isExpanded={expandedSections.result}
        onToggle={() => toggleSection('result')}
      >
        <ResultViewer result={stages.result} />
      </CollapsibleSection>
    </div>
  );
};

export default App;
