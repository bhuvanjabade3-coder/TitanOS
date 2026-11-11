"""Example TITAN plugin. Copy this directory into <data dir>/plugins/ and enable
it in the Plugins app. See docs/PLUGINS.md."""


def register(api):
    def greet(params):
        name = params.get("name") or "there"
        api.notify("Hello from a plugin", f"Hi {name}!")  # allowed: manifest grants `notifications`
        return {"greeting": f"Hi {name}!"}

    api.register_action(
        "greet", greet, "Greet someone and show a notification",
        params={"name": {"type": "string", "description": "Who to greet"}},
    )
