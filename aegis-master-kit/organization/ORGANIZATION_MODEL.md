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

The Master does not care how many internal agents a department uses.

## 3. Second layer: department leader view

A department leader may define:

- internal sub-groups
- internal task split
- internal review loop
- internal testing loop
- department-local router domain

Department internals may be defined by documents or by executable network programs.

## 4. Future communication platform

A future agent communication platform can instantiate topology networks from Aegis organization definitions.

`aegis-master-kit` defines topology semantics; it does not mandate transport implementation.
