# Debate Internal Topology Contract

## 1. Purpose

This contract defines the internal communication shape used inside a single Debate Department run.

The goal is to let every worker know what other workers said while preventing uncontrolled group chat and infinite message loops.

## 2. Default topology

The default topology is leader-mediated round-robin broadcast.

```text
                 +------------------+
                 |  Debate Leader   |
                 +------------------+
                  ^      ^       ^
                  |      |       |
              turn|  turn|   turn|
                  |      |       |
            +-----+  +---+---+   +-----+
            | W1  |  | W2    |   | Wn  |
            +-----+  +-------+   +-----+

worker turn -> leader
leader appends to transcript
leader broadcasts updated transcript to all workers
leader selects next speaker
```

## 3. Why not full mesh

Worker full mesh is not the default because it increases:

- message explosion;
- ordering ambiguity;
- repeated arguments;
- hidden side-channel reasoning;
- infinite debate risk;
- Leader adjudication difficulty.

## 4. Communication permissions

Within a debate run:

- a worker may send only to the Leader;
- the Leader may send transcript updates to all workers;
- the Leader may send turn instructions to one selected worker;
- workers must not open uncontrolled direct peer-to-peer chats unless a future contract explicitly enables a constrained variant.

## 5. Broadcast semantics

Broadcast does not mean simultaneous free-form speaking.

Broadcast means every worker receives the same canonical transcript state before its next turn.

The Leader owns the canonical transcript.

## 6. Turn ordering

The Leader must define a speaking order at the start of each round.

Common policies:

```text
fixed_order
weakest_first
strongest_first
last_attacked_first
leader_selected
```

The selected policy must be recorded in run metadata.

## 7. Transcript model

The transcript is append-only during a run.

Each turn entry must include:

```yaml
round: ...
turn_index: ...
worker_id: ...
stance_id: ...
turn_type: ...
content_ref: ...
summary: ...
new_information: true|false
```

## 8. Termination support

The topology must support termination by the Leader.

Workers must stop when the Leader declares:

```text
DEBATE_STOP
```

After this signal, workers may only provide final short self-status if requested.

## 9. Resource release

The internal topology is temporary. It must be released after final report generation.

No worker-to-worker route survives beyond the run.
