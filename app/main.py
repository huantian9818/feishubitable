from fastapi import FastAPI

app = FastAPI(title="Feishu Bitable Monitor")


@app.get("/health")
def health():
    return {"status": "ok"}
