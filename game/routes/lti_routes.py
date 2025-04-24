from flask import Blueprint, request, render_template, redirect, jsonify, url_for, current_app
from pylti1p3.contrib.flask import FlaskOIDCLogin, FlaskRequest
from pylti1p3.deep_link_resource import DeepLinkResource
from pylti1p3.tool_config import ToolConfJsonFile
import json
import pprint
from datetime import datetime

from config import get_lti_config_path, PAGE_TITLE
from services.lti_service import get_launch_data_storage
from services.challenge_service import get_juice_shop_challenges
from models.challenge import save_assigned_challenges

# Create blueprint
lti_bp = Blueprint('lti', __name__)

@lti_bp.route('/login/', methods=['GET', 'POST'])
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

@lti_bp.route('/jwks/', methods=['GET'])
def get_jwks():
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    return tool_conf.get_jwks()["keys"][0]

@lti_bp.route('/configure/<launch_id>/', methods=['POST'])
def save_configuration(launch_id):
    """Save selected challenges for an assignment"""
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    
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
    
    # Create a DeepLinkResource to return to the platform
    launch_url = f"{request.url_root}assignment/"
    
    # Extract just the IDs and essential info for the custom parameters
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
        current_app.logger.error("Deep link return URL not found in launch data")
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

@lti_bp.route('/configure/<launch_id>/<int:challenge_id>/', methods=['GET', 'POST'])
def configure(launch_id, challenge_id):
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    
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

@lti_bp.route('/assignment/', methods=['GET', 'POST'])
def assignment_page():
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    
    tool_conf = ToolConfJsonFile(get_lti_config_path())
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch(flask_request, tool_conf, launch_data_storage=launch_data_storage)
    message_launch_data = message_launch.get_launch_data()
    
    # Log launch data for debugging
    current_app.logger.info("LTI Launch data received:")
    current_app.logger.info(pprint.pformat(message_launch_data))

    if message_launch.is_deep_link_launch():
        current_app.logger.info("Processing deep link launch")
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
        current_app.logger.info("Deep linking settings: %s", deep_link_settings)
        
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
        current_app.logger.info("Processing regular assignment launch")
        # Regular launch - direct to assignment page
        # Extract user_id from launch data
        user_id = message_launch_data.get('sub')
        assignment_id = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
        
        current_app.logger.info(f"Assignment launch for user {user_id}, assignment {assignment_id}")
        
        # Check for selected challenges in custom parameters
        custom_params = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/custom', {})
        current_app.logger.info(f"Custom parameters: {custom_params}")
        
        selected_challenges_json = custom_params.get('selected_challenges')
        
        # If we have selected challenges from deep linking and a valid assignment ID,
        # store them in the database
        if selected_challenges_json and assignment_id:
            current_app.logger.info(f"Found selected challenges in custom parameters for assignment {assignment_id}")
            try:
                # Parse the JSON string
                selected_challenges = json.loads(selected_challenges_json)
                current_app.logger.info(f"Parsed {len(selected_challenges)} selected challenges")
                
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
                    current_app.logger.info(f"Saving {len(challenges_to_save)} challenges to assignment {assignment_id}")
                    save_assigned_challenges(assignment_id, challenges_to_save)
                else:
                    current_app.logger.warning("No challenges found to save")
            except Exception as e:
                current_app.logger.error(f"Error processing challenge parameters: {str(e)}")
        
        tpl_kwargs = {
            'page_title': PAGE_TITLE,
            'launch_id': message_launch.get_launch_id(),
            'user_id': user_id,
            'assignment_id': assignment_id,
        }
        return render_template('assignment.html', **tpl_kwargs)

@lti_bp.route('/assignment/<launch_id>/<user_id>/<assignment_id>', methods=['GET'])
def assignment(launch_id, user_id, assignment_id):
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    
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
        current_app.logger.error(f"Error loading assignment page: {str(e)}")
        return jsonify({'error': str(e)}), 500

@lti_bp.route('/api/score/<launch_id>/<earned_score>/', methods=['POST'])
def score(launch_id, earned_score):
    """Submit score back to LMS"""
    try:
        # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
        from app import ExtendedFlaskMessageLaunch
        
        current_app.logger.info(f"Score submission request: launch_id={launch_id}, score={earned_score}")
        
        tool_conf = ToolConfJsonFile(get_lti_config_path())
        flask_request = FlaskRequest()
        launch_data_storage = get_launch_data_storage()
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)

        if not message_launch.has_ags():
            current_app.logger.error("LTI launch doesn't have Assignment and Grade Service")
            return jsonify({'success': False, 'error': "Don't have grades service!"}), 403

        sub = message_launch.get_launch_data().get('sub')
        timestamp = datetime.now().isoformat() + 'Z'
        earned_score = int(earned_score)
        
        current_app.logger.info(f"Submitting score {earned_score} for user {sub}")

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
        
        current_app.logger.info(f"Score submission result: {result}")

        return jsonify({'success': True, 'result': result.get('body')})
    
    except Exception as e:
        current_app.logger.error(f"Error submitting score: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500