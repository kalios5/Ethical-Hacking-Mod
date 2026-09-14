"""
HOW TO CREATE A NEW PLUGIN
--------------------------
1. Copy this whole folder and rename it to your plugin's name
   (use lowercase and underscores, no spaces, e.g. "loyalty_points").
2. Fill in PLUGIN_NAME, PLUGIN_DESCRIPTION, and render_widget() below.
"""

PLUGIN_NAME = "Your Plugin Name"
PLUGIN_DESCRIPTION = "One-line description of what this plugin does."


def register(shop=None):
    # Optional one-time setup logic, runs once when activated.
    pass


def render_widget(context=None):
    # Return the HTML this plugin should display on the storefront.
    return "<div>Hello from my plugin!</div>"
