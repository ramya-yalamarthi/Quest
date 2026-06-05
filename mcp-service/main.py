from fastapi import FastAPI

app = FastAPI()

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/tools")
def tools():
    return {"tools": []}
