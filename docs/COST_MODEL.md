# Cost Model Specification

**Adaptive Query Execution Planner for a Mini SQL-like Query Language**  
*Compiler Design Laboratory / Microproject*

---

## 1. Motivation: Why a Cost Model is Needed

In relational query compilation, an Abstract Syntax Tree (AST) defines the logical semantics of a query ("*what* data is requested"). The query optimizer translates this into multiple semantically equivalent physical execution plans ("*how* the operations are carried out").

For example, when a query specifies multiple filter conditions:
```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;
```
The execution planner can produce two valid plans:
- **Plan A**: Scan $\to$ Filter(`department = 'CSE'`) $\to$ Filter(`marks > 80`) $\to$ Project $\to$ Sort
- **Plan B**: Scan $\to$ Filter(`marks > 80`) $\to$ Filter(`department = 'CSE'`) $\to$ Project $\to$ Sort

Both plans are provably equivalent in final output. However, their intermediate resource consumption differs significantly depending on the order in which filters discard non-qualifying tuples.

A **Cost Model** assigns a deterministic numerical estimate to each candidate physical execution plan. This allows the query optimizer (specifically the Plan Selector) to evaluate and rank plans **ahead of execution** without running them.

> **Crucial Design Rule**: The cost model does **not** measure wall-clock execution time or CPU cycles. Wall-clock timing fluctuates with system load, caching, and hardware differences. Instead, the cost model measures **logical processing work**—the volume of data (tuples/rows) examined and manipulated by each operator.

---

## 2. Operation Cost Formulas

The cost model defines simple, transparent, and additive cost formulas for each physical operation:

| Physical Operation | Cost Formula | Definition of Terms |
| :--- | :--- | :--- |
| **PhysicalScan** | $\text{Cost} = N_{\text{table}}$ | $N_{\text{table}}$: Total number of rows read from the base dataset. |
| **PhysicalFilter** | $\text{Cost} = N_{\text{in}}$ | $N_{\text{in}}$: Number of incoming tuples inspected by the filter predicate. |
| **PhysicalProject** | $\text{Cost} = N_{\text{in}}$ | $N_{\text{in}}$: Number of tuples projected to the target column list. |
| **PhysicalSort** | $\text{Cost} = N_{\text{in}} \cdot \log_2(N_{\text{in}})$ | $N_{\text{in}}$: Number of tuples entering the comparison sort ($N_{\text{in}} > 1$; 0 if $N_{\text{in}} \le 1$). |

---

## 3. Filter Selectivity Calculation

**Selectivity** ($s$) is the probability that a random tuple in a table satisfies a given boolean condition. It is a real number in the range $[0.0, 1.0]$.

Because our dataset is bounded and deterministic (e.g. `students.csv` with 200 rows), the `DatasetStatistics` component inspects the underlying data directly to compute exact single-predicate selectivities:

$$s(P) = \frac{|\{r \in \text{Table} \mid P(r) = \text{True}\}|}{|\text{Table}|}$$

### Concrete Selectivities in `data/students.csv` (200 rows):

1. **`department = 'CSE'`**:
   - Matching tuples: $38$
   - Selectivity: $s_1 = \frac{38}{200} = 0.1900$ (19% of rows qualify)

2. **`marks > 80`**:
   - Matching tuples: $65$
   - Selectivity: $s_2 = \frac{65}{200} = 0.3250$ (32.5% of rows qualify)

---

## 4. Intermediate Cardinality (Row Count) Estimation

When multiple independent filter predicates are applied in sequence, the cost model applies the standard **attribute independence assumption** (established by System R / Selinger et al.):

$$N_{\text{out}} = \max\left(1, \text{round}(N_{\text{in}} \cdot s)\right) \quad \text{for } s > 0 \text{ and } N_{\text{in}} > 0$$
$$N_{\text{out}} = 0 \quad \text{if } s = 0.0 \text{ or } N_{\text{in}} = 0$$

### Cascading Row Count Comparison

Let total table rows $N = 200$:

#### In Plan A (`department = 'CSE'` first):
1. **Filter 1** (`department = 'CSE'`):
   - $N_{\text{in}} = 200$
   - $N_{\text{out}} = \text{round}(200 \cdot 0.19) = 38$
2. **Filter 2** (`marks > 80`):
   - $N_{\text{in}} = 38$
   - $N_{\text{out}} = \text{round}(38 \cdot 0.325) = \text{round}(12.35) = 12$

#### In Plan B (`marks > 80` first):
1. **Filter 1** (`marks > 80`):
   - $N_{\text{in}} = 200$
   - $N_{\text{out}} = \text{round}(200 \cdot 0.325) = 65$
2. **Filter 2** (`department = 'CSE'`):
   - $N_{\text{in}} = 65$
   - $N_{\text{out}} = \text{round}(65 \cdot 0.19) = \text{round}(12.35) = 12$

Notice that both plans arrive at the same final estimated cardinality ($12$ tuples), but **Plan A processes far fewer intermediate rows**.

---

## 5. Sort Cost Calculation

Sorting $n$ tuples using comparison-based sorting (such as Timsort/Quicksort) requires $O(n \log_2 n)$ comparisons.

The cost model defines:
$$\text{Cost}_{\text{SORT}} = \begin{cases} 
n \cdot \log_2(n) & \text{if } n > 1 \\ 
0.0 & \text{if } n \le 1 
\end{cases}$$

For $n = 12$ rows entering sort:
$$\text{Cost}_{\text{SORT}} = 12 \cdot \log_2(12) \approx 12 \cdot 3.58496 \approx 43.02$$

---

## 6. Total Plan Cost Calculation

The total cost of a physical plan is the algebraic sum of the costs of its constituent operations:

$$\text{Total Cost} = \text{Cost}_{\text{SCAN}} + \sum \text{Cost}_{\text{FILTER}} + \text{Cost}_{\text{PROJECT}} + \text{Cost}_{\text{SORT}}$$

### Detailed Walkthrough: Reference Query

```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;
```

#### Plan A Breakdown:
```
  SCAN students                  input:   0,  output: 200,  cost: 200.00
  FILTER department = 'CSE'      input: 200,  output:  38,  cost: 200.00  (s = 0.1900)
  FILTER marks > 80              input:  38,  output:  12,  cost:  38.00  (s = 0.3250)
  PROJECT name, marks            input:  12,  output:  12,  cost:  12.00
  SORT marks DESC                input:  12,  output:  12,  cost:  43.02
--------------------------------------------------------------------------
  TOTAL PLAN A COST = 200 + 200 + 38 + 12 + 43.02 = 493.02
```

#### Plan B Breakdown:
```
  SCAN students                  input:   0,  output: 200,  cost: 200.00
  FILTER marks > 80              input: 200,  output:  65,  cost: 200.00  (s = 0.3250)
  FILTER department = 'CSE'      input:  65,  output:  12,  cost:  65.00  (s = 0.1900)
  PROJECT name, marks            input:  12,  output:  12,  cost:  12.00
  SORT marks DESC                input:  12,  output:  12,  cost:  43.02
--------------------------------------------------------------------------
  TOTAL PLAN B COST = 200 + 200 + 65 + 12 + 43.02 = 520.02
```

### Analytical Conclusion:
Plan A is **27.0 cost units cheaper** ($493.02 < 520.02$).  
By evaluating the **more selective filter** (`department = 'CSE'`) first, Plan A discards 162 tuples upfront, saving 27 tuple inspections in the second filter stage.

---

## 7. Limitations and Assumptions of this Model

1. **Independence Assumption**:
   The model assumes filter predicates are statistically independent ($P(A \land B) = P(A) \cdot P(B)$). While true for many real-world attributes, correlated attributes (e.g., `age` and `grade_level`) may require joint multi-dimensional histograms in full database systems.
2. **Uniform Operator Weight**:
   Inspecting an integer comparison (`marks > 80`) and a string comparison (`department = 'CSE'`) are both modeled as 1 unit of tuple inspection cost. In production DBMS engines, complex regex or float comparisons might carry higher constant CPU weights.
3. **No I/O Page Modeling**:
   Because the dataset fits in memory in a CSV file, costs are modeled on tuple counts rather than disk block / page reads.
4. **Static Statistics**:
   Statistics are derived directly from the loaded dataset and remain static during single-query optimization.
