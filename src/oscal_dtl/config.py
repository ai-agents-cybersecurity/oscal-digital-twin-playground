# src/oscal_dtl/config.py
"""Configuration and paths for OSCAL Digital Twin Lab."""

from pathlib import Path
import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parents[2]

# Data paths
DATA_DIR = BASE_DIR / "data"
OSCAL_CONTENT_DIR = DATA_DIR / "oscal-content"

# SSP and live config paths
DEMO_SSP_PATH = DATA_DIR / "ssp" / "demo-ssp.json"
LIVE_CONFIG_PATH = DATA_DIR / "live_state" / "live-config-1.yaml"

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Validate required configuration
def validate_config():
    """Validate that required configuration is present."""
    errors = []
    
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY environment variable is not set")
    
    if not DEMO_SSP_PATH.exists():
        errors.append(f"Demo SSP not found at {DEMO_SSP_PATH}")
    
    if not LIVE_CONFIG_PATH.exists():
        errors.append(f"Live config not found at {LIVE_CONFIG_PATH}")
    
    return errors
