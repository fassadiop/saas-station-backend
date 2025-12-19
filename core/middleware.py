class TenantMiddleware:
    """
    Assigne request.tenant = request.user.tenant si user authentifié.
    Pour une logique plus avancée (sous-domaine, header X-Tenant-ID), adaptez.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            request.tenant = getattr(user, "tenant", None)
        return self.get_response(request)
