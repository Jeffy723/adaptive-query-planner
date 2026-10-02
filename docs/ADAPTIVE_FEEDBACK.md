# Runtime Feedback & Adaptive Statistics Learning Specification

**Adaptive Query Execution Planner for a Mini SQL-like Query Language**  
*Compiler Design Laboratory / Microproject*

---

## 1. Motivation: Closing the Query Optimization Loop

In traditional static compilers, optimization passes make decisions based on static heuristics. Similarly, classical database cost-based optimizers estimate query plan costs using pre-computed table statistics and simplifying assumptions (such as attribute independence).

However, static estimates often diverge from reality due to:
1. **Attribute Correlation**: Two predicates may not be statistically independent (e.g. higher marks in specific departments).
2. **Data Distribution Skew**: Non-uniform distributions across subsets of the dataset.
3. **Compound Filters**: Chained filter operations where the output distribution of the first filter changes the input distribution of the second.

The **Runtime Feedback & Adaptive Learning Component** closes this optimization loop by measuring what actually happens during query execution, comparing actual metrics against compile-time estimates, and feeding updated empirical statistics back into future planning passes:

```
             QUERY
               ↓
        COMPILER PIPELINE
               ↓
        LOGICAL QUERY IR
               ↓
      ALTERNATIVE PLANS
          ↙          ↘
       PLAN A       PLAN B
          ↓          ↓
        COST        COST
          ↘          ↙
        PLAN SELECTOR
               ↓
        SELECTED PLAN
               ↓
           EXECUTE
               ↓
          ACTUAL STATS
               ↓
       ┌───────────────┐
       │    FEEDBACK   │
       └───────┬───────┘
               ↓
       UPDATED STATISTICS
               ↓
        FUTURE RUNS
```

---

## 2. Estimated vs. Actual Statistics

For every physical operator in the executed plan, the system collects and compares:

| Metric | Source | Description |
| :--- | :--- | :--- |
| **Estimated Input Rows** | `CostEstimator` | Expected number of input records entering the operator |
| **Actual Input Rows** | `Executor` (Runtime) | True count of records piped into the operator |
| **Estimated Output Rows** | `CostEstimator` | Expected cardinality after operator processing |
| **Actual Output Rows** | `Executor` (Runtime) | True cardinality produced by the operator |
| **Previous Selectivity** | `CostEstimator` | Selectivity factor $\in [0.0, 1.0]$ assumed before run |
| **Observed Selectivity** | `Executor` (Runtime) | Empirical ratio: $\frac{\text{actual output rows}}{\text{actual input rows}}$ |

---

## 3. Error Metrics & Formulations

For each operator $i$, the feedback component computes deterministic error metrics:

### 3.1. Signed Difference
$$\text{diff}_i = \text{actual\_output\_rows}_i - \text{estimated\_output\_rows}_i$$
- $\text{diff}_i > 0$: Cost model underestimated cardinality.
- $\text{diff}_i < 0$: Cost model overestimated cardinality.
- $\text{diff}_i = 0$: Perfect estimation.

### 3.2. Absolute Error
$$\text{abs\_err}_i = |\text{estimated\_output\_rows}_i - \text{actual\_output\_rows}_i|$$

### 3.3. Relative Error & Percentage
$$\text{rel\_err}_i = \begin{cases} 
\frac{\text{abs\_err}_i}{\text{actual\_output\_rows}_i}, & \text{if } \text{actual\_output\_rows}_i > 0 \\
0.0, & \text{if } \text{actual\_output\_rows}_i = 0 \text{ and } \text{estimated\_output\_rows}_i = 0 \\
1.0, & \text{if } \text{actual\_output\_rows}_i = 0 \text{ and } \text{estimated\_output\_rows}_i > 0
\end{cases}$$

$$\text{rel\_err\_pct}_i = \text{rel\_err}_i \times 100\%$$

### 3.4. Query-Level Aggregate Metrics
- **Total Absolute Error**: $\sum_i \text{abs\_err}_i$
- **Max Absolute Error**: $\max_i \text{abs\_err}_i$
- **Average Relative Error**: $\frac{1}{N} \sum_{i=1}^N \text{rel\_err\_pct}_i$

---

## 4. Adaptive Selectivity Update Rule

When a filter predicate is evaluated, its observed selectivity is calculated as:
$$\text{observed\_selectivity} = \frac{\text{actual\_output\_rows}}{\max(1, \text{actual\_input\_rows})}$$

The new selectivity value stored for future cost estimation is updated using an Exponentially Weighted Moving Average (EWMA):
$$\text{updated\_selectivity} = \alpha \cdot \text{observed\_selectivity} + (1 - \alpha) \cdot \text{previous\_selectivity}$$

Where:
- $\alpha \in [0.0, 1.0]$: Smoothing parameter (default $\alpha = 0.50$).
- $\alpha = 1.0$: Fully reactive (replaces prior estimate with latest run).
- $\alpha = 0.0$: Static (retains prior estimate, disables adaptation).
- $\alpha = 0.50$: Balanced EWMA between historical prior and empirical observation.

---

## 5. Architectural Components

The feedback subsystem is organized under `backend/feedback/`:

1. **`backend/feedback/model.py`**:
   - `SelectivityFeedback`: Frozen dataclass detailing prior, observed, and updated selectivities.
   - `OperationFeedback`: Operator-level comparison of estimated vs actual input/output rows, difference, and relative errors.
   - `ExecutionFeedback`: Query-level report containing all operation feedbacks, summary statistics, and `.explain()` formatter.

2. **`backend/feedback/collector.py`**:
   - `FeedbackCollector`: Matches compile-time `PlanCostEstimate` operations with runtime `ExecutionResult.stats`, calculates errors, and computes EWMA selectivity updates.
   - `collect_feedback(...)`: Functional helper.

3. **`backend/feedback/adaptive_store.py`**:
   - `AdaptiveStatisticsStore`: In-memory repository mapping `(table_name, predicate)` tuples to learned selectivities.
   - Supports case-insensitive table matching and flexible query predicate formatting (handles both `"marks > 80"` and `"FILTER marks > 80"`).

4. **Integration with `CostEstimator` (`backend/cost/stats.py`)**:
   - `DatasetStatistics` accepts an optional `adaptive_store`.
   - In `calculate_selectivity(table, predicate)`: checks `adaptive_store` first; if present, uses the learned selectivity; otherwise falls back to static dataset inspection.

5. **Integration with `QueryPipeline` (`backend/pipeline.py`)**:
   - `QueryResult` contains field `feedback: ExecutionFeedback | None`.
   - Pipeline generates feedback for every executed query.
   - If `enable_learning=True`, updates the attached `AdaptiveStatisticsStore`.

---

## 6. Configurable Learning Design

Updating stored statistics is strictly configurable via:
- `enable_learning: bool = False` (default)
- `adaptive_store: AdaptiveStatisticsStore | None = None`
- `alpha: float = 0.5`

### Rationale:
1. **Preserving Determinism**: Default test suites and cost model benchmarks rely on deterministic static numbers. Keeping learning opt-in ensures no side effects occur in standard compiler pipeline tests.
2. **Dataset Immutability**: The underlying CSV data files (`students.csv`) are never altered or rewritten. Adaptation lives cleanly in an in-memory statistics layer.
3. **Controlled Experimentation**: Enables instructors and students to run queries with `enable_learning=False` vs `enable_learning=True` to observe differences side by side.

---

## 7. Reference Query Walkthrough

### Reference Query:
```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;
```

### Static Cost Model Assumptions:
- `students` row count: 200
- `department = 'CSE'` count: 38 rows ($s_1 = 0.1900$)
- `marks > 80` count: 65 rows ($s_2 = 0.3250$)
- Independence assumption: $200 \times 0.1900 \times 0.3250 = 12.35 \implies 12$ rows.

### Actual Runtime Execution:
- Scanning `students`: reads 200 rows.
- Filter 1 (`department = 'CSE'`): 200 input rows $\to$ 38 output rows (estimate: 38, error: 0).
- Filter 2 (`marks > 80`): 38 input rows $\to$ **13 output rows**!
- Because CSE students have slightly higher marks than average, exactly 13 students pass both criteria rather than 12.

### Generated Feedback Report:
```
RUNTIME FEEDBACK & ADAPTATION REPORT
==================================================
Plan Evaluated: plan_A
Estimated Total Cost: 278.00

OPERATION ACCURACY ANALYSIS:
  SCAN students
    Estimated: input=0, output=200
    Actual:    input=0, output=200
    Feedback:  error=0 (0.0%), diff=+0
  FILTER department = 'CSE'
    Estimated: input=200, output=38
    Actual:    input=200, output=38
    Feedback:  error=0 (0.0%), diff=+0
    Learning:  prev_sel=0.1900, observed_sel=0.1900 -> updated_sel=0.1900
  FILTER marks > 80
    Estimated: input=38, output=12
    Actual:    input=38, output=13
    Feedback:  error=1 (7.7%), diff=+1
    Learning:  prev_sel=0.3250, observed_sel=0.3421 -> updated_sel=0.3336
  PROJECT name, marks
    Estimated: input=12, output=12
    Actual:    input=13, output=13
    Feedback:  error=1 (7.7%), diff=+1
  SORT marks DESC
    Estimated: input=12, output=12
    Actual:    input=13, output=13
    Feedback:  error=1 (7.7%), diff=+1

SUMMARY:
  Total Absolute Output Error: 3 rows
  Average Relative Error:      4.62%
==================================================
```

On subsequent queries with `enable_learning=True`, the cost estimator uses $s_2 = 0.3336$, predicting $38 \times 0.3336 = 12.68 \approx 13$ rows, reducing compile-time estimation error to zero.

---

## 8. Pedagogical Value & Scope Boundaries

- **In Scope**:
  - Transparent error reporting (diff, absolute error, relative percentage).
  - Clean EWMA selectivity updates.
  - Zero disruption to baseline query correctness and existing stages.
- **Out of Scope**:
  - Complex black-box machine learning models or neural cardinality estimators.
  - Dynamic runtime plan re-optimization (mid-flight adaptive query execution / eddies).
  - Disk-backed persistent catalog serialization.
