from __future__ import annotations

from fastapi import FastAPI
import uvicorn


app = FastAPI(title="Blackjack OS API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
