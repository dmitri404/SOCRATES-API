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

_LOGS = {
    "municipal":     "/opt/portal/logs/portal_municipal_mao_cron.log",
    "estado-am":     "/opt/portal/logs/portal_estado_am_cron.log",
    "municipio-pvh": "/opt/portal/logs/portal-municipio-pvh.log",
    "estado-ms":     "/opt/portal/logs/portal-estado-ms-cron.log",
    "estado-ro":     "/opt/portal/logs/portal-estado-ro-cron.log",
}


_DOCKER = "/usr/bin/docker"


def _esta_rodando(service: str) -> bool:
    result = subprocess.run(
        [_DOCKER, "ps",
         "--filter", f"label=com.docker.compose.service={service}",
         "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=5,
    )
    return bool(result.stdout.strip())


def _disparar(service: str, log_path: str) -> None:
    log_file = open(log_path, "a")
    subprocess.Popen(
        [_DOCKER, "compose", "-f", _COMPOSE_FILE,
         "--project-directory", "/opt/portal", "run", "--rm", service],
        stdout=log_file,
        stderr=log_file,
    )


@router.post("/{portal}/trigger")
def trigger(portal: str, usuario=Depends(requer_role("admin", "supervisor"))):
    service = _SERVICES.get(portal)
    if not service:
        raise HTTPException(status_code=404, detail="Portal não encontrado")
    if _esta_rodando(service):
        return {"status": "ja_rodando", "message": f"O scraper '{service}' já está em execução."}
    _disparar(service, _LOGS[portal])
    return {"status": "iniciado", "message": f"Scraper '{service}' iniciado com sucesso!"}
