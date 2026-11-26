# Regression report

New document folder: `D:\projects\ESHNA TASK\demos\hr\docs_v2`

Score of the old eval set on the re-indexed agent: **96.7%** (stale cases count as failures in this number)

| status | count |
|---|---|
| still_passing | 29 |
| regression | 0 |
| newly_passing | 0 |
| still_failing | 0 |
| stale_eval | 1 |

## Stale eval cases (expected fact no longer in the documents)

| id | question | category | note |
|---|---|---|---|
| A08 | According to the leave policy, what completes this statement: "Full-time shore staff are e | retrieval_miss | missing: 25 days |

Stale cases should be regenerated (re-run the factory) rather than counted as agent bugs.