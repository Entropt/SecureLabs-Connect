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

    // Initial actions
    checkInstanceStatus();
    loadChallenges();
    
    // Set up periodic refresh
    setInterval(checkInstanceStatus, 30000); // Check every 30 seconds
    setInterval(updateChallengeStatus, 15000); // Update challenges every 15 seconds
    
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
                // Update total challenges count
                totalChallenges.textContent = data.challenges.length;
                
                // Clear the challenge list
                challengeList.innerHTML = '';
                
                // Add each challenge to the list
                data.challenges.forEach(challenge => {
                    const challengeItem = document.createElement('div');
                    challengeItem.className = 'challenge-item';
                    challengeItem.id = `challenge-${challenge.id}`;
                    
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
                        </div>
                    `;
                    
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
    
    function updateChallengeStatus() {
        fetch(`/api/challenge-status/${launchId}/${userId}/${assignmentId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to update challenge status');
                }
                return response.json();
            })
            .then(data => {
                // Update progress
                updateProgress(data.completed, data.total);
                completedChallenges.textContent = data.completed;
                
                // Update individual challenge statuses
                data.challenges.forEach(challenge => {
                    const challengeElement = document.getElementById(`challenge-${challenge.id}`);
                    if (challengeElement) {
                        const statusElement = challengeElement.querySelector('.challenge-status');
                        
                        if (challenge.completed) {
                            statusElement.className = 'challenge-status completed';
                            statusElement.textContent = '✓';
                        } else {
                            statusElement.className = 'challenge-status incomplete';
                            statusElement.textContent = '';
                        }
                    }
                });
                
                // If all challenges are complete, submit the score
                if (data.completed === data.total && data.total > 0) {
                    submitScore(100); // Submit full score when all challenges are completed
                } else if (data.completed > 0) {
                    // Calculate partial score
                    const score = Math.round((data.completed / data.total) * 100);
                    submitScore(score);
                }
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
    
    function submitScore(score) {
        // Only submit score if we have a valid score
        if (score >= 0 && score <= 100) {
            fetch(`/api/score/${launchId}/${score}`, {
                method: 'POST'
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Score submitted:', data);
                })
                .catch(error => {
                    console.error('Error submitting score:', error);
                });
        }
    }
});