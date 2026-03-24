from fastapi import FastAPI
from routers import portal_municipal_manaus, portal_estado_am, portal_estado_ms, portal_estado_ro, trigger, conf

app = FastAPI(title="Portal API", version="1.0.0")

app.include_router(portal_municipal_manaus.router)
app.include_router(portal_estado_am.router)
app.include_router(portal_estado_ms.router)
app.include_router(portal_estado_ro.router)
app.include_router(trigger.router)
app.include_router(conf.router)

@app.get("/health")
def health():
    return {"status": "ok"}
