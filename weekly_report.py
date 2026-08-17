"""
Genera un resumen semanal de tus datos de Garmin y lo envía por email.

Pensado para ejecutarse automáticamente cada lunes vía GitHub Actions
(ver .github/workflows/weekly-report.yml), NO dentro de una conversación
de Claude — es un proceso independiente.

Variables de entorno necesarias (se configuran como "Secrets" en GitHub,
Settings -> Secrets and variables -> Actions):
  - GARMIN_EMAIL
  - GARMIN_PASSWORD
  - GMAIL_ADDRESS        (la cuenta de Gmail desde la que se envía)
  - GMAIL_APP_PASSWORD   (contraseña de aplicación de esa cuenta de Gmail)
  - RECIPIENT_EMAIL      (a qué email quieres que llegue el resumen)
"""

import os
import smtplib
import datetime
from email.mime.text import MIMEText

from garminconnect import Garmin


def get_week_data():
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]
    client = Garmin(email, password)
    client.login()

    today = datetime.date.today()
    start = today - datetime.timedelta(days=7)

    steps_total = 0
    sleep_hours = []
    resting_hr = []

    day = start
    while day <= today:
        d = day.isoformat()
        try:
            stats = client.get_stats(d)
            steps_total += stats.get("totalSteps") or 0
            rhr = stats.get("restingHeartRate")
            if rhr:
                resting_hr.append(rhr)
        except Exception:
            pass
        try:
            sleep = client.get_sleep_data(d)
            seconds = (
                sleep.get("dailySleepDTO", {}).get("sleepTimeSeconds") or 0
            )
            if seconds:
                sleep_hours.append(seconds / 3600)
        except Exception:
            pass
        day += datetime.timedelta(days=1)

    try:
        activities = client.get_activities(0, 20)
        activities = [
            a
            for a in activities
            if a.get("startTimeLocal", "") >= start.isoformat()
        ]
    except Exception:
        activities = []

    return {
        "start": start.isoformat(),
        "end": today.isoformat(),
        "steps_total": steps_total,
        "steps_avg": round(steps_total / 7),
        "sleep_avg_hours": round(sum(sleep_hours) / len(sleep_hours), 1)
        if sleep_hours
        else None,
        "resting_hr_avg": round(sum(resting_hr) / len(resting_hr))
        if resting_hr
        else None,
        "num_activities": len(activities),
        "activities": [
            {
                "nombre": a.get("activityName"),
                "tipo": a.get("activityType", {}).get("typeKey"),
                "distancia_km": round((a.get("distance") or 0) / 1000, 2),
                "duracion_min": round((a.get("duration") or 0) / 60),
            }
            for a in activities
        ],
    }


def build_email_body(data: dict) -> str:
    lines = [
        f"Resumen semanal Garmin ({data['start']} a {data['end']})",
        "",
        f"Pasos totales: {data['steps_total']}",
        f"Media diaria de pasos: {data['steps_avg']}",
    ]
    if data["sleep_avg_hours"] is not None:
        lines.append(f"Media de sueño: {data['sleep_avg_hours']} h/noche")
    if data["resting_hr_avg"] is not None:
        lines.append(
            f"Frecuencia cardiaca en reposo media: {data['resting_hr_avg']} ppm"
        )
    lines.append(f"Entrenamientos registrados: {data['num_activities']}")
    lines.append("")
    for a in data["activities"]:
        lines.append(
            f"  - {a['nombre']} ({a['tipo']}): {a['distancia_km']} km, "
            f"{a['duracion_min']} min"
        )
    return "\n".join(lines)


def send_email(subject: str, body: str):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)


if __name__ == "__main__":
    data = get_week_data()
    body = build_email_body(data)
    send_email("Tu resumen semanal de Garmin", body)
    print("Email enviado correctamente.")
