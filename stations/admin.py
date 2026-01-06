from django.contrib import admin
from .models import RelaisEquipe


@admin.register(RelaisEquipe)
class RelaisEquipeAdmin(admin.ModelAdmin):
    list_display = (
        "station",
        "debut_relais",
        "fin_relais",
        "status",
        "created_by",
    )
    list_filter = ("station", "status")
    search_fields = ("equipe_sortante", "equipe_entrante")
