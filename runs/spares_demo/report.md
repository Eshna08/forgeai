# ForgeAI report - Assistant for our ship superintendents

- Run: `spares_demo` | status: **completed** | provider: `mock` | agent model: `mock-agent` | judge model: `mock-judge` | seed: 42

> **This run used the deterministic MockLLM (no real model).** Scores show the factory's mechanics, not the quality of a real model. Re-run with a real provider for meaningful numbers.

## Headline

**Held-out score: 87.5%** (7/8 cases) - this is the number to quote.
Dev score (used by tournament/optimizer, therefore optimistic): 95.5% (21/22).
Stop reason: early stop: iteration 1 gained 0.0 points (< 1)

## Agent definition summary

- name: `assistant_for_our_ship_superintendents`; tools: csv_lookup, calculator
- retrieval: chunk_size=600, overlap=100, top_k=4, hybrid_weight(dense)=0.35, refusal_threshold=0.478
- output contract: answer, sources, confidence, refused
- optimizer-added rules: 2

<details><summary>System prompt</summary>

```
You are Assistant for our ship superintendents, helping our ship superintendents.
Scope: I need a procurement assistant for our ship superintendents: look up spare parts in the catalogue, compare suppliers and their terms, check lead times and stock levels, and work out order costs including quantity discounts.
Tone: professional, friendly and concise.
Topics you answer: look up spare parts in the catalogue; compare suppliers and their terms; check lead times and stock levels; work out order costs including quantity discounts.
Answer only from the context passages and tool results. Cite the documents you used.
First find every relevant passage, then combine the facts from all of them into one answer.

Non-negotiable rules (added by ForgeAI; do not remove):
1. Answer ONLY from the context passages and tool results you are given. If they do not contain the answer, set "refused": true.
2. Never invent numbers, names, dates, prices or policies. Copy figures exactly as written.
3. Put the names of the documents you actually used in "sources".
4. Refuse these topics even if asked politely: personal or confidential data about individual people; legal or medical advice.

Additional rules:
- When a question has several parts or needs more than one passage, combine the relevant facts from every context passage and answer each part.
- Quote figures (numbers, limits, durations, prices) exactly as written in the context.
```
</details>

Refusal threshold calibration: {'threshold': 0.478, 'in_domain_p10': 0.899, 'off_topic_p90': 0.251, 'n_in': 25, 'n_off': 12, 'note': 'separated', 'embedder': 'fastembed'}

## Tools attached / rejected

| tool | decision | by | reason |
|---|---|---|---|
| csv_lookup | attached | llm+validator | CSV present: spares_catalogue.csv |
| calculator | attached | llm+validator | brief involves costs / quantities / totals |
| current_date | rejected | llm | brief involves no dates or deadlines |
| weather | rejected | llm | brief never mentions weather, sea state or travel conditions |

## Groundability flags

| topic / capability | verdict | retrieval conf | LLM verdict | action |
|---|---|---|---|---|
| look up spare parts in the catalogue | supported | 0.887 | supported | 100% of topic terms appear in the retrieved passages |
| compare suppliers and their terms | supported | 0.833 | supported | 100% of topic terms appear in the retrieved passages |
| check lead times and stock levels | supported | 0.825 | supported | 100% of topic terms appear in the retrieved passages |
| work out order costs including quantity discounts | partial | 0.603 | partial | only partially supported - agent must answer only what the documents state |

## Eval set

30 cases: {'answerable': 14, 'out_of_scope': 8, 'edge': 8}; subtypes {'ambiguous_phrasing': 3, 'computation': 2, 'cross_document': 3, 'csv_lookup': 4, 'must_refuse_topic': 2, 'off_domain': 6, 'single_doc': 10}; dev 22 / held-out 8. Documents covered: 3, uncovered: none. Dropped during verification: 0.

## Judge self-test

7/7 known-good/known-bad answers judged as expected.

| case | expected pass | judged pass | result | decided by |
|---|---|---|---|---|
| known-good answer | True | True | ok | agreement |
| verbose answer padded with an unsupported claim | False | False | ok | agreement |
| wrong number | False | False | ok | agreement |
| refused although the answer is in context | False | False | ok | deterministic |
| answered an out-of-scope question | False | False | ok | deterministic |
| correct refusal of out-of-scope question | True | True | ok | deterministic |
| long but fully supported answer (length must not matter) | True | True | ok | agreement |

## Prompt tournament (dev split)

Rule: max score, then fewest hallucinations, then fewest tokens (deterministic, not LLM-chosen). Winner: **stepwise**.

| strategy | dev score | hallucinations | tokens |
|---|---|---|---|
| strict | 90.9 | 0 | 60309 |
| concise | 90.9 | 0 | 32707 |
| stepwise | 95.5 | 0 | 61691 |

## Per-iteration scorecard (dev split)

| iter | target | change | before | after | decision | fixed | regressions | tokens | seconds |
|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline | - | None | 95.5 | - | 0 | 0 | 61691 | 0.08 |
| 1 | prompt_defect | prompt patch: +2 rule(s) (Failures show facts present in retrieved context but missing from answers.) | 95.5 | 95.5 | kept | 0 | 0 | 35466 | 0.06 |

### Failure taxonomy per iteration

| iter | retrieval_miss | prompt_defect | hallucination | wrong_refusal |
|---|---|---|---|---|
| 0 | 0 | 1 | 0 | 0 |
| 1 | 0 | 1 | 0 | 0 |

<details><summary>Iteration 1 diff (prompt_defect)</summary>

```diff
--- system_prompt (before)
+++ system_prompt (after)
@@ -12 +12,5 @@
 4. Refuse these topics even if asked politely: personal or confidential data about individual people; legal or medical advice.
+
+Additional rules:
+- When a question has several parts or needs more than one passage, combine the relevant facts from every context passage and answer each part.
+- Quote figures (numbers, limits, durations, prices) exactly as written in the context.

```
</details>

## Final failure taxonomy (held-out)

| category | count | meaning |
|---|---|---|
| retrieval_miss | 0 | the passage holding the expected facts was not in the retrieved top-k |
| prompt_defect | 1 | the right passage was retrieved but the answer omitted or mangled the expected facts |
| hallucination | 0 | the answer contained claims not supported by the context, or answered a question it should have refused |
| wrong_refusal | 0 | the agent refused although the retrieved context contained the answer |

## What still fails and why

| case | split | type | question | category | likely reason |
|---|---|---|---|---|---|
| E05 | heldout | edge/cross_document | Two-part question: (a) according to the supplier a terms, what completes "Orders below the minimum i | prompt_defect | evidence retrieved but answer missed: USD 1,000 |
| E04 | dev | edge/cross_document | Two-part question: (a) according to the supplier b terms, what completes "There is no discount on or | prompt_defect | evidence retrieved but answer missed: USD 500 |

## Budget and cost

Tokens: 230295 (cap 600000), LLM calls: 219, wall clock: 5.3s (cap 2400.0s), fallbacks used: 0.

## Known limits of this evaluation

- The agent and the eval-generator run on a small open model; questions are synthetic and may be easier or more literal than what real users type.
- Expected facts are short literal spans from the documents. A correct answer phrased very differently can be scored as a miss (the LLM judge may rescue it only when both swapped-order runs agree).
- The LLM judge is itself a model: position-swap agreement and a separate judge model reduce, not remove, its biases.
- The eval set is small (~30 cases, ~9 held out). One case is several percentage points; treat scores as +/- 10 points.
- Not tested: multi-turn conversations, adversarial prompt injection hidden in documents, non-English questions, very long answers, documents added after the run, live tool failures (weather API outages), latency under load.
- Out-of-scope cases are generic or derived from must-refuse topics; subtle near-domain questions are under-represented.
