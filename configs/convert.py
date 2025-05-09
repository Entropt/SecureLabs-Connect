#!/usr/bin/env python3

# This script converts a PEM public key to a JWK (JSON Web Key) format.

import sys
import json
import base64
import hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Read the PEM public key from file
with open('public.key', 'rb') as f:
    pem_data = f.read()

# Load the public key
public_key = serialization.load_pem_public_key(
    pem_data,
    backend=default_backend()
)

# Get the numbers from the key
public_numbers = public_key.public_numbers()

# Convert to JWK format
def int_to_base64url(value):
    """Convert an integer to a base64url-encoded string"""
    value_hex = format(value, 'x')
    # Ensure even length
    if len(value_hex) % 2 == 1:
        value_hex = '0' + value_hex
    value_bytes = bytes.fromhex(value_hex)
    encoded = base64.urlsafe_b64encode(value_bytes).decode('ascii')
    return encoded.rstrip('=')  # Remove any trailing '='

# Create the JWK
jwk = {
    "kty": "RSA",
    "n": int_to_base64url(public_numbers.n),
    "e": int_to_base64url(public_numbers.e),
    "alg": "RS256",
    "use": "sig",
}

# Generate kid (Key ID) from the JWK thumbprint
jwk_thumbprint = json.dumps({"e": jwk["e"], "kty": "RSA", "n": jwk["n"]}, 
                         sort_keys=True, separators=(',', ':')).encode()
kid = base64.urlsafe_b64encode(hashlib.sha256(jwk_thumbprint).digest()).decode('ascii').rstrip('=')
jwk["kid"] = kid

# Output the JWK
with open('public.jwk.json', 'w') as f:
    json.dump(jwk, f, indent=4)

print("JWK file created successfully as public.jwk.json")
