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

import os
import base64
import json
import tempfile
import datetime
from pathlib import Path
from typing import Optional

from garminconnect import Garmin
from garminconnect import workout as gc_workout
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "garmin-mcp",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# --- Sesión de Garmin, con reintento de login ---------------------------

_client: Optional[Garmin] = None


def _login_with_saved_tokens() -> Optional[Garmin]:
    """Si existe la variable de entorno GARMIN_TOKENS (generada con
    local_login.py), inicia sesión reutilizando esa sesión guardada, sin
    contraseña ni MFA."""
    tokens_b64 = os.environ.get("GARMIN_TOKENS")
    if not tokens_b64:
        return None
    try:
        combined = json.loads(base64.b64decode(tokens_b64))
        tmp_dir = Path(tempfile.mkdtemp())
        for name, content in combined.items():
            (tmp_dir / name).write_text(content)
        client = Garmin()
        client.login(str(tmp_dir))
        return client
    except Exception:
        return None


def get_client() -> Garmin:
    """Devuelve un cliente Garmin ya logueado, reutilizando sesión si puede."""
    global _client

    if _client is None:
        _client = _login_with_saved_tokens()

    if _client is not None:
        try:
            _client.get_full_name()
            return _client
        except Exception:
            _client = None

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Faltan las variables de entorno GARMIN_EMAIL y/o GARMIN_PASSWORD "
            "en el hosting."
        )

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


@mcp.tool()
def schedule_workout(
    name: str,
    date: str,
    sport: str = "running",
    duration_minutes: float = 0,
    distance_km: float = 0,
) -> dict:
    """Crea un entrenamiento simple (un solo bloque, sin intervalos) y lo
    programa en tu calendario de Garmin en la fecha indicada.

    Args:
        name: nombre del entrenamiento, ej. "Rodaje suave".
        date: fecha en formato YYYY-MM-DD en la que quieres que aparezca
            en tu calendario de Garmin.
        sport: "running", "cycling" o "walking".
        duration_minutes: duración objetivo en minutos (usa esto O
            distance_km, no ambos).
        distance_km: distancia objetivo en km (usa esto O
            duration_minutes, no ambos).
    """
    client = get_client()

    sport_map = {
        "running": ("RunningWorkout", {"sportTypeId": 1, "sportTypeKey": "running"}),
        "cycling": ("CyclingWorkout", {"sportTypeId": 2, "sportTypeKey": "cycling"}),
        "walking": ("WalkingWorkout", {"sportTypeId": 9, "sportTypeKey": "walking"}),
    }
    class_name, sport_info = sport_map.get(sport, sport_map["running"])
    WorkoutClass = getattr(gc_workout, class_name, gc_workout.RunningWorkout)

    if distance_km and not duration_minutes:
        step = gc_workout.create_distance_interval_step(
            distance_km * 1000, step_order=1
        )
        est_duration = 0
    else:
        duration_seconds = (duration_minutes or 30) * 60
        step = gc_workout.create_interval_step(duration_seconds, step_order=1)
        est_duration = duration_seconds

    workout = WorkoutClass(
        workoutName=name,
        estimatedDurationInSecs=est_duration,
        workoutSegments=[
            gc_workout.WorkoutSegment(
                segmentOrder=1, sportType=sport_info, workoutSteps=[step]
            )
        ],
    )

    upload_method = getattr(client, f"upload_{sport}_workout", None)
    if upload_method is None:
        upload_method = client.upload_running_workout

    result = upload_method(workout)
    client.schedule_workout(result["workoutId"], date)

    return {
        "status": "programado",
        "workout_id": result["workoutId"],
        "nombre": name,
        "fecha": date,
    }


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http")
