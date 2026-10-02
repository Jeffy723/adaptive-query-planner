/**
 * frontend/src/types/pipeline.ts
 *
 * TypeScript type definitions mirroring backend data models across all compiler
 * and query execution stages.
 */

export type StageStatus = 'NOT_RUN' | 'RUNNING' | 'PASSED' | 'ERROR';

export interface TokenItem {
  index: number;
  type: string;
  value: string;
  line: number;
  col: number;
}

export interface LexerStage {
  status: StageStatus;
  token_count?: number;
  tokens?: TokenItem[];
  error?: {
    message: string;
    line?: number;
    col?: number;
  };
}

export interface ParserStage {
  status: StageStatus;
  ast_tree_text?: string;
  ast?: Record<string, unknown>;
  error?: {
    message: string;
    line?: number;
    col?: number;
  };
}

export interface SemanticCheck {
  name: string;
  description: string;
  passed: boolean;
}

export interface SemanticErrorItem {
  code: string;
  message: string;
  line: number;
  col: number;
}

export interface SemanticStage {
  status: StageStatus;
  valid?: boolean;
  table?: string;
  resolved_columns?: string[];
  checks?: SemanticCheck[];
  errors?: SemanticErrorItem[];
  error_count?: number;
}

export interface IROperation {
  index: number;
  type: string;
  description: string;
}

export interface LogicalIRStage {
  status: StageStatus;
  source_table?: string;
  operations?: IROperation[];
  explain_text?: string;
}

export interface PhysicalOperationItem {
  type: string;
  description: string;
}

export interface PhysicalPlanItem {
  plan_id: string;
  description: string;
  pipeline: string;
  operations: PhysicalOperationItem[];
  filter_order: string[];
  is_selected: boolean;
}

export interface PlannerStage {
  status: StageStatus;
  candidate_count?: number;
  plans?: PhysicalPlanItem[];
}

export interface OperationCostEstimateItem {
  operation: string;
  operation_type: string;
  input_rows: number;
  output_rows: number;
  cost: number;
  selectivity: number | null;
  description: string;
}

export interface PlanCostEstimateItem {
  plan_id: string;
  total_cost: number;
  operations: OperationCostEstimateItem[];
}

export interface CostStage {
  status: StageStatus;
  plan_costs?: Record<string, number>;
  estimates?: PlanCostEstimateItem[];
}

export interface RankedCandidateItem {
  rank: number;
  plan_id: string;
  cost: number;
  is_selected: boolean;
}

export interface SelectorStage {
  status: StageStatus;
  selected_plan_id?: string;
  selected_cost?: number;
  selection_rule?: string;
  reason?: string;
  ranked_candidates?: RankedCandidateItem[];
}

export interface ExecutionStatItem {
  operation: string;
  operation_type: string;
  estimated_input: number;
  actual_input: number;
  estimated_output: number;
  actual_output: number;
}

export interface ExecutionStage {
  status: StageStatus;
  selected_plan_id?: string;
  rows_returned?: number;
  baseline_matched?: boolean;
  statistics?: ExecutionStatItem[];
}

export interface SelectivityFeedbackItem {
  predicate: string;
  previous_selectivity: number;
  observed_selectivity: number;
  updated_selectivity: number;
  alpha: number;
}

export interface OperationFeedbackItem {
  operation: string;
  operation_type: string;
  estimated_input: number;
  actual_input: number;
  estimated_output: number;
  actual_output: number;
  difference: number;
  absolute_error: number;
  relative_error: number;
  relative_error_percentage: number;
  selectivity_feedback: SelectivityFeedbackItem | null;
}

export interface FeedbackStage {
  status: StageStatus;
  learning_enabled?: boolean;
  selected_plan_id?: string;
  total_absolute_error?: number;
  max_absolute_error?: number;
  average_relative_error?: number;
  operations?: OperationFeedbackItem[];
  stored_profile_count?: number;
  explain_text?: string;
}

export interface ResultStage {
  status: StageStatus;
  columns?: string[];
  rows?: Record<string, unknown>[];
  row_count?: number;
}

export interface PipelineStages {
  lexer: LexerStage;
  parser: ParserStage;
  semantic: SemanticStage;
  logical_ir: LogicalIRStage;
  planner: PlannerStage;
  cost: CostStage;
  selector: SelectorStage;
  execution: ExecutionStage;
  feedback: FeedbackStage;
  result: ResultStage;
}

export interface PipelineError {
  stage: string;
  message: string;
  line?: number;
  col?: number;
  errors?: SemanticErrorItem[];
}

export interface PipelineResponse {
  success: boolean;
  query: string;
  error: PipelineError | null;
  active_stage: string;
  stages: PipelineStages;
}

export interface ExampleQuery {
  id: string;
  title: string;
  query: string;
  description: string;
}
