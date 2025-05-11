import subprocess
from flask import current_app
from models.instance import find_available_port, save_instance, update_instance_status, get_user_instance, get_expired_instances

# Global list to track running containers in memory
running_containers = []
# Global variable to track the master Juice Shop container for challenges
master_juice_shop_container = None

def is_container_running(container_id):
    """Check if a Docker container exists and is running"""
    try:
        # Check if container exists and is running
        cmd = ["docker", "inspect", "--format='{{.State.Running}}'", container_id]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # If command executed successfully and output contains "true", container is running
        if result.returncode == 0 and 'true' in result.stdout.lower():
            return True
        
        # Container not found or not running
        current_app.logger.warning(f"Container {container_id} not running or not found: {result.stderr}")
        return False
    except Exception as e:
        current_app.logger.error(f"Error checking container {container_id} status: {str(e)}")
        return False

def create_docker_instance(user_id, assignment_id=None):
    """Create a new Juice Shop Docker instance for the user"""
    try:
        from flask import current_app
        
        # Check if user already has an instance
        existing_instance = get_user_instance(user_id)
        
        if existing_instance['exists']:
            return {
                'success': False,
                'message': 'User already has a running instance',
                'instance': existing_instance
            }
        
        # Find available port
        port = find_available_port()
        
        # Create Docker container
        container_name = f"juice_shop_{user_id}_{port}"
        
        # Run the docker command with auto-removal
        cmd = [
            "docker", "run", 
            "--rm",  # Ensure container is removed when stopped
            "-d",
            "--name", container_name,
            "-e", "NODE_ENV=unsafe",
            "-p", f"{port}:3000",
            "--label", "managed-by=lti-juice-shop",  # Add label for tracking
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
        instance_id = save_instance(user_id, container_id, port, 'running', assignment_id)
        
        return {
            'success': True,
            'container_id': container_id,
            'port': port,
            'instance_id': instance_id,
            'url': f"http://{current_app.config['HOST_IP']}:{port}"
        }
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error creating Docker instance: {str(e)}")
        return {'success': False, 'message': str(e)}

def stop_docker_container(container_id):
    """Stop a Docker container"""
    try:
        from flask import current_app
        current_app.logger.info(f"Stopping container {container_id}")
        
        stop_cmd = ["docker", "stop", container_id]
        result = subprocess.run(stop_cmd, capture_output=True, text=True)
        
        global running_containers
        if container_id in running_containers:
            running_containers.remove(container_id)
        
        return result.returncode == 0
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error stopping Docker container: {str(e)}")
        return False

def restart_docker_instance(user_id):
    """Restart a user's Docker instance"""
    try:
        # Get user's current instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            return {'success': False, 'message': 'No running instance found'}
        
        # Stop the container
        container_id = instance['container_id']
        stop_successful = stop_docker_container(container_id)
        
        if not stop_successful:
            from flask import current_app
            current_app.logger.error(f"Failed to stop container {container_id}")
        
        # Update instance status
        update_instance_status(instance['id'], 'stopped')
        
        # Create a new instance
        assignment_id = instance.get('assignment_id')
        create_result = create_docker_instance(user_id, assignment_id)
        return create_result
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error restarting Docker instance: {str(e)}")
        return {'success': False, 'message': str(e)}

def cleanup_expired_instances():
    """Cleanup expired Docker instances"""
    try:
        from flask import current_app
        # Get expired instances
        expired_instances = get_expired_instances()
        
        for instance_id, container_id in expired_instances:
            # Stop the container
            stop_docker_container(container_id)
            
            # Update instance status
            update_instance_status(instance_id, 'expired')
        
        return {'success': True, 'cleaned_count': len(expired_instances)}
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error cleaning up expired instances: {str(e)}")
        return {'success': False, 'message': str(e)}

def shutdown_user_instance(user_id):
    """Shutdown a user's Docker instance"""
    try:
        # Get user's current instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            return {'success': False, 'message': 'No running instance found'}
        
        # Stop the container
        container_id = instance['container_id']
        stop_successful = stop_docker_container(container_id)
        
        if not stop_successful:
            from flask import current_app
            current_app.logger.error(f"Failed to stop container {container_id}")
            return {'success': False, 'message': f"Failed to stop container {container_id}"}
        
        # Update instance status
        update_instance_status(instance['id'], 'stopped')
        
        return {'success': True, 'message': 'Instance successfully shutdown'}
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error shutting down Docker instance: {str(e)}")
        return {'success': False, 'message': str(e)}

def start_master_juice_shop():
    """
    Start a master Juice Shop instance on port 3000 for challenge fetching
    """
    try:
        from flask import current_app
        current_app.logger.info("Starting master Juice Shop instance for challenges...")
        
        # Check if master container is already running
        global master_juice_shop_container
        
        # First, check if there's an orphaned container with our name from a previous run
        container_name = "juice_shop_master_challenges"
        check_cmd = ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.ID}}"]
        result = subprocess.run(check_cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            # Found an existing container with this name, remove it first
            existing_container_id = result.stdout.strip()
            current_app.logger.info(f"Found existing master Juice Shop container: {existing_container_id}. Removing it...")
            
            # Stop the container if it's running
            stop_cmd = ["docker", "stop", existing_container_id]
            subprocess.run(stop_cmd, capture_output=True, text=True)
            
            # Remove the container
            rm_cmd = ["docker", "rm", "-f", existing_container_id]
            rm_result = subprocess.run(rm_cmd, capture_output=True, text=True)
            
            if rm_result.returncode != 0:
                error_msg = f"Failed to remove existing container: {rm_result.stderr}"
                current_app.logger.error(error_msg)
        
        # Check if we already have a tracked container
        if master_juice_shop_container:
            current_app.logger.info(f"Master Juice Shop already running with container ID: {master_juice_shop_container}")
            return {'success': True, 'container_id': master_juice_shop_container}

        # Run the docker command
        cmd = [
            "docker", "run", 
            "--rm",  # Ensure container is removed when stopped
            "-d",
            "--name", container_name,
            "-e", "NODE_ENV=unsafe",
            "-p", "127.0.0.1:3000:3000",  # Bind to localhost only
            "--label", "managed-by=lti-juice-shop-master",  # Special label for the master instance
            "bkimminich/juice-shop"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to create master Juice Shop container: {result.stderr}"
            current_app.logger.error(error_msg)
            raise Exception(error_msg)
        
        container_id = result.stdout.strip()
        master_juice_shop_container = container_id
        
        # Keep track of running containers
        global running_containers
        running_containers.append(container_id)
        
        current_app.logger.info(f"Master Juice Shop started with container ID: {container_id}")
        return {'success': True, 'container_id': container_id}
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error starting master Juice Shop: {str(e)}")
        return {'success': False, 'message': str(e)}

def stop_master_juice_shop():
    """
    Stop the master Juice Shop instance used for challenge fetching
    """
    try:
        from flask import current_app
        global master_juice_shop_container
        
        if not master_juice_shop_container:
            current_app.logger.info("No master Juice Shop running, nothing to stop")
            return {'success': True, 'message': 'No master instance running'}
        
        current_app.logger.info(f"Stopping master Juice Shop container {master_juice_shop_container}")
        
        stop_cmd = ["docker", "stop", master_juice_shop_container]
        result = subprocess.run(stop_cmd, capture_output=True, text=True)
        
        global running_containers
        if master_juice_shop_container in running_containers:
            running_containers.remove(master_juice_shop_container)
        
        master_juice_shop_container = None
        
        if result.returncode != 0:
            error_msg = f"Failed to stop master Juice Shop container: {result.stderr}"
            current_app.logger.error(error_msg)
            return {'success': False, 'message': error_msg}
        
        return {'success': True, 'message': 'Master Juice Shop stopped successfully'}
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error stopping master Juice Shop: {str(e)}")
        return {'success': False, 'message': str(e)}

def cleanup_all_containers():
    """Stop all running containers created by this application"""
    try:
        from flask import current_app
        from models.database import get_db_connection
        
        current_app.logger.info("Cleaning up all Docker containers...")
        
        # First stop the master Juice Shop if it's running
        stop_master_juice_shop()
        
        # Get all running containers from database
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT container_id FROM instances WHERE status='running'")
        containers_from_db = [row[0] for row in c.fetchall()]
        
        conn.close()
        
        # Also include any containers tracked in memory
        global running_containers
        containers_to_stop = set(running_containers + containers_from_db)
        
        # Count successful stops
        success_count = 0
        
        # Stop each container
        for container_id in containers_to_stop:
            if container_id:
                try:
                    current_app.logger.info(f"Stopping container {container_id}")
                    subprocess.run(["docker", "stop", container_id], capture_output=True, text=True)
                    success_count += 1
                except Exception as e:
                    current_app.logger.error(f"Error stopping container {container_id}: {str(e)}")
        
        # As a backup, try to find and remove any containers with our labels that might have been missed
        try:
            current_app.logger.info("Checking for any labeled containers that might have been missed...")
            # Check for both regular and master containers
            for label in ["managed-by=lti-juice-shop", "managed-by=lti-juice-shop-master"]:
                list_cmd = ["docker", "ps", "-q", "--filter", f"label={label}"]
                result = subprocess.run(list_cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and result.stdout.strip():
                    labeled_containers = result.stdout.strip().split('\n')
                    for container_id in labeled_containers:
                        if container_id.strip():
                            current_app.logger.info(f"Stopping missed labeled container {container_id}")
                            subprocess.run(["docker", "stop", container_id.strip()], capture_output=True, text=True)
        except Exception as e:
            current_app.logger.error(f"Error cleaning up labeled containers: {str(e)}")
        
        current_app.logger.info(f"Cleanup complete. Stopped {success_count} containers.")
        
        return {'success': True, 'stopped_count': success_count}
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error during container cleanup: {str(e)}")
        return {'success': False, 'message': str(e)}