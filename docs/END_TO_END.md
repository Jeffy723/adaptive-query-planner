# End-to-End Pipeline & Correctness Verification

**Adaptive Query Execution Planner for a Mini SQL-like Query Language**  
*Compiler Design Laboratory / Microproject Specification*

---

## 1. Complete Architecture Overview

The system compiles, optimizes, executes, and verifies restricted SQL-like queries through a unified 9-stage pipeline:

```
                          SQL Query String
                                ↓
                       [ 1. Lexical Analyzer ]
                                ↓ Token Stream
                       [ 2. Recursive-Descent Parser ]
                                ↓ Abstract Syntax Tree (AST)
                       [ 3. Semantic Analyzer ]
                                ↓ Validated AST + Schema
                       [ 4. Logical IR Builder ]
                                ↓ LogicalPlan (SCAN → FILTER → PROJECT → SORT)
                       [ 5. Physical Plan Generator ]
                                ↓ Alternative PhysicalPlans (Permuted Filters)
                       [ 6. Cost Estimator ]
                                ↓ Per-Plan Estimated Costs & Cardinalities
                       [ 7. Plan Selector ]
                                ↓ Optimal PhysicalPlan (Lowest Cost)
                       [ 8. Execution Engine ]
                                ↓ ExecutionResult
                       [ 9. Result Verifier ]
                                ↓ (Selected Plan Result == Logical Baseline)
                          Final Verified Result
```

---

## 2. Stage-by-Stage Breakdown

### Stage 1: Lexical Analysis (`backend.lexer`)
- Scans the raw SQL query character-by-character.
- Emits typed tokens (`SELECT`, `IDENTIFIER`, `COMMA`, `OPERATOR`, `STRING`, `INTEGER`, etc.).
- Rejects invalid characters and malformed literal tokens with line and column numbers.

### Stage 2: Syntactic Parsing (`backend.parser`)
- Consumes the token stream using recursive descent.
- Constructs an Abstract Syntax Tree (`Query`, `SelectClause`, `FromClause`, `WhereClause`, `OrderByClause`).
- Enforces grammar structure: `SELECT ... FROM ... [WHERE ...] [ORDER BY ...]`.

### Stage 3: Semantic Analysis (`backend.semantic`)
- Validates the AST against the schema (`STUDENTS_SCHEMA`).
- Checks:
  - Table existence (`students`).
  - Column existence in `SELECT`, `WHERE`, and `ORDER BY`.
  - Type compatibility between columns and literal constants.
  - Operator compatibility (e.g. preventing `<` or `>` on string columns).
- Expands `SELECT *` into the concrete list of schema column names.

### Stage 4: Logical IR (`backend.ir`)
- Converts the validated AST into a syntax-independent relational plan: `LogicalPlan`.
- Standard canonical structure: `ScanOp` $\to$ `FilterOp` $\to$ `ProjectOp` $\to$ `[SortOp]`.
- Completely decoupled from parser AST structures.

### Stage 5: Physical Plan Generation (`backend.planner.generator`)
- Explores alternative execution strategies by decomposing conjunctive filter predicates.
- Decomposes top-level `AND` conditions into independent filter stages.
- Generates alternative filter orderings (e.g. Plan A vs Plan B) while leaving `OR` expressions intact.
- Preserves `SCAN`, `PROJECT`, and `SORT` in their established positions.

### Stage 6: Cost Estimation (`backend.cost.estimator`)
- Assigns a deterministic processing cost to each candidate physical plan.
- Calculates exact single-predicate selectivities from actual dataset statistics (`DatasetStatistics`).
- Estimates cascading intermediate row counts:
  $$N_{\text{out}} = \max\left(1, \text{round}(N_{\text{in}} \cdot s)\right)$$
- Computes operation costs:
  - Scan: $N_{\text{table}}$
  - Filter: $N_{\text{in}}$
  - Project: $N_{\text{in}}$
  - Sort: $N_{\text{in}} \cdot \log_2(N_{\text{in}})$

### Stage 7: Plan Selection (`backend.planner.selector`)
- Evaluates candidate plans and their estimated costs.
- Selects the plan with the lowest estimated total cost.
- Resolves ties deterministically using plan identifier lexicographical ordering.

### Stage 8: Physical Plan Execution (`backend.executor`)
- Executes the selected plan against the CSV dataset (`data/students.csv`).
- Seamlessly consumes the physical plan through the thin `.to_logical()` adapter.
- Records deterministic per-operation execution statistics (actual input and output row counts).

### Stage 9: Baseline Correctness Verification (`backend.pipeline`)
- Concurrently runs the canonical logical IR plan through the executor as a ground-truth baseline.
- Asserts strict equivalence between the selected physical plan's output and the logical baseline:
  - Identical column names and order.
  - Identical row count.
  - Identical row dictionaries and tuple sequence (preserving `ORDER BY` ordering).
- Raises `ResultMismatchError` immediately if any divergence is detected.

---

## 3. Why Result Verification Is Performed

In query optimization, the cardinal rule is:
> **An optimization that produces incorrect results is not an optimization; it is a bug.**

Alternative physical plans reorder operations to reduce intermediate data volume. However, the user expects the **exact same query results** regardless of the plan chosen by the optimizer.

By automatically running both:
1. $\text{Result}_{\text{physical}} = \text{Execute}(\text{Selected Physical Plan})$
2. $\text{Result}_{\text{logical}} = \text{Execute}(\text{Canonical Logical Plan})$

and verifying $\text{Result}_{\text{physical}} \equiv \text{Result}_{\text{logical}}$, the system provides an automated formal correctness proof for every executed query.

---

## 4. Reference Query Walkthrough

```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;
```

### Complete Demonstration Report (`result.explain()`):

```
======================================================================
QUERY:
  SELECT name, marks
  FROM students
  WHERE department = 'CSE'
  AND marks > 80
  ORDER BY marks DESC;

LOGICAL PLAN:
  SCAN students
  FILTER (department = 'CSE' AND marks > 80)
  PROJECT name, marks
  SORT marks DESC

ALTERNATIVE PLANS & ESTIMATED COSTS (2 generated):
  plan_A   (Cost:   493.02)  <-- SELECTED
    Pipeline: SCAN students -> FILTER department = 'CSE' -> FILTER marks > 80 -> PROJECT name, marks -> SORT marks DESC
  plan_B   (Cost:   520.02)
    Pipeline: SCAN students -> FILTER marks > 80 -> FILTER department = 'CSE' -> PROJECT name, marks -> SORT marks DESC

SELECTED PLAN:
  plan_A (Estimated Cost: 493.02)
  Reason: Lowest estimated total cost (493.02 vs plan_B at 520.02, saving 27.00 cost units).

EXECUTION RESULT:
  Rows returned: 13
  Columns: ['name', 'marks']
  Execution Statistics:
    SCAN students: input=0 -> output=200
    FILTER department = 'CSE': input=200 -> output=38
    FILTER marks > 80: input=38 -> output=13
    PROJECT name, marks: input=13 -> output=13
    SORT marks DESC: input=13 -> output=13

CORRECTNESS VERIFICATION:
  Selected plan result == logical baseline result: YES (Identical columns, row count, and ordered tuples)
======================================================================
```

---

## 5. Returned Tuples (Reference Query)

| Rank | Name | Marks |
| :---: | :--- | :---: |
| 1 | Donna | 96 |
| 2 | Brenda | 96 |
| 3 | Sam | 95 |
| 4 | Isla | 91 |
| 5 | Umar | 89 |
| 6 | Carlos | 89 |
| 7 | Harsh | 89 |
| 8 | Alice | 87 |
| 9 | Tarun | 87 |
| 10 | Victor | 87 |
| 11 | Judy | 84 |
| 12 | Zaid | 82 |
| 13 | Eve | 82 |

*(13 qualifying students, department = 'CSE', marks > 80, sorted descending by marks).*
