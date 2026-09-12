from stations.models import Notification

def create_notification(
    tenant_id,
    station_id,
    type,
    message,
    role_cible,
    lien=None
):
    # Anti-duplication
    exists = Notification.objects.filter(
        type=type,
        station_id=station_id,
        lien=lien,
        lu=False
    ).exists()

    if exists:
        return

    Notification.objects.create(
        tenant_id=tenant_id,
        station_id=station_id,
        type=type,
        message=message,
        role_cible=role_cible,
        lien=lien,
    )