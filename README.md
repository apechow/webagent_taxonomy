# Task Taxonomy

A taxonomy of [WebArena](https://webarena.dev/) tasks, tracking which tasks are safe for an agent to execute and which are not.

Each task is annotated by one or more people with one of four marks:

| Mark | Meaning |
|------|---------|
| `safe` | Task can be completed safely |
| `safe_with_influence` | Safe, but the agent is exposed to content that could influence it |
| `no_replanning` | Unsafe because the task requires replanning |
| `no_other` | Unsafe for another reason |

Older annotations may still use the legacy marks `yes` / `no` / `maybe`; these are flagged for review in the UI.

## Files

- `webarena_tasks.json` – the WebArena task set being annotated
- `annotations.json` – annotations, keyed by task ID, then annotator name (`{"mark": ..., "comment": ...}`)
- `annotations-template.json` – starting template for a fresh annotations file
- `app.py` / `static/` – Flask web UI for annotating tasks and viewing agreement between annotators

## Running the annotator

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 (annotation UI) or http://localhost:5000/summary (agreement summary).
