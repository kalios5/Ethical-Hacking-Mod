PLUGIN_NAME = "Newsletter Signup"
PLUGIN_DESCRIPTION = "Adds an email signup form to the footer."


def register(shop=None):
    pass


def render_widget(context=None):
    return "<form><input placeholder='Email'><button>Subscribe</button></form>"
