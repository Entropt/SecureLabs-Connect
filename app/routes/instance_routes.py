from flask import Blueprint, jsonify, current_app
from pylti1p3.tool_config import ToolConfJsonFile
from pylti1p3.contrib.flask import FlaskRequest
from datetime import datetime

from config import get_lti_config_path
from services.lti_service import get_launch_data_storage
from services.docker_service import create_docker_instance, restart_docker_instance, shutdown_user_instance
from models.instance import get_user_instance

# Create blueprint
instance_bp = Blueprint('instance', __name__, url_prefix='/api')

@instance_bp.route('/instance-status/<launch_id>/<user_id>', methods=['GET'])
def instance_status(launch_id, user_id):
    # Import ExtendedFlaskMessageLaunch from app to avoid circular imports
    from app import ExtendedFlaskMessageLaunch
    from services.docker_service import is_container_running
    from flask import request
    
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
        
        # Get the verification level from query parameters (strict or normal)
        verification = request.args.get('verification', 'normal')
        
        # Get user's instance with container validation
        instance = get_user_instance(user_id)
        
        # If strict verification is requested and the instance exists, double-check the container
        if verification == 'strict' and instance.get('exists'):
            container_id = instance.get('container_id')
            if not is_container_running(container_id):
                # Container is not running but database says it is - update our response
                instance['exists'] = False
                instance['reason'] = 'Container not running'
                current_app.logger.warning(f"Strict verification failed for container {container_id}")
                
                # Could optionally update the database here as well
        
        # Add a verification timestamp to help the client know when the status was verified
        instance['verified_at'] = datetime.now().isoformat()
        instance['verification_level'] = verification
        
        return jsonify(instance)
    
    except Exception as e:
        current_app.logger.error(f"Error checking instance status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@instance_bp.route('/create-instance/<launch_id>/<user_id>', methods=['POST'])
def create_instance(launch_id, user_id):
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
        
        # Get assignment ID from launch data
        assignment_id = message_launch.get_launch_data().get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
        
        # Create Docker instance
        result = create_docker_instance(user_id, assignment_id)
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f"Error creating instance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@instance_bp.route('/restart-instance/<launch_id>/<user_id>', methods=['POST'])
def restart_instance(launch_id, user_id):
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
        
        # Restart Docker instance
        result = restart_docker_instance(user_id)
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f"Error restarting instance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@instance_bp.route('/shutdown-instance/<launch_id>/<user_id>', methods=['POST'])
def shutdown_instance(launch_id, user_id):
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
        
        # Shutdown Docker instance
        result = shutdown_user_instance(user_id)
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f"Error shutting down instance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500