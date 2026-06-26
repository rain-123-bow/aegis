"""Thin parent router for resident Aegis subgraphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from aegis.models import utc_now
from aegis.top_level.models import (
    ModuleRouteDecision,
    ParentRouteEvent,
    RouteStatus,
    TopLevelGraphState,
    TopLevelTerminalStatus,
)
from aegis.top_level.registry import ModuleRegistry
from aegis.top_level.routing import (
    RouteSchemaRegistry,
    RouteValidationError,
    default_route_schema_registry,
)
from aegis.top_level.runtime_lock import RuntimeProjectLock


class TopLevelStateDict(TypedDict, total=False):
    aegis_instance_id: str
    project_root: str
    run_id: str
    thread_id: str
    current_module: str
    resident_modules: dict[str, Any]
    active_handoff_ref: dict[str, Any] | None
    route_history_tail: list[dict[str, Any]]
    route_history_log_ref: str | None
    route_count: int
    pending_interrupt_ref: str | None
    blockers: list[str]
    terminal_status: str
    closeout_package_ref: str | None
    failure_evidence_ref: str | None


def build_top_level_graph(runtime: "AegisTopLevelRuntime"):
    """Build the parent StateGraph.

    The graph contains a single structural router node. Business behavior lives
    in resident subgraphs captured by the runtime registry.
    """

    builder = StateGraph(TopLevelStateDict)
    builder.add_node("route_step", runtime.route_once)
    builder.add_edge(START, "route_step")
    builder.add_conditional_edges(
        "route_step",
        _route_after_step,
        {
            "route_step": "route_step",
            "end": END,
        },
    )
    return builder.compile()


def _route_after_step(state: TopLevelStateDict) -> str:
    if state.get("terminal_status") == TopLevelTerminalStatus.RUNNING.value:
        return "route_step"
    return "end"


class AegisTopLevelRuntime:
    """One resident Aegis runtime bound to one project root."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        registry: ModuleRegistry,
        route_registry: RouteSchemaRegistry | None = None,
        acquire_lock: bool = True,
        route_history_tail_limit: int = 50,
        max_route_steps: int = 100,
        aegis_instance_id: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.aegis_instance_id = aegis_instance_id or f"aegis-{uuid4().hex[:12]}"
        self.registry = registry
        self.route_registry = route_registry or default_route_schema_registry()
        self.route_history_tail_limit = route_history_tail_limit
        self.max_route_steps = max_route_steps
        self.runtime_root = self.project_root / ".aegis" / "runtime" / "top_level"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self._lock = (
            RuntimeProjectLock(self.project_root, aegis_instance_id=self.aegis_instance_id)
            if acquire_lock
            else None
        )
        if self._lock is not None:
            self._lock.acquire()
        self.graph = build_top_level_graph(self)
        if self._lock is not None:
            self._lock.mark_ready()

    def close(self) -> None:
        if self._lock is not None:
            self._lock.release()

    def __enter__(self) -> "AegisTopLevelRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(self, *, run_id: str | None = None, thread_id: str | None = None) -> TopLevelGraphState:
        actual_run_id = run_id or f"run-{uuid4().hex[:12]}"
        actual_thread_id = thread_id or f"top-level-{actual_run_id}"
        state = TopLevelGraphState(
            aegis_instance_id=self.aegis_instance_id,
            project_root=str(self.project_root),
            run_id=actual_run_id,
            thread_id=actual_thread_id,
            resident_modules=self.registry.records,
            route_history_log_ref=str(self._run_root(actual_run_id) / "route_history.jsonl"),
        )
        result = self.graph.invoke(
            state.model_dump(mode="json"),
            config={"recursion_limit": self.max_route_steps + 5},
        )
        return TopLevelGraphState.model_validate(result)

    def route_once(self, raw_state: TopLevelStateDict) -> TopLevelStateDict:
        state = TopLevelGraphState.model_validate(raw_state)
        if state.terminal_status != TopLevelTerminalStatus.RUNNING:
            return state.model_dump(mode="json")
        if state.route_count >= self.max_route_steps:
            return self._stop_with_failure(state, "parent route step limit exceeded")
        if state.current_module == "closeout":
            state.terminal_status = TopLevelTerminalStatus.CLOSED
            return state.model_dump(mode="json")
        try:
            module = self.registry.get(state.current_module)  # type: ignore[arg-type]
            decision = ModuleRouteDecision.model_validate(
                module.handle(state.model_dump(mode="json"))
            )
            return self._apply_decision(state, decision)
        except Exception as exc:
            return self._stop_with_failure(state, str(exc), failed_module=state.current_module)

    def _apply_decision(
        self,
        state: TopLevelGraphState,
        decision: ModuleRouteDecision,
    ) -> TopLevelStateDict:
        if decision.source_module != state.current_module:
            return self._stop_with_failure(
                state,
                "module route decision source_module does not match current_module",
                failed_module=state.current_module,
            )
        if decision.route_status == RouteStatus.RUNTIME_TERMINAL:
            event = ParentRouteEvent(
                event_index=state.route_count + 1,
                run_id=state.run_id,
                source_module=decision.source_module,
                target_module="closeout",
                handoff_kind=decision.handoff_kind or "master_closeout",
                route_status=decision.route_status,
            )
            self._append_route_event(state, event)
            state.closeout_package_ref = decision.output_handoff.package_path if decision.output_handoff else None
            state.terminal_status = TopLevelTerminalStatus.CLOSED
            return state.model_dump(mode="json")
        if decision.route_status == RouteStatus.FAILED:
            return self._stop_with_failure(
                state,
                decision.failure_reason or "module reported failure",
                failed_module=decision.source_module,
            )
        if decision.route_status == RouteStatus.BLOCKED:
            state.blockers.extend(decision.blockers)
            state.terminal_status = TopLevelTerminalStatus.BLOCKED
            return state.model_dump(mode="json")
        if decision.route_status == RouteStatus.INTERRUPTED:
            state.pending_interrupt_ref = decision.interrupt_ref
            state.terminal_status = TopLevelTerminalStatus.INTERRUPTED
            return state.model_dump(mode="json")
        if decision.output_handoff is None:
            return self._stop_with_failure(
                state,
                "routable module decision missing output_handoff",
                failed_module=decision.source_module,
            )
        try:
            validation = self.route_registry.validate_envelope(
                decision.output_handoff,
                project_root=self.project_root,
            )
            validation_ref = self._write_validation_result(state.run_id, validation.model_dump(mode="json"))
        except RouteValidationError as exc:
            return self._stop_with_failure(state, str(exc), failed_module=decision.source_module)

        event = ParentRouteEvent(
            event_index=state.route_count + 1,
            run_id=state.run_id,
            source_module=decision.source_module,
            target_module=decision.output_handoff.target_module,
            handoff_kind=decision.output_handoff.handoff_kind,
            route_status=decision.route_status,
            package_ref=decision.output_handoff.package_path,
            validation_ref=validation_ref,
        )
        self._append_route_event(state, event)
        state.active_handoff_ref = decision.output_handoff
        state.current_module = decision.output_handoff.target_module
        return state.model_dump(mode="json")

    def _append_route_event(self, state: TopLevelGraphState, event: ParentRouteEvent) -> None:
        run_root = self._run_root(state.run_id)
        history_path = run_root / "route_history.jsonl"
        with history_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=True, sort_keys=True))
            handle.write("\n")
        state.route_count += 1
        tail = [*state.route_history_tail, event]
        state.route_history_tail = tail[-self.route_history_tail_limit :]
        state.route_history_log_ref = str(history_path)

    def _stop_with_failure(
        self,
        state: TopLevelGraphState,
        reason: str,
        *,
        failed_module: str | None = None,
    ) -> TopLevelStateDict:
        evidence = {
            "schema_version": "top_level.failure_evidence.v1",
            "run_id": state.run_id,
            "failed_module": failed_module,
            "reason": reason,
            "created_at_utc": utc_now(),
            "state_snapshot": state.model_dump(mode="json"),
        }
        failure_dir = self._run_root(state.run_id) / "failure_evidence"
        failure_dir.mkdir(parents=True, exist_ok=True)
        failure_path = failure_dir / "failure.json"
        failure_path.write_text(
            json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        state.failure_evidence_ref = str(failure_path)
        state.terminal_status = TopLevelTerminalStatus.STOPPED_DUE_TO_MODULE_FAILURE
        return state.model_dump(mode="json")

    def _write_validation_result(self, run_id: str, payload: dict[str, Any]) -> str:
        target_dir = self._run_root(run_id) / "validation_results"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"validation-{uuid4().hex[:12]}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return str(target)

    def _run_root(self, run_id: str) -> Path:
        run_root = self.runtime_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        readme = run_root / "README.md"
        if not readme.exists():
            readme.write_text(
                "Top-Level Graph runtime evidence. Read route_history.jsonl first.\n",
                encoding="utf-8",
                newline="\n",
            )
        return run_root
