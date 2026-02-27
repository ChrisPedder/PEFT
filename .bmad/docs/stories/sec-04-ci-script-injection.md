# Fix script injection in CI/CD workflow inputs

**Epic:** Security Hardening

**Points:** 2

## User Story

As a platform operator, I want CI/CD workflow inputs to be safely handled so that repository collaborators cannot inject arbitrary shell commands.

## Acceptance Criteria

- [ ] All `workflow_dispatch` inputs in `train.yml` are passed through `env:` blocks, not `${{ inputs.* }}` in `run:` blocks
- [ ] All string inputs in `process.yml` are validated before use (e.g. `sample_size` is a non-negative integer)
- [ ] All `workflow_dispatch` inputs in `update-model.yml` continue to use `env:` (already correct — verify)
- [ ] Shell variables are double-quoted in all `run:` blocks
- [ ] `actionlint` passes on all workflow files

## Technical Notes

The primary issue is in `.github/workflows/train.yml` lines 47-54 where `${{ inputs.learning_rate }}` and `${{ inputs.instance_type }}` are interpolated directly into the shell.

Fix pattern:
```yaml
# BEFORE (vulnerable):
run: |
  python script.py --rate ${{ inputs.learning_rate }}

# AFTER (safe):
env:
  LEARNING_RATE: ${{ inputs.learning_rate }}
run: |
  python script.py --rate "$LEARNING_RATE"
```

Also add input validation in `process.yml` for `sample_size`:
```bash
if ! [[ "$SAMPLE_SIZE" =~ ^[0-9]+$ ]]; then
  echo "Invalid sample_size"
  exit 1
fi
```

## Implementation Subtasks

- [ ] Refactor `train.yml` to pass all inputs via `env:` block
- [ ] Add input validation for string inputs in `process.yml`
- [ ] Audit `scrape.yml` for similar patterns
- [ ] Double-quote all shell variable references
- [ ] Run `actionlint` to verify

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
