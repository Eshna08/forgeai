# ForgeAI report - Assistant for international students

- Run: `admissions_demo` | status: **completed** | provider: `mock` | agent model: `mock-agent` | judge model: `mock-judge` | seed: 42

> **This run used the deterministic MockLLM (no real model).** Scores show the factory's mechanics, not the quality of a real model. Re-run with a real provider for meaningful numbers.

## Headline

**Held-out score: 87.5%** (7/8 cases) - this is the number to quote.
Dev score (used by tournament/optimizer, therefore optimistic): 100.0% (22/22).
Stop reason: target reached (100.0 >= 100.0)

> **100% here is NOT a claim that the agent is correct.** It means every case in a small synthetic set (8 held-out cases) passed. See *Known limits* for everything that was not tested.

## Agent definition summary

- name: `assistant_for_international_students`; tools: calculator, current_date
- retrieval: chunk_size=600, overlap=100, top_k=4, hybrid_weight(dense)=0.5, refusal_threshold=0.496
- output contract: answer, sources, confidence, refused
- optimizer-added rules: 0

<details><summary>System prompt</summary>

```
You are Assistant for international students, helping international students.
Scope: I need an assistant that answers prospective students' questions about undergraduate admissions: application deadlines and how many days are left, entry requirements, English language requirements for international students, tuition fees and total course cost, and scholarships.
Tone: professional, friendly and concise.
Topics you answer: application deadlines and how many days are left; entry requirements; English language requirements for international students; tuition fees and total course cost; scholarships.
Answer only from the context passages and tool results. Cite the documents you used.
Answer in one or two sentences, quoting the exact figure from the context.

Non-negotiable rules (added by ForgeAI; do not remove):
1. Answer ONLY from the context passages and tool results you are given. If they do not contain the answer, set "refused": true.
2. Never invent numbers, names, dates, prices or policies. Copy figures exactly as written.
3. Put the names of the documents you actually used in "sources".
4. Refuse these topics even if asked politely: personal or confidential data about individual people; legal or medical advice.
```
</details>

Refusal threshold calibration: {'threshold': 0.496, 'in_domain_p10': 0.855, 'off_topic_p90': 0.303, 'n_in': 6, 'n_off': 12, 'note': 'separated', 'embedder': 'fastembed'}

## Tools attached / rejected

| tool | decision | by | reason |
|---|---|---|---|
| calculator | attached | llm+validator | brief involves costs / quantities / totals |
| current_date | attached | llm+validator | brief involves dates / deadlines |
| csv_lookup | rejected | llm | no CSV file in the document folder |
| weather | rejected | llm | brief never mentions weather, sea state or travel conditions |

## Groundability flags

| topic / capability | verdict | retrieval conf | LLM verdict | action |
|---|---|---|---|---|
| application deadlines and how many days are left | supported | 0.7 | supported | 67% of topic terms appear in the retrieved passages |
| entry requirements | supported | 0.842 | supported | 100% of topic terms appear in the retrieved passages |
| English language requirements for international students | supported | 0.921 | supported | 100% of topic terms appear in the retrieved passages |
| tuition fees and total course cost | supported | 0.651 | supported | 60% of topic terms appear in the retrieved passages |
| scholarships | supported | 0.852 | supported | 100% of topic terms appear in the retrieved passages |

## Eval set

30 cases: {'answerable': 14, 'out_of_scope': 8, 'edge': 8}; subtypes {'ambiguous_phrasing': 3, 'cross_document': 3, 'false_premise': 2, 'must_refuse_topic': 2, 'off_domain': 6, 'single_doc': 14}; dev 22 / held-out 8. Documents covered: 3, uncovered: none. Dropped during verification: 0.

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

Rule: max score, then fewest hallucinations, then fewest tokens (deterministic, not LLM-chosen). Winner: **concise**.

| strategy | dev score | hallucinations | tokens |
|---|---|---|---|
| strict | 100.0 | 0 | 46838 |
| concise | 100.0 | 0 | 20640 |
| stepwise | 100.0 | 0 | 32916 |

## Per-iteration scorecard (dev split)

| iter | target | change | before | after | decision | fixed | regressions | tokens | seconds |
|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline | - | None | 100.0 | - | 0 | 0 | 20640 | 0.06 |

### Failure taxonomy per iteration

| iter | retrieval_miss | prompt_defect | hallucination | wrong_refusal |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |

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
| E03 | heldout | edge/cross_document | Two-part question: (a) according to the international students, what completes "On-campus accommodat | prompt_defect | evidence retrieved but answer missed: 30 |

## Budget and cost

Tokens: 141716 (cap 600000), LLM calls: 157, wall clock: 2.2s (cap 2400.0s), fallbacks used: 0.

## Known limits of this evaluation

- The agent and the eval-generator run on a small open model; questions are synthetic and may be easier or more literal than what real users type.
- Expected facts are short literal spans from the documents. A correct answer phrased very differently can be scored as a miss (the LLM judge may rescue it only when both swapped-order runs agree).
- The LLM judge is itself a model: position-swap agreement and a separate judge model reduce, not remove, its biases.
- The eval set is small (~30 cases, ~9 held out). One case is several percentage points; treat scores as +/- 10 points.
- Not tested: multi-turn conversations, adversarial prompt injection hidden in documents, non-English questions, very long answers, documents added after the run, live tool failures (weather API outages), latency under load.
- Out-of-scope cases are generic or derived from must-refuse topics; subtle near-domain questions are under-represented.
