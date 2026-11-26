# ForgeAI — final verification

Verified on 2026-11-27 with `python -m pytest -q` (**80 passed**: 64 unit/API/end-to-end + 16 Playwright UI tests,
including an axe-core WCAG 2 A/AA audit of every view in light and dark mode), plus a direct inspection of the
committed demo artifacts in `runs/`. All committed runs used `LLM_PROVIDER=mock` with real bge-small embeddings.

Status: **PASS** = implemented, covered by a test, and visible in artifacts/UI. **PARTIAL** = works, but something
is only shown on demand. **FAIL** = missing.

## The 9 mandatory requirements

| # | Requirement | Status | Implementation | Proving test(s) | Where in the UI |
|---|---|---|---|---|---|
| 1 | Intake interviewer | **PASS** | `forgeai/intake.py` (`MAX_QUESTIONS = 5` enforced by `filter_questions`), `prompts/intake_*.txt`, `prompts/requirements.txt` | `test_question_cap_and_filters`, `test_intake_interactive_and_auto`, UI: `test_mock_build_stepper_intake_and_results` (asserts ≤ 5 in "Question n of N") | Build › step 1 *Interview*: chat-style Q&A card with "Let ForgeAI answer for me" |
| 2 | Groundability guard | **PASS** | `forgeai/groundability.py` (retrieval confidence **and** judge-model verdict; unsupported → `must_refuse`; tool-gap flags) | `test_guard_moves_unsupported_topic_to_must_refuse`, `test_e2e_all_artifacts`, UI test asserts a red "Not in your documents" card | Build › step 2: green / amber / red cards with reason and "What you can do" |
| 3 | Agent generator + tool validator | **PASS** | `forgeai/generator.py` (`validate_tools`, `retrieval_params`, `calibrate_threshold`, `enforce_guards`), `forgeai/tools/` (registry + 4 tools; calculator is an AST walker) | `test_tool_validator_hr_rejects_weather_and_csv`, `test_tool_validator_spares_attaches_csv_and_calculator_not_weather`, `test_weather_attached_when_brief_mentions_conditions_at_location`, `test_build_agent_definition`, `test_calculator_rejects_unsafe` | Results › agent card: tools attached / rejected with reasons, retrieval settings, raw YAML |
| 4 | Eval generator | **PASS** | `forgeai/evalgen.py` (literal-fact verification, CSV answers computed in code, OOS verification, per-document coverage repair, seeded 70/30 split), `prompts/eval_*.txt` | `test_evalset_size_types_coverage_and_verified_facts[hr_docs/spares_docs]`, `test_csv_cases_computed_in_code` | Results › "Every test question" (filterable, expandable) |
| 5 | Judge with bias defences | **PASS** | `forgeai/judge.py`: deterministic checks first (refusal match, normalised + fuzzy fact coverage, source overlap, unsupported numbers/terms), then the LLM judge on `JUDGE_MODEL`, run twice with the order swapped; disagreement → deterministic fallback; length-blind rubric; 7-case self-test | `test_deterministic_checks`, `test_judge_selftest_catches_known_bad`, `test_position_swap_disagreement_falls_back_to_deterministic`, `test_llm_veto_when_both_orders_agree`, `test_judge_role_uses_separate_model` | Build › step 5 *Judge*; Results › judge self-test card; per-case "Judge reasoning" |
| 6 | Critic–optimizer loop | **PASS** | `forgeai/optimizer.py` (rule-based `classify`, one targeted `apply_fix` per round, revert on drop, max 3, stop reasons, full `iterations.json`) | `test_classify_rules`, `test_optimizer_reverts_on_drop_and_stops`, `test_optimizer_max_three_iterations_and_targets`, `test_optimizer_target_and_plateau`, `test_targeted_fixes_are_minimal` | Build › step 6 *Improve*; Results › score line chart, failure-taxonomy bars, changelog timeline with diff and kept/reverted badges |
| 7 | Honest reporting | **PASS** | `forgeai/report.py` (always writes "What still fails and why" and "Known limits"; 100% always carries a warning plus what was not tested; partial report on failure) | `test_report_has_failure_section_and_never_silent_100`, `test_e2e_empty_folder_fails_gracefully`, `test_e2e_budget_stop_still_writes_report` | Results › headline (labelled "Below target" / "Meets target", never celebratory), "What still fails and why" panel |
| 8 | Runnable chat agent | **PASS** | `forgeai/runner.py` (hybrid retrieval, deterministic refusal gate, JSON tool protocol ≤ 2 calls, validated contract), `python -m forgeai chat`, `POST /api/chat` | `test_runner_answers_with_valid_contract`, `test_runner_refusal_gate_and_must_refuse`, `test_runner_tool_protocol_max_two_calls`, `test_runner_blocks_unattached_tool`, UI: `test_chat_returns_answer_with_sources` | Chat view: agent selector, "How I answered" (sources, confidence meter, tools, refused badge) |
| 9 | Demonstrations | **PASS** | `demos/synth_docs.py` + `prompts/synth_*.txt`, `scripts/run_demos.py`, `runs/hr_demo`, `runs/spares_demo`, `runs/admissions_demo` (+ `runs/hr_demo/regression_report.md`) | `test_e2e_all_artifacts`, `test_requirements_page_lists_all_nine` (R9 live check passes) | Runs view (cards); Requirements view (R9 live check with links to all three reports) |

## Stretch goals

| Goal | Status | Implementation | Proving test(s) | Where in the UI |
|---|---|---|---|---|
| Prompt tournament + held-out split | **PASS** | `forgeai/tournament.py`, `prompts/tournament_*.txt`; winner = max dev score, then fewest hallucinations, then fewest tokens; split in `evalgen._finalize` | `test_e2e_all_artifacts` (tournament.json), split ratio in `test_evalset_size…` | Build option "Run a prompt tournament"; Results › tournament table (winner highlighted; held-out shown for the shipped agent only, so held-out never influences the choice) |
| Budget enforcement | **PASS** | `Budget` in `forgeai/llm.py`; optimizer stops early; final held-out eval still runs and the report says the budget was exceeded | `test_budget_enforced`, `test_e2e_budget_stop_still_writes_report`, `test_budget_stops_optimizer_but_final_eval_still_reported` | Results › budget card (tokens/time used vs cap) |
| Human checkpoint | **PASS** | `pipeline.py` approval loop (edit → re-validate + re-run guard), `POST /api/runs/{id}/approval` | `test_approval_edit_then_approve_and_reject`, `test_approval_flow_via_api`, UI: `test_approval_blocks_generation_until_approved` | Build option "Let me review the requirements first" → editable review card with Approve / Save edits / Reject |
| Regression mode | **PASS** | `forgeai/regression.py`, `python -m forgeai regress`, `POST /api/runs/{id}/regress` | `test_regression_mode`, `test_regress_endpoint` | Runs › Regression check (upload changed docs or use the sample) |
| Reproducibility (`--seed`) | **PASS** | seed in `meta.json`, seeded sampling and split | `test_e2e_all_artifacts` | Run header pill "seed 42"; Build › Advanced |
| Factory vs human baseline | skipped | optional per the brief | – | – |

The live Requirements page reports stretch items as **Partial** ("available but not used yet") when no run on that
server has exercised them yet. For example, the human checkpoint stays Partial until someone runs a build with
"review the requirements". That is a live usage status, not a missing feature.

## Specific re-checks (committed artifacts)

| Check | Result |
|---|---|
| Question cap ≤ 5 | hr / spares / admissions: 5 questions each; the mock proposed 7, and `intake_dropped_questions.json` logs one dropped as "answerable from the brief" and one over the cap |
| Guard flags a gap | HR: "our employee pension and retirement plan" is **unsupported** and moved to must-refuse; "leave entitlements" is partial. Spares: "order costs including quantity discounts" is partial |
| HR agent has no weather tool | HR `agent.yaml` `tools: []`; `tools.json` rejects csv_lookup, calculator, current_date and weather, each with a reason. Spares: csv_lookup + calculator (weather rejected). Admissions: calculator + current_date |
| Eval set ≥ 24, all three types | each demo: 30 cases = 14 answerable + 8 out-of-scope + 8 edge; no document uncovered; `meets_minimums: true` |
| Judge: deterministic + bias defences | self-test 7/7 in every demo; position-swap fallback and veto proven by tests with stub judges |
| Optimizer: ≤ 3 iterations, revert, full logs | spares: 1 kept iteration (prompt patch with diff), stopped "gained 0.0 points (< 1)"; HR/admissions: stopped "target reached". Revert is proven by `test_optimizer_reverts_on_drop_and_stops` |
| Report honesty | all three reports contain "What still fails and why" and "Known limits of this evaluation"; the HR 100% carries the "NOT a claim that the agent is correct" warning |
| Chat runner loads any agent.yaml | `python -m forgeai chat --agent runs/<x>_demo/agent.yaml --docs demos/<x>/docs` works for all three (off-topic question → refusal gate) |
| Demo folders complete | all 14 expected artifacts present in each of `runs/hr_demo`, `runs/spares_demo`, `runs/admissions_demo` |

## Fixed during this verification

- **Refusal threshold vs embedder.** A threshold calibrated with fastembed was being applied with hashed embeddings
  when `EMBEDDING_BACKEND` differed, so the gate refused everything. `agent.yaml` now records `embedding:` and the
  runner uses it.
- **Refusal copy.** The refusal message had an internal instruction appended ("Politely decline and say…"). It is now
  a clean user-facing sentence; the instruction stays in the system prompt.
- **Weather rule** now also recognises "conditions at the port/location/destination", as the spec asks.
- **UI:** 360px overflow (tooltips, long pills), one axe violation (scrollable activity feed not keyboard-focusable),
  step 2 not turning amber when gaps were found, and chart label collisions.

## Accessibility

- axe-core WCAG 2 A/AA: **0 violations** on Home, Build, Run results, Chat, Runs and Requirements, in light and dark
  mode (`test_axe_wcag_aa_no_violations`).
- Every control has an accessible name (`test_accessibility_basics`); the first Tab reaches "Skip to content"; modals
  trap focus, close on Esc and return focus to the opener; charts have `role="img"` summaries and focusable points with
  tooltips; motion is disabled under `prefers-reduced-motion`.
- Contrast pairs computed with the WCAG formula are listed in `design-notes.md` (all ≥ 4.5:1 for text).
- Not checked: screen-reader walkthroughs with NVDA or VoiceOver, and Lighthouse performance scores (no Lighthouse CLI on this machine).
