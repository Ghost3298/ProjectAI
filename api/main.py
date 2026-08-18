from fastapi import FastAPI

app = FastAPI()

@app.get("/health", status_code=200)
def is_healthy():
    return {"status" : "ok"}