/**
 * frontend/src/__tests__/App.test.tsx
 *
 * Unit and integration tests for the Interactive Demonstration UI:
 * - Query editor renders with default query and examples
 * - Execution triggering and stage updates
 * - Lexer tokens table rendering
 * - Parser AST tree rendering
 * - Semantic analysis validation & error display
 * - Logical IR flow display
 * - Physical plan generation display
 * - Cost comparison & bar display
 * - Plan selection highlighting
 * - Execution statistics comparison
 * - Adaptive feedback & learned selectivity
 * - Final query result table
 * - Error handling for parser/semantic errors
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';
import * as apiClient from '../api/client';
import type { PipelineResponse } from '../types/pipeline';

// Mock response for reference query
const MOCK_REFERENCE_RESPONSE: PipelineResponse = {
  success: true,
  query: "SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;",
  error: null,
  active_stage: 'completed',
  stages: {
    lexer: {
      status: 'PASSED',
      token_count: 5,
      tokens: [
        { index: 1, type: 'KEYWORD', value: 'SELECT', line: 1, col: 1 },
        { index: 2, type: 'IDENTIFIER', value: 'name', line: 1, col: 8 },
        { index: 3, type: 'COMMA', value: ',', line: 1, col: 12 },
        { index: 4, type: 'IDENTIFIER', value: 'marks', line: 1, col: 14 },
        { index: 5, type: 'KEYWORD', value: 'FROM', line: 2, col: 1 },
      ],
    },
    parser: {
      status: 'PASSED',
      ast_tree_text: 'QUERY\n├── SELECT\n│   ├── name\n│   └── marks\n└── FROM\n    └── students',
      ast: { type: 'Query' },
    },
    semantic: {
      status: 'PASSED',
      valid: true,
      table: 'students',
      resolved_columns: ['name', 'marks'],
      checks: [
        { name: 'Dataset existence', description: "Table 'students' exists", passed: true },
        { name: 'SELECT column validation', description: 'Columns exist', passed: true },
      ],
    },
    logical_ir: {
      status: 'PASSED',
      source_table: 'students',
      operations: [
        { index: 1, type: 'SCAN', description: 'SCAN students' },
        { index: 2, type: 'FILTER', description: "FILTER department = 'CSE' AND marks > 80" },
        { index: 3, type: 'PROJECT', description: 'PROJECT name, marks' },
        { index: 4, type: 'SORT', description: 'SORT marks DESC' },
      ],
      explain_text: 'LOGICAL PLAN: ...',
    },
    planner: {
      status: 'PASSED',
      candidate_count: 2,
      plans: [
        {
          plan_id: 'plan_A',
          description: 'Filter department first, then marks',
          pipeline: 'SCAN -> FILTER department -> FILTER marks -> PROJECT -> SORT',
          operations: [
            { type: 'SCAN', description: 'SCAN students' },
            { type: 'FILTER', description: "FILTER department = 'CSE'" },
            { type: 'FILTER', description: 'FILTER marks > 80' },
          ],
          filter_order: ["department = 'CSE'", 'marks > 80'],
          is_selected: true,
        },
        {
          plan_id: 'plan_B',
          description: 'Filter marks first, then department',
          pipeline: 'SCAN -> FILTER marks -> FILTER department -> PROJECT -> SORT',
          operations: [
            { type: 'SCAN', description: 'SCAN students' },
            { type: 'FILTER', description: 'FILTER marks > 80' },
            { type: 'FILTER', description: "FILTER department = 'CSE'" },
          ],
          filter_order: ['marks > 80', "department = 'CSE'"],
          is_selected: false,
        },
      ],
    },
    cost: {
      status: 'PASSED',
      plan_costs: { plan_A: 278.0, plan_B: 331.0 },
      estimates: [
        {
          plan_id: 'plan_A',
          total_cost: 278.0,
          operations: [
            {
              operation: 'SCAN students',
              operation_type: 'SCAN',
              input_rows: 0,
              output_rows: 200,
              cost: 200.0,
              selectivity: null,
              description: 'Read rows',
            },
            {
              operation: "FILTER department = 'CSE'",
              operation_type: 'FILTER',
              input_rows: 200,
              output_rows: 38,
              cost: 200.0,
              selectivity: 0.19,
              description: 'Filter CSE',
            },
          ],
        },
        {
          plan_id: 'plan_B',
          total_cost: 331.0,
          operations: [
            {
              operation: 'SCAN students',
              operation_type: 'SCAN',
              input_rows: 0,
              output_rows: 200,
              cost: 200.0,
              selectivity: null,
              description: 'Read rows',
            },
          ],
        },
      ],
    },
    selector: {
      status: 'PASSED',
      selected_plan_id: 'plan_A',
      selected_cost: 278.0,
      selection_rule: 'Lowest estimated total processing cost according to current cost model',
      reason: 'Plan plan_A has lowest cost (278.00 vs 331.00)',
      ranked_candidates: [
        { rank: 1, plan_id: 'plan_A', cost: 278.0, is_selected: true },
        { rank: 2, plan_id: 'plan_B', cost: 331.0, is_selected: false },
      ],
    },
    execution: {
      status: 'PASSED',
      selected_plan_id: 'plan_A',
      rows_returned: 13,
      baseline_matched: true,
      statistics: [
        {
          operation: 'SCAN students',
          operation_type: 'SCAN',
          estimated_input: 0,
          actual_input: 0,
          estimated_output: 200,
          actual_output: 200,
        },
        {
          operation: "FILTER department = 'CSE'",
          operation_type: 'FILTER',
          estimated_input: 200,
          actual_input: 200,
          estimated_output: 38,
          actual_output: 38,
        },
        {
          operation: 'FILTER marks > 80',
          operation_type: 'FILTER',
          estimated_input: 38,
          actual_input: 38,
          estimated_output: 12,
          actual_output: 13,
        },
      ],
    },
    feedback: {
      status: 'PASSED',
      learning_enabled: false,
      selected_plan_id: 'plan_A',
      total_absolute_error: 1,
      max_absolute_error: 1,
      average_relative_error: 7.69,
      operations: [
        {
          operation: 'FILTER marks > 80',
          operation_type: 'FILTER',
          estimated_input: 38,
          actual_input: 38,
          estimated_output: 12,
          actual_output: 13,
          difference: 1,
          absolute_error: 1,
          relative_error: 0.0769,
          relative_error_percentage: 7.69,
          selectivity_feedback: {
            predicate: 'FILTER marks > 80',
            previous_selectivity: 0.325,
            observed_selectivity: 0.3421,
            updated_selectivity: 0.3336,
            alpha: 0.5,
          },
        },
      ],
      explain_text: 'FEEDBACK REPORT: ...',
    },
    result: {
      status: 'PASSED',
      columns: ['name', 'marks'],
      rows: [
        { name: 'Alice', marks: 95 },
        { name: 'Bob', marks: 88 },
      ],
      row_count: 2,
    },
  },
};

describe('Interactive Demonstration UI Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(apiClient, 'fetchHealth').mockResolvedValue({ status: 'ok', dataset_rows: 200 });
    vi.spyOn(apiClient, 'fetchExamples').mockResolvedValue([
      { id: 'ref', title: 'Reference Query', query: 'SELECT name FROM students;', description: 'Demo' },
    ]);
  });

  it('1. Query editor renders with default query and controls', () => {
    render(<App />);
    expect(screen.getByText(/ADAPTIVE QUERY EXECUTION PLANNER/i)).toBeInTheDocument();
    expect(screen.getByText(/Execute Query/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Enter SQL-like query/i)).toBeInTheDocument();
  });

  it('2. Execute button sends query and populates pipeline stages', async () => {
    const executeSpy = vi.spyOn(apiClient, 'executeQuery').mockResolvedValue(MOCK_REFERENCE_RESPONSE);
    render(<App />);

    const execBtn = screen.getByRole('button', { name: /Execute Query/i });
    fireEvent.click(execBtn);

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalled();
    });

    // Expand all sections to test all stages visible
    const expandAllBtn = screen.getByRole('button', { name: /Expand All Stages/i });
    fireEvent.click(expandAllBtn);

    // 3. Lexer section displays tokens
    expect(screen.getByText('Lexical Analysis (Lexer)')).toBeInTheDocument();
    expect(screen.getAllByText('SELECT').length).toBeGreaterThan(0);
    expect(screen.getAllByText('marks').length).toBeGreaterThan(0);

    // 4. Parser section displays AST
    expect(screen.getByText('Syntax Analysis (Parser)')).toBeInTheDocument();
    expect(screen.getByText(/Parsing successful/i)).toBeInTheDocument();
    expect(screen.getByText(/├── SELECT/i)).toBeInTheDocument();

    // 5. Semantic section displays validation result
    expect(screen.getByText('Semantic Analysis')).toBeInTheDocument();
    expect(screen.getByText(/Table 'students' exists/i)).toBeInTheDocument();

    // 6. Logical IR section displays IR
    expect(screen.getByText('Logical Intermediate Representation')).toBeInTheDocument();
    expect(screen.getAllByText(/SCAN students/i).length).toBeGreaterThan(0);

    // 7. Physical plans are displayed
    expect(screen.getByText('Physical Execution Plan Generator')).toBeInTheDocument();
    expect(screen.getAllByText('plan_A').length).toBeGreaterThan(0);
    expect(screen.getAllByText('plan_B').length).toBeGreaterThan(0);

    // 8. Cost comparison is displayed
    expect(screen.getByText('Cost Estimator')).toBeInTheDocument();
    expect(screen.getAllByText(/Detailed Cost Breakdown/i).length).toBeGreaterThan(0);

    // 9. Selected plan is highlighted
    expect(screen.getByText('Plan Selector')).toBeInTheDocument();
    expect(screen.getByText(/Selected Execution Plan: plan_A/i)).toBeInTheDocument();

    // 10. Execution statistics are displayed
    expect(screen.getByText('Selected Plan Execution')).toBeInTheDocument();
    expect(screen.getAllByText(/100% Match/i).length).toBeGreaterThan(0);

    // 11. Adaptive feedback is displayed
    expect(screen.getByText('Runtime Adaptive Feedback')).toBeInTheDocument();
    expect(screen.getByText(/Total Output Error/i)).toBeInTheDocument();

    // 12. Final result table is displayed
    expect(screen.getByText('Query Result')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('13. Backend error (semantic/parser) is displayed correctly without crashing', async () => {
    vi.spyOn(apiClient, 'executeQuery').mockResolvedValue({
      success: false,
      query: 'SELECT salary FROM students;',
      error: {
        stage: 'semantic',
        message: "Column 'salary' does not exist in table 'students'.",
        line: 1,
        col: 8,
      },
      active_stage: 'semantic',
      stages: {
        ...MOCK_REFERENCE_RESPONSE.stages,
        semantic: {
          status: 'ERROR',
          valid: false,
          errors: [
            {
              code: 'UNKNOWN_COLUMN',
              message: "Column 'salary' does not exist in table 'students'.",
              line: 1,
              col: 8,
            },
          ],
        },
        logical_ir: { status: 'NOT_RUN' },
      },
    });

    render(<App />);
    const execBtn = screen.getByRole('button', { name: /Execute Query/i });
    fireEvent.click(execBtn);

    await waitFor(() => {
      expect(screen.getByText(/Compilation \/ Execution Halt/i)).toBeInTheDocument();
      expect(screen.getAllByText(/Column 'salary' does not exist in table/i).length).toBeGreaterThan(0);
    });
  });
});
