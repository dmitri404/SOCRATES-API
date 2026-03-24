import subprocess
from fastapi import APIRouter, Header
from auth import verificar_api_key

router = APIRouter(tags=["Trigger"])

_COMPOSE_FILE = "/opt/portal/docker-compose.yml"
_SERVICES = {
    "portal-municipal-manaus": "portal-municipal-mao",
    "portal-estado-am":        "portal-estado-am",
    "portal-estado-ms":        "portal-estado-ms",
    "portal-estado-ro":        "portal-estado-ro",
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


@router.post("/portal-municipal-manaus/trigger")
def trigger_municipal(x_api_key: str = Header(...)):
    verificar_api_key("portal_municipal_manaus", x_api_key)
    service = _SERVICES["portal-municipal-manaus"]
    if _esta_rodando(service):
        return {"status": "ja_rodando", "servico": service}
    _disparar(service)
    return {"status": "iniciado", "servico": service}


@router.post("/portal-estado-am/trigger")
def trigger_estado_am(x_api_key: str = Header(...)):
    verificar_api_key("portal_estado_am", x_api_key)
    service = _SERVICES["portal-estado-am"]
    if _esta_rodando(service):
        return {"status": "ja_rodando", "servico": service}
    _disparar(service)
    return {"status": "iniciado", "servico": service}


@router.post("/portal-estado-ms/trigger")
def trigger_estado_ms(x_api_key: str = Header(...)):
    verificar_api_key("portal_estado_ms", x_api_key)
    service = _SERVICES["portal-estado-ms"]
    if _esta_rodando(service):
        return {"status": "ja_rodando", "servico": service}
    _disparar(service)
    return {"status": "iniciado", "servico": service}


@router.post("/portal-estado-ro/trigger")
def trigger_estado_ro(x_api_key: str = Header(...)):
    verificar_api_key("portal_estado_ro", x_api_key)
    service = _SERVICES["portal-estado-ro"]
    if _esta_rodando(service):
        return {"status": "ja_rodando", "servico": service}
    _disparar(service)
    return {"status": "iniciado", "servico": service}
