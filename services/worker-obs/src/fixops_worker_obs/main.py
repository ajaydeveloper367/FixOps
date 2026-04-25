import uvicorn

from fixops_worker_obs.app import app


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8081)


if __name__ == "__main__":
    run()
