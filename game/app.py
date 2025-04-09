import datetime
import os
import pprint
import requests
import json

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
    "JUICE_SHOP_URL": "http://172.22.183.134:3000"  # Add your IP address as Juice Shop URL
}
app.config.from_mapping(config)
cache = Cache(app)

PAGE_TITLE = 'Security Challenges'


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
    try:
        response = requests.get(f"{app.config['JUICE_SHOP_URL']}/api/challenges/", 
                                headers={
                                    'Accept-Language': 'en-GB,en;q=0.9',
                                    'Accept': 'application/json, text/plain, */*',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                                    'Connection': 'keep-alive'
                                })
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            app.logger.error(f"Failed to fetch challenges: {response.status_code}")
            return []
    except Exception as e:
        app.logger.error(f"Error fetching challenges: {str(e)}")
        return []


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


@app.route('/launch/', methods=['POST'])
def launch():
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch(flask_request, tool_conf, launch_data_storage=launch_data_storage)
    message_launch_data = message_launch.get_launch_data()
    pprint.pprint(message_launch_data)

    # Fetch challenges from Juice Shop
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
        'is_deep_link_launch': message_launch.is_deep_link_launch(),
        'launch_data': message_launch.get_launch_data(),
        'launch_id': message_launch.get_launch_id(),
        'curr_user_name': message_launch_data.get('name', ''),
        'challenges': challenges,
        'challenge_categories': challenge_categories
    }
    return render_template('game.html', **tpl_kwargs)


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
        # For regular launches, redirect directly to Juice Shop
        return redirect(f"{app.config['JUICE_SHOP_URL']}/#/challenge")

    # For deep linking, create a resource that will redirect to Juice Shop
    launch_url = f"{app.config['JUICE_SHOP_URL']}/#/challenge"

    resource = DeepLinkResource()
    resource.set_url(launch_url) \
        .set_custom_params({'challenge_id': challenge_id}) \
        .set_title('Security Challenge')

    html = message_launch.get_deep_link().output_response_form([resource])
    return html


@app.route('/redirect-to-challenge/<int:challenge_id>/', methods=['GET'])
def redirect_to_challenge(challenge_id):
    """Redirect to the specific challenge on Juice Shop"""
    return redirect(f"{app.config['JUICE_SHOP_URL']}/#/challenge")


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