from datetime import datetime
from flask import current_app
from models.database import get_db_connection

def get_assigned_challenges(assignment_id):
    """Get challenges assigned to a specific assignment"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM assignment_challenges 
        WHERE assignment_id = ?
    """, (assignment_id,))
    
    challenges = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return challenges

def save_assigned_challenges(assignment_id, challenges):
    """Save challenges assigned to an assignment"""
    conn = get_db_connection()
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

def save_solved_challenge(user_id, challenge_id, assignment_id=None):
    """Save a solved challenge to the database"""
    from flask import current_app
    
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT OR IGNORE INTO solved_challenges 
            (user_id, challenge_id, assignment_id, solved_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, challenge_id, assignment_id, datetime.now().isoformat()))
        
        conn.commit()
        success = c.rowcount > 0  # Check if a row was inserted
    except Exception as e:
        current_app.logger.error(f"Error saving solved challenge: {str(e)}")
        success = False
    
    conn.close()
    return success

def get_user_solved_challenges(user_id, assignment_id=None):
    """Get list of challenge IDs solved by a user"""
    conn = get_db_connection()
    c = conn.cursor()
    
    query = "SELECT challenge_id FROM solved_challenges WHERE user_id=?"
    params = [user_id]
    
    if assignment_id:
        query += " AND assignment_id=?"
        params.append(assignment_id)
    
    c.execute(query, params)
    challenge_ids = [row['challenge_id'] for row in c.fetchall()]
    
    conn.close()
    return challenge_ids