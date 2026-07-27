import hashlib
import os

ITERATIONS = 100000
ALGORITHM = 'sha256'

def hash_password(password):
    # Generate a random salt
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac(
        ALGORITHM,
        password.encode('utf-8'),
        salt,
        ITERATIONS
    )
    # Store salt + key together
    return salt + key

def verify_password(stored_key, provided_password):
    # Convert hex string back to bytes
    stored_key = bytes.fromhex(stored_key.replace("\\x", ""))

    # Extract the salt (first 32 bytes)
    salt = stored_key[:32]
    stored_key = stored_key[32:]

    # Hash the provided password with the same salt
    new_key = hashlib.pbkdf2_hmac(
        ALGORITHM,
        provided_password.encode('utf-8'),
        salt,
        ITERATIONS
    )

    return new_key == stored_key
