from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


# ---------------------------------------------------------------------------
# Catalogue des modules (défini dans le code, pas dans la base de données)
# ---------------------------------------------------------------------------
CATALOGUE = [
    {
        'code': 'clients', 'nom': 'Clients', 'icone': '👥', 'disponible': True,
        'description': 'Gardez la liste de vos clients : nom, téléphone, e-mail, adresse.',
    },
    {
        'code': 'produits', 'nom': 'Produits & Stock', 'icone': '📦', 'disponible': True,
        'description': 'Suivez vos produits, leurs prix et les quantités en stock.',
    },
    {
        'code': 'ventes', 'nom': 'Ventes', 'icone': '🧾', 'disponible': True,
        'description': 'Créez des devis et confirmez-les. Le stock baisse automatiquement.',
        'depend_de': ['clients', 'produits'],
    },
    {'code': 'rh', 'nom': 'RH', 'icone': '🧑‍💼', 'disponible': False,
     'description': 'Employés, congés et présences.'},
    {'code': 'projets', 'nom': 'Projets', 'icone': '📋', 'disponible': False,
     'description': 'Projets, tâches et échéances.'},
    {'code': 'comptabilite', 'nom': 'Comptabilité', 'icone': '📊', 'disponible': False,
     'description': 'Indicateurs financiers simplifiés.'},
    {'code': 'siteweb', 'nom': 'Site Web', 'icone': '🌐', 'disponible': False,
     'description': 'Une vitrine en ligne pour votre entreprise.'},
]
CODES_DISPONIBLES = [m['code'] for m in CATALOGUE if m['disponible']]
SEUIL_STOCK_BAS = 5


class Entreprise(models.Model):
    """Une entreprise créée dans TCHONEX. Chaque utilisateur en possède une seule."""
    proprietaire = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='entreprise')
    nom = models.CharField('Nom de l’entreprise', max_length=120)
    secteur = models.CharField('Secteur d’activité', max_length=120)
    adresse = models.CharField('Adresse', max_length=200, blank=True)
    telephone = models.CharField('Téléphone', max_length=30, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom

    def codes_modules(self):
        return set(self.modules.values_list('code_module', flat=True))


class ModuleActif(models.Model):
    """Indique qu'une entreprise a activé un module."""
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='modules')
    code_module = models.CharField(max_length=30)

    class Meta:
        unique_together = ('entreprise', 'code_module')

    def __str__(self):
        return f'{self.entreprise} – {self.code_module}'


class Client(models.Model):
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='clients')
    nom = models.CharField(max_length=120)
    telephone = models.CharField('Téléphone', max_length=30, blank=True)
    email = models.EmailField('E-mail', blank=True)
    adresse = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Produit(models.Model):
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='produits')
    nom = models.CharField(max_length=120)
    prix = models.PositiveIntegerField('Prix (FCFA)', validators=[MinValueValidator(0)])
    quantite_stock = models.PositiveIntegerField('Quantité en stock', default=0)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom

    @property
    def stock_bas(self):
        return self.quantite_stock <= SEUIL_STOCK_BAS


class Devis(models.Model):
    BROUILLON = 'brouillon'
    CONFIRME = 'confirme'
    STATUTS = [(BROUILLON, 'Brouillon'), (CONFIRME, 'Confirmé')]

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='devis')
    numero = models.CharField(max_length=20)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='devis')
    date_creation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=STATUTS, default=BROUILLON)
    total = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ['-id']
        unique_together = ('entreprise', 'numero')

    def __str__(self):
        return self.numero

    @staticmethod
    def prochain_numero(entreprise):
        """Numéro DEV-0001, DEV-0002… propre à chaque entreprise."""
        dernier = Devis.objects.filter(entreprise=entreprise).count()
        numero = dernier + 1
        while Devis.objects.filter(entreprise=entreprise, numero=f'DEV-{numero:04d}').exists():
            numero += 1
        return f'DEV-{numero:04d}'

    def recalculer_total(self):
        """Total du devis = somme des montants des lignes (pas de TVA)."""
        self.total = sum(l.montant for l in self.lignes.all())
        self.save(update_fields=['total'])

    @transaction.atomic
    def confirmer(self):
        """
        Confirme le devis : tout ou rien.
        1) vérifie le devis, 2) vérifie le stock, 3) diminue le stock, 4) passe à « Confirmé ».
        """
        devis = Devis.objects.select_for_update().get(pk=self.pk)
        if devis.statut != Devis.BROUILLON:
            raise ValidationError('Ce devis est déjà confirmé.')
        lignes = list(devis.lignes.select_related('produit'))
        if not lignes:
            raise ValidationError('Ajoutez au moins une ligne avant de confirmer le devis.')

        # Regrouper les quantités par produit (un produit peut apparaître sur plusieurs lignes)
        besoins = {}
        for ligne in lignes:
            besoins[ligne.produit_id] = besoins.get(ligne.produit_id, 0) + ligne.quantite

        produits = {p.pk: p for p in Produit.objects.select_for_update().filter(pk__in=besoins)}
        for produit_id, quantite in besoins.items():
            produit = produits[produit_id]
            if produit.quantite_stock < quantite:
                raise ValidationError(
                    f'Stock insuffisant pour le produit « {produit.nom} » '
                    f'(disponible : {produit.quantite_stock}, demandé : {quantite}).')

        for produit_id, quantite in besoins.items():
            produit = produits[produit_id]
            produit.quantite_stock -= quantite
            produit.save(update_fields=['quantite_stock'])

        devis.statut = Devis.CONFIRME
        devis.save(update_fields=['statut'])
        self.statut = Devis.CONFIRME


class LigneDevis(models.Model):
    devis = models.ForeignKey(Devis, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='lignes')
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    prix_unitaire = models.PositiveIntegerField()
    montant = models.PositiveBigIntegerField()

    def save(self, *args, **kwargs):
        if not self.prix_unitaire:
            self.prix_unitaire = self.produit.prix
        self.montant = self.quantite * self.prix_unitaire
        super().save(*args, **kwargs)
