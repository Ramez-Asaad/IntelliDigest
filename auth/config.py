import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH_DB_PATH = os.path.join(_REPO_ROOT, "data", "auth.db")

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
