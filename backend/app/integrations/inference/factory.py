from app.core.config import settings
from .http import HttpAdapter
from .mock import MockAdapter

def model_adapter():
    return HttpAdapter() if settings().model_provider == 'http' else MockAdapter()
