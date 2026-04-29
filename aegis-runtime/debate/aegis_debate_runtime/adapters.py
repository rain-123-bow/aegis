from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from .models import DebateContractError, EvidenceRef, StancePacket, WorkerRecord, WorkerTurn


class DebateWorkerHandle(Protocol):
    worker_id: str
    stance: StancePacket

    def take_turn(self, *, run_id: str, round_index: int, turn_index: int, context: dict[str, Any]) -> WorkerTurn:
        ...

    def release(self) -> WorkerRecord:
        ...


class DebateWorkerFactory(Protocol):
    def create_worker(self, *, run_id: str, stance: StancePacket) -> DebateWorkerHandle:
        ...


@dataclass
class InProcessDemoWorker:
    """Deterministic in-process worker used for demo/runtime tests.

    This class proves lifecycle and protocol behavior. It is not intended to replace
    real nested-codex reasoning. A production or richer demo can swap it with a
    nested-codex backed factory without changing Leader semantics.
    """

    worker_id: str
    stance: StancePacket
    released: bool = False

    def take_turn(self, *, run_id: str, round_index: int, turn_index: int, context: dict[str, Any]) -> WorkerTurn:
        if self.released:
            raise DebateContractError(f"worker already released: {self.worker_id}")
        other_stances = [item for item in context.get("stances", []) if item.get("stance_id") != self.stance.stance_id]
        transcript_seen_turn_ids = [item["turn_id"] for item in context.get("transcript_digest", [])]
        targets_attacked = []
        for other in other_stances:
            targets_attacked.append(
                {
                    "stance_id": other["stance_id"],
                    "attack": (
                        "Check whether this alternative has stronger evidence, lower risk, and a narrower valid scope "
                        "than the current stance."
                    ),
                }
            )
        is_first_turn = round_index == 0
        claim = self.stance.claim
        why = self.stance.why
        if is_first_turn:
            turn_type = "defend"
            weakness = "Competing stances must prove stronger evidence or clearer invalidation conditions."
            new_information = True
        else:
            turn_type = "attack" if targets_attacked else "answer"
            weakness = "No new decisive contradiction found beyond the existing transcript in this demo turn."
            new_information = False
        return WorkerTurn(
            run_id=run_id,
            round_index=round_index,
            turn_index=turn_index,
            worker_id=self.worker_id,
            stance_id=self.stance.stance_id,
            turn_type=turn_type,
            claim=claim,
            why=why,
            evidence=list(self.stance.evidence) or [EvidenceRef(type="request", ref="stance_packet", relevance="demo stance evidence path")],
            assumptions=list(self.stance.assumptions),
            targets_attacked=targets_attacked,
            weakness_found=weakness,
            confidence="medium",
            new_information=new_information,
            transcript_seen_turn_ids=transcript_seen_turn_ids,
        )

    def release(self) -> WorkerRecord:
        self.released = True
        return WorkerRecord(worker_id=self.worker_id, stance_id=self.stance.stance_id, status="released")


class InProcessDemoWorkerFactory:
    def create_worker(self, *, run_id: str, stance: StancePacket) -> DebateWorkerHandle:
        return InProcessDemoWorker(worker_id=f"{run_id}__worker__{stance.stance_id}__{uuid4().hex[:8]}", stance=stance)


@dataclass
class NestedCodexCommandWorker:
    """Subprocess worker adapter for future nested-codex integration.

    The command must read JSON from the path stored in the environment variable
    `AEGIS_DEBATE_WORKER_INPUT` or from the last argument supplied by the command
    template. It must print one JSON object matching the WorkerTurn shape.

    This adapter is included to define the runtime extension point. The contract
    tests use `InProcessDemoWorkerFactory` because demo closure does not require
    a real nested-codex binary.
    """

    worker_id: str
    stance: StancePacket
    command: list[str]
    released: bool = False
    timeout_seconds: int = 120

    def take_turn(self, *, run_id: str, round_index: int, turn_index: int, context: dict[str, Any]) -> WorkerTurn:
        if self.released:
            raise DebateContractError(f"worker already released: {self.worker_id}")
        payload = {
            "run_id": run_id,
            "round_index": round_index,
            "turn_index": turn_index,
            "worker_id": self.worker_id,
            "stance": self.stance.to_dict(),
            "context": context,
        }
        with tempfile.TemporaryDirectory(prefix="aegis_debate_worker_") as tmp:
            input_path = Path(tmp) / "worker_input.json"
            input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            env = None
            command = [part.replace("{input_path}", str(input_path)) for part in self.command]
            completed = subprocess.run(
                command,
                cwd=Path.cwd(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False,
                env=env,
            )
            if completed.returncode != 0:
                raise DebateContractError(
                    f"nested-codex worker failed: rc={completed.returncode} stderr={completed.stderr.strip()}"
                )
            try:
                data = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise DebateContractError("nested-codex worker stdout must be one JSON object") from exc
        return WorkerTurn(
            run_id=run_id,
            round_index=round_index,
            turn_index=turn_index,
            worker_id=self.worker_id,
            stance_id=data["stance_id"],
            turn_type=data.get("turn_type", "answer"),
            claim=data["claim"],
            why=data["why"],
            evidence=[EvidenceRef.from_any(item) for item in data.get("evidence", [])],
            assumptions=list(data.get("assumptions", [])),
            targets_attacked=list(data.get("targets_attacked", [])),
            weakness_found=data.get("weakness_found", ""),
            confidence=data.get("confidence", "medium"),
            new_information=bool(data.get("new_information", False)),
            transcript_seen_turn_ids=list(data.get("transcript_seen_turn_ids", [])),
        )

    def release(self) -> WorkerRecord:
        self.released = True
        return WorkerRecord(worker_id=self.worker_id, stance_id=self.stance.stance_id, status="released")


@dataclass
class NestedCodexCommandWorkerFactory:
    command: list[str]
    timeout_seconds: int = 120

    def create_worker(self, *, run_id: str, stance: StancePacket) -> DebateWorkerHandle:
        return NestedCodexCommandWorker(
            worker_id=f"{run_id}__worker__{stance.stance_id}__{uuid4().hex[:8]}",
            stance=stance,
            command=list(self.command),
            timeout_seconds=self.timeout_seconds,
        )
