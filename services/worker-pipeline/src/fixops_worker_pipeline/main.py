import uvicorn

from fixops_worker_pipeline.app import app


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8084)


if __name__ == "__main__":
    run()
