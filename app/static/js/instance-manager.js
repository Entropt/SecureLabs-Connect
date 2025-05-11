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
        
        if (this.uiController.shutdownBtn) {
            this.uiController.shutdownBtn.addEventListener('click', () => this.shutdownInstance());
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
     * With enhanced verification to ensure the instance container is running
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
                this.instanceIsReady = true;
                
                // Return data for other components to use
                return data;
            } else {
                this.instanceIsReady = false;
                this.currentInstanceUrl = null;
                
                // Show an appropriate message if we know the reason
                if (data.reason === 'Container not running') {
                    this.uiController.showError('Your container is no longer running. It may have been stopped or deleted. Please create a new instance.');
                } else {
                    this.uiController.showNoInstance();
                }
                return data;  // Return data even for non-existent instance for error handling
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
     * Now with container verification
     * @returns {Promise<Object>} Instance data if available
     */
    async getInstanceStatus() {
        try {
            const response = await fetch(`/api/instance-status/${launchId}/${userId}`);
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            const data = await response.json();
            
            // Reset any stored URL if the instance doesn't exist anymore
            if (!data.exists) {
                this.currentInstanceUrl = null;
                this.instanceIsReady = false;
            }
            
            return data;
        } catch (error) {
            console.error('Error getting instance status:', error);
            return null;
        }
    }
    
    /**
     * Continue to the instance in a new tab
     * With real-time container verification to ensure the instance is actually running
     */
    async continueToInstance() {
        try {
            this.uiController.showLoading();
            
            // Always request fresh instance status to prevent using cached URL
            const data = await fetch(`/api/instance-status/${launchId}/${userId}?verification=strict`).then(res => res.json());
            
            if (data && data.exists && data.url) {
                // Update the stored URL before opening
                this.currentInstanceUrl = data.url;
                this.instanceIsReady = true;
                
                // Show the instance exists again before opening the tab
                this.uiController.showInstanceExists(data);
                
                // Open the instance in a new tab
                window.open(data.url, '_blank');
            } else {
                // If instance no longer exists but we had a URL before, it means it was deleted or expired
                if (this.currentInstanceUrl && !data.exists) {
                    if (data.reason === 'Container not running') {
                        this.uiController.showContainerError('Your instance container is no longer running. It may have been stopped when the server restarted. Please create a new instance.');
                    } else {
                        this.uiController.showError('Your instance has expired or been deleted. Please create a new instance.');
                    }
                    // Reset the stored URL
                    this.currentInstanceUrl = null;
                    this.instanceIsReady = false;
                } else {
                    this.uiController.showError('Instance URL not available');
                }
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
     * Shutdown the instance
     * @returns {Promise<Object>} Shutdown result
     */
    async shutdownInstance() {
        this.uiController.showLoading();
        this.uiController.setChallengeListLoadingMessage('Shutting down instance...');
        
        // Set instance as not ready during shutdown
        this.instanceIsReady = false;
        this.currentInstanceUrl = null;
        
        try {
            const response = await fetch(`/api/shutdown-instance/${launchId}/${userId}`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error('Failed to shutdown instance');
            }
            
            const data = await response.json();
            
            if (data.success) {
                // Check status to update UI
                setTimeout(() => this.checkInstanceStatus(), 2000);
                return data;
            } else {
                this.uiController.showError(data.message || 'Failed to shutdown instance');
                return null;
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiController.showError(error.message || 'An error occurred while shutting down the instance');
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
     * Now with improved container verification
     */
    pollInstanceCreation() {
        // Check status every 5 seconds until instance is ready
        const pollInterval = setInterval(async () => {
            try {
                const data = await this.getInstanceStatus();
                
                if (data && data.exists && data.status === 'running') {
                    clearInterval(pollInterval);
                    await this.checkInstanceStatus();
                } else if (data && !data.exists && data.reason === 'Container not running') {
                    // Container was created but isn't running anymore
                    clearInterval(pollInterval);
                    this.uiController.showContainerError('Container failed to start properly. Please try creating a new instance.');
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