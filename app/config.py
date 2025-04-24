import os
from tempfile import mkdtemp

# Configuration
config = {
    "DEBUG": True,
    "ENV": "development",
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 600,
    "SECRET_KEY": "replace-me",
    "SESSION_TYPE": "filesystem",
    "SESSION_FILE_DIR": mkdtemp(),
    "SESSION_COOKIE_NAME": "Thesis",
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SECURE": False,   # should be True in case of HTTPS usage (production)
    "SESSION_COOKIE_SAMESITE": None,  # should be 'None' in case of HTTPS usage (production)
    "DEBUG_TB_INTERCEPT_REDIRECTS": False,
    "PORT_RANGE_START": 3001,         # Start of port range for Juice Shop instances
    "PORT_RANGE_END": 3999,           # End of port range for Juice Shop instances
    "DOCKER_NETWORK": "juice_shop_network", # Docker network name
    "HOST_IP": "172.22.183.134",      # Host IP to access Juice Shop instances (change to your server's public IP)
    "DB_PATH": "juice_shop_instances.db",  # Database file path
    "INSTANCE_EXPIRY_DAYS": 7         # Number of days before an instance expires
}

PAGE_TITLE = 'Security Challenges'

def get_lti_config_path():
    """Get the path to the LTI config file"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'configs', 'app.json')