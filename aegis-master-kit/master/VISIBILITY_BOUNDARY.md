# Visibility Boundary

## 1. Rule

Every layer sees only the next layer's interface. It does not directly inspect or control that layer's internal structure.

```text
Developer
  -> Master
      -> Department leader
          -> Sub-department / group leader
              -> Atomic agent
```

## 2. What the Master can see

The Master can see:

- department identity
- department leader identity
- department capability boundary
- department input/output contract
- department state
- department escalation requests

The Master should not inspect:

- internal agent count
- internal deliberation traces
- internal sub-role topology
- internal execution details unless escalated

## 3. Why this exists

Visibility boundaries prevent:

- micro-management by the Master
- responsibility collapse
- global governance being polluted by local execution details
- unlimited all-to-all agent communication
