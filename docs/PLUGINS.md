# Writing a TITAN plugin

A plugin is a directory in `~/.local/share/titan/plugins/<id>/`:

```
example_hello/
  manifest.json
  plugin.py
```

`manifest.json`:

```json
{ "id": "example_hello", "name": "Hello Example", "version": "1.0.0",
  "description": "…", "permissions": ["notifications"], "entry": "plugin.py" }
```

- `id` must match the directory name (`[a-z][a-z0-9_]*`). `version` is semantic.
- `permissions` lists the action categories the plugin may use through TITAN:
  `files terminal apps windows input browser memory notifications system
  settings dev security tasks preferences`. Unknown permissions invalidate the
  manifest.

`plugin.py` exposes `register(api)`:

```python
def register(api):
    api.register_action("greet", lambda p: {"hi": p.get("name", "you")},
                        "Greet someone", params={"name": {"type": "string"}}, risk="low")
```

| API | Notes |
|---|---|
| `api.register_action(name, handler, description, params=None, required=None, risk="low")` | Appears as `plugin.<id>.<name>` to the UI and the assistant. `risk` of `medium`/`high` makes it ask for approval. |
| `api.perform(action, params)` | Calls a TITAN action. Refused unless the action's category is in your manifest; risk gates and approvals still apply. Returns `{"status": ...}`. |
| `api.notify(title, body)` | Needs the `notifications` permission. |

Plugins are discovered disabled. The user enables them in the Plugins app, which
shows the permissions being granted. Errors during load or in a handler are
caught and shown; they do not crash TITAN. Plugins run inside TITAN Core and are
not sandboxed, so they must be trusted (see SECURITY.md).

Try it: `cp -r plugins/example_hello ~/.local/share/titan/plugins/`.
