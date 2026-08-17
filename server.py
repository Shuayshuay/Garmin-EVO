"""
Servidor MCP remoto para Garmin Connect.

Expone tus datos de Garmin (sueño, pasos, frecuencia cardiaca, estrés,
body battery, actividades, etc.) como herramientas que Claude puede usar,
sin pasar por servicios de terceros de pago.

Usa la librería no oficial `garminconnect` (basada en `garth`), que inicia
sesión en Garmin con tu email y contraseña, igual que hacen internamente
servicios como Pulsai o FitMCP.

Variables de entorno necesarias (las configuras en tu hosting, NO en este
archivo):
  - GARMIN_EMAIL
  - GARMIN_PASSWORD
  - PORT (la pone el hosting automáticamente, ej. Render)
"""

import os
import datetime
from typing import Optional

from garminconnect import Garmin
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("garmin-mcp")

# --- Sesión de Garmin, con reintento de login ---------------------------

_client: Optional[Garmin] = None


def get_client() -> Garmin:
    """Devuelve un cliente Garmin ya logueado, reutilizando sesión si puede."""
    global _client

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Faltan las variables de entorno GARMIN_EMAIL y/o GARMIN_PASSWORD "
            "en el hosting."
        )

    if _client is None:
        _client = Garmin(email, password)
        _client.login()
        return _client

    # Comprobación ligera de que la sesión sigue viva; si no, relogin.
    try:
        _client.get_full_name()
        return _client
    except Exception:
        _client = Garmin(email, password)
        _client.login()
        return _client


def _today() -> str:
    return datetime.date.today().isoformat()


# --- Herramientas expuestas a Claude -------------------------------------

@mcp.tool()
def get_sleep(date: str = "") -> dict:
    """Devuelve el resumen de sueño de un día (formato YYYY-MM-DD).
    Si no se indica fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_sleep_data(d)


@mcp.tool()
def get_steps(date: str = "") -> dict:
    """Devuelve los pasos y actividad diaria de un día (formato YYYY-MM-DD).
    Si no se indica fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_stats(d)


@mcp.tool()
def get_heart_rate(date: str = "") -> dict:
    """Devuelve los datos de frecuencia cardiaca de un día (formato YYYY-MM-DD).
    Si no se indica fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_heart_rates(d)


@mcp.tool()
def get_stress(date: str = "") -> dict:
    """Devuelve los datos de estrés de un día (formato YYYY-MM-DD).
    Si no se indica fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_stress_data(d)


@mcp.tool()
def get_body_battery(start_date: str = "", end_date: str = "") -> list:
    """Devuelve el Body Battery entre dos fechas (formato YYYY-MM-DD).
    Si no se indican fechas, usa solo el día de hoy."""
    client = get_client()
    s = start_date or _today()
    e = end_date or s
    return client.get_body_battery(s, e)


@mcp.tool()
def get_training_readiness(date: str = "") -> dict:
    """Devuelve la preparación para entrenar (training readiness) de un día
    (formato YYYY-MM-DD). Si no se indica fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_training_readiness(d)


@mcp.tool()
def get_activities(limit: int = 10) -> list:
    """Devuelve las últimas actividades registradas (por defecto, las 10 más
    recientes)."""
    client = get_client()
    return client.get_activities(0, limit)


@mcp.tool()
def get_weight(start_date: str = "", end_date: str = "") -> dict:
    """Devuelve las pesadas registradas entre dos fechas (formato YYYY-MM-DD).
    Si no se indican fechas, usa los últimos 30 días."""
    client = get_client()
    e = end_date or _today()
    s = start_date or (
        datetime.date.today() - datetime.timedelta(days=30)
    ).isoformat()
    return client.get_body_composition(s, e)


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http")
