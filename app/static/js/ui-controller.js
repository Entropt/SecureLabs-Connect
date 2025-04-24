/**
 * UI Controller - Manages UI elements and state
 */

class UIController {
    constructor() {
        // UI Sections
        this.loadingSection = document.getElementById('loading');
        this.instanceExistsSection = document.getElementById('instance-exists');
        this.noInstanceSection = document.getElementById('no-instance');
        this.creatingInstanceSection = document.getElementById('creating-instance');
        this.errorMessageSection = document.getElementById('error-message');
        this.errorText = document.getElementById('error-text');
        
        // Instance Details
        this.instanceUrl = document.getElementById('instance-url');
        this.instanceCreated = document.getElementById('instance-created');
        
        // Buttons
        this.continueBtn = document.getElementById('continue-btn');
        this.restartBtn = document.getElementById('restart-btn');
        this.createBtn = document.getElementById('create-btn');
        this.retryBtn = document.getElementById('retry-btn');
        
        // Progress elements
        this.progressFill = document.getElementById('progress-fill');
        this.completedChallenges = document.getElementById('completed-challenges');
        this.totalChallenges = document.getElementById('total-challenges');
        this.challengeList = document.getElementById('challenge-list');
        
        // Modal elements
        this.challengeModal = document.getElementById('challenge-modal');
        if (this.challengeModal) {
            this.modalClose = this.challengeModal.querySelector('.close');
            this.closeModalBtn = document.getElementById('close-modal-btn');
            this.modalTitle = document.getElementById('modal-title');
            this.modalName = document.getElementById('modal-name');
            this.modalDifficulty = document.getElementById('modal-difficulty');
            this.modalStatus = document.getElementById('modal-status');
            this.modalDescription = document.getElementById('modal-description');
            
            // Initialize modal events
            this.initializeModalEvents();
        }
        
        // Add notification styles
        this.addNotificationStyles();
    }
    
    /**
     * Initialize modal event listeners
     */
    initializeModalEvents() {
        if (this.modalClose) {
            this.modalClose.addEventListener('click', () => this.hideModal());
        }
        
        if (this.closeModalBtn) {
            this.closeModalBtn.addEventListener('click', () => this.hideModal());
        }
        
        // Close modal when clicking outside
        window.addEventListener('click', (event) => {
            if (event.target === this.challengeModal) {
                this.hideModal();
            }
        });
    }
    
    /**
     * Show a specific UI section and hide others
     * @param {HTMLElement} section - The section to show
     */
    showSection(section) {
        // Hide all sections
        this.loadingSection.style.display = 'none';
        this.instanceExistsSection.style.display = 'none';
        this.noInstanceSection.style.display = 'none';
        this.creatingInstanceSection.style.display = 'none';
        this.errorMessageSection.style.display = 'none';
        
        // Show the requested section
        if (section) {
            section.style.display = 'flex';
        }
    }
    
    /**
     * Show loading section
     */
    showLoading() {
        this.showSection(this.loadingSection);
    }
    
    /**
     * Show existing instance section with instance details
     * @param {Object} instanceData - Data about the instance
     */
    showInstanceExists(instanceData) {
        if (this.instanceUrl && instanceData.url) {
            this.instanceUrl.textContent = instanceData.url;
            this.instanceUrl.href = instanceData.url;
        }
        
        if (this.instanceCreated && instanceData.created_at) {
            const created = new Date(instanceData.created_at);
            this.instanceCreated.textContent = created.toLocaleString();
        }
        
        this.showSection(this.instanceExistsSection);
    }
    
    /**
     * Show no instance section
     */
    showNoInstance() {
        this.showSection(this.noInstanceSection);
    }
    
    /**
     * Show creating instance section
     */
    showCreatingInstance() {
        this.showSection(this.creatingInstanceSection);
    }
    
    /**
     * Show error message section
     * @param {string} errorMessage - The error message to display
     */
    showError(errorMessage) {
        this.errorText.textContent = errorMessage || 'An error occurred';
        this.showSection(this.errorMessageSection);
    }
    
    /**
     * Update the progress bar
     * @param {number} completed - Number of completed challenges
     * @param {number} total - Total number of challenges
     */
    updateProgress(completed, total) {
        if (total > 0) {
            const percentage = (completed / total) * 100;
            this.progressFill.style.width = `${percentage}%`;
            this.completedChallenges.textContent = completed;
            this.totalChallenges.textContent = total;
        } else {
            this.progressFill.style.width = '0%';
            this.completedChallenges.textContent = '0';
            this.totalChallenges.textContent = '0';
        }
    }
    
    /**
     * Display the challenge list
     * @param {Array} challenges - Array of challenge objects
     */
    displayChallengeList(challenges) {
        this.challengeList.innerHTML = '';
        
        if (!challenges || challenges.length === 0) {
            this.challengeList.innerHTML = '<div class="loading-challenges">No challenges found for this assignment</div>';
            return;
        }
        
        // Add each challenge to the list
        challenges.forEach(challenge => {
            const challengeItem = document.createElement('div');
            challengeItem.className = 'challenge-item';
            challengeItem.id = `challenge-${challenge.id}`;
            challengeItem.dataset.id = challenge.id;
            
            const statusClass = challenge.completed ? 'completed' : 'incomplete';
            const checkmarkContent = challenge.completed ? '✓' : '';
            
            // Create difficulty stars
            let difficultyStars = '';
            for (let i = 0; i < challenge.difficulty; i++) {
                difficultyStars += '★';
            }
            for (let i = challenge.difficulty; i < 6; i++) {
                difficultyStars += '☆';
            }
            
            challengeItem.innerHTML = `
                <div class="challenge-status ${statusClass}">${checkmarkContent}</div>
                <div class="challenge-info">
                    <div class="challenge-name">${challenge.name}</div>
                    <div class="challenge-difficulty">
                        <span class="difficulty-stars">${difficultyStars}</span>
                    </div>
                    <div class="challenge-action">
                        <span class="view-details-btn">View Details</span>
                    </div>
                </div>
            `;
            
            this.challengeList.appendChild(challengeItem);
        });
    }
    
    /**
     * Set loading message in challenge list
     * @param {string} message - The message to display
     */
    setChallengeListLoadingMessage(message) {
        this.challengeList.innerHTML = `<div class="loading-challenges">${message || 'Loading challenges...'}</div>`;
    }
    
    /**
     * Show challenge details modal
     * @param {Object} challenge - The challenge to display details for
     */
    showChallengeDetails(challenge) {
        if (!challenge || !this.challengeModal) return;
        
        // Set modal content
        this.modalName.textContent = challenge.name;
        
        // Set difficulty stars
        let difficultyStars = '';
        for (let i = 0; i < challenge.difficulty; i++) {
            difficultyStars += '★';
        }
        for (let i = challenge.difficulty; i < 6; i++) {
            difficultyStars += '☆';
        }
        this.modalDifficulty.innerHTML = difficultyStars;
        
        // Set status
        this.modalStatus.textContent = challenge.completed ? 'Completed' : 'Not Completed';
        this.modalStatus.className = challenge.completed ? 'status-completed' : 'status-incomplete';
        
        // Set description
        this.modalDescription.textContent = challenge.description || 'No description available.';
        
        // Show the modal
        this.challengeModal.style.display = 'block';
    }
    
    /**
     * Hide the challenge details modal
     */
    hideModal() {
        if (this.challengeModal) {
            this.challengeModal.style.display = 'none';
        }
    }
    
    /**
     * Add open challenge button to modal
     * @param {string} instanceUrl - URL of the Juice Shop instance
     */
    addOpenChallengeButton(instanceUrl) {
        if (!this.challengeModal) return;
        
        const modalFooter = this.challengeModal.querySelector('.modal-footer');
        if (!modalFooter) return;
        
        // Remove any existing open challenge button
        const existingButton = document.getElementById('open-challenge-btn');
        if (existingButton) {
            existingButton.remove();
        }
        
        // Create open challenge button
        const openChallengeBtn = document.createElement('button');
        openChallengeBtn.id = 'open-challenge-btn';
        openChallengeBtn.className = 'primary-button';
        openChallengeBtn.textContent = 'Open Challenge';
        openChallengeBtn.style.marginRight = '10px';
        
        // Create the challenge URL - Juice Shop uses URL hashes for navigation
        const challengeUrl = `${instanceUrl}/#/challenge`;
        
        // Set click handler
        openChallengeBtn.addEventListener('click', function() {
            window.open(challengeUrl, '_blank');
        });
        
        // Add button to modal
        modalFooter.insertBefore(openChallengeBtn, this.closeModalBtn);
    }
    
    /**
     * Update a single challenge's status in the UI
     * @param {Object} challenge - The challenge to update
     */
    updateChallengeStatus(challenge) {
        const challengeElement = document.getElementById(`challenge-${challenge.id}`);
        if (challengeElement) {
            const statusElement = challengeElement.querySelector('.challenge-status');
            
            if (challenge.completed) {
                statusElement.className = 'challenge-status completed';
                statusElement.textContent = '✓';
                
                // If the modal is open and showing this challenge, update its status too
                if (this.challengeModal && 
                    this.challengeModal.style.display === 'block' && 
                    this.modalName.textContent === challenge.name) {
                    this.modalStatus.textContent = 'Completed';
                    this.modalStatus.className = 'status-completed';
                }
            } else {
                statusElement.className = 'challenge-status incomplete';
                statusElement.textContent = '';
            }
        }
    }
    
    /**
     * Add CSS for score notification
     */
    addNotificationStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .score-notification {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background-color: #4caf50;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                z-index: 1000;
                opacity: 1;
                transition: opacity 0.5s;
            }
        `;
        document.head.appendChild(style);
    }
    
    /**
     * Show a score notification
     * @param {string} message - The notification message
     * @param {number} duration - How long to show notification (ms)
     */
    showNotification(message, duration = 3000) {
        const notification = document.createElement('div');
        notification.className = 'score-notification';
        notification.textContent = message;
        document.body.appendChild(notification);
        
        // Remove after duration
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 500);
        }, duration);
    }
}