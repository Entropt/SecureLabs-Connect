import signal
import sys
import threading
import time
import atexit  # Import atexit for cleanup on exit
from flask import Flask
from flask_caching import Cache

from config import config, PAGE_TITLE
from models.database import init_db
from utils.helpers import ReverseProxied
from services.docker_service import cleanup_all_containers, cleanup_expired_instances, start_master_juice_shop, stop_master_juice_shop
from routes import all_blueprints
from pylti1p3.contrib.flask import FlaskMessageLaunch

app = Flask('Thesis', template_folder='templates', static_folder='static')
app.wsgi_app = ReverseProxied(app.wsgi_app)
app.config.from_mapping(config)

# Store cache as an app attribute so it can be easily accessed
cache = Cache(app)
app.cache = cache  # Make it accessible directly

# Initialize database with explicit db_path
init_db(app.config['DB_PATH'])

# Define the ExtendedFlaskMessageLaunch class
class ExtendedFlaskMessageLaunch(FlaskMessageLaunch):
    """
    Extended version of FlaskMessageLaunch that handles validation issues with IMSGlobal.
    """
    def validate_nonce(self):
        """
        Probably it is bug on "https://lti-ri.imsglobal.org":
        site passes invalid "nonce" value during deep links launch.
        Because of this in case of iss == http://imsglobal.org just skip nonce validation.
        """
        iss = self.get_iss()
        deep_link_launch = self.is_deep_link_launch()
        if iss == "http://imsglobal.org" and deep_link_launch:
            return self
        return super().validate_nonce()

# Register blueprints
for blueprint in all_blueprints:
    app.register_blueprint(blueprint)

# Function to guarantee cleanup on application exit
def ensure_cleanup():
    """Ensure all Docker containers are cleaned up on exit"""
    app.logger.info("Application shutting down, cleaning up Docker containers...")
    with app.app_context():
        cleanup_all_containers()

# Register the cleanup function with atexit
atexit.register(ensure_cleanup)

# Start a background thread to clean up expired instances
def start_cleanup_thread():
    def cleanup_thread_func():
        while True:
            try:
                with app.app_context():
                    cleanup_expired_instances()
            except Exception as e:
                app.logger.error(f"Error in cleanup thread: {str(e)}")
            
            # Sleep for 1 hour
            time.sleep(3600)
    
    cleanup_thread = threading.Thread(target=cleanup_thread_func, daemon=True)
    cleanup_thread.start()
    return cleanup_thread

if __name__ == '__main__':
    # Register signal handlers only in main thread
    def signal_handler(sig, frame):
        """Handle exit signals to cleanup resources"""
        app.logger.info(f"Received signal {sig}, cleaning up...")
        with app.app_context():
            cleanup_all_containers()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the cleanup thread
    cleanup_thread = start_cleanup_thread()
    
    # Start the master Juice Shop container
    with app.app_context():
        start_result = start_master_juice_shop()
        if start_result['success']:
            app.logger.info("Master Juice Shop container started successfully")
        else:
            app.logger.error(f"Failed to start master Juice Shop container: {start_result.get('message', 'Unknown error')}")
    
    app.run(host='0.0.0.0', port=9001)