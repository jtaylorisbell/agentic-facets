# Agentic FACETS — evaluation results

- Generated: `2026-07-24T13:11:22+00:00`
- Model: `system.ai.claude-sonnet-5`
- Questions per recipe / scoring: OfficeQA subset, graded by the official `reward.py`.

Real model + real data, so numbers vary run to run. The **pattern** is the point:
document access is the big lever; extra agents are not automatically better.

| Recipe | Questions | Answer accuracy | Avg model calls | Avg tokens |
|---|---|---|---|---|
| 00_closed_book_baseline | 4 | 0.50 | 1.0 | 425 |
| 01_single_tool_agent | 4 | 0.50 | 10.0 | 181587 |
| 02_routed_workflow | 4 | 0.50 | 6.5 | 33030 |
| 03_planner_executor | 4 | 0.50 | 6.0 | 16461 |
| 04_parallel_investigation | 3 | 0.33 | 11.7 | 158660 |
| 05_manager_worker | 4 | 0.50 | 17.8 | 67741 |

## Per-question detail

### 00_closed_book_baseline

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 1 | 517 | 1 | final |
| UID0121 | ✗ | 1 | 482 | 1 | final |
| UID0056 | ✓ | 1 | 354 | 1 | final |
| UID0184 | ✓ | 1 | 346 | 1 | final |

### 01_single_tool_agent

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 12 | 123538 | 12 | final |
| UID0121 | ✓ | 7 | 85721 | 7 | final |
| UID0056 | ✗ | 16 | 494420 | 16 | max_steps |
| UID0184 | ✓ | 5 | 22668 | 5 | final |

### 02_routed_workflow

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 5 | 6283 | 4 | final |
| UID0121 | ✓ | 6 | 48278 | 5 | final |
| UID0056 | ✗ | 9 | 55284 | 8 | max_steps |
| UID0184 | ✓ | 6 | 22274 | 5 | final |

### 03_planner_executor

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 6 | 16078 | 5 | max_replans |
| UID0121 | ✗ | 6 | 17104 | 5 | max_replans |
| UID0056 | ✓ | 6 | 13502 | 5 | max_replans |
| UID0184 | ✓ | 6 | 19159 | 5 | max_replans |

### 04_parallel_investigation

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0025 | ✗ | 14 | 197585 | 3 | final |
| UID0062 | ✗ | 12 | 168462 | 3 | final |
| UID0065 | ✓ | 9 | 109932 | 3 | final |

### 05_manager_worker

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 24 | 95522 | 5 | final |
| UID0121 | ✗ | 12 | 61971 | 3 | final |
| UID0056 | ✓ | 26 | 93220 | 5 | final |
| UID0184 | ✓ | 9 | 20252 | 3 | final |
