import calendar as calendrier_python
import datetime
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (ClientForm, ConnexionForm, ContactForm, DevisForm, EntrepriseForm, EvenementForm,
                    InscriptionForm, LigneDevisFormSet, ProduitForm)
from .models import (CATALOGUE, CODES_DISPONIBLES, SEUIL_STOCK_BAS, Client, Contact, Devis, Entreprise,
                     Evenement, LigneDevis, ModuleActif, Produit)


# ---------------------------------------------------------------------------
# Outils communs
# ---------------------------------------------------------------------------
def entreprise_requise(view):
    """
    Garde-fou du parcours : l'utilisateur doit être connecté, avoir une entreprise
    et au moins un module actif. Il pose `request.entreprise` et `request.modules`.
    Toutes les pages privées lisent les données à partir de `request.entreprise` :
    c'est ce qui isole les entreprises les unes des autres.
    """
    @wraps(view)
    def enveloppe(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('connexion')
        entreprise = Entreprise.objects.filter(proprietaire=request.user).first()
        if entreprise is None:
            return redirect('entreprise_creer')
        request.entreprise = entreprise
        request.modules = entreprise.codes_modules()
        if not request.modules and not getattr(view, 'sans_module', False):
            return redirect('modules')
        return view(request, *args, **kwargs)
    return enveloppe


def sans_module(view):
    """Marque une vue qui reste accessible même si aucun module n'est encore activé."""
    view.sans_module = True
    return view


def module_requis(code):
    """Refuse l'accès à un module que l'entreprise n'a pas activé."""
    def decorateur(view):
        @wraps(view)
        def enveloppe(request, *args, **kwargs):
            if code not in request.modules:
                messages.error(request, 'Ce module n’est pas activé pour votre entreprise.')
                return redirect('tableau_de_bord')
            return view(request, *args, **kwargs)
        return enveloppe
    return decorateur


ENTREES_MENU = {
    'tableau': 'tableau', 'parametres': 'parametres', 'client': 'clients', 'clients': 'clients',
    'produit': 'produits', 'produits': 'produits', 'devis': 'ventes', 'ventes': 'ventes', 'comptabilite': 'comptabilite',
    'calendrier': 'calendrier', 'evenement': 'calendrier', 'contacts': 'contacts', 'contact': 'contacts',
}


def page(request, gabarit, contexte=None, statut=200):
    """Rend une page privée avec le menu (modules activés) et l'entreprise."""
    contexte = dict(contexte or {})
    nom_url = request.resolver_match.url_name.split('_')[0] if request.resolver_match else ''
    contexte['actif'] = ENTREES_MENU.get(nom_url, '')
    contexte['entreprise'] = request.entreprise
    contexte['menu_modules'] = [m for m in CATALOGUE if m['code'] in request.modules]
    return render(request, gabarit, contexte, status=statut)


# ---------------------------------------------------------------------------
# Pages publiques : accueil, inscription, connexion
# ---------------------------------------------------------------------------
def home(request):
    if request.user.is_authenticated:
        return redirect('tableau_de_bord')
    return render(request, 'core/home.html', {'catalogue': CATALOGUE})


def inscription(request):
    if request.user.is_authenticated:
        return redirect('tableau_de_bord')
    form = InscriptionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        utilisateur = form.enregistrer()
        login(request, utilisateur)
        messages.success(request, 'Votre compte est créé. Créez maintenant votre entreprise.')
        return redirect('entreprise_creer')
    return render(request, 'core/inscription.html', {'form': form})


class ConnexionView(LoginView):
    template_name = 'core/connexion.html'
    authentication_form = ConnexionForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return '/tableau-de-bord/'


@require_POST
def deconnexion(request):
    logout(request)
    return redirect('home')


# ---------------------------------------------------------------------------
# Parcours : création d'entreprise puis choix des modules
# ---------------------------------------------------------------------------
def entreprise_creer(request):
    if not request.user.is_authenticated:
        return redirect('connexion')
    if Entreprise.objects.filter(proprietaire=request.user).exists():
        return redirect('tableau_de_bord')
    form = EntrepriseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entreprise = form.save(commit=False)
        entreprise.proprietaire = request.user
        entreprise.save()
        messages.success(request, 'Entreprise créée. Choisissez maintenant vos modules.')
        return redirect('modules')
    return render(request, 'core/entreprise_creer.html', {'form': form})


@entreprise_requise
@sans_module
def modules(request):
    """Catalogue de modules : sélection, récapitulatif et validation."""
    actifs = request.modules
    if request.method == 'POST':
        choisis = {c for c in request.POST.getlist('modules') if c in CODES_DISPONIBLES}
        # Dépendance : Ventes a besoin de Clients et de Produits & Stock
        for module in CATALOGUE:
            if module['code'] in choisis:
                choisis.update(module.get('depend_de', []))
        if not choisis:
            messages.error(request, 'Choisissez au moins un module pour continuer.')
        else:
            with transaction.atomic():
                ModuleActif.objects.filter(entreprise=request.entreprise).exclude(
                    code_module__in=choisis).delete()
                for code in choisis:
                    ModuleActif.objects.get_or_create(
                        entreprise=request.entreprise, code_module=code)
            messages.success(request, 'Vos modules sont enregistrés.')
            return redirect('tableau_de_bord')
    premiere_fois = not actifs
    return render(request, 'core/modules.html', {
        'entreprise': request.entreprise,
        'catalogue': CATALOGUE,
        'actifs': actifs,
        'premiere_fois': premiere_fois,
        'menu_modules': [m for m in CATALOGUE if m['code'] in actifs],
    })


# ---------------------------------------------------------------------------
# Tableau de bord et paramètres
# ---------------------------------------------------------------------------
@entreprise_requise
def tableau_de_bord(request):
    e, actifs = request.entreprise, request.modules
    cartes = []
    if 'clients' in actifs:
        cartes.append({'titre': 'Clients', 'valeur': e.clients.count(), 'url': 'clients',
                       'texte': 'clients enregistrés', 'icone': '👥'})
    if 'produits' in actifs:
        bas = e.produits.filter(quantite_stock__lte=SEUIL_STOCK_BAS).count()
        cartes.append({'titre': 'Produits & Stock', 'valeur': e.produits.count(), 'url': 'produits',
                       'texte': f'produits, dont {bas} en stock bas', 'icone': '📦'})
    if 'ventes' in actifs:
        stats = e.devis.aggregate(
            nb=Count('id'),
            confirmes=Count('id', filter=Q(statut=Devis.CONFIRME)),
            total=Sum('total', filter=Q(statut=Devis.CONFIRME)))
        cartes.append({'titre': 'Devis', 'valeur': stats['nb'], 'url': 'ventes',
                       'texte': f"devis, dont {stats['confirmes']} confirmés", 'icone': '🧾'})
        cartes.append({'titre': 'Ventes confirmées', 'valeur': f"{(stats['total'] or 0):,}".replace(',', ' ') + ' FCFA',
                       'url': 'ventes', 'texte': 'total des devis confirmés', 'icone': '💰'})
    if 'comptabilite' in actifs:
        valeur_stock = e.produits.aggregate(v=Sum(F('prix') * F('quantite_stock')))['v'] or 0
        cartes.append({'titre': 'Comptabilité', 'valeur': f"{valeur_stock:,}".replace(',', ' ') + ' FCFA',
                       'url': 'comptabilite', 'texte': 'valeur du stock', 'icone': '📊'})
    if 'calendrier' in actifs:
        a_venir = e.evenements.filter(date__gte=timezone.localdate()).count()
        cartes.append({'titre': 'Calendrier', 'valeur': a_venir, 'url': 'calendrier',
                       'texte': 'événements à venir', 'icone': '📅'})
    if 'contacts' in actifs:
        cartes.append({'titre': 'Contacts', 'valeur': e.contacts.count(), 'url': 'contacts',
                       'texte': 'contacts dans l’annuaire', 'icone': '📇'})
    derniers = e.devis.select_related('client')[:5] if 'ventes' in actifs else []
    return page(request, 'core/tableau_de_bord.html', {
        'cartes': cartes, 'derniers_devis': derniers, 'avec_ventes': 'ventes' in actifs})


@entreprise_requise
def parametres(request):
    return page(request, 'core/parametres.html', {
        'modules_actifs': [m for m in CATALOGUE if m['code'] in request.modules]})


# ---------------------------------------------------------------------------
# Module Clients
# ---------------------------------------------------------------------------
@entreprise_requise
@module_requis('clients')
def clients(request):
    q = request.GET.get('q', '').strip()
    liste = request.entreprise.clients.all()
    if q:
        liste = liste.filter(Q(nom__icontains=q) | Q(telephone__icontains=q) | Q(email__icontains=q))
    return page(request, 'core/clients_liste.html', {'clients': liste, 'q': q})


@entreprise_requise
@module_requis('clients')
def client_form(request, pk=None):
    client = get_object_or_404(Client, pk=pk, entreprise=request.entreprise) if pk else None
    form = ClientForm(request.POST or None, instance=client)
    if request.method == 'POST' and form.is_valid():
        objet = form.save(commit=False)
        objet.entreprise = request.entreprise
        objet.save()
        messages.success(request, 'Client enregistré.')
        return redirect('clients')
    return page(request, 'core/formulaire.html', {
        'form': form, 'titre': 'Modifier le client' if client else 'Nouveau client',
        'retour': 'clients', 'bouton': 'Enregistrer le client'})


@entreprise_requise
@module_requis('clients')
@require_POST
def client_supprimer(request, pk):
    client = get_object_or_404(Client, pk=pk, entreprise=request.entreprise)
    try:
        client.delete()
        messages.success(request, 'Client supprimé.')
    except ProtectedError:
        messages.error(request, 'Ce client apparaît dans un devis : impossible de le supprimer.')
    return redirect('clients')


# ---------------------------------------------------------------------------
# Module Produits & Stock
# ---------------------------------------------------------------------------
@entreprise_requise
@module_requis('produits')
def produits(request):
    q = request.GET.get('q', '').strip()
    liste = request.entreprise.produits.all()
    if q:
        liste = liste.filter(nom__icontains=q)
    return page(request, 'core/produits_liste.html', {
        'produits': liste, 'q': q, 'seuil': SEUIL_STOCK_BAS})


@entreprise_requise
@module_requis('produits')
def produit_form(request, pk=None):
    produit = get_object_or_404(Produit, pk=pk, entreprise=request.entreprise) if pk else None
    form = ProduitForm(request.POST or None, instance=produit)
    if request.method == 'POST' and form.is_valid():
        objet = form.save(commit=False)
        objet.entreprise = request.entreprise
        objet.save()
        messages.success(request, 'Produit enregistré.')
        return redirect('produits')
    return page(request, 'core/formulaire.html', {
        'form': form, 'titre': 'Modifier le produit' if produit else 'Nouveau produit',
        'retour': 'produits', 'bouton': 'Enregistrer le produit'})


@entreprise_requise
@module_requis('produits')
@require_POST
def produit_supprimer(request, pk):
    produit = get_object_or_404(Produit, pk=pk, entreprise=request.entreprise)
    try:
        produit.delete()
        messages.success(request, 'Produit supprimé.')
    except ProtectedError:
        messages.error(request, 'Ce produit apparaît dans un devis : impossible de le supprimer.')
    return redirect('produits')


# ---------------------------------------------------------------------------
# Module Ventes (devis)
# ---------------------------------------------------------------------------
@entreprise_requise
@module_requis('ventes')
def ventes(request):
    liste = request.entreprise.devis.select_related('client')
    return page(request, 'core/devis_liste.html', {'devis_liste': liste})


@entreprise_requise
@module_requis('ventes')
def devis_form(request, pk=None):
    e = request.entreprise
    devis = get_object_or_404(Devis, pk=pk, entreprise=e) if pk else None
    if devis and devis.statut == Devis.CONFIRME:
        messages.error(request, 'Un devis confirmé ne peut plus être modifié.')
        return redirect('devis_detail', pk=devis.pk)

    form = DevisForm(request.POST or None, instance=devis, entreprise=e)
    lignes = LigneDevisFormSet(request.POST or None, instance=devis, form_kwargs={'entreprise': e})

    if request.method == 'POST' and form.is_valid() and lignes.is_valid():
        actives = [f for f in lignes.forms
                   if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if not actives:
            messages.error(request, 'Ajoutez au moins une ligne au devis.')
        else:
            with transaction.atomic():
                objet = form.save(commit=False)
                objet.entreprise = e
                if devis is None:
                    objet.numero = Devis.prochain_numero(e)
                objet.save()
                lignes.instance = objet
                for ligne_form in lignes.forms:
                    if not ligne_form.cleaned_data:
                        continue
                    if ligne_form.cleaned_data.get('DELETE'):
                        if ligne_form.instance.pk:
                            ligne_form.instance.delete()
                        continue
                    ligne = ligne_form.save(commit=False)
                    ligne.devis = objet
                    # Le prix unitaire est copié du produit au moment de l'enregistrement
                    ligne.prix_unitaire = ligne.produit.prix
                    ligne.save()
                objet.recalculer_total()
            messages.success(request, f'Devis {objet.numero} enregistré.')
            return redirect('devis_detail', pk=objet.pk)

    produits_prix = {p.pk: p.prix for p in e.produits.all()}
    return page(request, 'core/devis_form.html', {
        'form': form, 'lignes': lignes, 'devis': devis, 'produits_prix': produits_prix,
        'titre': f'Modifier le devis {devis.numero}' if devis else 'Nouveau devis'})


@entreprise_requise
@module_requis('ventes')
def devis_detail(request, pk):
    devis = get_object_or_404(Devis.objects.select_related('client'), pk=pk, entreprise=request.entreprise)
    return page(request, 'core/devis_detail.html', {
        'devis': devis, 'lignes': devis.lignes.select_related('produit')})


@entreprise_requise
@module_requis('ventes')
@require_POST
def devis_confirmer(request, pk):
    devis = get_object_or_404(Devis, pk=pk, entreprise=request.entreprise)
    try:
        devis.confirmer()
        messages.success(request, f'Devis {devis.numero} confirmé. Le stock a été mis à jour.')
    except ValidationError as erreur:
        messages.error(request, ' '.join(erreur.messages))
    return redirect('devis_detail', pk=devis.pk)


@entreprise_requise
@module_requis('ventes')
@require_POST
def devis_supprimer(request, pk):
    devis = get_object_or_404(Devis, pk=pk, entreprise=request.entreprise)
    if devis.statut == Devis.CONFIRME:
        messages.error(request, 'Un devis confirmé ne peut pas être supprimé.')
        return redirect('devis_detail', pk=devis.pk)
    devis.delete()
    messages.success(request, 'Devis supprimé.')
    return redirect('ventes')


# ---------------------------------------------------------------------------
# Module Comptabilité : indicateurs financiers simplifiés (lecture seule)
# ---------------------------------------------------------------------------
@entreprise_requise
@module_requis('comptabilite')
def comptabilite(request):
    """
    Indicateurs calculés à partir des données existantes. Ce module n'ajoute aucune table :
    il lit les devis confirmés (chiffre d'affaires) et les produits (valeur du stock).
    Ce n'est PAS une comptabilité légale (pas de plan comptable ni d'écritures).
    """
    e = request.entreprise
    confirmes = e.devis.filter(statut=Devis.CONFIRME)
    synthese = confirmes.aggregate(ca=Sum('total'), nb=Count('id'))
    chiffre_affaires = synthese['ca'] or 0
    nb_ventes = synthese['nb'] or 0
    panier_moyen = chiffre_affaires // nb_ventes if nb_ventes else 0
    brouillons = e.devis.filter(statut=Devis.BROUILLON).aggregate(t=Sum('total'), nb=Count('id'))
    valeur_stock = e.produits.aggregate(v=Sum(F('prix') * F('quantite_stock')))['v'] or 0

    par_mois = list(confirmes.annotate(mois=TruncMonth('date_creation'))
                    .values('mois').annotate(total=Sum('total'), nb=Count('id')).order_by('mois'))[-6:]
    maximum = max([m['total'] for m in par_mois], default=0)
    for m in par_mois:
        m['pourcentage'] = round(m['total'] * 100 / maximum) if maximum else 0

    meilleurs_clients = (confirmes.values('client__nom')
                         .annotate(total=Sum('total'), nb=Count('id')).order_by('-total')[:5])
    meilleurs_produits = (LigneDevis.objects.filter(devis__entreprise=e, devis__statut=Devis.CONFIRME)
                          .values('produit__nom').annotate(quantite=Sum('quantite'), total=Sum('montant'))
                          .order_by('-total')[:5])

    return page(request, 'core/comptabilite.html', {
        'chiffre_affaires': chiffre_affaires, 'nb_ventes': nb_ventes, 'panier_moyen': panier_moyen,
        'brouillons_total': brouillons['t'] or 0, 'brouillons_nb': brouillons['nb'] or 0,
        'valeur_stock': valeur_stock, 'par_mois': par_mois,
        'meilleurs_clients': meilleurs_clients, 'meilleurs_produits': meilleurs_produits})


# ---------------------------------------------------------------------------
# Module Calendrier : agenda mensuel
# ---------------------------------------------------------------------------
def _mois_demande(texte):
    """Lit « 2026-11 » dans l'adresse ; en cas d'erreur, on prend le mois en cours."""
    try:
        annee, mois = texte.split('-')
        return datetime.date(int(annee), int(mois), 1)
    except (ValueError, AttributeError):
        return timezone.localdate().replace(day=1)


@entreprise_requise
@module_requis('calendrier')
def calendrier(request):
    e = request.entreprise
    debut = _mois_demande(request.GET.get('mois'))
    precedent = (debut - datetime.timedelta(days=1)).replace(day=1)
    suivant = (debut + datetime.timedelta(days=32)).replace(day=1)
    semaines_dates = calendrier_python.Calendar(firstweekday=0).monthdatescalendar(debut.year, debut.month)
    premier, dernier = semaines_dates[0][0], semaines_dates[-1][-1]

    par_jour = {}
    for ev in e.evenements.filter(date__range=(premier, dernier)):
        par_jour.setdefault(ev.date, []).append(ev)

    aujourdhui = timezone.localdate()
    semaines = [[{'date': j, 'hors_mois': j.month != debut.month, 'aujourdhui': j == aujourdhui,
                  'evenements': par_jour.get(j, [])} for j in semaine] for semaine in semaines_dates]
    prochains = e.evenements.filter(date__gte=aujourdhui)[:6]
    return page(request, 'core/calendrier.html', {
        'debut': debut, 'precedent': precedent.strftime('%Y-%m'), 'suivant': suivant.strftime('%Y-%m'),
        'semaines': semaines, 'jours': ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'],
        'prochains': prochains})


@entreprise_requise
@module_requis('calendrier')
def evenement_form(request, pk=None):
    evenement = get_object_or_404(Evenement, pk=pk, entreprise=request.entreprise) if pk else None
    initial = {}
    if evenement is None and request.GET.get('date'):
        initial['date'] = request.GET['date']
    form = EvenementForm(request.POST or None, instance=evenement, initial=initial)
    if request.method == 'POST' and form.is_valid():
        objet = form.save(commit=False)
        objet.entreprise = request.entreprise
        objet.save()
        messages.success(request, 'Événement enregistré.')
        return redirect(f"{reverse('calendrier')}?mois={objet.date.strftime('%Y-%m')}")
    return page(request, 'core/formulaire.html', {
        'form': form, 'titre': 'Modifier l’événement' if evenement else 'Nouvel événement',
        'retour': 'calendrier', 'bouton': 'Enregistrer l’événement',
        'supprimer_url': reverse('evenement_supprimer', args=[evenement.pk]) if evenement else None})


@entreprise_requise
@module_requis('calendrier')
@require_POST
def evenement_supprimer(request, pk):
    evenement = get_object_or_404(Evenement, pk=pk, entreprise=request.entreprise)
    evenement.delete()
    messages.success(request, 'Événement supprimé.')
    return redirect('calendrier')


# ---------------------------------------------------------------------------
# Module Contacts : annuaire
# ---------------------------------------------------------------------------
@entreprise_requise
@module_requis('contacts')
def contacts(request):
    q = request.GET.get('q', '').strip()
    categorie = request.GET.get('categorie', '')
    liste = request.entreprise.contacts.all()
    if q:
        liste = liste.filter(Q(nom__icontains=q) | Q(societe__icontains=q) | Q(telephone__icontains=q)
                             | Q(email__icontains=q))
    if categorie in dict(Contact.CATEGORIES):
        liste = liste.filter(categorie=categorie)
    else:
        categorie = ''
    return page(request, 'core/contacts_liste.html', {
        'contacts': liste, 'q': q, 'categorie': categorie, 'categories': Contact.CATEGORIES})


@entreprise_requise
@module_requis('contacts')
def contact_form(request, pk=None):
    contact = get_object_or_404(Contact, pk=pk, entreprise=request.entreprise) if pk else None
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == 'POST' and form.is_valid():
        objet = form.save(commit=False)
        objet.entreprise = request.entreprise
        objet.save()
        messages.success(request, 'Contact enregistré.')
        return redirect('contacts')
    return page(request, 'core/formulaire.html', {
        'form': form, 'titre': 'Modifier le contact' if contact else 'Nouveau contact',
        'retour': 'contacts', 'bouton': 'Enregistrer le contact'})


@entreprise_requise
@module_requis('contacts')
@require_POST
def contact_supprimer(request, pk):
    contact = get_object_or_404(Contact, pk=pk, entreprise=request.entreprise)
    contact.delete()
    messages.success(request, 'Contact supprimé.')
    return redirect('contacts')
