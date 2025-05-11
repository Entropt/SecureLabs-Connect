from datetime import datetime, timedelta
import random
from flask import current_app
from models.database import get_db_connection

def get_user_instance(user_id):
    """Get user's Juice Shop instance"""
    from flask import current_app
    from services.docker_service import is_container_running
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM instances WHERE user_id=? AND status='running'", (user_id,))
    instance = c.fetchone()
    
    if instance:
        # Check if container is actually running in Docker
        container_id = instance['container_id']
        container_running = is_container_running(container_id)
        
        if container_running:
            # Update last accessed time
            c.execute("UPDATE instances SET last_accessed=? WHERE id=?", 
                    (datetime.now().isoformat(), instance['id']))
            conn.commit()
            
            instance_dict = dict(instance)
            instance_dict['url'] = f"http://{current_app.config['HOST_IP']}:{instance['port']}"
            instance_dict['exists'] = True
        else:
            # Container not running, update status in database
            c.execute("UPDATE instances SET status=? WHERE id=?", ('stopped', instance['id']))
            conn.commit()
            
            current_app.logger.warning(f"Instance {instance['id']} marked as running but container not found")
            instance_dict = {'exists': False, 'reason': 'Container not running'}
    else:
        instance_dict = {'exists': False}
    
    conn.close()
    return instance_dict

def find_available_port():
    """Find an available port in the configured range"""
    from flask import current_app
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get all ports currently in use
    c.execute("SELECT port FROM instances WHERE status='running'")
    used_ports = [row[0] for row in c.fetchall()]
    conn.close()
    
    # Find available port
    port_range = list(range(current_app.config['PORT_RANGE_START'], current_app.config['PORT_RANGE_END'] + 1))
    available_ports = [p for p in port_range if p not in used_ports]
    
    if not available_ports:
        raise Exception("No available ports in the specified range")
    
    # Randomize port selection for better distribution
    return random.choice(available_ports)

def save_instance(user_id, container_id, port, status, assignment_id=None):
    """Save instance info to database"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        INSERT INTO instances (user_id, container_id, port, status, assignment_id, created_at, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, container_id, port, status, assignment_id, 
          datetime.now().isoformat(), datetime.now().isoformat()))
    
    conn.commit()
    instance_id = c.lastrowid
    conn.close()
    
    return instance_id

def update_instance_status(instance_id, status):
    """Update instance status"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("UPDATE instances SET status=? WHERE id=?", (status, instance_id))
    conn.commit()
    conn.close()

def get_expired_instances():
    """Get list of expired instances"""
    from flask import current_app
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get expired instances
    expiry_date = (datetime.now() - timedelta(days=current_app.config['INSTANCE_EXPIRY_DAYS'])).isoformat()
    
    c.execute("""
        SELECT id, container_id FROM instances 
        WHERE status='running' AND last_accessed < ?
    """, (expiry_date,))
    
    expired_instances = c.fetchall()
    conn.close()
    
    return [(row[0], row[1]) for row in expired_instances]