"""Aegis DebateSubgraph v2."""

from aegis.modules.debate.admission import (
    admit_stances,
    analyze_stance_relations,
    validate_hard_constraints,
)
from aegis.modules.debate.artifacts import DebateArtifactWriter
from aegis.modules.debate.candidate_writer import (
    CausalCandidateWriteError,
    build_update_candidate,
    write_causal_store_candidate,
)
from aegis.modules.debate.context import build_context_bundle
from aegis.modules.debate.errors import DebateErrorCode, DebateRuntimeError
from aegis.modules.debate.graph import (
    DebateRuntime,
    build_debate_subgraph,
    run_deterministic_debate,
)
from aegis.modules.debate.leader import assess_leader_round
from aegis.modules.debate.merge import build_causal_candidate_nodes
from aegis.modules.debate.models import *  # noqa: F403
from aegis.modules.debate.store_binding import bind_project_stores
from aegis.modules.debate.worker import detect_worker_protocol_violations

__all__ = [
    "DebateArtifactWriter",
    "DebateErrorCode",
    "DebateRuntime",
    "DebateRuntimeError",
    "CausalCandidateWriteError",
    "admit_stances",
    "analyze_stance_relations",
    "assess_leader_round",
    "bind_project_stores",
    "build_causal_candidate_nodes",
    "build_context_bundle",
    "build_debate_subgraph",
    "build_update_candidate",
    "detect_worker_protocol_violations",
    "run_deterministic_debate",
    "validate_hard_constraints",
    "write_causal_store_candidate",
]
