from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adapters import DebateWorkerHandle
from .models import DebateProtocolError, WorkerTurn


@dataclass
class LeaderMediatedRoundRobinTopology:
    """Temporary internal topology for one Debate run.

    The topology supports only:
    - worker -> Leader turn submission;
    - Leader -> all workers transcript broadcast;
    - Leader-selected next speaker.

    It intentionally does not expose peer-to-peer worker messaging.
    """

    run_id: str
    workers: list[DebateWorkerHandle]
    released: bool = False
    broadcast_log: list[dict[str, Any]] = field(default_factory=list)

    def worker_ids(self) -> list[str]:
        return [worker.worker_id for worker in self.workers]

    def stance_ids(self) -> list[str]:
        return [worker.stance.stance_id for worker in self.workers]

    def ordered_workers(self) -> list[DebateWorkerHandle]:
        if self.released:
            raise DebateProtocolError("topology is released")
        return list(self.workers)

    def broadcast_transcript(self, transcript: list[WorkerTurn]) -> dict[str, Any]:
        if self.released:
            raise DebateProtocolError("topology is released")
        digest = [
            {
                "turn_id": turn.turn_id,
                "round_index": turn.round_index,
                "turn_index": turn.turn_index,
                "worker_id": turn.worker_id,
                "stance_id": turn.stance_id,
                "turn_type": turn.turn_type,
                "claim": turn.claim,
                "why": turn.why,
                "new_information": turn.new_information,
            }
            for turn in transcript
        ]
        event = {"recipients": self.worker_ids(), "transcript_turn_count": len(digest), "digest": digest}
        self.broadcast_log.append(event)
        return event

    def send_peer_message(self, from_worker_id: str, to_worker_id: str, payload: dict[str, Any]) -> None:
        raise DebateProtocolError(
            "worker-to-worker direct messages are forbidden; use Leader-mediated broadcast only"
        )

    def release(self) -> dict[str, Any]:
        self.released = True
        return {
            "run_id": self.run_id,
            "topology_released": True,
            "workers_in_topology": self.worker_ids(),
            "broadcast_events": len(self.broadcast_log),
        }
