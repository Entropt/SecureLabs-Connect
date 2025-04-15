import os
import pprint
import requests
import subprocess
import threading
import time
import random
import signal
import sys
import json
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

# Running docker containers
running_containers = []

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
    
    # Create assignment challenges table (NEW)
    c.execute('''
    CREATE TABLE IF NOT EXISTS assignment_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id TEXT NOT NULL,
        challenge_id INTEGER NOT NULL,
        challenge_name TEXT NOT NULL,
        challenge_description TEXT,
        challenge_difficulty INTEGER,
        UNIQUE(assignment_id, challenge_id)
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
    return []


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
            conn.close()
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
        
        # Keep track of running containers
        global running_containers
        running_containers.append(container_id)
        
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
        
        # Remove from running containers list
        global running_containers
        if container_id in running_containers:
            running_containers.remove(container_id)
        
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
                
                # Remove from running containers list
                global running_containers
                if container_id in running_containers:
                    running_containers.remove(container_id)
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


def get_assigned_challenges(assignment_id):
    """Get challenges assigned to a specific assignment"""
    conn = sqlite3.connect(app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM assignment_challenges 
        WHERE assignment_id = ?
    """, (assignment_id,))
    
    challenges = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return challenges


def get_user_challenges(user_id, assignment_id=None):
    """Get challenges and user's progress for a specific assignment"""
    try:
        # Get user's instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            return {'challenges': [], 'completed': 0, 'total': 0}
        
        # Fetch all challenges from Juice Shop first (we'll need this either way)
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
        
        all_challenges = response.json().get('data', [])
        
        # If assignment_id is provided, get only assigned challenges
        if assignment_id:
            # Get assigned challenges from database
            assigned_challenges = get_assigned_challenges(assignment_id)
            
            if assigned_challenges:
                # We have assigned challenges, use those
                challenges = []
                for assigned in assigned_challenges:
                    for challenge in all_challenges:
                        if assigned['challenge_id'] == challenge['id']:
                            # Merge the info from both sources
                            challenge_info = {
                                'id': challenge['id'],
                                'name': assigned['challenge_name'],
                                'description': assigned['challenge_description'],
                                'difficulty': assigned['challenge_difficulty'],
                                'solved': challenge.get('solved', False)
                            }
                            challenges.append(challenge_info)
                            break
            else:
                # No challenges specifically assigned yet
                # Check if we're in a transition state where the assignment was just created
                # but challenges haven't been saved to the database yet
                
                # Get custom parameters from the launch data
                conn = sqlite3.connect(app.config['DB_PATH'])
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                # Get a sample of easier challenges as a fallback
                # This is just a temporary measure until proper challenges are assigned
                easier_challenges = []
                for challenge in all_challenges:
                    if challenge.get('difficulty', 6) <= 2:  # Only include easy challenges (difficulty 1-2)
                        easier_challenges.append({
                            'id': challenge['id'],
                            'name': challenge['name'],
                            'description': challenge.get('description', ''),
                            'difficulty': challenge.get('difficulty', 1),
                            'solved': challenge.get('solved', False)
                        })
                        # Limit to 5 challenges for the fallback set
                        if len(easier_challenges) >= 5:
                            break
                
                challenges = easier_challenges
                
                # Also attempt to save these challenges to the assignment
                if challenges and assignment_id:
                    try:
                        save_assigned_challenges(assignment_id, challenges)
                        app.logger.info(f"Saved fallback challenges for assignment {assignment_id}")
                    except Exception as e:
                        app.logger.error(f"Error saving fallback challenges: {str(e)}")
        else:
            # No assignment_id, get all challenges from Juice Shop (old behavior)
            challenges = []
            for challenge in all_challenges:
                challenges.append({
                    'id': challenge['id'],
                    'name': challenge['name'],
                    'description': challenge.get('description', ''),
                    'difficulty': challenge.get('difficulty', 1),
                    'solved': challenge.get('solved', False)
                })
        
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
            # Check both the solved flag from the API and our database
            challenge['completed'] = challenge.get('solved', False) or challenge['id'] in solved_challenges
        
        # Count completed challenges
        completed_count = len([c for c in challenges if c.get('completed', False)])
        
        return {
            'challenges': challenges,
            'completed': completed_count,
            'total': len(challenges)
        }
    
    except Exception as e:
        app.logger.error(f"Error fetching user challenges: {str(e)}")
        return {'challenges': [], 'completed': 0, 'total': 0}


def check_challenge_completion(user_id, assignment_id=None, launch_id=None):
    """Check if user has completed challenges and save to database"""
    try:
        app.logger.info(f"Checking challenge completion for user {user_id}, assignment {assignment_id}")
        
        # Get user's instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            app.logger.warning(f"No instance found for user {user_id}")
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
            app.logger.error(f"Failed to fetch challenges from Juice Shop: {response.status_code}")
            return {'success': False, 'message': 'Failed to fetch challenges'}
        
        all_challenges = response.json().get('data', [])
        app.logger.info(f"Retrieved {len(all_challenges)} challenges from Juice Shop")
        
        # Get solved challenges from Juice Shop
        solved_challenges_from_api = [c for c in all_challenges if c.get('solved', False)]
        app.logger.info(f"Found {len(solved_challenges_from_api)} solved challenges from Juice Shop API")
        
        # If assignment_id is provided, filter for only assigned challenges
        if assignment_id:
            # Get assigned challenges from database
            assigned_challenges = get_assigned_challenges(assignment_id)
            assigned_ids = [c['challenge_id'] for c in assigned_challenges]
            app.logger.info(f"Assignment {assignment_id} has {len(assigned_ids)} assigned challenges")
            
            # Filter solved challenges to only include assigned ones
            solved_challenges = [c for c in solved_challenges_from_api if c['id'] in assigned_ids]
            app.logger.info(f"Found {len(solved_challenges)} solved challenges that are part of this assignment")
        else:
            solved_challenges = solved_challenges_from_api
        
        # Get solved challenges already in database
        conn = sqlite3.connect(app.config['DB_PATH'])
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        query = "SELECT challenge_id FROM solved_challenges WHERE user_id=?"
        params = [user_id]
        
        if assignment_id:
            query += " AND assignment_id=?"
            params.append(assignment_id)
        
        c.execute(query, params)
        solved_in_db = [row['challenge_id'] for row in c.fetchall()]
        app.logger.info(f"Found {len(solved_in_db)} challenges already marked as solved in database")
        
        # Save new solved challenges to database
        new_solved_count = 0
        for challenge in solved_challenges:
            if challenge['id'] not in solved_in_db:
                try:
                    app.logger.info(f"Saving new solved challenge {challenge['id']} for user {user_id}")
                    c.execute("""
                        INSERT OR IGNORE INTO solved_challenges 
                        (user_id, challenge_id, assignment_id, solved_at)
                        VALUES (?, ?, ?, ?)
                    """, (user_id, challenge['id'], assignment_id, datetime.now().isoformat()))
                    new_solved_count += 1
                except Exception as e:
                    app.logger.error(f"Error saving solved challenge: {str(e)}")
        
        conn.commit()
        app.logger.info(f"Saved {new_solved_count} new solved challenges to database")
        
        # Get updated challenge status
        result = get_user_challenges(user_id, assignment_id)
        app.logger.info(f"Final result: {result['completed']}/{result['total']} challenges completed")
        
        # Submit score directly if we have a launch_id
        # Use the raw number of completed challenges as the score (1 point per challenge)
        if launch_id and result['completed'] > 0:
            try:
                # Get the LTI launch to access the grading service
                tool_conf = ToolConfJsonFile(get_lti_config_path())
                launch_data_storage = get_launch_data_storage()
                
                # Create a mock Flask request
                mock_request = FlaskRequest(request_is_secure=request.is_secure)
                
                message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, mock_request, tool_conf,
                                                                    launch_data_storage=launch_data_storage)
                
                if message_launch.has_ags():
                    # Submit the raw number of completed challenges (1 point per challenge)
                    raw_score = result['completed']  # One point per completed challenge
                    app.logger.info(f"Submitting raw score: {raw_score} points")
                    
                    # Get user ID from launch data
                    sub = message_launch.get_launch_data().get('sub')
                    timestamp = datetime.now().isoformat() + 'Z'
                    
                    # Get grades service
                    grades = message_launch.get_ags()
                    
                    # Create a Grade object
                    sc = Grade()
                    sc.set_score_given(raw_score) \
                        .set_score_maximum(result['total']) \
                        .set_timestamp(timestamp) \
                        .set_activity_progress('Completed') \
                        .set_grading_progress('FullyGraded') \
                        .set_user_id(sub)
                    
                    # Submit grade
                    grade_result = grades.put_grade(sc)
                    app.logger.info(f"Score submission result: {grade_result}")
                else:
                    app.logger.warning("LTI launch doesn't have Assignment and Grade Service")
            except Exception as e:
                app.logger.error(f"Error submitting score from server: {str(e)}")
        
        conn.close()
        return result
    
    except Exception as e:
        app.logger.error(f"Error checking challenge completion: {str(e)}")
        return {'success': False, 'message': str(e), 'challenges': [], 'completed': 0, 'total': 0}


def save_assigned_challenges(assignment_id, challenges):
    """Save challenges assigned to an assignment"""
    conn = sqlite3.connect(app.config['DB_PATH'])
    c = conn.cursor()
    
    # Clear existing assignments
    c.execute("DELETE FROM assignment_challenges WHERE assignment_id = ?", (assignment_id,))
    
    # Insert new assignments
    for challenge in challenges:
        c.execute("""
            INSERT INTO assignment_challenges
            (assignment_id, challenge_id, challenge_name, challenge_description, challenge_difficulty)
            VALUES (?, ?, ?, ?, ?)
        """, (
            assignment_id,
            challenge['id'],
            challenge.get('name', ''),
            challenge.get('description', ''),
            challenge.get('difficulty', 0)
        ))
    
    conn.commit()
    conn.close()
    
    return True


# Cleanup all running containers when the app exits
def cleanup_all_containers():
    """Stop all running containers created by this application"""
    app.logger.info("Cleaning up all Docker containers...")
    
    try:
        # First, try to use the database to find all running containers
        conn = sqlite3.connect(app.config['DB_PATH'])
        c = conn.cursor()
        
        c.execute("SELECT container_id FROM instances WHERE status='running'")
        containers = [row[0] for row in c.fetchall()]
        
        conn.close()
        
        # Also include any containers tracked in memory
        global running_containers
        for container_id in running_containers + containers:
            if container_id:
                try:
                    app.logger.info(f"Stopping container {container_id}")
                    subprocess.run(["docker", "stop", container_id], capture_output=True, text=True)
                except Exception as e:
                    app.logger.error(f"Error stopping container {container_id}: {str(e)}")
    
    except Exception as e:
        app.logger.error(f"Error during container cleanup: {str(e)}")


# Register signal handlers to cleanup containers on exit
def signal_handler(sig, frame):
    """Handle exit signals to cleanup resources"""
    app.logger.info(f"Received signal {sig}, cleaning up...")
    cleanup_all_containers()
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


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


@app.route('/configure/<launch_id>/', methods=['POST'])
def save_configuration(launch_id):
    """Save selected challenges for an assignment"""
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                        launch_data_storage=launch_data_storage)
    
    if not message_launch.is_deep_link_launch():
        return jsonify({'error': 'Not a deep link launch'}), 400
    
    # Get selected challenges from request
    data = request.json
    selected_challenges = data.get('challenges', [])
    
    if not selected_challenges:
        return jsonify({'error': 'No challenges selected'}), 400
    
    # During deep linking, we don't have an assignment ID yet
    # So we'll pass the selected challenge IDs as custom parameters in the deep link
    
    # Create a DeepLinkResource to return to the platform
    launch_url = f"{request.url_root}assignment"
    
    # Extract just the IDs and essential info for the custom parameters
    # to avoid exceeding parameter size limits
    challenge_params = []
    for challenge in selected_challenges:
        challenge_params.append({
            'id': challenge['id'],
            'name': challenge['name'],
            'difficulty': challenge['difficulty']
        })
    
    # Get the return URL from launch data
    launch_data = message_launch.get_launch_data()
    return_url = launch_data.get('https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings', {}).get('deep_link_return_url')
    
    if not return_url:
        app.logger.error("Deep link return URL not found in launch data")
        return jsonify({'error': 'Return URL not found in launch data'}), 400
    
    resource = DeepLinkResource()
    resource.set_url(launch_url) \
        .set_custom_params({'selected_challenges': json.dumps(challenge_params)}) \
        .set_title('Security Challenges Assignment')
    
    # Return as JSON for frontend to submit
    return jsonify({
        'success': True,
        'deep_link_jwt': message_launch.get_deep_link().get_response_jwt([resource]),
        'return_url': return_url
    })


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
    
    # Log launch data for debugging
    app.logger.info("LTI Launch data received:")
    app.logger.info(pprint.pformat(message_launch_data))

    if message_launch.is_deep_link_launch():
        app.logger.info("Processing deep link launch")
        # Fetch challenges for deep linking
        challenges = get_juice_shop_challenges()
        
        # Group challenges by category for better organization
        challenge_categories = {}
        for challenge in challenges:
            category = challenge.get('category', 'Uncategorized')
            if category not in challenge_categories:
                challenge_categories[category] = []
            challenge_categories[category].append(challenge)

        # Log deep linking settings
        deep_link_settings = message_launch_data.get('https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings', {})
        app.logger.info("Deep linking settings: %s", deep_link_settings)
        
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
        app.logger.info("Processing regular assignment launch")
        # Regular launch - direct to assignment page
        # Extract user_id from launch data
        user_id = message_launch_data.get('sub')
        assignment_id = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
        
        app.logger.info(f"Assignment launch for user {user_id}, assignment {assignment_id}")
        
        # Check for selected challenges in custom parameters
        custom_params = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/custom', {})
        app.logger.info(f"Custom parameters: {custom_params}")
        
        selected_challenges_json = custom_params.get('selected_challenges')
        
        # If we have selected challenges from deep linking and a valid assignment ID,
        # store them in the database
        if selected_challenges_json and assignment_id:
            app.logger.info(f"Found selected challenges in custom parameters for assignment {assignment_id}")
            try:
                # Parse the JSON string
                selected_challenges = json.loads(selected_challenges_json)
                app.logger.info(f"Parsed {len(selected_challenges)} selected challenges")
                
                # Get full challenge details from Juice Shop
                all_challenges = get_juice_shop_challenges()
                
                # Prepare challenges with full details for saving
                challenges_to_save = []
                for selected in selected_challenges:
                    for challenge in all_challenges:
                        if selected['id'] == challenge['id']:
                            # Create a complete challenge object
                            challenge_info = {
                                'id': challenge['id'],
                                'name': selected['name'],
                                'description': challenge.get('description', ''),
                                'difficulty': selected['difficulty']
                            }
                            challenges_to_save.append(challenge_info)
                            break
                
                # Save to database
                if challenges_to_save:
                    app.logger.info(f"Saving {len(challenges_to_save)} challenges to assignment {assignment_id}")
                    save_assigned_challenges(assignment_id, challenges_to_save)
                else:
                    app.logger.warning("No challenges found to save")
            except Exception as e:
                app.logger.error(f"Error processing challenge parameters: {str(e)}")
        
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
        challenges_data = check_challenge_completion(user_id, assignment_id, launch_id)
        
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
    """Submit score back to LMS"""
    try:
        app.logger.info(f"Score submission request: launch_id={launch_id}, score={earned_score}")
        
        tool_conf = ToolConfJsonFile(get_lti_config_path())
        flask_request = FlaskRequest()
        launch_data_storage = get_launch_data_storage()
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)

        if not message_launch.has_ags():
            app.logger.error("LTI launch doesn't have Assignment and Grade Service")
            return jsonify({'success': False, 'error': "Don't have grades service!"}), 403

        sub = message_launch.get_launch_data().get('sub')
        timestamp = datetime.now().isoformat() + 'Z'
        earned_score = int(earned_score)
        
        app.logger.info(f"Submitting score {earned_score} for user {sub}")

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
        
        app.logger.info(f"Score submission result: {result}")

        return jsonify({'success': True, 'result': result.get('body')})
    
    except Exception as e:
        app.logger.error(f"Error submitting score: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9001)