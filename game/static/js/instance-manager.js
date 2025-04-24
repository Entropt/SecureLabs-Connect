/**
 * Instance Manager - Handles Juice Shop instance operations
 */

class InstanceManager {
    constructor(uiController) {
        this.uiController = uiController;
        this.instanceIsReady = false;
        this.currentInstanceUrl = null;
        
        // Bind event handlers to buttons
        this.bindEventHandlers();
    }
    
    /**
     * Bind event handlers to UI elements
     */
    bindEventHandlers() {
        if (this.uiController.continueBtn) {
            this.uiController.continueBtn.addEventListener('click', () => this.continueToInstance());
        }
        
        if (this.uiController.restartBtn) {
            this.uiController.restartBtn.addEventListener('click', () => this.restartInstance());
        }
        
        if (this.uiController.createBtn) {
            this.uiController.createBtn.addEventListener('click', () => this.createNewInstance());
        }
        
        if (this.uiController.retryBtn) {
            this.uiController.retryBtn.addEventListener('click', () => this.checkInstanceStatus());
        }
    }
    
    /**
     * Check the status of the user's instance
     * @returns {Promise<Object>} Instance data if available
     */
    async checkInstanceStatus() {
        this.uiController.showLoading();
        
        try {
            const response = await fetch(`/api/instance-status/${launchId}/${userId}`);
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            const data = await response.json();
            
            if (data.exists) {
                // Store instance URL for other components to use
                this.currentInstanceUrl = data.url;
                
                // Show existing instance info in UI
                this.uiController.showInstanceExists(data);
                
                // Set instance status to ready
                const wasReady = this.instanceIsReady;
                this.instanceIsReady = true;
                
                // Return data for other components to use
                return data;
            } else {
                this.instanceIsReady = false;
                this.currentInstanceUrl = null;
                this.uiController.showNoInstance();
                return null;
            }
        } catch (error) {
            console.error('Error checking instance status:', error);
            this.uiController.showError(error.message || 'Failed to check instance status');
            this.instanceIsReady = false;
            this.currentInstanceUrl = null;
            return null;
        }
    }
    
    /**
     * Get instance status without changing UI state
     * @returns {Promise<Object>} Instance data if available
     */
    async getInstanceStatus() {
        try {
            const response = await fetch(`/api/instance-status/${launchId}/${userId}`);
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error getting instance status:', error);
            return null;
        }
    }
    
    /**
     * Continue to the instance in a new tab
     */
    async continueToInstance() {
        try {
            const data = await this.getInstanceStatus();
            
            if (data && data.exists && data.url) {
                window.open(data.url, '_blank');
            } else {
                this.uiController.showError('Instance URL not available');
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiController.showError('Failed to get instance URL');
        }
    }
    
    /**
     * Restart the instance
     * @returns {Promise<Object>} New instance data
     */
    async restartInstance() {
        this.uiController.showCreatingInstance();
        this.uiController.setChallengeListLoadingMessage('Restarting instance and loading challenges...');
        
        // Set instance as not ready during restart
        this.instanceIsReady = false;
        this.currentInstanceUrl = null;
        
        try {
            const response = await fetch(`/api/restart-instance/${launchId}/${userId}`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error('Failed to restart instance');
            }
            
            const data = await response.json();
            
            if (data.success) {
                // Poll for instance status
                setTimeout(() => this.checkInstanceStatus(), 5000);
                return data;
            } else {
                this.uiController.showError(data.message || 'Failed to restart instance');
                return null;
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiController.showError(error.message || 'An error occurred while restarting the instance');
            return null;
        }
    }
    
    /**
     * Create a new instance
     * @returns {Promise<Object>} New instance data
     */
    async createNewInstance() {
        this.uiController.showCreatingInstance();
        this.uiController.setChallengeListLoadingMessage('Creating instance and loading challenges...');
        
        // Set instance as not ready during creation
        this.instanceIsReady = false;
        this.currentInstanceUrl = null;
        
        try {
            const response = await fetch(`/api/create-instance/${launchId}/${userId}`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error('Failed to create instance');
            }
            
            const data = await response.json();
            
            if (data.success) {
                // Poll for instance status
                this.pollInstanceCreation();
                return data;
            } else {
                this.uiController.showError(data.message || 'Failed to create instance');
                return null;
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiController.showError(error.message || 'An error occurred while creating the instance');
            return null;
        }
    }
    
    /**
     * Poll instance status until ready
     */
    pollInstanceCreation() {
        // Check status every 5 seconds until instance is ready
        const pollInterval = setInterval(async () => {
            try {
                const data = await this.getInstanceStatus();
                
                if (data && data.exists && data.status === 'running') {
                    clearInterval(pollInterval);
                    await this.checkInstanceStatus();
                }
            } catch (error) {
                console.error('Error polling instance status:', error);
                // Continue polling despite errors
            }
        }, 5000);
        
        // Set a timeout to stop polling after 5 minutes (to prevent infinite polling)
        setTimeout(() => {
            clearInterval(pollInterval);
            this.checkInstanceStatus();
        }, 300000);
    }
    
    /**
     * Check if instance is ready
     * @returns {boolean} Whether the instance is ready
     */
    isInstanceReady() {
        return this.instanceIsReady;
    }
    
    /**
     * Get current instance URL
     * @returns {string|null} Instance URL if available
     */
    getInstanceUrl() {
        return this.currentInstanceUrl;
    }
}