from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import portal_municipal_manaus, portal_estado_am, portal_estado_ms, portal_estado_ro, trigger, conf
from routers import auth_rbac

app = FastAPI(title="Portal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_rbac.router)
app.include_router(portal_municipal_manaus.router)
app.include_router(portal_estado_am.router)
app.include_router(portal_estado_ms.router)
app.include_router(portal_estado_ro.router)
app.include_router(trigger.router)
app.include_router(conf.router)

@app.get("/health")
def health():
    return {"status": "ok"}
