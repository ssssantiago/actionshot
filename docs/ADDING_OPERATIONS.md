# Adding a New IR Operation

This guide explains how to add a new canonical operation to ActionShot's Intermediate Representation.

## Steps

### 1. Register the operation in `ir_compiler.py`

Add the operation name to the `CANONICAL_OPS` frozenset:

```python
CANONICAL_OPS = frozenset({
    ...
    "my_new_op",
})
```

### 2. Add grouping logic in `_StepGrouper`

If the new operation requires multi-step pattern matching (e.g., two raw clicks that mean "select from dropdown"), add a `_try_my_new_op` method to `_StepGrouper`:

```python
def _try_my_new_op(self, i: int) -> int | None:
    """Detect my_new_op from raw steps. Returns steps consumed or None."""
    # Check if steps at index i match the pattern
    # If yes, append to self.ir_steps and return number of raw steps consumed
    # If no, return None
```

Then call it from the `run()` method's main loop, before the generic click handler.

### 3. Add assertion generation (if applicable)

In the `_generate_assertions` function, add a new case for your operation:

```python
elif op == "my_new_op":
    assertions.append({
        "after_step": step_id,
        "check": "my_check_type",
        ...
    })
```

### 4. Update the SDK reference in `prompt_template.py`

Add the corresponding rpakit API call to the `_SDK_REFERENCE` string so Claude knows how to generate code for it.

### 5. Add a few-shot example

Create a new directory under `examples/` with an `ir.json` and `script.py` that demonstrates the operation. See `docs/ADDING_FEWSHOT.md` for details.

### 6. Update rpakit SDK (if needed)

If the operation requires a new rpakit function, add it to `actionshot/rpakit.py`. Follow the existing pattern: selector resolution, wait, action, error handling.

## Checklist

- [ ] Added to `CANONICAL_OPS`
- [ ] Grouping logic in `_StepGrouper` (if multi-step)
- [ ] Assertion generation in `_generate_assertions`
- [ ] SDK reference updated in `prompt_template.py`
- [ ] Few-shot example in `examples/`
- [ ] rpakit SDK method (if new interaction type)
- [ ] Tested with a real recording
