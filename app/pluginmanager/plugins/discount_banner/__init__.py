PLUGIN_NAME = "Discount Banner"
PLUGIN_DESCRIPTION = "Shows a promotional banner on the storefront."


def register(shop=None):
    """Called once when the plugin is activated."""
    pass


def render_widget(context=None):
    """Called wherever the storefront wants this plugin's output."""
    return "<div class='banner'>10% off today only!</div>"
