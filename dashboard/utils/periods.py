from datetime import datetime, time
from django.utils import timezone

def get_period_dates(period: str):
    today = timezone.now().date()

    if period == "day":
        start = datetime.combine(today, time.min)
        end = datetime.combine(today, time.max)

    elif period == "month":
        start = datetime.combine(today.replace(day=1), time.min)
        end = datetime.combine(today, time.max)

    elif period == "year":
        start = datetime.combine(today.replace(month=1, day=1), time.min)
        end = datetime.combine(today, time.max)

    else:
        raise ValueError(f"Période invalide : {period}")

    return (
        timezone.make_aware(start),
        timezone.make_aware(end),
    )
