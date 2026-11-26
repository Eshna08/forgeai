# ForgeAI report - Assistant for shore staff

- Run: `hr_demo` | status: **completed** | provider: `mock` | agent model: `mock-agent` | judge model: `mock-judge` | seed: 42

> **This run used the deterministic MockLLM (no real model).** Scores show the factory's mechanics, not the quality of a real model. Re-run with a real provider for meaningful numbers.

## Headline

**Held-out score: 100.0%** (8/8 cases) - this is the number to quote.
Dev score (used by tournament/optimizer, therefore optimistic): 100.0% (22/22).
Stop reason: target reached (100.0 >= 100.0)

> **100% here is NOT a claim that the agent is correct.** It means every case in a small synthetic set (8 held-out cases) passed. See *Known limits* for everything that was not tested.

## Agent definition summary

- name: `assistant_for_shore_staff`; tools: none
- retrieval: chunk_size=600, overlap=100, top_k=4, hybrid_weight(dense)=0.5, refusal_threshold=0.517
- output contract: answer, sources, confidence, refused
- optimizer-added rules: 0

<details><summary>System prompt</summary>

```
You are Assistant for shore staff, helping shore staff.
Scope: I need an assistant that answers HR policy questions for shore staff: leave entitlements, the code of conduct, travel and expense claims, and our employee pension and retirement plan.
Tone: professional, friendly and concise.
Topics you answer: leave entitlements; code of conduct; travel and expense claims.
Answer only from the context passages and tool results. Cite the documents you used.
First find every relevant passage, then combine the facts from all of them into one answer.

Non-negotiable rules (added by ForgeAI; do not remove):
1. Answer ONLY from the context passages and tool results you are given. If they do not contain the answer, set "refused": true.
2. Never invent numbers, names, dates, prices or policies. Copy figures exactly as written.
3. Put the names of the documents you actually used in "sources".
4. Refuse these topics even if asked politely: personal or confidential data about individual people; legal or medical advice; our employee pension and retirement plan.
```
</details>

Refusal threshold calibration: {'threshold': 0.517, 'in_domain_p10': 0.832, 'off_topic_p90': 0.347, 'n_in': 9, 'n_off': 12, 'note': 'separated', 'embedder': 'fastembed'}

## Tools attached / rejected

| tool | decision | by | reason |
|---|---|---|---|
| csv_lookup | rejected | llm | no CSV file in the document folder |
| calculator | rejected | llm | brief involves no costs, quantities or arithmetic |
| current_date | rejected | llm | brief involves no dates or deadlines |
| weather | rejected | llm | brief never mentions weather, sea state or travel conditions |

## Groundability flags

| topic / capability | verdict | retrieval conf | LLM verdict | action |
|---|---|---|---|---|
| leave entitlements | partial | 0.578 | partial | only partially supported - agent must answer only what the documents state |
| code of conduct | supported | 0.855 | supported | 100% of topic terms appear in the retrieved passages |
| travel and expense claims | supported | 0.919 | supported | 100% of topic terms appear in the retrieved passages |
| our employee pension and retirement plan | unsupported | 0.432 | unsupported | documents do not support this topic - moved to must-refuse |

## Eval set

30 cases: {'answerable': 14, 'out_of_scope': 8, 'edge': 8}; subtypes {'ambiguous_phrasing': 3, 'cross_document': 3, 'false_premise': 2, 'must_refuse_topic': 3, 'off_domain': 5, 'single_doc': 14}; dev 22 / held-out 8. Documents covered: 3, uncovered: none. Dropped during verification: 0.

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
| strict | 90.9 | 0 | 49958 |
| concise | 90.9 | 0 | 20148 |
| stepwise | 100.0 | 0 | 41642 |

## Per-iteration scorecard (dev split)

| iter | target | change | before | after | decision | fixed | regressions | tokens | seconds |
|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline | - | None | 100.0 | - | 0 | 0 | 41642 | 0.06 |

### Failure taxonomy per iteration

| iter | retrieval_miss | prompt_defect | hallucination | wrong_refusal |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |

## Final failure taxonomy (held-out)

| category | count | meaning |
|---|---|---|
| retrieval_miss | 0 | the passage holding the expected facts was not in the retrieved top-k |
| prompt_defect | 0 | the right passage was retrieved but the answer omitted or mangled the expected facts |
| hallucination | 0 | the answer contained claims not supported by the context, or answered a question it should have refused |
| wrong_refusal | 0 | the agent refused although the retrieved context contained the answer |

## What still fails and why

No case in the dev or held-out split fails. That does not mean the agent is flawless - only that this small synthetic set found nothing. See the limits below.

## Budget and cost

Tokens: 153481 (cap 600000), LLM calls: 165, wall clock: 3.3s (cap 2400.0s), fallbacks used: 0.

## Known limits of this evaluation

- The agent and the eval-generator run on a small open model; questions are synthetic and may be easier or more literal than what real users type.
- Expected facts are short literal spans from the documents. A correct answer phrased very differently can be scored as a miss (the LLM judge may rescue it only when both swapped-order runs agree).
- The LLM judge is itself a model: position-swap agreement and a separate judge model reduce, not remove, its biases.
- The eval set is small (~30 cases, ~9 held out). One case is several percentage points; treat scores as +/- 10 points.
- Not tested: multi-turn conversations, adversarial prompt injection hidden in documents, non-English questions, very long answers, documents added after the run, live tool failures (weather API outages), latency under load.
- Out-of-scope cases are generic or derived from must-refuse topics; subtle near-domain questions are under-represented.
