/**
 * Main JavaScript file - initializes all components
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize UI Controller (should be first as other modules depend on it)
    const uiController = new UIController();
    
    // Initialize Instance Manager
    const instanceManager = new InstanceManager(uiController);
    
    // Initialize Challenge Manager
    const challengeManager = new ChallengeManager(uiController, instanceManager);
    
    // Initial actions - check instance status first, as challenges depend on it
    instanceManager.checkInstanceStatus();
    
    // Periodically check status
    setInterval(() => instanceManager.checkInstanceStatus(), 30000); // Every 30 seconds
    
    // Start checking for challenges completion immediately, then periodically
    challengeManager.updateChallengeStatus();
    challengeManager.startPeriodicUpdates(5000); // Every 5 seconds
});