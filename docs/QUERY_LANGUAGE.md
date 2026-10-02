# QUERY LANGUAGE SPECIFICATION
## Adaptive Query Execution Planner — Mini SQL-like Language

---

## 1. Purpose

This document defines the **mini SQL-like query language** accepted by the
Adaptive Query Execution Planner. It is a deliberately restricted subset of
SQL designed to be simple enough to implement a full compiler pipeline
(lexer → parser → semantic analyser → IR → planner → executor) within a
single academic project, while still being expressive enough to demonstrate
realistic query optimisation concepts.

This is **not** a standards-compliant SQL dialect. It covers only the
features needed to query a single CSV-backed dataset.

---

## 2. Dataset Schema

The language currently operates on a single table:

| Column       | Type    | Description                                  |
|--------------|---------|----------------------------------------------|
| `id`         | INTEGER | Unique student identifier (1-based)          |
| `name`       | STRING  | Full name of the student                     |
| `department` | STRING  | Department code: CSE, ECE, ME, CE, IT        |
| `semester`   | INTEGER | Current semester (1–8)                       |
| `marks`      | INTEGER | Total marks scored (40–100)                  |

Storage: `data/students.csv` (UTF-8, comma-separated, header row included).

---

## 3. Supported Keywords

Keywords are **case-insensitive** (canonically uppercase):

```
SELECT   FROM   WHERE   AND   OR   ORDER   BY   ASC   DESC
```

---

## 4. Supported Operators

### 4.1 Comparison Operators

| Operator | Meaning                  |
|----------|--------------------------|
| `=`      | Equal                    |
| `!=`     | Not equal                |
| `>`      | Greater than             |
| `<`      | Less than                |
| `>=`     | Greater than or equal to |
| `<=`     | Less than or equal to    |

### 4.2 Logical Operators

| Operator | Meaning     | Precedence |
|----------|-------------|------------|
| `AND`    | Logical AND | Higher     |
| `OR`     | Logical OR  | Lower      |

Parentheses for grouping are **not** supported in this version.

---

## 5. Supported Literals

| Kind    | Syntax                        | Examples           |
|---------|-------------------------------|--------------------|
| Integer | One or more decimal digits    | `80`, `0`, `100`   |
| String  | Single-quoted character sequence | `'CSE'`, `'Alice'` |

- Strings are delimited by single quotes (`'`).
- Double-quoted strings are **not** supported.
- Floating-point literals are **not** supported.
- Boolean literals are **not** supported.
- `NULL` is **not** supported.

---

## 6. Identifiers

An identifier is a sequence of letters, digits, and underscores that starts
with a letter or underscore. Identifiers are used for table names and column
names.

```
identifier  ::=  [a-zA-Z_][a-zA-Z0-9_]*
```

Reserved keywords cannot be used as identifiers.

---

## 7. Query Structure

A complete query has the following structure:

```
query ::= SELECT select_list FROM table_name
          [WHERE condition]
          [ORDER BY column_name [ASC | DESC]]
          [';']
```

Clauses must appear in the order shown. The semicolon is optional.

### 7.1 SELECT clause

```
select_list ::= '*'
              | column_name (',' column_name)*
```

`*` selects all columns. A comma-separated list selects the named columns in
the order listed.

### 7.2 FROM clause

```
from_clause ::= FROM table_name
table_name  ::= identifier
```

Only a single table name is supported. No aliases, no subqueries, no JOINs.

### 7.3 WHERE clause (optional)

```
where_clause ::= WHERE condition
condition    ::= simple_condition (logical_op simple_condition)*
simple_condition ::= column_name comparison_op literal
comparison_op    ::= '=' | '!=' | '>' | '<' | '>=' | '<='
logical_op       ::= AND | OR
literal          ::= integer_literal | string_literal
integer_literal  ::= [0-9]+
string_literal   ::= "'" [^']* "'"
```

Conditions are evaluated left-to-right without operator precedence (no
parentheses). `AND` does **not** bind tighter than `OR` in this
implementation — the sequence is evaluated strictly left-to-right.

### 7.4 ORDER BY clause (optional)

```
order_clause ::= ORDER BY column_name [ASC | DESC]
```

- Only a **single** column may be used for ordering.
- Default direction when neither `ASC` nor `DESC` is given: **ASC**.
- Ordering is performed after filtering.

---

## 8. Full EBNF Grammar

```ebnf
query
    = "SELECT" select_list
      "FROM"   identifier
      [ "WHERE" condition ]
      [ "ORDER" "BY" identifier [ "ASC" | "DESC" ] ]
      [ ";" ] ;

select_list
    = "*"
    | identifier { "," identifier } ;

condition
    = simple_condition { logical_op simple_condition } ;

simple_condition
    = identifier comparison_op literal ;

comparison_op
    = "=" | "!=" | ">" | "<" | ">=" | "<=" ;

logical_op
    = "AND" | "OR" ;

literal
    = integer_literal | string_literal ;

integer_literal
    = digit { digit } ;

string_literal
    = "'" { character } "'" ;

identifier
    = letter_or_underscore { letter_or_underscore | digit } ;

letter_or_underscore
    = "a" | ... | "z" | "A" | ... | "Z" | "_" ;

digit
    = "0" | "1" | ... | "9" ;

character
    = (* any character except single-quote *) ;
```

---

## 9. Valid Query Examples

### Example 1 — Filtered columns with two WHERE conditions (AND)
```sql
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;
```

### Example 2 — Single column, single WHERE condition
```sql
SELECT name
FROM students
WHERE marks >= 90;
```

### Example 3 — Two columns, OR condition
```sql
SELECT name, department
FROM students
WHERE department = 'CSE'
OR department = 'ECE';
```

### Example 4 — Select all columns, no WHERE
```sql
SELECT *
FROM students
ORDER BY semester ASC;
```

### Example 5 — Inequality condition
```sql
SELECT name, department, marks
FROM students
WHERE department != 'ME';
```

### Example 6 — Numeric range (chained AND)
```sql
SELECT name, marks
FROM students
WHERE semester = 3
AND marks >= 70
AND marks <= 90;
```

### Example 7 — No optional clauses (full table scan)
```sql
SELECT *
FROM students;
```

---

## 10. Invalid / Unsupported Examples

These are **not** part of the current language and will be rejected:

| Invalid Query Snippet | Reason |
|-----------------------|--------|
| `SELECT name FROM students, courses` | Multiple tables / implicit JOIN not supported |
| `SELECT COUNT(*) FROM students` | Aggregate functions not supported |
| `SELECT name FROM students WHERE marks BETWEEN 50 AND 90` | `BETWEEN` not supported |
| `SELECT name FROM students WHERE name LIKE 'A%'` | `LIKE` / pattern matching not supported |
| `SELECT name FROM students LIMIT 10` | `LIMIT` / `OFFSET` not supported |
| `SELECT name FROM students WHERE name IS NULL` | `NULL` / `IS NULL` not supported |
| `SELECT name FROM students GROUP BY department` | `GROUP BY` not supported |
| `SELECT name FROM students HAVING marks > 80` | `HAVING` not supported |
| `SELECT name FROM s WHERE (marks > 80 OR marks < 50)` | Parenthesised sub-expressions not supported |
| `INSERT INTO students VALUES (...)` | DML (`INSERT`, `UPDATE`, `DELETE`) not supported |
| `SELECT name FROM students JOIN courses ON ...` | `JOIN` not supported |
| `SELECT "name" FROM students` | Double-quoted strings not supported |
| `SELECT name FROM students ORDER BY marks, semester` | Multi-column ORDER BY not supported |
| `SELECT marks * 2 FROM students` | Arithmetic expressions in SELECT not supported |

---

## 11. Explicit Limitations vs. Full SQL

| Feature              | Full SQL | This Language |
|----------------------|----------|---------------|
| Multiple tables      | Yes      | No            |
| JOINs                | Yes      | No            |
| Subqueries           | Yes      | No            |
| Aggregates (SUM, COUNT, AVG, …) | Yes | No       |
| GROUP BY / HAVING    | Yes      | No            |
| LIMIT / OFFSET       | Yes      | No            |
| NULL handling        | Yes      | No            |
| BETWEEN / LIKE / IN  | Yes      | No            |
| Multi-column ORDER BY | Yes     | No            |
| Arithmetic in SELECT | Yes      | No            |
| DDL (CREATE TABLE, …)| Yes      | No            |
| DML (INSERT, UPDATE, DELETE) | Yes | No        |
| Transactions         | Yes      | No            |
| Views / CTEs         | Yes      | No            |
| Floating-point literals | Yes   | No            |
| Parenthesised conditions | Yes  | No            |

---

## 12. Design Decisions

- **Single-table only** — simplifies the planner; no join-order optimisation needed yet.
- **Left-to-right condition evaluation** — avoids precedence parsing complexity.
- **Integers only** — avoids type-widening and float comparison edge cases.
- **No NULL** — keeps the semantic validator and executor simple.
- **Optional semicolon** — friendly for interactive use without breaking parsability.
- **Case-insensitive keywords** — matches common SQL convention; identifiers preserve case.
