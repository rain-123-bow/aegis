# Organization Model

## 1. Core model

`aegis-master-kit` defines organization, not business content.

The Master creates departments. Department leaders create internal department structures.

```text
Master creates departments.
Department leaders create department internals.
Department members execute concrete work.
```

## 2. First layer: Master view

The first layer is precise only to departments.

The Master cares about:

- departments
- department leaders
- department relations
- department input/output
- department state
- escalation
- the top-level directed communication topology

The Master does not care how many internal agents a department uses.

The first-layer executable topology is defined by:

```text
aegis-master-kit/organization/topologies/master_top_level_v1.yaml
```

The topology is a directed graph. It defines which top-level roles may send envelopes to which other top-level roles.

## 3. Router-enforced topology

The top-level router owns an authoritative route table. It must reject any message whose `sender -> receiver` edge does not exist in the route table.

Each role also carries a role-local route table. The role-local table tells the role who it may send to, who may send to it, and which directed edges form protocol-level bidirectional loops.

Router enforcement and role-local self-limitation must describe the same directed graph.

## 4. Second layer: department leader view

A department leader may define:

- internal sub-groups
- internal task split
- internal review loop
- internal testing loop
- department-local router domain

Department internals may be defined by documents or by executable network programs.

## 5. Future communication platform

A future agent communication platform can instantiate topology networks from Aegis organization definitions.

`aegis-master-kit` defines topology semantics; it does not mandate transport implementation.
