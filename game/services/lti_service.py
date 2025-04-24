from flask import current_app, request
from pylti1p3.contrib.flask import FlaskCacheDataStorage, FlaskRequest
from pylti1p3.grade import Grade
from datetime import datetime
from pylti1p3.tool_config import ToolConfJsonFile
from config import get_lti_config_path

# Declare ExtendedFlaskMessageLaunch class here to be used across the application
class ExtendedFlaskMessageLaunch:
    """
    This class will be implemented in app.py to avoid circular imports
    It's declared here so that type hints work correctly
    """
    pass

def get_launch_data_storage():
    """Get the Flask cache data storage for LTI"""
    from flask import current_app
    from pylti1p3.contrib.flask import FlaskCacheDataStorage
    
    # Access the cache through the app attribute we added
    return FlaskCacheDataStorage(current_app.cache)

def get_jwk_from_public_key(key_name):
    """Get JWK from public key file"""
    import os
    from pylti1p3.registration import Registration
    
    key_path = os.path.join(current_app.root_path, '..', 'configs', key_name)
    with open(key_path, 'r') as f:
        key_content = f.read()
    
    jwk = Registration.get_jwk(key_content)
    return jwk

def submit_score(launch_id, earned_score, total_score):
    """Submit a score to the LMS via LTI AGS"""
    try:
        from flask import current_app
        # Import here to avoid circular imports
        from app import ExtendedFlaskMessageLaunch
        
        current_app.logger.info(f"Submitting score: {earned_score}/{total_score} for launch_id {launch_id}")
        
        # Get the tool configuration
        tool_conf = ToolConfJsonFile(get_lti_config_path())
        launch_data_storage = get_launch_data_storage()
        
        # Create a mock Flask request if needed
        mock_request = FlaskRequest(request_is_secure=request.is_secure if request else False)
        
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, mock_request, tool_conf,
                                                          launch_data_storage=launch_data_storage)
        
        if message_launch.has_ags():
            # Get user ID from launch data
            sub = message_launch.get_launch_data().get('sub')
            timestamp = datetime.now().isoformat() + 'Z'
            
            # Get grades service
            grades = message_launch.get_ags()
            
            current_app.logger.info(f"Creating grade object for user {sub}")
            
            # Create a Grade object
            sc = Grade()
            sc.set_score_given(earned_score) \
                .set_score_maximum(total_score) \
                .set_timestamp(timestamp) \
                .set_activity_progress('Completed') \
                .set_grading_progress('FullyGraded') \
                .set_user_id(sub)
            
            # Submit grade
            current_app.logger.info(f"Putting grade: {earned_score}/{total_score}")
            grade_result = grades.put_grade(sc)
            current_app.logger.info(f"Score submission result: {grade_result}")
            return True
        else:
            current_app.logger.warning("LTI launch doesn't have Assignment and Grade Service")
            return False
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error submitting score: {str(e)}")
        return False