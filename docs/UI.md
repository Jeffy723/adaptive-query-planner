# Interactive Demonstration UI Specification

**Adaptive Query Execution Planner for a Mini SQL-like Query Language**  
*Compiler Design Laboratory / Microproject*

---

## 1. Overview & Pedagogical Objective

The **Interactive Demonstration UI** provides a visual dashboard for instructors, students, and evaluators to trace the complete internal compilation and execution pipeline of a query language from raw text to execution results.

Instead of hiding compiler passes behind a single generic database execution button, the interface exposes every distinct Compiler Design stage:

$$\text{Query} \to \text{Lexer} \to \text{Parser (AST)} \to \text{Semantic Validation} \to \text{Logical IR} \to \text{Physical Plans} \to \text{Cost Model} \to \text{Plan Selection} \to \text{Execution} \to \text{Adaptive Feedback} \to \text{Result}$$

---

## 2. Frontend Architecture

The frontend is built with:
- **React 19**
- **TypeScript 5.x**
- **Vite 6.x**
- **Custom Technical CSS Theme** (`theme.css`) focused on high-contrast technical data display, monospace typography, and responsive grid layouts.

```
frontend/
├── package.json               # Frontend dependencies (React, TypeScript, Vitest)
├── vite.config.ts             # Vite configuration with /api reverse proxy and Vitest setup
├── tsconfig.json              # Strict TypeScript compiler options
└── src/
    ├── types/
    │   └── pipeline.ts        # TypeScript interfaces mirroring backend data models
    ├── api/
    │   └── client.ts          # HTTP client for REST API endpoints
    ├── styles/
    │   └── theme.css          # Technical compiler dashboard stylesheet
    ├── components/
    │   ├── Header.tsx             # Application branding and backend connection badge
    │   ├── PipelineTracker.tsx    # Global interactive status bar (NOT RUN, PASSED, ERROR)
    │   ├── QueryEditor.tsx        # SQL-like text editor with example presets and options
    │   ├── CollapsibleSection.tsx # Reusable accordion card for each pipeline stage
    │   ├── TokenViewer.tsx        # Stage 1: Lexical analysis token stream table
    │   ├── ASTViewer.tsx          # Stage 2: Syntax analysis tree diagram & structured JSON
    │   ├── SemanticViewer.tsx     # Stage 3: Schema checks & error diagnostics
    │   ├── LogicalPlanViewer.tsx  # Stage 4: Logical IR operation flow diagram
    │   ├── PhysicalPlanViewer.tsx # Stage 5: Candidate physical execution plans
    │   ├── CostViewer.tsx         # Stage 6: Cost model comparison & operation breakdowns
    │   ├── SelectionViewer.tsx    # Stage 7: Selected plan decision and rank table
    │   ├── ExecutionViewer.tsx    # Stage 8: Physical execution & actual runtime stats
    │   ├── FeedbackViewer.tsx     # Stage 9: Runtime feedback & adaptive selectivity updates
    │   └── ResultViewer.tsx       # Stage 10: Final relation output table
    ├── App.tsx                # Master orchestration state container
    ├── main.tsx               # DOM entry point
    └── __tests__/
        └── App.test.tsx       # Comprehensive Vitest/Testing Library test suite
```

---

## 3. Backend REST API (`backend/server.py`)

A lightweight Flask REST API (`backend/server.py`) with CORS and proxy support connects the React frontend directly to the underlying compiler pipeline:

### 3.1. `GET /api/health`
Checks server availability and dataset status.
- **Response**: `{"status": "ok", "version": "1.0.0", "dataset": "students", "dataset_rows": 200}`

### 3.2. `GET /api/examples`
Returns supported benchmark queries for instant loading into the editor.
- **Response**: List of `{id, title, query, description}`.

### 3.3. `POST /api/query/execute`
Compiles and executes a query through all compiler stages.
- **Request Body**:
  ```json
  {
    "query": "SELECT name, marks FROM students WHERE department = 'CSE' AND marks > 80 ORDER BY marks DESC;",
    "enable_learning": false,
    "alpha": 0.5,
    "reset_learned_stats": false
  }
  ```
- **Response**: Complete stage-by-stage payload containing real backend data:
  ```json
  {
    "success": true,
    "query": "...",
    "error": null,
    "active_stage": "completed",
    "stages": {
      "lexer": { "status": "PASSED", "token_count": 23, "tokens": [...] },
      "parser": { "status": "PASSED", "ast_tree_text": "...", "ast": {...} },
      "semantic": { "status": "PASSED", "valid": true, "table": "students", "checks": [...] },
      "logical_ir": { "status": "PASSED", "operations": [...] },
      "planner": { "status": "PASSED", "candidate_count": 2, "plans": [...] },
      "cost": { "status": "PASSED", "plan_costs": {"plan_A": 278.0, "plan_B": 331.0}, "estimates": [...] },
      "selector": { "status": "PASSED", "selected_plan_id": "plan_A", "reason": "..." },
      "execution": { "status": "PASSED", "rows_returned": 13, "statistics": [...] },
      "feedback": { "status": "PASSED", "total_absolute_error": 3, "operations": [...] },
      "result": { "status": "PASSED", "columns": ["name", "marks"], "rows": [...], "row_count": 13 }
    }
  }
  ```

### 3.4. `POST /api/adaptive/reset`
Clears in-memory learned selectivity profiles back to default static state.

---

## 4. Visible Pipeline Stages

1. **Query Specification**: SQL-like text editor with example loader, adaptive learning toggle, smoothing factor $\alpha$ input, and execute button.
2. **Pipeline Status Tracker**: Compact horizontal bar displaying the status (`PASSED`, `ERROR`, `NOT_RUN`, `RUNNING`) of every step. Clicking any node auto-scrolls to and expands that stage.
3. **Stage 1 (Lexer)**: Interactive token table with 1-based indices, token categories (`KEYWORD`, `IDENTIFIER`, `NUMBER`, `STRING`, `OPERATOR`, `COMMA`), lexeme values, and line/column coordinates.
4. **Stage 2 (Parser)**: Syntax validation status, printable ASCII diagram tree (`QUERY ├── SELECT ...`), and raw AST JSON tree inspector.
5. **Stage 3 (Semantic Analysis)**: Validated table and resolved columns, checklist of schema constraints, and error diagnostics with exact source coordinates if invalid.
6. **Stage 4 (Logical Query IR)**: Visual relational algebra operator chain (`SCAN` $\downarrow$ `FILTER` $\downarrow$ `PROJECT` $\downarrow$ `SORT`) representing the language-independent query plan.
7. **Stage 5 (Physical Plan Generator)**: Side-by-side candidate execution plans permuting filter orders (`plan_A` vs `plan_B`), with filter evaluation orders clearly labeled.
8. **Stage 6 (Cost Estimator)**: Horizontal bar comparison chart and detailed per-operation cardinality and cost breakdown tables.
9. **Stage 7 (Plan Selector)**: Highlighted winning plan (`plan_A`), cost savings percentage explanation, and ranked candidate table.
10. **Stage 8 (Selected Plan Execution)**: Runtime operator statistics (estimated input vs actual input, estimated output vs actual output), baseline verification status, and row count.
11. **Stage 9 (Runtime Adaptive Feedback)**: Summary error metrics (total output error, max error, average relative error %), operator accuracy table with signed differences, and updated filter selectivity formulas ($s_{\text{learned}} = \alpha \cdot s_{\text{obs}} + (1 - \alpha) \cdot s_{\text{prev}}$).
12. **Final Query Result**: Clean, formatted tabular presentation of returned tuples.

---

## 5. How to Run the Complete Application

### Prerequisites
- Python 3.10+ with the project virtual environment installed (`.venv`)
- Node.js v18+ and npm

### Step 1: Start the Backend API Server
In the project root directory:
```powershell
# Using the project virtual environment
.venv\Scripts\python.exe -m backend.server
```
The server will start listening on `http://127.0.0.1:5000`.

### Step 2: Start the Frontend Development Server
In a separate terminal window, navigate to the `frontend/` directory:
```powershell
cd frontend
npm run dev
```
Vite will start the development server on `http://localhost:5173`. Open this URL in any modern web browser.

### Step 3: Run the Test Suites
- **Backend Test Suite (722 tests)**:
  ```powershell
  .venv\Scripts\pytest -v --tb=short
  ```
- **Frontend Test Suite (Vitest)**:
  ```powershell
  cd frontend
  npm test
  ```
