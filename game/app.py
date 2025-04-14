import datetime
import os
import pprint
import requests
import subprocess
import threading
import time
import random
from datetime import datetime, timedelta
import sqlite3

from tempfile import mkdtemp
from flask import Flask, jsonify, request, render_template, url_for, redirect
from flask_caching import Cache
from werkzeug.exceptions import Forbidden
from pylti1p3.contrib.flask import FlaskOIDCLogin, FlaskMessageLaunch, FlaskRequest, FlaskCacheDataStorage
from pylti1p3.deep_link_resource import DeepLinkResource
from pylti1p3.grade import Grade
from pylti1p3.lineitem import LineItem
from pylti1p3.tool_config import ToolConfJsonFile
from pylti1p3.registration import Registration


class ReverseProxied:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        scheme = environ.get('HTTP_X_FORWARDED_PROTO')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        return self.app(environ, start_response)


app = Flask('Thesis', template_folder='templates', static_folder='static')
app.wsgi_app = ReverseProxied(app.wsgi_app)

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
    "HOST_IP": "172.22.183.134",           # Host IP to access Juice Shop instances (change to your server's public IP)
    "DB_PATH": "juice_shop_instances.db",  # Database file path
    "INSTANCE_EXPIRY_DAYS": 7         # Number of days before an instance expires
}
app.config.from_mapping(config)
cache = Cache(app)

PAGE_TITLE = 'Security Challenges'

# Initialize database
def init_db():
    """Initialize the SQLite database for tracking Juice Shop instances"""
    conn = sqlite3.connect(app.config['DB_PATH'])
    c = conn.cursor()
    
    # Create instances table
    c.execute('''
    CREATE TABLE IF NOT EXISTS instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        container_id TEXT,
        port INTEGER,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assignment_id TEXT
    )
    ''')
    
    # Create solved challenges table
    c.execute('''
    CREATE TABLE IF NOT EXISTS solved_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        challenge_id INTEGER NOT NULL,
        solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assignment_id TEXT,
        UNIQUE(user_id, challenge_id, assignment_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Call init_db when the app starts
init_db()

class ExtendedFlaskMessageLaunch(FlaskMessageLaunch):

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


def get_lti_config_path():
    return os.path.join(app.root_path, '..', 'configs', 'game.json')


def get_launch_data_storage():
    return FlaskCacheDataStorage(cache)


def get_jwk_from_public_key(key_name):
    key_path = os.path.join(app.root_path, '..', 'configs', key_name)
    f = open(key_path, 'r')
    key_content = f.read()
    jwk = Registration.get_jwk(key_content)
    f.close()
    return jwk


def get_juice_shop_challenges():
    """Fetch challenges from Juice Shop API"""
           
    juice_shop_url = f"http://127.0.0.1:3000"
        
    response = requests.get(f"{juice_shop_url}/api/challenges/", 
                            headers={
                                'Accept-Language': 'en-GB,en;q=0.9',
                                'Accept': 'application/json, text/plain, */*',
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                                'Connection': 'keep-alive'
                            })
    if response.status_code == 200:
        return response.json().get('data', [])


def get_user_instance(user_id):
    """Get user's Juice Shop instance"""
    conn = sqlite3.connect(app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM instances WHERE user_id=? AND status='running'", (user_id,))
    instance = c.fetchone()
    
    if instance:
        # Update last accessed time
        c.execute("UPDATE instances SET last_accessed=? WHERE id=?", 
                 (datetime.now().isoformat(), instance['id']))
        conn.commit()
        
        instance_dict = dict(instance)
        instance_dict['url'] = f"http://{app.config['HOST_IP']}:{instance['port']}"
        instance_dict['exists'] = True
    else:
        instance_dict = {'exists': False}
    
    conn.close()
    return instance_dict


def find_available_port():
    """Find an available port in the configured range"""
    conn = sqlite3.connect(app.config['DB_PATH'])
    c = conn.cursor()
    
    # Get all ports currently in use
    c.execute("SELECT port FROM instances WHERE status='running'")
    used_ports = [row[0] for row in c.fetchall()]
    conn.close()
    
    # Find available port
    port_range = list(range(app.config['PORT_RANGE_START'], app.config['PORT_RANGE_END'] + 1))
    available_ports = [p for p in port_range if p not in used_ports]
    
    if not available_ports:
        raise Exception("No available ports in the specified range")
    
    # Randomize port selection for better distribution
    return random.choice(available_ports)


def create_docker_instance(user_id, assignment_id=None):
    """Create a new Juice Shop Docker instance for the user"""
    try:
        # Check if user already has an instance
        conn = sqlite3.connect(app.config['DB_PATH'])
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM instances WHERE user_id=? AND status='running'", (user_id,))
        existing_instance = c.fetchone()
        
        if existing_instance:
            return {
                'success': False,
                'message': 'User already has a running instance',
                'instance': dict(existing_instance)
            }
        
        # Find available port
        port = find_available_port()
        
        # Create Docker container
        container_name = f"juice_shop_{user_id}_{port}"
        
        # Run the docker command
        cmd = [
            "docker", "run", "--rm", "-d",
            "--name", container_name,
            "-e", "NODE_ENV=unsafe",
            "-p", f"{port}:3000",
            "bkimminich/juice-shop"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Failed to create Docker container: {result.stderr}")
        
        container_id = result.stdout.strip()
        
        # Save instance info to database
        c.execute("""
            INSERT INTO instances (user_id, container_id, port, status, assignment_id, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, container_id, port, 'running', assignment_id, 
              datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        
        instance_id = c.lastrowid
        
        conn.close()
        
        return {
            'success': True,
            'container_id': container_id,
            'port': port,
            'instance_id': instance_id,
            'url': f"http://{app.config['HOST_IP']}:{port}"
        }
    
    except Exception as e:
        app.logger.error(f"Error creating Docker instance: {str(e)}")
        return {'success': False, 'message': str(e)}


def restart_docker_instance(user_id):
    """Restart a user's Docker instance"""
    try:
        # Get user's current instance
        conn = sqlite3.connect(app.config['DB_PATH'])
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM instances WHERE user_id=? AND status='running'", (user_id,))
        instance = c.fetchone()
        
        if not instance:
            conn.close()
            return {'success': False, 'message': 'No running instance found'}
        
        # Stop the container
        container_id = instance['container_id']
        
        stop_cmd = ["docker", "stop", container_id]
        stop_result = subprocess.run(stop_cmd, capture_output=True, text=True)
        
        if stop_result.returncode != 0:
            app.logger.error(f"Failed to stop container {container_id}: {stop_result.stderr}")
        
        # Update instance status
        c.execute("UPDATE instances SET status='stopped' WHERE id=?", (instance['id'],))
        conn.commit()
        
        # Create a new instance
        conn.close()
        
        create_result = create_docker_instance(user_id, instance['assignment_id'])
        return create_result
    
    except Exception as e:
        app.logger.error(f"Error restarting Docker instance: {str(e)}")
        return {'success': False, 'message': str(e)}


def cleanup_expired_instances():
    """Cleanup expired Docker instances"""
    try:
        conn = sqlite3.connect(app.config['DB_PATH'])
        c = conn.cursor()
        
        # Get expired instances
        expiry_date = (datetime.now() - timedelta(days=app.config['INSTANCE_EXPIRY_DAYS'])).isoformat()
        
        c.execute("""
            SELECT id, container_id FROM instances 
            WHERE status='running' AND last_accessed < ?
        """, (expiry_date,))
        
        expired_instances = c.fetchall()
        
        for instance_id, container_id in expired_instances:
            # Stop the container
            try:
                stop_cmd = ["docker", "stop", container_id]
                subprocess.run(stop_cmd, capture_output=True, text=True)
            except Exception as e:
                app.logger.error(f"Error stopping container {container_id}: {str(e)}")
            
            # Update instance status
            c.execute("UPDATE instances SET status='expired' WHERE id=?", (instance_id,))
        
        conn.commit()
        conn.close()
        
        return {'success': True, 'cleaned_count': len(expired_instances)}
    
    except Exception as e:
        app.logger.error(f"Error cleaning up expired instances: {str(e)}")
        return {'success': False, 'message': str(e)}


def get_user_challenges(user_id, assignment_id=None):
    """Get challenges and user's progress for a specific assignment"""
    try:
        # Get user's instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            return {'challenges': [], 'completed': 0, 'total': 0}
        
        # Fetch challenges from Juice Shop
        juice_shop_url = instance['url']
        
        response = requests.get(f"{juice_shop_url}/api/challenges/", 
                                headers={
                                    'Accept-Language': 'en-GB,en;q=0.9',
                                    'Accept': 'application/json, text/plain, */*',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                                    'Connection': 'keep-alive'
                                })
        
        if response.status_code != 200:
            return {'challenges': [], 'completed': 0, 'total': 0}
        
        challenges = response.json().get('data', [])
        
        # Get user's solved challenges
        conn = sqlite3.connect(app.config['DB_PATH'])
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        query = "SELECT challenge_id FROM solved_challenges WHERE user_id=?"
        params = [user_id]
        
        if assignment_id:
            query += " AND assignment_id=?"
            params.append(assignment_id)
        
        c.execute(query, params)
        solved_challenges = [row['challenge_id'] for row in c.fetchall()]
        conn.close()
        
        # Mark solved challenges
        for challenge in challenges:
            if challenge['id'] in solved_challenges:
                challenge['completed'] = True
            else:
                challenge['completed'] = False
        
        # Filter challenges if needed based on assignment
        # This would depend on how you want to assign specific challenges to assignments
        
        completed_count = len([c for c in challenges if c.get('completed', False)])
        
        return {
            'challenges': challenges,
            'completed': completed_count,
            'total': len(challenges)
        }
    
    except Exception as e:
        app.logger.error(f"Error fetching user challenges: {str(e)}")
        return {'challenges': [], 'completed': 0, 'total': 0}


def check_challenge_completion(user_id, assignment_id=None):
    """Check if user has completed challenges and save to database"""
    try:
        # Get user's instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            return {'success': False, 'message': 'No running instance found'}
        
        # Fetch challenges from Juice Shop
        juice_shop_url = instance['url']
        
        response = requests.get(f"{juice_shop_url}/api/challenges/", 
                                headers={
                                    'Accept-Language': 'en-GB,en;q=0.9',
                                    'Accept': 'application/json, text/plain, */*',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                                    'Connection': 'keep-alive'
                                })
        
        if response.status_code != 200:
            return {'success': False, 'message': 'Failed to fetch challenges'}
        
        challenges = response.json().get('data', [])
        
        # Get solved challenges
        solved_challenges = [c for c in challenges if c.get('solved', False)]
        
        # Save to database
        conn = sqlite3.connect(app.config['DB_PATH'])
        c = conn.cursor()
        
        for challenge in solved_challenges:
            try:
                c.execute("""
                    INSERT OR IGNORE INTO solved_challenges 
                    (user_id, challenge_id, assignment_id, solved_at)
                    VALUES (?, ?, ?, ?)
                """, (user_id, challenge['id'], assignment_id, datetime.now().isoformat()))
            except Exception as e:
                app.logger.error(f"Error saving solved challenge: {str(e)}")
        
        conn.commit()
        conn.close()
        
        # Get updated challenge status
        return get_user_challenges(user_id, assignment_id)
    
    except Exception as e:
        app.logger.error(f"Error checking challenge completion: {str(e)}")
        return {'success': False, 'message': str(e)}


# Start a background thread to clean up expired instances
def cleanup_thread():
    while True:
        try:
            cleanup_expired_instances()
        except Exception as e:
            app.logger.error(f"Error in cleanup thread: {str(e)}")
        
        # Sleep for 1 hour
        time.sleep(3600)

# Start the cleanup thread
cleanup_thread = threading.Thread(target=cleanup_thread, daemon=True)
cleanup_thread.start()


# Routes

@app.route('/login/', methods=['GET', 'POST'])
def login():
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    launch_data_storage = get_launch_data_storage()

    flask_request = FlaskRequest()
    target_link_uri = flask_request.get_param('target_link_uri')
    if not target_link_uri:
        raise Exception('Missing "target_link_uri" param')

    oidc_login = FlaskOIDCLogin(flask_request, tool_conf, launch_data_storage=launch_data_storage)
    return oidc_login\
        .enable_check_cookies()\
        .redirect(target_link_uri)


@app.route('/jwks/', methods=['GET'])
def get_jwks():
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    return tool_conf.get_jwks()["keys"][0]


@app.route('/configure/<launch_id>/<int:challenge_id>/', methods=['GET', 'POST'])
def configure(launch_id, challenge_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                        launch_data_storage=launch_data_storage)

    if not message_launch.is_deep_link_launch():
        # For regular launches, redirect to assignment page
        user_id = message_launch.get_launch_data().get('sub')
        assignment_id = message_launch.get_launch_data().get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
        
        return redirect(f"/assignment/{launch_id}/{user_id}/{assignment_id}")

    # For deep linking, create a resource that will redirect to assignment page
    launch_url = f"{request.url_root}assignment"

    resource = DeepLinkResource()
    resource.set_url(launch_url) \
        .set_custom_params({'challenge_id': challenge_id}) \
        .set_title('Security Challenge')

    html = message_launch.get_deep_link().output_response_form([resource])
    return html


@app.route('/assignment/<launch_id>/<user_id>/<assignment_id>', methods=['GET'])
def assignment(launch_id, user_id, assignment_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    
    try:
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        
        message_launch_data = message_launch.get_launch_data()
        
        # Verify user_id matches the one in the launch data to prevent unauthorized access
        launch_user_id = message_launch_data.get('sub')
        
        if launch_user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        tpl_kwargs = {
            'page_title': PAGE_TITLE,
            'launch_id': launch_id,
            'user_id': user_id,
            'assignment_id': assignment_id
        }
        
        return render_template('assignment.html', **tpl_kwargs)
    
    except Exception as e:
        app.logger.error(f"Error loading assignment page: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/instance-status/<launch_id>/<user_id>', methods=['GET'])
def instance_status(launch_id, user_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    
    try:
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        
        # Verify user_id matches the one in the launch data to prevent unauthorized access
        launch_user_id = message_launch.get_launch_data().get('sub')
        
        if launch_user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        # Get user's instance
        instance = get_user_instance(user_id)
        
        return jsonify(instance)
    
    except Exception as e:
        app.logger.error(f"Error checking instance status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/create-instance/<launch_id>/<user_id>', methods=['POST'])
def create_instance(launch_id, user_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    
    try:
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        
        # Verify user_id matches the one in the launch data to prevent unauthorized access
        launch_user_id = message_launch.get_launch_data().get('sub')
        
        if launch_user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        # Get assignment ID from launch data
        assignment_id = message_launch.get_launch_data().get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
        
        # Create Docker instance
        result = create_docker_instance(user_id, assignment_id)
        
        return jsonify(result)
    
    except Exception as e:
        app.logger.error(f"Error creating instance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/restart-instance/<launch_id>/<user_id>', methods=['POST'])
def restart_instance(launch_id, user_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    
    try:
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        
        # Verify user_id matches the one in the launch data to prevent unauthorized access
        launch_user_id = message_launch.get_launch_data().get('sub')
        
        if launch_user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        # Restart Docker instance
        result = restart_docker_instance(user_id)
        
        return jsonify(result)
    
    except Exception as e:
        app.logger.error(f"Error restarting instance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/assignment/', methods=['GET', 'POST'])
def assignment_page():
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch(flask_request, tool_conf, launch_data_storage=launch_data_storage)
    message_launch_data = message_launch.get_launch_data()
    pprint.pprint(message_launch_data)

    if message_launch.is_deep_link_launch():
        # Fetch challenges for deep linking
        challenges = get_juice_shop_challenges()
        
        # Group challenges by category for better organization
        challenge_categories = {}
        for challenge in challenges:
            category = challenge.get('category', 'Uncategorized')
            if category not in challenge_categories:
                challenge_categories[category] = []
            challenge_categories[category].append(challenge)

        tpl_kwargs = {
            'page_title': PAGE_TITLE,
            'is_deep_link_launch': True,
            'launch_data': message_launch_data,
            'launch_id': message_launch.get_launch_id(),
            'challenges': challenges,
            'challenge_categories': challenge_categories
        }
        return render_template('game.html', **tpl_kwargs)
    else:
        # Regular launch - direct to assignment page
        # Extract user_id from launch data
        user_id = message_launch_data.get('sub')
        assignment_id = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
        
        tpl_kwargs = {
            'page_title': PAGE_TITLE,
            'launch_id': message_launch.get_launch_id(),
            'user_id': user_id,
            'assignment_id': assignment_id,
        }
        return render_template('assignment.html', **tpl_kwargs)

@app.route('/api/challenge-list/<launch_id>/<assignment_id>', methods=['GET'])
def challenge_list(launch_id, assignment_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    
    try:
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        
        user_id = message_launch.get_launch_data().get('sub')
        
        # Get challenges for the user
        challenges_data = get_user_challenges(user_id, assignment_id)
        
        return jsonify({
            'challenges': challenges_data['challenges'], 
            'completed': challenges_data['completed'],
            'total': challenges_data['total']
        })
    
    except Exception as e:
        app.logger.error(f"Error getting challenge list: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/challenge-status/<launch_id>/<user_id>/<assignment_id>', methods=['GET'])
def challenge_status(launch_id, user_id, assignment_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    
    try:
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        
        # Verify user_id matches the one in the launch data to prevent unauthorized access
        launch_user_id = message_launch.get_launch_data().get('sub')
        
        if launch_user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        # Check challenge completion
        challenges_data = check_challenge_completion(user_id, assignment_id)
        
        return jsonify({
            'challenges': challenges_data['challenges'], 
            'completed': challenges_data['completed'],
            'total': challenges_data['total']
        })
    
    except Exception as e:
        app.logger.error(f"Error checking challenge status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/score/<launch_id>/<earned_score>/', methods=['POST'])
def score(launch_id, earned_score):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                        launch_data_storage=launch_data_storage)

    if not message_launch.has_ags():
        raise Forbidden("Don't have grades!")

    sub = message_launch.get_launch_data().get('sub')
    timestamp = datetime.datetime.now().isoformat() + 'Z'
    earned_score = int(earned_score)

    grades = message_launch.get_ags()
    
    # Create a Grade object
    sc = Grade()
    sc.set_score_given(earned_score) \
        .set_score_maximum(100) \
        .set_timestamp(timestamp) \
        .set_activity_progress('Completed') \
        .set_grading_progress('FullyGraded') \
        .set_user_id(sub)
    
    # Use the default line item (don't create a new one)
    # This will post the grade back to the original assignment
    result = grades.put_grade(sc)

    return jsonify({'success': True, 'result': result.get('body')})


@app.route('/api/check-challenge-status/<launch_id>/<int:challenge_id>/', methods=['GET'])
def check_challenge_status(launch_id, challenge_id):
    """Check if a challenge has been solved by calling Juice Shop API"""
    try:
        # Fetch the current status of all challenges
        challenges = get_juice_shop_challenges()
        
        # Find the specific challenge
        for challenge in challenges:
            if challenge.get('id') == challenge_id:
                # Return the solved status
                return jsonify({
                    'id': challenge_id,
                    'solved': challenge.get('solved', False)
                })
        
        return jsonify({'error': 'Challenge not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scoreboard/<launch_id>/', methods=['GET', 'POST'])
def scoreboard(launch_id):
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                        launch_data_storage=launch_data_storage)

    if not message_launch.has_nrps():
        raise Forbidden("Don't have names and roles!")

    if not message_launch.has_ags():
        raise Forbidden("Don't have grades!")

    ags = message_launch.get_ags()
    
    # Get grades from the default line item
    scores = ags.get_grades()
    
    members = message_launch.get_nrps().get_members()
    scoreboard_result = []

    for sc in scores:
        result = {
            'score': sc['resultScore']
        }
        
        for member in members:
            if member['user_id'] == sc['userId']:
                result['name'] = member.get('name', 'Unknown')
                break
        
        scoreboard_result.append(result)

    return jsonify(scoreboard_result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9001)