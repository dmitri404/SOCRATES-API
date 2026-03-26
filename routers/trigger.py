import subprocess
from fastapi import APIRouter, Depends, HTTPException
from routers.auth_rbac import requer_role

router = APIRouter(tags=["Trigger"])

_COMPOSE_FILE = "/opt/portal/docker-compose.yml"

_SERVICES = {
    "municipal":     "portal-municipal-mao",
    "estado-am":     "portal-estado-am",
    "municipio-pvh": "portal-municipio-pvh",
    "estado-ms":     "portal-estado-ms",
    "estado-ro":     "portal-estado-ro",
}


def _esta_rodando(service: str) -> bool:
    result = subprocess.run(
        ["docker", "ps",
         "--filter", f"label=com.docker.compose.service={service}",
         "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=5,
    )
    return bool(result.stdout.strip())


def _disparar(service: str) -> None:
    subprocess.Popen(
        ["docker", "compose", "-f", _COMPOSE_FILE,
         "--project-directory", "/opt/portal", "run", "--rm", service],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@router.post("/{portal}/trigger")
def trigger(portal: str, usuario=Depends(requer_role("admin", "supervisor"))):
    service = _SERVICES.get(portal)
    if not service:
        raise HTTPException(status_code=404, detail="Portal não encontrado")
    if _esta_rodando(service):
        return {"status": "ja_rodando", "message": f"O scraper '{service}' já está em execução."}
    _disparar(service)
    return {"status": "iniciado", "message": f"Scraper '{service}' iniciado com sucesso!"}
