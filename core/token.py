# core/token.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # claims custom
        if getattr(user, "tenant", None):
            token['tenant_id'] = str(user.tenant.id)
        token['role'] = getattr(user, "role", None)
        token['username'] = user.username
        return token
