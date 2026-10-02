"""
main.py — Entry point for the Adaptive Query Execution Planner backend.

Demonstrates the complete end-to-end pipeline on the reference query:
  Lexer -> Parser -> Semantic -> IR -> Planner -> Cost -> Selector -> Executor -> Verifier
"""

from backend.cost import __name__ as _cost
from backend.executor import __name__ as _executor
from backend.ir import __name__ as _ir
from backend.lexer import __name__ as _lexer
from backend.parser import __name__ as _parser
from backend.pipeline import execute_query
from backend.planner import __name__ as _planner
from backend.semantic import __name__ as _semantic

DEMO_QUERY = """\
SELECT name, marks
FROM students
WHERE department = 'CSE'
AND marks > 80
ORDER BY marks DESC;"""


def main() -> None:
    print("=" * 58)
    print("  Adaptive Query Execution Planner - backend started")
    print("=" * 58)
    print()
    print("Pipeline modules detected:")
    for stage in [_lexer, _parser, _semantic, _ir, _planner, _cost, _executor]:
        print(f"  [ok]  {stage}")
    print()
    print("Status: foundation ready - full end-to-end pipeline active.")
    print()
    print("Running reference query demonstration:")
    result = execute_query(DEMO_QUERY)
    print(result.explain())


if __name__ == "__main__":
    main()
