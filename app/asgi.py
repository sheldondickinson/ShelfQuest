from app.main import app
from app.integrations.home_assistant import register_home_assistant_routes

register_home_assistant_routes(app)
