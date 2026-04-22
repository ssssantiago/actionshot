# Adding a New Few-Shot Example

Few-shot examples teach Claude how to convert IR into rpakit scripts. They are stored in the `examples/` directory and selected dynamically based on similarity to the target workflow.

## Directory structure

```
examples/
  NN_descriptive_name/
    ir.json      # The IR for this example
    script.py    # The corresponding rpakit script
```

Use a two-digit prefix (e.g., `06_`) so examples sort predictably.

## Creating the IR (`ir.json`)

1. Start from a real recording or write the IR manually.
2. Include all required fields: `workflow_id`, `description`, `inputs`, `outputs`, `steps`, `assertions`.
3. Use realistic Brazilian law-firm data in examples (process numbers, CPFs, Portuguese labels).
4. Include the selector hierarchy (primary, tertiary at minimum) to demonstrate proper resolution.
5. Add appropriate assertions matching the rules in `ir_compiler.py`:
   - `field_has_value` after `fill_field`
   - `element_visible` after submit clicks
   - `output_not_empty` after `extract_text`

## Creating the script (`script.py`)

1. Import only `rpakit` (plus standard library or `openpyxl` if needed for data sources).
2. Define a `run()` function that accepts IR inputs as parameters.
3. Follow the pattern: define selectors, then wait + interact for each step.
4. Include assertion checks that match the IR's `assertions` list.
5. Add `if __name__ == "__main__":` with example values.
6. The script must be syntactically valid and runnable.

## Similarity matching

The prompt builder (`prompt_template.py`) selects 2-3 examples by scoring:

| Feature match         | Score |
|-----------------------|-------|
| Loop presence matches | +3    |
| Conditional matches   | +3    |
| Extract_text matches  | +2    |
| Step count within 3   | +1    |

To ensure your example gets selected for the right workflows, make sure its features (loops, conditionals, extractions) accurately reflect its category.

## Testing

After adding an example, verify it loads correctly:

```python
from actionshot.prompt_template import _load_all_examples
examples = _load_all_examples()
print([(e["name"], e["has_loop"], e["has_conditional"]) for e in examples])
```
