import os
from datetime import timedelta

class Config:
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    JWT_TOKEN_LOCATION = ['cookies', 'headers']
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    WTF_CSRF_ENABLED = False
    JWT_COOKIE_CSRF_PROTECT = False

    if not JWT_SECRET_KEY:
        raise RuntimeError(
            'JWT_SECRET_KEY is not set. Create a .env file based on .env.example '
            'and define JWT_SECRET_KEY before starting the app.'
        )
