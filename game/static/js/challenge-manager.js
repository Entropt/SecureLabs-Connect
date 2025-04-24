/**
 * Challenge Manager - Handles challenges loading and status updates
 */

class ChallengeManager {
    constructor(uiController, instanceManager) {
        this.uiController = uiController;
        this.instanceManager = instanceManager;
        this.challengesData = [];
        this.lastSubmittedScore = 0;
        this.updateInterval = null;
        
        // Bind event handlers for challenge list
        this.bindChallengeEvents();
    }
    
    /**
     * Bind event handlers for challenges
     */
    bindChallengeEvents() {
        // Delegate event handling for challenge items (which are dynamically created)
        if (this.uiController.challengeList) {
            this.uiController.challengeList.addEventListener('click', (event) => {
                // Find closest challenge item
                const challengeItem = event.target.closest('.challenge-item');
                if (challengeItem) {
                    const challengeId = parseInt(challengeItem.dataset.id);
                    this.showChallengeDetails(challengeId);
                }
            });
        }
    }
    
    /**
     * Load challenges for the current assignment
     */
    async loadChallenges() {
        console.log("Loading challenges for assignment:", assignmentId);
        
        // Skip loading if no instance is ready yet
        if (!this.instanceManager.isInstanceReady()) {
            console.log("Instance not ready, skipping challenge load.");
            this.uiController.setChallengeListLoadingMessage('Waiting for instance to be ready...');
            return;
        }
        
        // Update UI to show loading state
        this.uiController.setChallengeListLoadingMessage('Loading challenges...');
        
        try {
            const response = await fetch(`/api/challenge-list/${launchId}/${assignmentId}`);
            
            if (!response.ok) {
                throw new Error('Failed to load challenges');
            }
            
            const data = await response.json();
            console.log("Challenges loaded:", data);
            
            // Store challenges data
            this.challengesData = data.challenges;
            
            // Update UI with challenges
            this.uiController.displayChallengeList(data.challenges);
            this.uiController.updateProgress(data.completed, data.total);
            
            return data;
        } catch (error) {
            console.error('Error loading challenges:', error);
            this.uiController.challengeList.innerHTML = `<div class="error">Failed to load challenges: ${error.message}</div>`;
            return null;
        }
    }
    
    /**
     * Show challenge details in modal
     * @param {number} challengeId - ID of the challenge to show
     */
    async showChallengeDetails(challengeId) {
        // Find the challenge data
        const challenge = this.challengesData.find(c => c.id === challengeId);
        
        if (!challenge) {
            console.error('Challenge not found:', challengeId);
            return;
        }
        
        // Show challenge details in modal
        this.uiController.showChallengeDetails(challenge);
        
        // Get instance URL for the open challenge button
        try {
            const instanceData = await this.instanceManager.getInstanceStatus();
            
            if (instanceData && instanceData.exists && instanceData.url) {
                this.uiController.addOpenChallengeButton(instanceData.url);
            }
        } catch (error) {
            console.error('Error getting instance URL:', error);
        }
    }
    
    /**
     * Update challenge status from server
     */
    async updateChallengeStatus() {
        // Skip update if no instance is available
        if (!this.instanceManager.isInstanceReady()) {
            return;
        }
        
        console.log('Checking challenge status...');
        
        try {
            const response = await fetch(`/api/challenge-status/${launchId}/${userId}/${assignmentId}`);
            
            if (!response.ok) {
                throw new Error(`Failed to update challenge status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Challenge status data:', data);
            
            // If this is the first time we're getting challenge data and the list is empty, populate it
            if (data.challenges && data.challenges.length > 0 && 
                (this.challengesData.length === 0 || this.uiController.challengeList.querySelector('.loading-challenges'))) {
                console.log("Initial challenge data received, populating list...");
                this.challengesData = data.challenges;
                await this.loadChallenges();
                return;
            }
            
            // Update challenges data
            this.challengesData = data.challenges;
            
            // Update progress
            this.uiController.updateProgress(data.completed, data.total);
            
            // Update individual challenge statuses
            data.challenges.forEach(challenge => {
                this.uiController.updateChallengeStatus(challenge);
            });
            
            return data;
        } catch (error) {
            console.error('Error updating challenge status:', error);
            return null;
        }
    }
    
    /**
     * Start periodic updates of challenge status
     * @param {number} interval - Update interval in milliseconds
     */
    startPeriodicUpdates(interval = 5000) {
        // Clear any existing interval
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
        
        // Set new interval
        this.updateInterval = setInterval(() => this.updateChallengeStatus(), interval);
    }
    
    /**
     * Stop periodic updates
     */
    stopPeriodicUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
    
    /**
     * Submit score to LMS
     * @param {number} score - Score to submit
     * @param {number} maxScore - Maximum possible score
     */
    async submitScore(score, maxScore) {
        try {
            // Avoid submitting the same score multiple times
            if (score === this.lastSubmittedScore) {
                return;
            }
            
            const response = await fetch(`/api/score/${launchId}/${score}/`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error('Failed to submit score');
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.lastSubmittedScore = score;
                this.uiController.showNotification(`Score submitted: ${score}/${maxScore}`, 3000);
                return true;
            } else {
                console.error('Error submitting score:', data.error);
                return false;
            }
        } catch (error) {
            console.error('Error submitting score:', error);
            return false;
        }
    }
}