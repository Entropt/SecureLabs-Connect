# Import routes here to make them available to the app
from .lti_routes import lti_bp
from .instance_routes import instance_bp
from .challenge_routes import challenge_bp

# List of all blueprints
all_blueprints = [lti_bp, instance_bp, challenge_bp]