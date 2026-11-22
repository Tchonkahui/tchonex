from django.contrib import admin

from .models import Client, Devis, Entreprise, LigneDevis, ModuleActif, Produit


class LigneDevisInline(admin.TabularInline):
    model = LigneDevis
    extra = 0


@admin.register(Devis)
class DevisAdmin(admin.ModelAdmin):
    list_display = ('numero', 'entreprise', 'client', 'statut', 'total')
    inlines = [LigneDevisInline]


admin.site.register(Entreprise)
admin.site.register(ModuleActif)
admin.site.register(Client)
admin.site.register(Produit)
