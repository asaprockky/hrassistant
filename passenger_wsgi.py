import os
import sys

# Add the project root to the sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Explicitly add the site-packages for Python 3.12
venv_pkgs = '/home/fulstek1/virtualenv/repositories/hrassistant/3.12/lib/python3.12/site-packages'
if venv_pkgs not in sys.path:
    sys.path.append(venv_pkgs)

from a2wsgi import ASGIMiddleware
from main import app  # This imports 'app' from your main.py

application = ASGIMiddleware(app)
