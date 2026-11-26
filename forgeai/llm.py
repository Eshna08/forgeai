"""The ONE gateway for every LLM call.

JSON mode + Pydantic validation + JSON repair + up to 3 validation retries + exponential backoff on
429/5xx + token/latency counters + run budget. LLM_PROVIDER=mock swaps in the deterministic MockLLM so
the whole pipeline and test-suite run offline.
"""
from __future__ import annotations

import json
import logging
import re
import string
import threading
import time
from typing import Any, Callable, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .config import PROMPTS_DIR, Settings, get_settings

log = logging.getLogger("forgeai.llm")
T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


class Budget:
    def __init__(self, max_tokens: int = 0, max_seconds: float = 0):
        self.max_tokens = max_tokens
        self.max_seconds = max_seconds
        self.start = time.monotonic()
        self.tokens = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def check(self) -> None:
        if self.max_tokens and self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"token budget exhausted ({self.tokens}/{self.max_tokens})")
        if self.max_seconds and self.elapsed() >= self.max_seconds:
            raise BudgetExceeded(f"time budget exhausted ({self.elapsed():.0f}s/{self.max_seconds:.0f}s)")


# ---------------------------------------------------------------- prompt rendering / JSON helpers
def render(template: str, vars: dict) -> str:
    text = (PROMPTS_DIR / f"{template}.txt").read_text(encoding="utf-8")
    flat = {k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1) for k, v in vars.items()}
    return string.Template(text).safe_substitute(flat)


def _strip_titles(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _strip_titles(v) for k, v in o.items() if k not in ("title", "description")}
    if isinstance(o, list):
        return [_strip_titles(x) for x in o]
    return o


def schema_hint(model: Type[BaseModel]) -> str:
    return json.dumps(_strip_titles(model.model_json_schema()), separators=(",", ":"))


def repair_json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model output")
    t = t[start : end + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    t2 = re.sub(r",\s*([}\]])", r"\1", t)
    t2 = t2.replace("“", '"').replace("”", '"').replace("’", "'")
    t2 = re.sub(r"\bTrue\b", "true", t2)
    t2 = re.sub(r"\bFalse\b", "false", t2)
    t2 = re.sub(r"\bNone\b", "null", t2)
    t2 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t2)
    return json.loads(t2, strict=False)


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ---------------------------------------------------------------- client
class LLM:
    def __init__(self, settings: Settings | None = None, budget: Budget | None = None):
        self.s = settings or get_settings()
        self.budget = budget or Budget(self.s.max_tokens_per_run, self.s.max_seconds_per_run)
        self.is_mock = self.s.provider == "mock"
        self.json_mode = True
        self._lock = threading.Lock()
        self._last_call = 0.0
        self.cache: dict[str, str] = {}
        self.stats: dict[str, Any] = {
            "calls": 0, "tokens_in": 0, "tokens_out": 0, "latency_s": 0.0,
            "validation_retries": 0, "transport_retries": 0, "fallbacks": 0, "cache_hits": 0, "by_task": {},
        }
        self._mock = None
        if not self.is_mock:
            from openai import OpenAI

            self.client = OpenAI(
                base_url=self.s.base_url, api_key=self.s.api_key or "not-needed",
                timeout=self.s.request_timeout, max_retries=0,
            )

    @property
    def mock(self):
        if self._mock is None:
            from .mock_llm import MockLLM

            self._mock = MockLLM()
        return self._mock

    def model_for(self, role: str) -> str:
        if self.is_mock:
            return "mock-judge" if role == "judge" else "mock-agent"
        return self.s.judge_model if role == "judge" else self.s.model

    def snapshot(self) -> dict:
        return {"tokens": self.stats["tokens_in"] + self.stats["tokens_out"], "calls": self.stats["calls"],
                "latency_s": round(self.stats["latency_s"], 2)}

    # ------------------------------------------------------------ public
    def call(
        self,
        task: str,
        template: str,
        vars: dict,
        schema: Type[T],
        role: str = "agent",
        fallback: Any = None,
        cache: bool = False,
    ) -> T:
        """Render prompts/<template>.txt, call the model, return a validated `schema` instance.

        fallback: None -> raise LLMError after 3 invalid attempts; "mock" -> deterministic heuristic of the
        MockLLM for this task (graceful degradation, logged); dict/callable -> that value.
        """
        prompt = render(template, vars) + "\n\nReturn ONLY one JSON object matching this JSON schema:\n" + schema_hint(schema)
        messages = [
            {"role": "system", "content": "You reply with exactly one valid JSON object and nothing else."},
            {"role": "user", "content": prompt},
        ]
        key = f"{role}|{task}|{prompt}" if cache else ""
        last_err: Exception | None = None
        for attempt in range(3):
            if key and key in self.cache and attempt == 0:
                raw = self.cache[key]
                self.stats["cache_hits"] += 1
            else:
                self.budget.check()
                try:
                    raw = self._complete(task, vars, messages, role)
                except BudgetExceeded:
                    raise
                except Exception as e:  # transport failure after backoff
                    last_err = e
                    break
            try:
                obj = schema.model_validate(repair_json(raw))
                if key:
                    self.cache[key] = raw
                return obj
            except (ValueError, ValidationError) as e:
                last_err = e
                self.stats["validation_retries"] += 1
                messages = messages + [
                    {"role": "assistant", "content": (raw or "")[:3000]},
                    {"role": "user", "content": f"That output was invalid: {str(e)[:600]}\nReply again with ONLY the corrected JSON object."},
                ]
        if fallback is not None:
            self.stats["fallbacks"] += 1
            log.warning("LLM task %s failed (%s); using fallback", task, last_err)
            if fallback == "mock":
                data = self.mock.respond(task, vars)
            else:
                data = fallback() if callable(fallback) else fallback
            return schema.model_validate(data)
        raise LLMError(f"{task}: {last_err}")

    # ------------------------------------------------------------ internals
    def _account(self, task: str, tin: int, tout: int, dt: float) -> None:
        with self._lock:
            st = self.stats
            st["calls"] += 1
            st["tokens_in"] += tin
            st["tokens_out"] += tout
            st["latency_s"] += dt
            bt = st["by_task"].setdefault(task, {"calls": 0, "tokens": 0})
            bt["calls"] += 1
            bt["tokens"] += tin + tout
            self.budget.tokens += tin + tout

    def _complete(self, task: str, vars: dict, messages: list[dict], role: str) -> str:
        if self.is_mock:
            t0 = time.monotonic()
            out = json.dumps(self.mock.respond(task, vars))
            self._account(task, sum(est_tokens(m["content"]) for m in messages), est_tokens(out), time.monotonic() - t0)
            return out
        return self._remote(task, messages, role)

    def _remote(self, task: str, messages: list[dict], role: str) -> str:
        import openai

        delay = 2.0
        last: Exception | None = None
        for attempt in range(6):
            self.budget.check()
            if self.s.min_interval_s:
                wait = self.s.min_interval_s - (time.monotonic() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
            self._last_call = time.monotonic()
            kwargs: dict[str, Any] = dict(
                model=self.model_for(role), messages=messages, temperature=self.s.temperature, max_tokens=1500,
            )
            if self.json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            t0 = time.monotonic()
            try:
                r = self.client.chat.completions.create(**kwargs)
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
                last = e
                retry_after = _retry_after(e)
                self.stats["transport_retries"] += 1
                time.sleep(min(retry_after or delay, 60))
                delay *= 2
                continue
            except openai.BadRequestError as e:
                msg = str(e)
                if "response_format" in msg and self.json_mode:
                    self.json_mode = False  # endpoint has no JSON mode -> rely on repair
                    continue
                failed = _failed_generation(e)
                if failed is not None or "json" in msg.lower():
                    self._account(task, sum(est_tokens(m["content"]) for m in messages), 0, time.monotonic() - t0)
                    return failed or ""  # let repair/validation retry handle it
                raise
            dt = time.monotonic() - t0
            text = r.choices[0].message.content or ""
            u = r.usage
            tin = u.prompt_tokens if u else sum(est_tokens(m["content"]) for m in messages)
            tout = u.completion_tokens if u else est_tokens(text)
            self._account(task, tin, tout, dt)
            return text
        raise LLMError(f"transport failed after retries: {last}")


def _retry_after(e: Exception) -> float | None:
    try:
        h = e.response.headers  # type: ignore[attr-defined]
        v = h.get("retry-after")
        return float(v) if v else None
    except Exception:
        return None


def _failed_generation(e: Exception) -> str | None:
    try:
        body = e.body  # type: ignore[attr-defined]
        if isinstance(body, dict):
            err = body.get("error", body)
            return err.get("failed_generation")
    except Exception:
        pass
    return None


NOOP: Callable[..., None] = lambda *a, **k: None
