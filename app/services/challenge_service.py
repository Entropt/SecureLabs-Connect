import requests
from flask import current_app
from models.instance import get_user_instance
from models.challenge import (
    get_assigned_challenges, 
    save_assigned_challenges, 
    save_solved_challenge, 
    get_user_solved_challenges
)

def get_juice_shop_challenges():
    """Fetch challenges from the master Juice Shop API"""
    juice_shop_url = "http://127.0.0.1:3000"
    
    try:
        current_app.logger.info("Fetching challenges from master Juice Shop instance")
        response = requests.get(f"{juice_shop_url}/api/challenges/", 
                        headers={
                            'Accept-Language': 'en-GB,en;q=0.9',
                            'Accept': 'application/json, text/plain, */*',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                            'Connection': 'keep-alive'
                        },
                        timeout=10)  # Add a timeout to prevent hanging
        
        if response.status_code == 200:
            challenges = response.json().get('data', [])
            current_app.logger.info(f"Successfully fetched {len(challenges)} challenges from master Juice Shop")
            return challenges
        else:
            current_app.logger.error(f"Failed to fetch challenges from master Juice Shop: HTTP {response.status_code}")
            return []
    except Exception as e:
        current_app.logger.error(f"Error fetching challenges from master Juice Shop: {str(e)}")
        return []

def get_challenges_from_instance(instance_url):
    """Fetch challenges from a specific Juice Shop instance"""
    response = requests.get(f"{instance_url}/api/challenges/", 
                            headers={
                                'Accept-Language': 'en-GB,en;q=0.9',
                                'Accept': 'application/json, text/plain, */*',
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                                'Connection': 'keep-alive'
                            })
    
    if response.status_code == 200:
        return response.json().get('data', [])
    return []

def get_user_challenges(user_id, assignment_id=None):
    """Get challenges and user's progress for a specific assignment"""
    try:
        # Get user's instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            return {'challenges': [], 'completed': 0, 'total': 0}
        
        # Fetch all challenges from Juice Shop
        juice_shop_url = instance['url']
        all_challenges = get_challenges_from_instance(juice_shop_url)
        
        # If assignment_id is provided, filter for only assigned challenges
        if assignment_id:
            # Get assigned challenges from database
            assigned_challenges = get_assigned_challenges(assignment_id)
            
            if assigned_challenges:
                # We have assigned challenges, use those
                challenges = []
                for assigned in assigned_challenges:
                    for challenge in all_challenges:
                        if assigned['challenge_id'] == challenge['id']:
                            # Merge the info from both sources
                            challenge_info = {
                                'id': challenge['id'],
                                'name': assigned['challenge_name'],
                                'description': assigned['challenge_description'],
                                'difficulty': assigned['challenge_difficulty'],
                                'solved': challenge.get('solved', False)
                            }
                            challenges.append(challenge_info)
                            break
            else:
                # No challenges specifically assigned yet
                # Use easier challenges as a fallback
                easier_challenges = []
                for challenge in all_challenges:
                    if challenge.get('difficulty', 6) <= 2:  # Only include easy challenges (difficulty 1-2)
                        easier_challenges.append({
                            'id': challenge['id'],
                            'name': challenge['name'],
                            'description': challenge.get('description', ''),
                            'difficulty': challenge.get('difficulty', 1),
                            'solved': challenge.get('solved', False)
                        })
                        # Limit to 5 challenges for the fallback set
                        if len(easier_challenges) >= 5:
                            break
                
                challenges = easier_challenges
                
                # Also attempt to save these challenges to the assignment
                if challenges and assignment_id:
                    try:
                        save_assigned_challenges(assignment_id, challenges)
                        current_app.logger.info(f"Saved fallback challenges for assignment {assignment_id}")
                    except Exception as e:
                        current_app.logger.error(f"Error saving fallback challenges: {str(e)}")
        else:
            # No assignment_id, get all challenges
            challenges = []
            for challenge in all_challenges:
                challenges.append({
                    'id': challenge['id'],
                    'name': challenge['name'],
                    'description': challenge.get('description', ''),
                    'difficulty': challenge.get('difficulty', 1),
                    'solved': challenge.get('solved', False)
                })
        
        # Get user's solved challenges from database
        solved_challenges = get_user_solved_challenges(user_id, assignment_id)
        
        # Mark solved challenges
        for challenge in challenges:
            # Check both the solved flag from the API and our database
            challenge['completed'] = challenge.get('solved', False) or challenge['id'] in solved_challenges
        
        # Count completed challenges
        completed_count = len([c for c in challenges if c.get('completed', False)])
        
        return {
            'challenges': challenges,
            'completed': completed_count,
            'total': len(challenges)
        }
    
    except Exception as e:
        current_app.logger.error(f"Error fetching user challenges: {str(e)}")
        return {'challenges': [], 'completed': 0, 'total': 0}

def check_challenge_completion(user_id, assignment_id=None, launch_id=None):
    """Check if user has completed challenges and save to database"""
    try:
        from flask import current_app
        current_app.logger.info(f"Checking challenge completion for user {user_id}, assignment {assignment_id}")
        
        # Get user's instance
        instance = get_user_instance(user_id)
        
        if not instance['exists']:
            current_app.logger.warning(f"No instance found for user {user_id}")
            return {'success': False, 'message': 'No running instance found'}
        
        # Fetch challenges from Juice Shop
        juice_shop_url = instance['url']
        all_challenges = get_challenges_from_instance(juice_shop_url)
        
        current_app.logger.info(f"Retrieved {len(all_challenges)} challenges from Juice Shop")
        
        # Get solved challenges from Juice Shop
        solved_challenges_from_api = [c for c in all_challenges if c.get('solved', False)]
        current_app.logger.info(f"Found {len(solved_challenges_from_api)} solved challenges from Juice Shop API")
        
        # If assignment_id is provided, filter for only assigned challenges
        if assignment_id:
            # Get assigned challenges from database
            assigned_challenges = get_assigned_challenges(assignment_id)
            assigned_ids = [c['challenge_id'] for c in assigned_challenges]
            current_app.logger.info(f"Assignment {assignment_id} has {len(assigned_ids)} assigned challenges")
            
            # Filter solved challenges to only include assigned ones
            solved_challenges = [c for c in solved_challenges_from_api if c['id'] in assigned_ids]
            current_app.logger.info(f"Found {len(solved_challenges)} solved challenges that are part of this assignment")
        else:
            solved_challenges = solved_challenges_from_api
        
        # Get solved challenges already in database
        solved_in_db = get_user_solved_challenges(user_id, assignment_id)
        current_app.logger.info(f"Found {len(solved_in_db)} challenges already marked as solved in database")
        
        # Save new solved challenges to database
        new_solved_count = 0
        for challenge in solved_challenges:
            if challenge['id'] not in solved_in_db:
                if save_solved_challenge(user_id, challenge['id'], assignment_id):
                    new_solved_count += 1
        
        current_app.logger.info(f"Saved {new_solved_count} new solved challenges to database")
        
        # Get updated challenge status
        result = get_user_challenges(user_id, assignment_id)
        current_app.logger.info(f"Final result: {result['completed']}/{result['total']} challenges completed")
        
        # Submit score directly if we have a launch_id
        if launch_id and result['completed'] > 0 and result['total'] > 0:
            current_app.logger.info(f"Submitting score for user {user_id}: {result['completed']}/{result['total']}")
            
            # Import here to avoid circular imports
            from services.lti_service import submit_score
            
            # The score is the number of completed challenges out of the total possible
            score_result = submit_score(launch_id, result['completed'], result['total'])
            
            if score_result:
                current_app.logger.info(f"Score submission successful: {result['completed']}/{result['total']}")
            else:
                current_app.logger.error(f"Score submission failed for user {user_id}")
        
        return result
    
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error checking challenge completion: {str(e)}")
        return {'success': False, 'message': str(e), 'challenges': [], 'completed': 0, 'total': 0}