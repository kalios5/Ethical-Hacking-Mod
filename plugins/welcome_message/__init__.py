PLUGIN_NAME = "Welcome Message"
PLUGIN_DESCRIPTION = "Greets returning customers by name."


def register(shop=None):
    pass


def render_widget(context=None):
    name = (context or {}).get("customer_name", "Guest")
    return f"<div class='welcome'>Welcome back, {name}!</div>"
