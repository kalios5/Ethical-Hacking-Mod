from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class PluginToggle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<PluginToggle {self.name} enabled={self.enabled}>"
