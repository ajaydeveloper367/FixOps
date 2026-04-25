import uvicorn

from fixops_executor.app import app


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8082)


if __name__ == "__main__":
    run()
