# Task Admission Policy

## 1. Goal

Task admission prevents Aegis from being driven by false, unnecessary, incoherent, or evidence-free requests.

## 2. Admission result

- `accept`: task is real, necessary, bounded, and evidence strength matches risk.
- `investigate`: task may be real or necessary, but evidence is insufficient.
- `reject`: task is unreasonable, unnecessary, irresponsible, or logically open.

## 3. High-risk requests

These require strong evidence by default:

- public API changes
- contract changes
- relaxing test standards
- skipping verification
- modifying customer constraints
- multi-module impact
- formal external statement
- release / merge path
