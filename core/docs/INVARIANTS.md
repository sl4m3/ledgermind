# Agent Memory Core: Architectural Invariants

This document defines the core rules that MUST NOT be broken by any changes to the codebase.

## I1: Semantic Immutability
Core meaning fields (`target`, `rationale`, `content`, `choice`) are immutable once written. 
Knowledge evolution MUST happen only through `supersede` (creating a new file).

## I2: Physical Append-Only (Semantic)
Memory files in the semantic store MUST NOT be deleted or overwritten by the API. 
The only allowed change is status/link update in the YAML frontmatter.

## I3: Bidirectional Links
If Decision A is `superseded_by` Decision B, Decision B MUST have a `supersedes` link back to Decision A.
Broken or one-way links are considered corruption.

## I4: Single Active Reality
For any given `target`, there can be AT MOST one decision with `status: active`.
Conflicts MUST be resolved before a new active decision for the same target is accepted.

## I5: Acyclic Knowledge Evolution
The supersede graph MUST be a Directed Acyclic Graph (DAG). 
Cycles (A -> B -> A) are strictly prohibited and will result in a system halt.

## I6: Immortal Evidence
Episodic events linked to semantic decisions MUST NEVER be physically pruned (deleted), 
regardless of their age or TTL.

## I7: The Hypothesis Invariant
The Reflection engine MUST only create memories of `kind: proposal`. No automated process is allowed to create or modify `kind: decision` directly. Transition from `proposal` to `decision` requires an explicit `ResolutionIntent` signed by a trusted boundary.
Proposals MUST NOT interfere with the Single Active Reality (I4) or Conflict Engine until accepted.
