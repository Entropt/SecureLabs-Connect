from flask import Blueprint, jsonify, current_app
from pylti1p3.tool_config import ToolConfJsonFile
from pylti1p3.contrib.flask import FlaskRequest

from config import get_lti_config_path
from services.lti_service import get_launch_data_storage
from services.challenge_service import get_user_challenges, check_challenge_completion, get_juice_shop_challenges

# Create blueprint
challenge_bp = Blueprint('challenge', __name__, url_prefix='/api')

@challenge_bp.route('/challenge-list/<launch_id>/<assignment_id>', methods=['GET'])
def challenge_list(launch_id, assignment_id):
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    
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
        current_app.logger.error(f"Error getting challenge list: {str(e)}")
        return jsonify({'error': str(e)}), 500

@challenge_bp.route('/challenge-status/<launch_id>/<user_id>/<assignment_id>', methods=['GET'])
def challenge_status(launch_id, user_id, assignment_id):
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    
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
            'challenges': challenges_data.get('challenges', []), 
            'completed': challenges_data.get('completed', 0),
            'total': challenges_data.get('total', 0)
        })
    
    except Exception as e:
        current_app.logger.error(f"Error checking challenge status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@challenge_bp.route('/check-challenge-status/<launch_id>/<int:challenge_id>/', methods=['GET'])
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