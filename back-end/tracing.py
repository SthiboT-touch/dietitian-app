"""LangSmith tracing helpers.

LangChain/LangGraph send traces to LangSmith automatically when LANGSMITH_TRACING=true and
LANGSMITH_API_KEY are set (see docker-compose.langsmith.yml). This module adds:
  * names, tags and conversation threads for runs (``trace_config``)
  * the dietitian's decision as LangSmith feedback on the run that drafted a plan (``record_review_feedback``)
  * flushing of pending traces on shutdown (``flush``)
"""
import logging
import os
import uuid
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def tracing_enabled() -> bool:
    return (
        os.getenv("LANGSMITH_TRACING", "").strip().lower() in _TRUE_VALUES
        and bool(os.getenv("LANGSMITH_API_KEY"))
    )


def trace_config(
    run_name: str,
    *,
    tags: tuple = (),
    metadata: Optional[dict] = None,
    run_id: Optional[uuid.UUID] = None,
) -> dict:
    """Build the ``config=`` argument for ``.invoke()`` so runs get a readable name, tags and metadata.

    Put a ``thread_id`` in ``metadata`` to group a conversation's runs under LangSmith's Threads tab.
    Never put patient names or health details in metadata.
    """
    config = {
        "run_name": run_name,
        "tags": ["dietitian-app", *tags],
        "metadata": {"environment": os.getenv("APP_ENV", "development"), **(metadata or {})},
    }
    if run_id is not None:
        config["run_id"] = run_id
    return config


@lru_cache(maxsize=1)
def _client():
    from langsmith import Client

    return Client()


def record_review_feedback(run_id: Optional[str], action: str) -> None:
    """Attach the dietitian's decision to the run that generated the plan.

    The decision (APPROVED / MODIFIED / REJECTED) shows up as feedback on the trace, so you can
    filter LangSmith for plans dietitians rejected and use them as evaluation examples.
    Review notes are deliberately not sent, because they can contain health details.
    Failures here must never break the review request.
    """
    if not run_id or not tracing_enabled():
        return
    score = {"APPROVED": 1.0, "MODIFIED": 0.5, "REJECTED": 0.0}.get(action)
    try:
        _client().create_feedback(run_id=run_id, key="dietitian_review", value=action, score=score)
    except Exception:  # noqa: BLE001 - tracing must never break the app
        logger.warning("Could not record LangSmith feedback for run %s", run_id, exc_info=True)


def flush() -> None:
    """Send any traces still waiting in the background queue (call on shutdown)."""
    if not tracing_enabled():
        return
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    except Exception:  # noqa: BLE001
        logger.warning("Could not flush LangSmith traces", exc_info=True)
