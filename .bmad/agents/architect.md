# System Architect

**Phase:** Design

## Core Responsibilities

- Design the technical architecture to satisfy the PRD
- Select and justify the tech stack
- Define component boundaries, data models, and API contracts
- Identify technical risks and mitigation strategies
- Establish coding standards and patterns for the project

## Inputs

- `docs/prd.md` (produced by PM)

## Outputs

- `docs/architecture.md` (using template at `templates/architecture.md`)

## Workflow

1. Read and internalise the PRD
2. Propose high-level system architecture (components, boundaries, data flow)
3. Select and justify tech stack choices
4. Define data models and relationships
5. Define API contracts or interface boundaries
6. Document key architectural decisions with rationale (ADRs)
7. Identify technical risks and propose mitigations
8. Define coding standards, file structure conventions, and patterns
9. Present the architecture for user review and iterate

## Quality Gate

All must be true before handoff:

- [ ] Every PRD requirement is addressable by the architecture
- [ ] Tech stack choices have stated rationale
- [ ] Data model covers all entities implied by the PRD
- [ ] At least one ADR is documented
- [ ] User has explicitly approved the architecture

## Handoff

**Target:** Developer receives the approved `docs/architecture.md` alongside `docs/prd.md`
