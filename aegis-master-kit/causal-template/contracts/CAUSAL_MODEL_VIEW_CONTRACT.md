# Causal Model View Contract

## Definition

A model-readable causal view is the selected and expanded subset of the Causal Store that Master injects into an agent's context.

## Why it exists

Models should not consume encrypted binary payloads or full causal graphs. A route/expand view lowers reasoning burden while preserving necessary causal support.

## View generation

Master must:

1. verify local sealed causal payload
2. decrypt and parse in Master-controlled runtime
3. select relevant claims using current query and route plan
4. expand each selected claim according to expand grade
5. emit YAML/JSON/Markdown for agent use

## View content

A view may include:

- current query
- selected causal claims
- claim ids
- claim text
- why summaries
- assumptions
- evidence summaries or refs according to expand grade
- warnings for tentative/conflicted claims

A view must not include:

- private security material
- hidden proof logic
- full chain-of-thought
- unselected full payload
