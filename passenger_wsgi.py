import os
import sys

# Ensure the app directory is in the python path
sys.path.insert(0, os.getcwd())

from a2wsgi import ASGIMiddleware
from main import app  # This matches your 'main.py' and 'app = FastAPI()'

application = ASGIMiddleware(app)
