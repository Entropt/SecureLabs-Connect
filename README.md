# Flask app integration into Canvas LMS through LTI Advantage

### Setup
1. Configure configs/game.json file
    ```
    {
        "https://canvas.instructure.com" : [{ // You can change this if you don't use Canvas LMS
            "default": true, // this block will be used in case if client-id was not passed
            "client_id" : "<client_id1>", // This is the id received in the 'aud' during a launch
            "auth_login_url" : "<auth_login_url>", // The platform's OIDC login endpoint
            "auth_token_url" : "<auth_token_url>", // The platform's service authorization endpoint
            "auth_audience": null,  // The platform's OAuth2 Audience (aud). Is used to get platform's access token,
                                    // Usually the same as "auth_token_url" but in the common case could be a different url
            "key_set_url" : "<key_set_url>", // The platform's JWKS endpoint
            "key_set": null, // in case if platform's JWKS endpoint somehow unavailable you may paste JWKS here
            "private_key_file" : "<path_to_private_key>", // Relative path to the tool's private key
            "public_key_file": "<path_to_public_key>", // Relative path to the tool's public key
            "deployment_ids" : ["<deployment_id>"] // The deployment_id passed by the platform during launch
        }, {
            "default": false,
            "client_id" : "<client_id2>",
            ...
        }]
    }
    ```

2. Create virtual environment for python and run app
    ```
    $ python -m venv .venv
    $ source .venv/bin/activate
    $ pip install -r requirements.txt
    $ cd game
    $ python app.py
    ```
3. Add the following information for LTI Key in Canvas LMS
    ```
    OIDC Login URL: http://<ip_address>:9001/login/
    LTI Launch URL: http://<ip_address>:9001/assignment/
    JWKS URL: http://<ip_address>:9001/jwks/
    ```

**Note:** In case the error pop up in score phase, change JWKS to manually input and copy jwk in above URL to LTI Key.