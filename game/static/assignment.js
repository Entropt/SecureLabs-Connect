document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const loadingSection = document.getElementById('loading');
    const instanceExistsSection = document.getElementById('instance-exists');
    const noInstanceSection = document.getElementById('no-instance');
    const creatingInstanceSection = document.getElementById('creating-instance');
    const errorMessageSection = document.getElementById('error-message');
    const errorText = document.getElementById('error-text');
    
    const instanceUrl = document.getElementById('instance-url');
    const instanceCreated = document.getElementById('instance-created');
    
    const continueBtn = document.getElementById('continue-btn');
    const restartBtn = document.getElementById('restart-btn');
    const createBtn = document.getElementById('create-btn');
    const retryBtn = document.getElementById('retry-btn');
    
    const progressFill = document.getElementById('progress-fill');
    const completedChallenges = document.getElementById('completed-challenges');
    const totalChallenges = document.getElementById('total-challenges');
    const challengeList = document.getElementById('challenge-list');
    
    // Modal elements
    const challengeModal = document.getElementById('challenge-modal');
    const modalClose = challengeModal.querySelector('.close');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const modalTitle = document.getElementById('modal-title');
    const modalName = document.getElementById('modal-name');
    const modalDifficulty = document.getElementById('modal-difficulty');
    const modalStatus = document.getElementById('modal-status');
    const modalDescription = document.getElementById('modal-description');
    
    // Challenge data storage
    let challengesData = [];
    
    // Event listeners
    if (continueBtn) {
        continueBtn.addEventListener('click', continueToInstance);
    }
    if (restartBtn) {
        restartBtn.addEventListener('click', restartInstance);
    }
    if (createBtn) {
        createBtn.addEventListener('click', createNewInstance);
    }
    if (retryBtn) {
        retryBtn.addEventListener('click', checkInstanceStatus);
    }
    
    // Modal close buttons
    if (modalClose) {
        modalClose.addEventListener('click', function() {
            challengeModal.style.display = 'none';
        });
    }
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', function() {
            challengeModal.style.display = 'none';
        });
    }
    
    // Close modal when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target === challengeModal) {
            challengeModal.style.display = 'none';
        }
    });

    // Initial actions
    checkInstanceStatus();
    loadChallenges();
    
    // Set up periodic refresh - shorter interval for more responsive updates
    setInterval(checkInstanceStatus, 30000); // Check every 30 seconds
    
    // Start checking challenges immediately and then periodically
    updateChallengeStatus(); // Check immediately
    progressCheckInterval = setInterval(updateChallengeStatus, 5000); // Then every 5 seconds
    
    // Add CSS for score notification
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
    
    let lastSubmittedScore = 0; // Track the last score we submitted
    let progressCheckInterval; // Interval reference for challenge updates
    
    // Functions
    function showSection(section) {
        // Hide all sections
        loadingSection.style.display = 'none';
        instanceExistsSection.style.display = 'none';
        noInstanceSection.style.display = 'none';
        creatingInstanceSection.style.display = 'none';
        errorMessageSection.style.display = 'none';
        
        // Show the requested section
        if (section) {
            section.style.display = 'flex';
        }
    }
    
    function checkInstanceStatus() {
        showSection(loadingSection);
        
        fetch(`/api/instance-status/${launchId}/${userId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.exists) {
                    // Show existing instance info
                    instanceUrl.textContent = data.url;
                    instanceUrl.href = data.url;
                    
                    // Format date
                    const created = new Date(data.created_at);
                    instanceCreated.textContent = created.toLocaleString();
                    
                    showSection(instanceExistsSection);
                } else {
                    showSection(noInstanceSection);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                errorText.textContent = error.message || 'Failed to check instance status';
                showSection(errorMessageSection);
            });
    }
    
    function continueToInstance() {
        fetch(`/api/instance-status/${launchId}/${userId}`)
            .then(response => response.json())
            .then(data => {
                if (data.exists && data.url) {
                    window.open(data.url, '_blank');
                } else {
                    errorText.textContent = 'Instance URL not available';
                    showSection(errorMessageSection);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                errorText.textContent = 'Failed to get instance URL';
                showSection(errorMessageSection);
            });
    }
    
    function restartInstance() {
        showSection(creatingInstanceSection);
        
        fetch(`/api/restart-instance/${launchId}/${userId}`, {
            method: 'POST'
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to restart instance');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Set a timeout to check status after restart
                    setTimeout(checkInstanceStatus, 5000);
                } else {
                    errorText.textContent = data.message || 'Failed to restart instance';
                    showSection(errorMessageSection);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                errorText.textContent = error.message || 'An error occurred while restarting the instance';
                showSection(errorMessageSection);
            });
    }
    
    function createNewInstance() {
        showSection(creatingInstanceSection);
        
        fetch(`/api/create-instance/${launchId}/${userId}`, {
            method: 'POST'
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to create instance');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Poll for instance status
                    pollInstanceCreation();
                } else {
                    errorText.textContent = data.message || 'Failed to create instance';
                    showSection(errorMessageSection);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                errorText.textContent = error.message || 'An error occurred while creating the instance';
                showSection(errorMessageSection);
            });
    }
    
    function pollInstanceCreation() {
        // Check status every 5 seconds until instance is ready
        const pollInterval = setInterval(() => {
            fetch(`/api/instance-status/${launchId}/${userId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.exists && data.status === 'running') {
                        clearInterval(pollInterval);
                        checkInstanceStatus();
                    }
                })
                .catch(error => {
                    console.error('Error polling instance status:', error);
                    // Continue polling despite errors
                });
        }, 5000);
        
        // Set a timeout to stop polling after 5 minutes (to prevent infinite polling)
        setTimeout(() => {
            clearInterval(pollInterval);
            checkInstanceStatus();
        }, 300000);
    }
    
    function loadChallenges() {
        fetch(`/api/challenge-list/${launchId}/${assignmentId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to load challenges');
                }
                return response.json();
            })
            .then(data => {
                // Store challenges data for reference
                challengesData = data.challenges;
                
                // Update total challenges count
                totalChallenges.textContent = data.challenges.length;
                
                // Clear the challenge list
                challengeList.innerHTML = '';
                
                // Add each challenge to the list
                data.challenges.forEach(challenge => {
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
                    
                    // Add click event to show challenge details
                    challengeItem.addEventListener('click', function() {
                        showChallengeDetails(challenge.id);
                    });
                    
                    challengeList.appendChild(challengeItem);
                });
                
                // Update progress
                updateProgress(data.completed, data.challenges.length);
            })
            .catch(error => {
                console.error('Error:', error);
                challengeList.innerHTML = `<div class="error">Failed to load challenges: ${error.message}</div>`;
            });
    }
    
    function showChallengeDetails(challengeId) {
        // Find the challenge data
        const challenge = challengesData.find(c => c.id === challengeId);
        
        if (!challenge) {
            console.error('Challenge not found:', challengeId);
            return;
        }
        
        // Set modal content
        modalName.textContent = challenge.name;
        
        // Set difficulty stars
        let difficultyStars = '';
        for (let i = 0; i < challenge.difficulty; i++) {
            difficultyStars += '★';
        }
        for (let i = challenge.difficulty; i < 6; i++) {
            difficultyStars += '☆';
        }
        modalDifficulty.innerHTML = difficultyStars;
        
        // Set status
        modalStatus.textContent = challenge.completed ? 'Completed' : 'Not Completed';
        modalStatus.className = challenge.completed ? 'status-completed' : 'status-incomplete';
        
        // Set description
        modalDescription.textContent = challenge.description || 'No description available.';
        
        // Get instance URL to create the challenge link
        fetch(`/api/instance-status/${launchId}/${userId}`)
            .then(response => response.json())
            .then(data => {
                if (data.exists && data.url) {
                    // Add the open challenge button
                    const modalFooter = document.querySelector('.modal-footer');
                    
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
                    const challengeUrl = `${data.url}/#/challenge`;
                    
                    // Set click handler
                    openChallengeBtn.addEventListener('click', function() {
                        window.open(challengeUrl, '_blank');
                    });
                    
                    // Add button to modal
                    modalFooter.insertBefore(openChallengeBtn, closeModalBtn);
                }
            })
            .catch(error => {
                console.error('Error getting instance URL:', error);
            });
        
        // Show the modal
        challengeModal.style.display = 'block';
    }
    
    function updateChallengeStatus() {
        console.log('Checking challenge status...');
        
        // Debug info for troubleshooting
        console.log(`Launch ID: ${launchId}`);
        console.log(`User ID: ${userId}`);
        console.log(`Assignment ID: ${assignmentId}`);
        
        fetch(`/api/challenge-status/${launchId}/${userId}/${assignmentId}`)
            .then(response => {
                console.log('Challenge status response:', response.status);
                if (!response.ok) {
                    throw new Error(`Failed to update challenge status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Challenge status data:', data);
                
                // Update challenges data
                challengesData = data.challenges;
                
                // Update progress
                updateProgress(data.completed, data.total);
                completedChallenges.textContent = data.completed;
                totalChallenges.textContent = data.total;
                
                // Update individual challenge statuses
                data.challenges.forEach(challenge => {
                    const challengeElement = document.getElementById(`challenge-${challenge.id}`);
                    if (challengeElement) {
                        const statusElement = challengeElement.querySelector('.challenge-status');
                        
                        if (challenge.completed) {
                            statusElement.className = 'challenge-status completed';
                            statusElement.textContent = '✓';
                            
                            // If the modal is open and showing this challenge, update its status too
                            if (challengeModal.style.display === 'block' && 
                                modalName.textContent === challenge.name) {
                                modalStatus.textContent = 'Completed';
                                modalStatus.className = 'status-completed';
                            }
                        } else {
                            statusElement.className = 'challenge-status incomplete';
                            statusElement.textContent = '';
                        }
                    }
                });
                
                // Note: Score submission is now handled by the server directly
            })
            .catch(error => {
                console.error('Error updating challenge status:', error);
            });
    }
    
    function updateProgress(completed, total) {
        if (total > 0) {
            const percentage = (completed / total) * 100;
            progressFill.style.width = `${percentage}%`;
            completedChallenges.textContent = completed;
        }
    }
});