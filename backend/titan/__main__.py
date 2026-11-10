import uvicorn

from .config import Settings
from .main import create_app


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
