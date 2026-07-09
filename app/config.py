from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

# ── IBM watsonx / Granite configuration ──────────────────────────────────────
# Add these to your .env file.  See app/ai/README.md for details.
WATSONX_API_KEY    = os.getenv('WATSONX_API_KEY', '')
WATSONX_PROJECT_ID = os.getenv('WATSONX_PROJECT_ID', '')
WATSONX_URL        = os.getenv('WATSONX_URL', 'https://us-south.ml.cloud.ibm.com')
GRANITE_MODEL_ID   = os.getenv('GRANITE_MODEL_ID', 'ibm/granite-3-3-8b-instruct')