"""
Vercel ASGI entrypoint.

Vercel maps Python serverless functions from `api/*.py`; exposing `app` here
allows stable routing for FastAPI deployments.
"""

from api.main import app

