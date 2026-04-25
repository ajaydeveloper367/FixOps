import uvicorn

from fixops_worker_k8s.app import app


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8083)


if __name__ == "__main__":
    run()
