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
        print("GARMIN_TOKENS no está definida, se omite el login por token.")
        return None
    try:
        combined = json.loads(base64.b64decode(tokens_b64))
        print(f"GARMIN_TOKENS decodificada, archivos: {list(combined.keys())}")
        tmp_dir = Path(tempfile.mkdtemp())
        for name, content in combined.items():
            (tmp_dir / name).write_text(content)
        client = Garmin()
        client.login(str(tmp_dir))
        print("Login con token guardado: OK")
        return client
    except Exception:
        import traceback
        print("Login con token guardado FALLÓ:")
        traceback.print_exc()
        return None


def get_client() -> Garmin:
    """Devuelve un cliente Garmin ya logueado, reutilizando sesión si puede."""
    global _client

    if _client is not None:
        return _client

    _client = _login_with_saved_tokens()
    if _client is not None:
        return _client

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Faltan las variables de entorno GARMIN_EMAIL y/o GARMIN_PASSWORD "
            "en el hosting."
        )

    print("Intentando login con email/contraseña (respaldo)...")
    _client = Garmin(email, password)
    _client.login()
    print("Login con email/contraseña: OK")
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
def get_activity_splits(activity_id: int) -> dict:
    """Devuelve los splits (parciales por km/milla) de una actividad
    concreta. Usa el activity_id que devuelve get_activities."""
    client = get_client()
    return client.get_activity_splits(activity_id)


@mcp.tool()
def get_vo2max(date: str = "") -> dict:
    """Devuelve las métricas máximas (VO2max, edad de fitness) de un día
    (formato YYYY-MM-DD). Si no se indica fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_max_metrics(d)


@mcp.tool()
def get_training_status(date: str = "") -> dict:
    """Devuelve el estado de entrenamiento (carga, VO2max, recuperación,
    indicadores de forma) de un día (formato YYYY-MM-DD). Si no se indica
    fecha, usa el día de hoy."""
    client = get_client()
    d = date or _today()
    return client.get_training_status(d)


@mcp.tool()
def get_activity_weather(activity_id: int) -> dict:
    """Devuelve las condiciones climáticas (temperatura, humedad, viento...)
    registradas durante una actividad concreta. Usa el activity_id que
    devuelve get_activities."""
    client = get_client()
    method = getattr(client, "get_activity_weather", None)
    if method is not None:
        return method(activity_id)
    # Respaldo si esta versión de la librería no trae el método directo.
    return client.connectapi(f"/activity-service/activity/{activity_id}/weather")


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


def _pace_target(min_per_km_slow: float, min_per_km_fast: float) -> dict:
    """Convierte un rango de ritmo (min/km) al formato que espera Garmin
    (velocidad en m/s, de más lento a más rápido)."""
    speed_slow = 1000.0 / (min_per_km_slow * 60.0)
    speed_fast = 1000.0 / (min_per_km_fast * 60.0)
    return {
        "targetType": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"},
        "targetValueOne": min(speed_slow, speed_fast),
        "targetValueTwo": max(speed_slow, speed_fast),
    }


def _hr_target(bpm_low: int, bpm_high: int) -> dict:
    return {
        "targetType": {
            "workoutTargetTypeId": 4,
            "workoutTargetTypeKey": "heart.rate.zone",
        },
        "targetValueOne": min(bpm_low, bpm_high),
        "targetValueTwo": max(bpm_low, bpm_high),
    }


def _apply_target(step, target: dict):
    """Aplica un target (ritmo o FC) a un step, sea cual sea el tipo de
    objeto que devuelvan los create_*_step de la librería (dict o
    dataclass)."""
    if isinstance(step, dict):
        step.update(target)
    else:
        for key, value in target.items():
            setattr(step, key, value)
    return step


@mcp.tool()
def schedule_interval_workout(
    name: str,
    date: str,
    repeat_count: int,
    work_distance_m: float = 0,
    work_duration_seconds: float = 0,
    recovery_duration_seconds: float = 90,
    warmup_minutes: float = 15,
    cooldown_minutes: float = 10,
    pace_slow_min_per_km: float = 0,
    pace_fast_min_per_km: float = 0,
    hr_low_bpm: int = 0,
    hr_high_bpm: int = 0,
    sport: str = "running",
) -> dict:
    """Crea y programa un entrenamiento de SERIES (con calentamiento,
    repeticiones de trabajo + recuperación, y enfriamiento) en el
    calendario de Garmin. Pensado para sesiones tipo "6x1000m a ritmo X
    con 90s de recuperación".

    Args:
        name: nombre del entrenamiento.
        date: fecha YYYY-MM-DD en la que programarlo.
        repeat_count: número de repeticiones (ej. 6 para "6x1000m").
        work_distance_m: distancia de cada repetición en metros (usa esto
            O work_duration_seconds, no ambos).
        work_duration_seconds: duración de cada repetición en segundos
            (alternativa a work_distance_m).
        recovery_duration_seconds: duración de la recuperación entre
            repeticiones, en segundos.
        warmup_minutes: minutos de calentamiento antes de las series.
        cooldown_minutes: minutos de enfriamiento después de las series.
        pace_slow_min_per_km / pace_fast_min_per_km: rango de ritmo objetivo
            para las repeticiones de trabajo, en minutos por km (ej. 4.17 y
            4.0 para un objetivo de 4:10-4:00 min/km). Opcional.
        hr_low_bpm / hr_high_bpm: rango de frecuencia cardiaca objetivo para
            las repeticiones de trabajo, en pulsaciones por minuto. Opcional
            (usa esto O el ritmo, normalmente no ambos a la vez).
        sport: "running" o "cycling".

    Nota: esta herramienta es más compleja y menos probada que las demás.
    Si el resultado en Garmin no sale como esperas (por ejemplo el objetivo
    de ritmo no aparece), dímelo para revisarlo.
    """
    client = get_client()

    sport_map = {
        "running": ("RunningWorkout", {"sportTypeId": 1, "sportTypeKey": "running"}),
        "cycling": ("CyclingWorkout", {"sportTypeId": 2, "sportTypeKey": "cycling"}),
    }
    class_name, sport_info = sport_map.get(sport, sport_map["running"])
    WorkoutClass = getattr(gc_workout, class_name, gc_workout.RunningWorkout)

    steps = []
    order = 1

    warmup_step = gc_workout.create_warmup_step(warmup_minutes * 60, step_order=order)
    steps.append(warmup_step)
    order += 1

    # Paso de trabajo (con objetivo de ritmo o FC si se ha indicado)
    if work_distance_m:
        work_step = gc_workout.create_distance_interval_step(
            work_distance_m, step_order=1
        )
    else:
        work_step = gc_workout.create_interval_step(
            work_duration_seconds or 240, step_order=1
        )
    if pace_slow_min_per_km and pace_fast_min_per_km:
        work_step = _apply_target(
            work_step, _pace_target(pace_slow_min_per_km, pace_fast_min_per_km)
        )
    elif hr_low_bpm and hr_high_bpm:
        work_step = _apply_target(work_step, _hr_target(hr_low_bpm, hr_high_bpm))

    recovery_step = gc_workout.create_recovery_step(
        recovery_duration_seconds, step_order=2
    )

    repeat_group = gc_workout.create_repeat_group(
        repeat_count, [work_step, recovery_step], step_order=order
    )
    steps.append(repeat_group)
    order += 1

    cooldown_step = gc_workout.create_cooldown_step(
        cooldown_minutes * 60, step_order=order
    )
    steps.append(cooldown_step)

    est_duration = (
        warmup_minutes * 60
        + repeat_count * ((work_duration_seconds or 240) + recovery_duration_seconds)
        + cooldown_minutes * 60
    )

    workout = WorkoutClass(
        workoutName=name,
        estimatedDurationInSecs=est_duration,
        workoutSegments=[
            gc_workout.WorkoutSegment(
                segmentOrder=1, sportType=sport_info, workoutSteps=steps
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
        "repeticiones": repeat_count,
    }


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http")
