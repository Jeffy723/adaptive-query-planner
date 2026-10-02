# Plan Selector Specification

**Adaptive Query Execution Planner for a Mini SQL-like Query Language**  
*Compiler Design Laboratory / Microproject*

---

## 1. Purpose of the Plan Selector

The **Plan Selector** is the decision-making engine of the Adaptive Query Execution Planner. 

Following the compilation pipeline:
$$\text{Query} \longrightarrow \text{AST} \longrightarrow \text{Logical IR} \longrightarrow \text{Alternative Physical Plans} \longrightarrow \text{Cost Estimates}$$

The Plan Selector takes all candidate physical execution plans along with their estimated processing costs, evaluates them under a deterministic cost-based optimization policy, and selects the single optimal plan to execute.

---

## 2. Inputs and Outputs

### Input
The Plan Selector accepts candidate physical execution plans paired with their estimated costs:
- **Plans**: `Sequence[PhysicalPlan]` (e.g. `[plan_A, plan_B]`)
- **Cost Estimates**: `Sequence[PlanCostEstimate]` or numerical total costs corresponding to each plan.

Supported calling conventions:
```python
# Convention 1: Separate sequences
result = PlanSelector().select(plans, cost_estimates)

# Convention 2: Sequence of (plan, cost) tuples
result = PlanSelector().select([(plan_A, cost_A), (plan_B, cost_B)])

# Convention 3: Convenient functional helper
result = select_plan(plans, cost_estimates)
```

### Output
The selector returns a structured `PlanSelectionResult` dataclass:
- `selected_plan`: The winning `PhysicalPlan` instance.
- `selected_plan_id`: Deterministic string identifier (e.g. `"plan_A"`).
- `selected_cost`: The numerical total cost of the selected plan.
- `ranked_candidates`: An ordered tuple of `RankedPlan` objects sorted from lowest to highest cost (rank 1 is best).
- `reason`: A human-readable explanation of the selection decision.
- `metadata`: Selection metrics and flags (e.g. `tie_detected`).

---

## 3. Selection Algorithm

1. **Input Normalization**: Pairs each physical plan with its corresponding cost estimate.
2. **Validation**: Enforces non-empty candidate lists, valid numerical costs, and plan-cost identifier consistency.
3. **Sorting**: Sorts all candidate plans using a deterministic composite comparison key:
   $$\text{sort\_key}(\text{candidate}) = \left(\text{cost}, \; \text{plan\_id}, \; \text{original\_index}\right)$$
4. **Ranking**: Assigns 1-based ranks ($1, 2, \dots, N$) to all candidates.
5. **Winner Assignment**: Selects Rank 1 as the optimal execution plan.
6. **Explanation Formulation**: Generates an informative explanation detailing cost savings over the runner-up plan or noting tie-breaker activation.

---

## 4. Tie-Breaking Rule

When two or more candidate plans have **identical estimated total costs**, random selection is strictly forbidden. 

Ties are resolved deterministically using:
1. **Primary Key**: Lowest estimated total cost ($\min \text{cost}$).
2. **Secondary Key (Tie-Breaker)**: Deterministic lexicographical order of `plan_id` (e.g. `"plan_A"` precedes `"plan_B"`).
3. **Tertiary Key**: Input sequence order (preserving stability).

This ensures that query compilation is **100% reproducible and deterministic** across runs and environments.

---

## 5. Error Handling & Input Validation

The selector raises a structured `SelectionError` when invalid inputs are encountered:

| Error Condition | Trigger Scenario | Result |
| :--- | :--- | :--- |
| **Empty Input** | `select([])` | `SelectionError("Cannot select plan from an empty plan list.")` |
| **Mismatched Counts** | `len(plans) != len(costs)` | `SelectionError("Mismatched plan and cost counts: ...")` |
| **Missing Cost** | Cost is `None` | `SelectionError("Missing cost estimate for plan '...'")` |
| **Mismatched Plan ID** | `plan.plan_id != cost.plan_id` | `SelectionError("Inconsistent plan and cost association: ...")` |
| **Non-Finite Cost** | Cost is `NaN` or `Inf` | `SelectionError("Invalid non-finite cost (...) for plan '...'")` |
| **Negative Cost** | Cost $< 0.0$ | `SelectionError("Invalid negative cost (...) for plan '...'")` |

---

## 6. Example: Reference Query Selection

```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;
```

### Candidate Evaluation:
- **Plan A** (`department = 'CSE'` then `marks > 80`): Estimated Cost = **$493.02$**
- **Plan B** (`marks > 80` then `department = 'CSE'`): Estimated Cost = **$520.02$**

### Visual Output (`result.explain()`):
```
PLAN COMPARISON
--------------------------------------------------
  #1 plan_A     cost:   493.02  <-- SELECTED
  #2 plan_B     cost:   520.02
--------------------------------------------------
Selected Plan: plan_A
Estimated Cost: 493.02
Reason: Lowest estimated total cost (493.02 vs plan_B at 520.02, saving 27.00 cost units).
```

### Analysis:
Because Plan A evaluates the more selective filter first ($s = 0.1900$ vs $s = 0.3250$), it performs 27 fewer tuple inspections, leading to a lower estimated cost. The Plan Selector picks Plan A as the optimal physical plan.
