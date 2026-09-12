import uvicorn

from app.infra.config import settings
from app.infra.logging_config import configure_logging


if __name__ == "__main__":
    configure_logging("control")
    uvicorn.run(
        "app.control.main:app",
        host=settings.control_host,
        port=settings.control_port,
        access_log=False,
        log_config=None,
    )
