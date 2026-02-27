# Pin CI/CD pip installs with lockfiles and hashes

**Epic:** Security Hardening

**Points:** 3

## User Story

As a platform operator, I want CI/CD Python package installs to be reproducible and verified so that a compromised PyPI package cannot execute arbitrary code in my pipelines.

## Acceptance Criteria

- [ ] `update-model.yml` installs from a pinned requirements file with exact versions
- [ ] `ci.yml` Python installs are pinned
- [ ] `train.yml` Python installs are pinned
- [ ] Hash verification is used where practical (`--require-hashes`)
- [ ] Requirements files are committed to the repo

## Technical Notes

Create dedicated requirements files for CI workflows:

**`.github/requirements-merge.txt`** (for `update-model.yml`):
```
torch==2.5.1+cpu --hash=sha256:...
transformers==4.47.1 --hash=sha256:...
peft==0.14.0 --hash=sha256:...
accelerate==0.26.0 --hash=sha256:...
sentencepiece==0.2.0 --hash=sha256:...
protobuf==5.29.3 --hash=sha256:...
boto3==1.35.0 --hash=sha256:...
huggingface-hub==0.27.1 --hash=sha256:...
```

Generate with: `pip install pip-tools && pip-compile --generate-hashes requirements-merge.in`

Or use `uv` (already in the project): `uv pip compile --generate-hashes requirements-merge.in`

Update workflows to use: `pip install --require-hashes -r .github/requirements-merge.txt`

For `backend/inference/requirements.txt`, also pin exact versions (though the Docker build provides some isolation).

## Implementation Subtasks

- [ ] Create `.github/requirements-merge.txt` with pinned versions + hashes
- [ ] Update `update-model.yml` to use the pinned file
- [ ] Pin CI test dependencies in `ci.yml`
- [ ] Pin training launch dependencies in `train.yml`
- [ ] Pin `backend/inference/requirements.txt` to exact versions
- [ ] Verify all workflows pass

## Status

Todo | In Progress | In Review | **Done**
