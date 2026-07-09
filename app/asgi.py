import app.main as main_module
from app.cover_crop import register_cover_crop_routes
from app.integrations.home_assistant import register_home_assistant_routes

app = main_module.app

register_cover_crop_routes(app, main_module)
register_home_assistant_routes(app)
