# Agentic FACETS — evaluation results

- Generated: `2026-07-28T17:11:05+00:00`
- Models: `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5`
- Scoring: OfficeQA subset, graded by the official `reward.py`.

Real models + real data, so numbers vary run to run. The **pattern** is the point:
document access is the big lever, and a better *architecture* can beat a better *model*.

## The thesis, in two numbers

Models ranked weakest→strongest by closed-book accuracy: `claude-haiku-4-5`, `claude-opus-5`, `claude-sonnet-5`.

- **Model lift** (upgrade the LLM, closed-book): `claude-sonnet-5` − `claude-haiku-4-5` = **+0.10**
- **Architecture lift** (give `claude-haiku-4-5` document tools): `01` − `00` = **+0.30**

The architecture lever is **at least as large as** the model lever (**+0.30** vs **+0.10**).

**Head-to-head:** weak model + tools = **0.50**; strong model, closed-book = **0.30**. Does architecture beat the model upgrade? **Yes.**

## Accuracy: architecture (rows) × model (columns)

Accuracy is over successfully-scored runs (`n`). Infra failures (rate limit / connection) are excluded, not scored wrong; ⚠ marks cells that had any.

| Recipe | claude-haiku-4-5 | claude-sonnet-5 | claude-opus-5 |
|---|---|---|---|
| 00_closed_book_baseline | 0.20 (n=10) | 0.30 (n=10) | 0.20 (n=10) |
| 01_single_tool_agent | 0.50 (n=10) | 0.40 (n=10) | 0.70 (n=10) |
| 02_routed_workflow | 0.30 (n=10) | 0.30 (n=10) | 0.50 (n=10) |
| 03_planner_executor | 0.20 (n=10) | 0.30 (n=10) | 0.50 (n=10) |
| 04_parallel_investigation | 0.20 (n=5) | 0.20 (n=5) | 0.60 (n=5) |
| 05_manager_worker | 0.30 (n=10) | 0.60 (n=10) | 0.80 (n=10) |

## Cost: average tokens per question

| Recipe | claude-haiku-4-5 | claude-sonnet-5 | claude-opus-5 |
|---|---|---|---|
| 00_closed_book_baseline | 383 | 435 | 972 |
| 01_single_tool_agent | 223,432 | 147,028 | 187,653 |
| 02_routed_workflow | 127,363 | 76,120 | 79,775 |
| 03_planner_executor | 10,509 | 15,435 | 19,871 |
| 04_parallel_investigation | 257,555 | 307,853 | 164,421 |
| 05_manager_worker | 296,059 | 216,303 | 313,328 |

## Per-question detail

### 00_closed_book_baseline · claude-haiku-4-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 1 | 288 | 1 | final |
| UID0121 | ✗ | 1 | 660 | 1 | final |
| UID0056 | ✓ | 1 | 448 | 1 | final |
| UID0184 | ✗ | 1 | 429 | 1 | final |
| UID0001 | ✗ | 1 | 315 | 1 | final |
| UID0031 | ✓ | 1 | 316 | 1 | final |
| UID0035 | ✗ | 1 | 381 | 1 | final |
| UID0058 | ✗ | 1 | 332 | 1 | final |
| UID0012 | ✗ | 1 | 313 | 1 | final |
| UID0093 | ✗ | 1 | 346 | 1 | final |

### 00_closed_book_baseline · claude-sonnet-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 1 | 543 | 1 | final |
| UID0121 | ✗ | 1 | 482 | 1 | final |
| UID0056 | ✓ | 1 | 483 | 1 | final |
| UID0184 | ✓ | 1 | 346 | 1 | final |
| UID0001 | ✗ | 1 | 258 | 1 | final |
| UID0031 | ✓ | 1 | 311 | 1 | final |
| UID0035 | ✗ | 1 | 766 | 1 | final |
| UID0058 | ✗ | 1 | 284 | 1 | final |
| UID0012 | ✗ | 1 | 597 | 1 | final |
| UID0093 | ✗ | 1 | 279 | 1 | final |

### 00_closed_book_baseline · claude-opus-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 1 | 617 | 1 | final |
| UID0121 | ✗ | 1 | 1573 | 1 | final |
| UID0056 | ✓ | 1 | 950 | 1 | final |
| UID0184 | ✗ | 1 | 888 | 1 | final |
| UID0001 | ✗ | 1 | 879 | 1 | final |
| UID0031 | ✓ | 1 | 495 | 1 | final |
| UID0035 | ✗ | 1 | 641 | 1 | final |
| UID0058 | ✗ | 1 | 1171 | 1 | final |
| UID0012 | ✗ | 1 | 600 | 1 | final |
| UID0093 | ✗ | 1 | 1906 | 1 | final |

### 01_single_tool_agent · claude-haiku-4-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 11 | 80759 | 11 | final |
| UID0121 | ✗ | 12 | 218010 | 12 | final |
| UID0056 | ✓ | 12 | 638686 | 12 | final |
| UID0184 | ✓ | 7 | 41666 | 7 | final |
| UID0001 | ✓ | 13 | 335345 | 13 | final |
| UID0031 | ✗ | 16 | 466528 | 16 | max_steps |
| UID0035 | ✗ | 12 | 218168 | 12 | final |
| UID0058 | ✓ | 6 | 34682 | 6 | final |
| UID0012 | ✗ | 7 | 102429 | 7 | final |
| UID0093 | ✓ | 10 | 98052 | 10 | final |

### 01_single_tool_agent · claude-sonnet-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 16 | 162074 | 16 | max_steps |
| UID0121 | ✓ | 6 | 52994 | 6 | final |
| UID0056 | ✗ | 16 | 263917 | 16 | max_steps |
| UID0184 | ✓ | 5 | 22423 | 5 | final |
| UID0001 | ✓ | 5 | 24793 | 5 | final |
| UID0031 | ✗ | 16 | 255417 | 16 | max_steps |
| UID0035 | ✗ | 6 | 24361 | 6 | final |
| UID0058 | ✓ | 6 | 33038 | 6 | final |
| UID0012 | ✗ | 4 | 43619 | 4 | final |
| UID0093 | ✗ | 16 | 587640 | 16 | max_steps |

### 01_single_tool_agent · claude-opus-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 7 | 94541 | 7 | final |
| UID0121 | ✓ | 6 | 119288 | 6 | final |
| UID0056 | ✓ | 13 | 530003 | 13 | final |
| UID0184 | ✓ | 6 | 35066 | 6 | final |
| UID0001 | ✓ | 5 | 36537 | 5 | final |
| UID0031 | ✗ | 16 | 480588 | 16 | max_steps |
| UID0035 | ✓ | 10 | 76865 | 10 | final |
| UID0058 | ✓ | 6 | 75573 | 6 | final |
| UID0012 | ✗ | 6 | 128431 | 6 | final |
| UID0093 | ✓ | 14 | 299636 | 14 | final |

### 02_routed_workflow · claude-haiku-4-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 9 | 58960 | 8 | max_steps |
| UID0121 | ✓ | 6 | 114066 | 5 | final |
| UID0056 | ✓ | 10 | 359321 | 9 | final |
| UID0184 | ✓ | 9 | 51064 | 8 | final |
| UID0001 | ✗ | 9 | 28298 | 8 | max_steps |
| UID0031 | ✗ | 9 | 56704 | 8 | max_steps |
| UID0035 | ✗ | 10 | 72967 | 9 | final |
| UID0058 | ✗ | 7 | 36973 | 6 | final |
| UID0012 | ✗ | 6 | 55619 | 5 | final |
| UID0093 | ✗ | 17 | 439659 | 16 | max_steps |

### 02_routed_workflow · claude-sonnet-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 9 | 81405 | 8 | max_steps |
| UID0121 | ✓ | 10 | 189620 | 9 | final |
| UID0056 | ✗ | 9 | 52280 | 8 | max_steps |
| UID0184 | ✓ | 6 | 21767 | 5 | final |
| UID0001 | ✓ | 7 | 31863 | 6 | final |
| UID0031 | ✗ | 9 | 33420 | 8 | max_steps |
| UID0035 | ✗ | 6 | 21421 | 5 | final |
| UID0058 | ✗ | 9 | 151871 | 8 | max_steps |
| UID0012 | ✗ | 6 | 64115 | 5 | final |
| UID0093 | ✗ | 9 | 113443 | 8 | max_steps |

### 02_routed_workflow · claude-opus-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 8 | 48090 | 7 | final |
| UID0121 | ✓ | 9 | 107797 | 8 | final |
| UID0056 | ✓ | 9 | 164698 | 8 | final |
| UID0184 | ✓ | 6 | 24978 | 5 | final |
| UID0001 | ✓ | 7 | 75966 | 6 | final |
| UID0031 | ✗ | 9 | 48526 | 8 | max_steps |
| UID0035 | ✗ | 17 | 181387 | 16 | max_steps |
| UID0058 | ✓ | 5 | 24300 | 4 | final |
| UID0012 | ✗ | 5 | 29519 | 4 | final |
| UID0093 | ✗ | 9 | 92490 | 8 | max_steps |

### 03_planner_executor · claude-haiku-4-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 6 | 9277 | 5 | max_replans |
| UID0121 | ✗ | 6 | 12686 | 5 | max_replans |
| UID0056 | ✓ | 6 | 9564 | 7 | max_replans |
| UID0184 | ✗ | 6 | 13131 | 5 | max_replans |
| UID0001 | ✗ | 6 | 10377 | 5 | max_replans |
| UID0031 | ✓ | 6 | 8519 | 6 | max_replans |
| UID0035 | ✗ | 6 | 9411 | 5 | max_replans |
| UID0058 | ✗ | 6 | 11599 | 6 | max_replans |
| UID0012 | ✗ | 6 | 9571 | 5 | max_replans |
| UID0093 | ✗ | 6 | 10952 | 5 | max_replans |

### 03_planner_executor · claude-sonnet-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 6 | 12830 | 5 | max_replans |
| UID0121 | ✗ | 6 | 17006 | 5 | max_replans |
| UID0056 | ✓ | 6 | 11192 | 5 | max_replans |
| UID0184 | ✓ | 6 | 18038 | 5 | max_replans |
| UID0001 | ✗ | 6 | 15417 | 5 | max_replans |
| UID0031 | ✓ | 6 | 12936 | 5 | max_replans |
| UID0035 | ✗ | 6 | 15806 | 6 | max_replans |
| UID0058 | ✗ | 6 | 14658 | 5 | max_replans |
| UID0012 | ✗ | 6 | 15034 | 5 | max_replans |
| UID0093 | ✗ | 6 | 21434 | 5 | max_replans |

### 03_planner_executor · claude-opus-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 6 | 17143 | 11 | max_replans |
| UID0121 | ✗ | 6 | 23174 | 8 | max_replans |
| UID0056 | ✓ | 6 | 14693 | 10 | max_replans |
| UID0184 | ✓ | 6 | 19247 | 6 | max_replans |
| UID0001 | ✓ | 6 | 19345 | 6 | max_replans |
| UID0031 | ✓ | 6 | 17943 | 9 | max_replans |
| UID0035 | ✗ | 6 | 24265 | 8 | max_replans |
| UID0058 | ✗ | 6 | 18979 | 7 | max_replans |
| UID0012 | ✗ | 6 | 15710 | 8 | max_replans |
| UID0093 | ✓ | 6 | 28207 | 12 | max_replans |

### 04_parallel_investigation · claude-haiku-4-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0025 | ✗ | 17 | 375183 | 3 | final |
| UID0062 | ✗ | 14 | 140033 | 3 | final |
| UID0065 | ✓ | 13 | 67770 | 3 | final |
| UID0244 | ✗ | 17 | 282222 | 3 | final |
| UID0077 | ✗ | 17 | 422568 | 3 | final |

### 04_parallel_investigation · claude-sonnet-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0025 | ✗ | 17 | 462279 | 3 | final |
| UID0062 | ✗ | 13 | 199680 | 3 | final |
| UID0065 | ✓ | 11 | 157742 | 3 | final |
| UID0244 | ✗ | 14 | 437660 | 3 | final |
| UID0077 | ✗ | 17 | 281904 | 3 | final |

### 04_parallel_investigation · claude-opus-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0025 | ✓ | 9 | 74992 | 3 | final |
| UID0062 | ✗ | 10 | 112705 | 3 | final |
| UID0065 | ✓ | 5 | 16610 | 3 | final |
| UID0244 | ✓ | 12 | 241503 | 3 | final |
| UID0077 | ✗ | 17 | 376294 | 3 | final |

### 05_manager_worker · claude-haiku-4-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 8 | 19509 | 2 | final |
| UID0121 | ✓ | 10 | 74274 | 2 | final |
| UID0056 | ✗ | 60 | 1255279 | 8 | final |
| UID0184 | ✓ | 11 | 37488 | 3 | final |
| UID0001 | ✗ | 9 | 38097 | 2 | final |
| UID0031 | ✗ | 108 | 1345347 | 12 | max_steps |
| UID0035 | ✗ | 8 | 33319 | 2 | final |
| UID0058 | ✗ | 6 | 16390 | 2 | final |
| UID0012 | ✗ | 7 | 57997 | 2 | final |
| UID0093 | ✓ | 11 | 82887 | 3 | final |

### 05_manager_worker · claude-sonnet-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 10 | 49396 | 2 | final |
| UID0121 | ✗ | 9 | 43933 | 3 | final |
| UID0056 | ✓ | 13 | 45701 | 3 | final |
| UID0184 | ✓ | 10 | 31041 | 3 | final |
| UID0001 | ✓ | 41 | 564669 | 7 | final |
| UID0031 | ✗ | 98 | 848158 | 12 | max_steps |
| UID0035 | ✓ | 14 | 78803 | 3 | final |
| UID0058 | ✓ | 11 | 64718 | 3 | final |
| UID0012 | ✗ | 7 | 19987 | 2 | final |
| UID0093 | ✓ | 51 | 416620 | 8 | final |

### 05_manager_worker · claude-opus-5

| Question | Correct | Model calls | Tokens | Steps | Stopped |
|---|---|---|---|---|---|
| UID0030 | ✗ | 40 | 349601 | 7 | final |
| UID0121 | ✓ | 12 | 155107 | 3 | final |
| UID0056 | ✓ | 15 | 132094 | 4 | final |
| UID0184 | ✓ | 9 | 19627 | 3 | final |
| UID0001 | ✓ | 9 | 24968 | 3 | final |
| UID0031 | ✓ | 69 | 1275480 | 10 | final |
| UID0035 | ✓ | 18 | 74661 | 4 | final |
| UID0058 | ✓ | 12 | 78065 | 3 | final |
| UID0012 | ✗ | 7 | 65316 | 2 | final |
| UID0093 | ✓ | 54 | 958362 | 8 | final |
