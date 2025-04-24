# Refactored LTI Integration for Juice Shop

This project provides integration between Canvas LMS and OWASP Juice Shop using LTI Advantage standards. 
The code has been refactored to improve organization and maintainability while preserving the original functionality.

## Project Structure

The application is now organized using a modular structure with clear separation of concerns:

```
app/
├── app.py                  # Main application entry point
├── config.py               # Configuration settings
├── models/                 # Database and data models
│   ├── __init__.py
│   ├── database.py         # Database initialization and connection
│   ├── instance.py         # Docker instance management models
│   └── challenge.py        # Challenge management models
├── services/               # Business logic
│   ├── __init__.py
│   ├── docker_service.py   # Docker container management
│   ├── lti_service.py      # LTI integration services
│   └── challenge_service.py # Challenge-related services
├── routes/                 # Route handlers
│   ├── __init__.py
│   ├── lti_routes.py       # LTI-related routes
│   ├── instance_routes.py  # Instance management routes
│   └── challenge_routes.py # Challenge-related routes
├── utils/                  # Utility functions
│   ├── __init__.py
│   └── helpers.py          # Helper functions and middleware
├── templates/              # HTML templates
│   ├── assignment.html
│   └── app.html
└── static/                 # Static files
    ├── assignment.js
    └── style.css
```

## Key Components

### Models Layer

- **database.py**: Handles database connection and initialization
- **instance.py**: Manages Docker instances in the database
- **challenge.py**: Manages challenges and assignments

### Services Layer

- **docker_service.py**: Handles Docker container creation, restarting, and cleanup
- **lti_service.py**: Provides LTI integration services
- **challenge_service.py**: Manages challenge-related business logic

### Routes Layer

- **lti_routes.py**: Handles LTI launch, deep linking, and configuration
- **instance_routes.py**: API endpoints for Docker instance management
- **challenge_routes.py**: API endpoints for challenge management

### Utilities

- **helpers.py**: Contains utility functions like the ReverseProxied middleware

## Setup and Installation

1. Configure configs/app.json file with your LTI settings
   ```json
   {
      "https://canvas.instructure.com" : [{
         "default": true,
         "client_id" : "<client_id1>",
         "auth_login_url" : "<auth_login_url>",
         "auth_token_url" : "<auth_token_url>",
         "auth_audience": null,
         "key_set_url" : "<key_set_url>",
         "key_set": null,
         "private_key_file" : "<path_to_private_key>",
         "public_key_file": "<path_to_public_key>",
         "deployment_ids" : ["<deployment_id>"]
      }, {
         "default": false,
         "client_id" : "<client_id2>",
         ...
      }]
   }
   ```

2. Create a virtual environment and install dependencies
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Run the application
   ```bash
   cd app
   python app.py
   ```

4. Set up local Juice Shop instance in port 3000
   ```bash
   docker run --rm -e "NODE_ENV=unsafe" -p 127.0.0.1:3000:3000 bkimminich/juice-shop
   ```

5. Configure your LTI tool in Canvas LMS with:
   ```
   OIDC Login URL: http://<ip_address>:9001/login/
   LTI Launch URL: http://<ip_address>:9001/assignment/
   JWKS URL: http://<ip_address>:9001/jwks/
   ```
**Note:** In case the error pop up in score phase, change JWKS to manually input and copy jwk in above URL to LTI Key.

6. Change necessary settings in `app.json`after deploy the app's information in a specific course

Read more [here](https://github.com/dmitry-viskov/pylti1.3/wiki/Configure-Canvas-as-LTI-1.3-Platform)

### Docker Management

This application manages Docker containers for each user's Juice Shop instance. Key features include:

- Creating containers on demand
- Restarting containers when requested
- Automatic cleanup of expired containers
- Graceful shutdown of all containers when the application exits

### LTI Integration

The application uses PyLTI1.3 for LTI Advantage integration, supporting:

- LTI 1.3 launches with OIDC authentication
- Deep Linking for selecting challenges
- Assignment and Grades Service (AGS) for reporting scores back to Canvas

### Juice Shop Challenge Integration

The application integrates with Juice Shop's challenge system:

- Fetching available challenges
- Tracking user progress on challenges
- Submitting scores back to Canvas based on completed challenges