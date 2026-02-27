# Sanitise Mistral control tokens from user input

**Epic:** Security Hardening

**Points:** 1

## User Story

As a platform operator, I want Mistral control sequences stripped from user input so that users cannot break out of the instruction template.

## Acceptance Criteria

- [ ] `[INST]`, `[/INST]`, `<s>`, and `</s>` tokens are stripped from the user question before prompt construction
- [ ] The sanitisation happens before the prompt template is applied
- [ ] Normal user questions are unaffected
- [ ] Tests cover prompt injection attempts

## Technical Notes

Add a sanitisation function in `backend/inference/app.py`:

```python
import re

_CONTROL_TOKENS = re.compile(r"\[/?INST\]|</?s>", re.IGNORECASE)

def sanitise_prompt(text: str) -> str:
    return _CONTROL_TOKENS.sub("", text).strip()
```

Then in the `ask` endpoint:
```python
clean_question = sanitise_prompt(req.question)
prompt = f"<s>[INST] {clean_question} [/INST]"
```

This is defence-in-depth — it raises the bar for prompt injection but does not eliminate it entirely (the model may still follow adversarial instructions in natural language).

## Implementation Subtasks

- [ ] Add `sanitise_prompt` function to `app.py`
- [ ] Call it before constructing the prompt template
- [ ] Add tests: normal input unchanged, control tokens stripped, edge cases
- [ ] Consider logging sanitised inputs for monitoring

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
