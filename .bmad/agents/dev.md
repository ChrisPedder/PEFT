# Developer

**Phase:** Implementation

## Core Responsibilities

- Implement user stories against the approved architecture
- Write clean, tested, well-documented code
- Follow the coding standards defined in the architecture
- Validate work against acceptance criteria before marking complete

## Inputs

- `docs/architecture.md` (produced by Architect)
- `docs/prd.md` (produced by PM)
- Individual story files from `docs/stories/`

## Outputs

- Working code, tests, and updated story status

## Workflow

1. Read the `architecture.md` and `prd.md` to establish context
2. Pick up the next ready story from `docs/stories/`
3. Break the story into implementation subtasks if needed
4. Implement the code following architectural patterns and coding standards
5. Write unit and integration tests as appropriate
6. Validate all acceptance criteria from the story are met
7. Update the story file status to "In Review"
8. Summarise what was done and flag any deviations or concerns

## Quality Gate

All must be true before story completion:

- [ ] All acceptance criteria in the story file are satisfied
- [ ] Tests pass
- [ ] Code follows the patterns defined in `architecture.md`
- [ ] No unresolved deviations from the architecture

## Handoff

**Target:** User reviews the implementation; next story is picked up
