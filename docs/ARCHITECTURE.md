# Aegis Architecture

## 1. Two different concepts

Aegis separates organization from business.

```text
Organization system:
  aegis-master-kit

Concrete business instance:
  code-repo
  aegis-archive
  aegis-causal
  aegis-knowledge
```

The organization system can handle many businesses, just like a company can run many projects through stable departments.

## 2. Layered visibility

Each layer sees only the next layer's interface.

```text
Developer
  -> Master
      -> Department leader
          -> Sub-department / group leader
              -> Atomic agent
```

The Master sees departments, department leaders, department status, and department input/output contracts. The Master does not directly inspect every internal agent.

## 3. Router domains

Each hub owns a local routing domain.

- The Master owns a top-level router domain for department leaders.
- Each department leader may own a department-local router domain.
- Each sub-department leader may own another nested router domain.

Routers do not judge payload truth. Routers only handle identity, visibility, routing, mailbox state, ack, heartbeat, and logs.

## 4. Business state libraries

A concrete business uses three state libraries:

- Archive: what happened.
- Knowledge: what is known.
- Causal: why something holds.

These libraries are not part of `aegis-master-kit`; they belong to the business instance.
