import uvicorn

from fixops_controller.api.app import app


def run() -> None:
    uvicorn.run("fixops_controller.api.app:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    run()
