# Import models here for easier access from other modules
from models.database import get_db_connection, init_db
from models.instance import get_user_instance, find_available_port, save_instance, update_instance_status
from models.challenge import get_assigned_challenges, save_assigned_challenges, save_solved_challenge, get_user_solved_challenges