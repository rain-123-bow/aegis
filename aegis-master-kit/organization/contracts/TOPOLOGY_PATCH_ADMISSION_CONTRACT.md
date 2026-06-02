# Top-Level Topology Patch Admission Contract

## 1. Purpose

This contract defines how a request to change the top-level route topology may
be admitted as a governance patch task.

It does not add any new route by itself.

It exists to prevent convenience requests such as `test -> master` from being
treated as ordinary runtime messages.

## 2. Boundary

The active runtime topology remains:

```text
aegis-master-kit/organization/topologies/master_top_level_v1.yaml
```

No agent may use a missing route just because a developer, Master, or department
finds it convenient.

A missing edge is invalid until a formal topology patch is admitted, reviewed,
implemented, tested, and accepted.

## 3. Admission Labels

Master must classify a topology-change request as one of:

- `reject_runtime_route_request`
- `admit_topology_patch_investigation`
- `admit_topology_patch_task`
- `block_topology_patch`

## 4. Runtime Route Request Rejection

Use `reject_runtime_route_request` when the user asks to use a missing route as
normal runtime behavior.

Required response:

- state that the current route is invalid;
- cite the active topology or topology contract;
- do not send the message through the missing edge;
- do not modify the route table.

Example:

```text
Request: send Test result directly from test -> master for convenience.
Decision: reject_runtime_route_request.
Reason: v1 has no test -> master edge. Test success goes test -> final_review -> master.
```

## 5. Topology Patch Investigation

Use `admit_topology_patch_investigation` when the request may be legitimate but
does not yet contain enough evidence to change the route table.

Minimum investigation output:

- requested edge;
- current edge owner and affected roles;
- claimed problem with the current topology;
- evidence required;
- risks of adding the edge;
- alternatives under the existing topology;
- explicit statement that the edge is not active.

An investigation must not activate the requested route.

## 6. Topology Patch Task

Use `admit_topology_patch_task` only when all of the following exist:

- requested edge or route-table change;
- reason current topology is insufficient;
- evidence that existing routes cannot satisfy the need;
- affected contracts and tests;
- compatibility impact on router runtime;
- migration and rollback plan;
- acceptance tests;
- developer authorization to modify topology contracts.

The patch task must update contracts, topology files, router tests if needed,
and verification reports together. It must not silently edit only one side of
the topology.

## 7. Blocking Conditions

Use `block_topology_patch` when:

- the request bypasses required review gates;
- the request would let a department bypass Master or Final Review authority;
- the request weakens evidence-state routing;
- the request tries to convert a protocol shortcut into governance authority;
- the request lacks developer authorization for topology mutation.

## 8. Non-Expansion Rule

This contract is an admission workflow only. It does not add cross-domain
routing, unrestricted bidirectional chat, or any new first-layer edge.

The router route table remains the mechanism-level authority until a separately
accepted topology patch changes it.
