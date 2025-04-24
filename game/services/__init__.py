# Import services here for easier access from other modules
from services.docker_service import (
    create_docker_instance, 
    restart_docker_instance, 
    cleanup_expired_instances, 
    cleanup_all_containers
)
from services.challenge_service import (
    get_juice_shop_challenges, 
    get_user_challenges, 
    check_challenge_completion
)
from services.lti_service import get_launch_data_storage, submit_score