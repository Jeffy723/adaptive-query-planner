# Adaptive Query Execution Planner

A **Compiler Design micro-project** that implements a mini SQL-like query language with an adaptive execution planner and an interactive visual compiler demonstration UI.

The system accepts a restricted SQL query, passes it through a classic compiler front-end pipeline, then generates, costs, selects, and executes query plans against a CSV dataset — complete with runtime adaptive selectivity learning — without any external database server.

---

## Project Goal & Pipeline

```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
  AND marks > 80
ORDER BY marks DESC;
```

Given a query like the one above, the system traces the complete compiler & execution lifecycle:

$$\text{Query} \to \text{Lexer} \to \text{Parser (AST)} \to \text{Semantic Validation} \to \text{Logical IR} \to \text{Physical Plans} \to \text{Cost Model} \to \text{Plan Selection} \to \text{Execution} \to \text{Adaptive Feedback} \to \text{Result}$$

| # | Stage | Module | Description |
|---|-------|--------|-------------|
| 1 | **Lexer** | `backend/lexer/` | Tokenises raw SQL query into typed lexical tokens with source coordinates |
| 2 | **Parser** | `backend/parser/` | Builds an Abstract Syntax Tree (AST) representing the syntactic structure |
| 3 | **Semantic Validator** | `backend/semantic/` | Checks table existence, column validity, and type/operator compatibility |
| 4 | **Logical Query IR** | `backend/ir/` | Produces language-independent relational algebra operations (`SCAN`, `FILTER`, `PROJECT`, `SORT`) |
| 5 | **Plan Generator** | `backend/planner/` | Generates semantically equivalent physical execution plans permuting filter orders |
| 6 | **Cost Estimator** | `backend/cost/` | Computes deterministic intermediate cardinalities and processing costs |
| 7 | **Plan Selector** | `backend/planner/` | Selects optimal plan with lowest total estimated cost |
| 8 | **Execution Engine** | `backend/executor/` | Executes selected plan against `students.csv` and verifies equivalence to baseline |
| 9 | **Runtime Feedback** | `backend/feedback/` | Compares estimated vs actual stats and updates predicate selectivities |
| 10 | **Interactive UI** | `frontend/` | React + TypeScript + Vite dashboard visualizing every compiler pass |

---

## Directory Structure

```
adaptive-query-planner/
├── backend/
│   ├── main.py          ← CLI pipeline demo
│   ├── server.py        ← REST API server for interactive UI
│   ├── pipeline.py      ← End-to-end orchestration
│   ├── lexer/           ← Stage 1: Lexical analysis
│   ├── parser/          ← Stage 2: Syntax parsing & AST
│   ├── semantic/        ← Stage 3: Semantic analysis & schema checks
│   ├── ir/              ← Stage 4: Logical intermediate representation
│   ├── planner/         ← Stage 5 & 7: Physical plan generator & selector
│   ├── cost/            ← Stage 6: Cost estimation model
│   ├── executor/        ← Stage 8: Query execution engine
│   └── feedback/        ← Stage 9: Runtime feedback & adaptive store
├── frontend/            ← Stage 10: Interactive Demonstration UI (React + Vite)
│   ├── src/
│   │   ├── components/  ← Stage-by-stage visualizers
│   │   ├── api/         ← REST API client
│   │   ├── types/       ← Pipeline TypeScript definitions
│   │   ├── styles/      ← Technical compiler theme
│   │   └── App.tsx      ← Master UI container
├── data/
│   └── students.csv     ← Dataset (200 records)
├── tests/               ← Complete backend pytest suite (722 tests)
├── docs/                ← Specifications and walkthroughs
│   ├── QUERY_LANGUAGE.md
│   ├── COST_MODEL.md
│   ├── PLAN_SELECTOR.md
│   ├── END_TO_END.md
│   ├── ADAPTIVE_FEEDBACK.md
│   └── UI.md
├── pyproject.toml
└── requirements.txt
```

---

## Quick Start

### 1. Backend Setup & Tests
```powershell
# 1. Activate virtual environment
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 3. Run full backend test suite (722 tests)
pytest

# 4. Run CLI demonstration
python -m backend.main
```

### 2. Start the Interactive UI
```powershell
# Terminal 1: Start the backend REST API server (port 5000)
.venv\Scripts\python.exe -m backend.server

# Terminal 2: Start the frontend development server (port 5173)
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** in your web browser.

### 3. Run Frontend Tests
```powershell
cd frontend
npm test
```

---

## Implementation Status

All stages are fully implemented and verified:

| Stage | Status | Tests |
|-------|--------|-------|
| Project foundation & dataset | ✅ Complete | 8 tests |
| Lexer | ✅ Complete | 114 tests |
| Parser & AST | ✅ Complete | 277 tests |
| Semantic validator | ✅ Complete | 87 tests |
| Logical Query IR | ✅ Complete | 75 tests |
| Physical plan generator | ✅ Complete | 69 tests |
| Cost model estimator | ✅ Complete | 21 tests |
| Plan selector | ✅ Complete | 18 tests |
| Selected plan execution & verification | ✅ Complete | 27 tests |
| Runtime adaptive feedback | ✅ Complete | 20 tests |
| Backend REST API | ✅ Complete | 6 tests |
| Interactive Demonstration UI (React/TS) | ✅ Complete | 3 test suites |
| **Total Backend Verification** | ✅ **722 Passing** | |
