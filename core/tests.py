"""
Tests automatiques de TCHONEX.
Lancer avec :  python manage.py test
Ils vérifient les règles importantes du cahier des charges :
isolation des entreprises, modules activés, calcul des devis, stock.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Client, Devis, Entreprise, LigneDevis, ModuleActif, Produit

User = get_user_model()
SANS_MANIFESTE = override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')


def creer_entreprise(email, nom, modules=('clients', 'produits', 'ventes')):
    utilisateur = User.objects.create_user(username=email, email=email, password='MotDePasse-2026!')
    entreprise = Entreprise.objects.create(proprietaire=utilisateur, nom=nom, secteur='Commerce')
    for code in modules:
        ModuleActif.objects.create(entreprise=entreprise, code_module=code)
    return utilisateur, entreprise


def donnees_devis(client, lignes):
    """Construit les données POST d'un devis avec ses lignes [(produit, quantite), ...]."""
    data = {
        'client': client.pk,
        'lignes-TOTAL_FORMS': len(lignes), 'lignes-INITIAL_FORMS': 0,
        'lignes-MIN_NUM_FORMS': 0, 'lignes-MAX_NUM_FORMS': 1000,
    }
    for i, (produit, quantite) in enumerate(lignes):
        data[f'lignes-{i}-produit'] = produit.pk
        data[f'lignes-{i}-quantite'] = quantite
    return data


@SANS_MANIFESTE
class ParcoursTests(TestCase):
    def test_parcours_complet_inscription_entreprise_modules(self):
        r = self.client.post(reverse('inscription'), {
            'email': 'Landry@Exemple.com', 'mot_de_passe': 'Tchonex-ERP-2026!',
            'confirmation': 'Tchonex-ERP-2026!'})
        self.assertRedirects(r, reverse('entreprise_creer'))
        r = self.client.post(reverse('entreprise_creer'), {'nom': 'Fally Fashion', 'secteur': 'Mode'})
        self.assertRedirects(r, reverse('modules'))
        r = self.client.post(reverse('modules'), {'modules': ['ventes']})
        self.assertRedirects(r, reverse('tableau_de_bord'))
        entreprise = Entreprise.objects.get(nom='Fally Fashion')
        # Dépendance : Ventes active aussi Clients et Produits & Stock
        self.assertEqual(entreprise.codes_modules(), {'clients', 'produits', 'ventes'})
        self.assertEqual(self.client.get(reverse('tableau_de_bord')).status_code, 200)

    def test_mot_de_passe_trop_court_refuse(self):
        r = self.client.post(reverse('inscription'), {
            'email': 'a@b.com', 'mot_de_passe': '123', 'confirmation': '123'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='a@b.com').exists())

    def test_pages_privees_exigent_la_connexion(self):
        for nom in ('tableau_de_bord', 'clients', 'produits', 'ventes', 'modules', 'parametres'):
            self.assertRedirects(self.client.get(reverse(nom)), reverse('connexion'))

    def test_connexion_par_email(self):
        creer_entreprise('boutique@ex.com', 'Boutique')
        ok = self.client.post(reverse('connexion'), {
            'username': 'Boutique@ex.com', 'password': 'MotDePasse-2026!'})
        self.assertRedirects(ok, '/tableau-de-bord/')

    def test_utilisateur_sans_entreprise_renvoye_vers_creation(self):
        User.objects.create_user(username='x@x.com', email='x@x.com', password='MotDePasse-2026!')
        self.client.login(username='x@x.com', password='MotDePasse-2026!')
        self.assertRedirects(self.client.get(reverse('tableau_de_bord')), reverse('entreprise_creer'))

    def test_au_moins_un_module_obligatoire(self):
        u, e = creer_entreprise('m@m.com', 'M', modules=())
        self.client.force_login(u)
        self.assertRedirects(self.client.get(reverse('tableau_de_bord')), reverse('modules'))
        r = self.client.post(reverse('modules'), {})
        self.assertEqual(r.status_code, 200)

    def test_module_non_active_inaccessible(self):
        u, e = creer_entreprise('c@c.com', 'C', modules=('clients',))
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('clients')).status_code, 200)
        self.assertRedirects(self.client.get(reverse('ventes')), reverse('tableau_de_bord'))
        self.assertRedirects(self.client.get(reverse('produits')), reverse('tableau_de_bord'))

    def test_pages_publiques_et_espace_s_affichent(self):
        u, e = creer_entreprise('p@p.com', 'P')
        for nom in ('home', 'inscription', 'connexion'):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200)
        self.client.force_login(u)
        for nom in ('tableau_de_bord', 'parametres', 'modules', 'clients', 'client_nouveau',
                    'produits', 'produit_nouveau', 'ventes', 'devis_nouveau'):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)


@SANS_MANIFESTE
class IsolationTests(TestCase):
    """Règle RG1 : une entreprise ne voit jamais les données d'une autre."""

    def setUp(self):
        self.ua, self.a = creer_entreprise('a@a.com', 'Entreprise A')
        self.ub, self.b = creer_entreprise('b@b.com', 'Entreprise B')
        self.client_a = Client.objects.create(entreprise=self.a, nom='Client secret de A')
        self.produit_a = Produit.objects.create(entreprise=self.a, nom='Produit secret de A', prix=1000, quantite_stock=10)
        self.devis_a = Devis.objects.create(entreprise=self.a, numero='DEV-0001', client=self.client_a)

    def test_listes_isolees(self):
        self.client.force_login(self.ub)
        self.assertNotContains(self.client.get(reverse('clients')), 'Client secret de A')
        self.assertNotContains(self.client.get(reverse('produits')), 'Produit secret de A')
        self.assertNotContains(self.client.get(reverse('ventes')), 'DEV-0001')

    def test_acces_direct_par_adresse_refuse(self):
        self.client.force_login(self.ub)
        self.assertEqual(self.client.get(reverse('client_modifier', args=[self.client_a.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('produit_modifier', args=[self.produit_a.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('devis_detail', args=[self.devis_a.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('client_supprimer', args=[self.client_a.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('devis_confirmer', args=[self.devis_a.pk])).status_code, 404)
        self.assertTrue(Client.objects.filter(pk=self.client_a.pk).exists())

    def test_devis_avec_client_ou_produit_d_une_autre_entreprise_refuse(self):
        self.client.force_login(self.ub)
        client_b = Client.objects.create(entreprise=self.b, nom='Client B')
        produit_b = Produit.objects.create(entreprise=self.b, nom='Produit B', prix=500, quantite_stock=5)
        # client de A
        r = self.client.post(reverse('devis_nouveau'), donnees_devis(self.client_a, [(produit_b, 1)]))
        self.assertEqual(r.status_code, 200)
        # produit de A
        r = self.client.post(reverse('devis_nouveau'), donnees_devis(client_b, [(self.produit_a, 1)]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Devis.objects.filter(entreprise=self.b).count(), 0)

    def test_numerotation_propre_a_chaque_entreprise(self):
        self.client.force_login(self.ub)
        client_b = Client.objects.create(entreprise=self.b, nom='Client B')
        produit_b = Produit.objects.create(entreprise=self.b, nom='Produit B', prix=500, quantite_stock=5)
        self.client.post(reverse('devis_nouveau'), donnees_devis(client_b, [(produit_b, 1)]))
        self.assertEqual(Devis.objects.get(entreprise=self.b).numero, 'DEV-0001')


@SANS_MANIFESTE
class VentesTests(TestCase):
    """Règles RG4 à RG7 : total du devis, stock et confirmation."""

    def setUp(self):
        self.u, self.e = creer_entreprise('v@v.com', 'Fally Fashion')
        self.c = Client.objects.create(entreprise=self.e, nom='DG Landry')
        self.chemise = Produit.objects.create(entreprise=self.e, nom='Chemise homme blanche', prix=12500, quantite_stock=10)
        self.pantalon = Produit.objects.create(entreprise=self.e, nom='Pantalon chino noir', prix=12500, quantite_stock=10)
        self.ceinture = Produit.objects.create(entreprise=self.e, nom='Ceinture cuir', prix=5000, quantite_stock=2)
        self.client.force_login(self.u)

    def creer_devis(self, lignes):
        r = self.client.post(reverse('devis_nouveau'), donnees_devis(self.c, lignes))
        devis = Devis.objects.get(entreprise=self.e)
        self.assertRedirects(r, reverse('devis_detail', args=[devis.pk]))
        return devis

    def test_total_sans_tva(self):
        devis = self.creer_devis([(self.chemise, 1), (self.pantalon, 1), (self.ceinture, 1)])
        self.assertEqual(devis.numero, 'DEV-0001')
        self.assertEqual(devis.total, 30000)          # 12 500 + 12 500 + 5 000, sans TVA
        self.assertEqual(devis.statut, Devis.BROUILLON)
        self.assertEqual(devis.lignes.count(), 3)

    def test_confirmation_diminue_le_stock(self):
        devis = self.creer_devis([(self.chemise, 3), (self.ceinture, 2)])
        r = self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        self.assertRedirects(r, reverse('devis_detail', args=[devis.pk]))
        devis.refresh_from_db(); self.chemise.refresh_from_db(); self.ceinture.refresh_from_db()
        self.assertEqual(devis.statut, Devis.CONFIRME)
        self.assertEqual(self.chemise.quantite_stock, 7)
        self.assertEqual(self.ceinture.quantite_stock, 0)

    def test_stock_insuffisant_rien_ne_change(self):
        # 1 chemise (disponible) + 3 ceintures (2 en stock) : tout doit être refusé
        devis = self.creer_devis([(self.chemise, 1), (self.ceinture, 3)])
        self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        devis.refresh_from_db(); self.chemise.refresh_from_db(); self.ceinture.refresh_from_db()
        self.assertEqual(devis.statut, Devis.BROUILLON)
        self.assertEqual(self.chemise.quantite_stock, 10)   # « tout ou rien »
        self.assertEqual(self.ceinture.quantite_stock, 2)

    def test_meme_produit_sur_deux_lignes_compte_ensemble(self):
        devis = self.creer_devis([(self.ceinture, 2), (self.ceinture, 1)])  # 3 demandées, 2 en stock
        self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        devis.refresh_from_db()
        self.assertEqual(devis.statut, Devis.BROUILLON)

    def test_double_confirmation_ne_diminue_pas_deux_fois(self):
        devis = self.creer_devis([(self.chemise, 4)])
        self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        self.chemise.refresh_from_db()
        self.assertEqual(self.chemise.quantite_stock, 6)

    def test_devis_sans_ligne_refuse(self):
        data = donnees_devis(self.c, [])
        data['lignes-TOTAL_FORMS'] = 1
        r = self.client.post(reverse('devis_nouveau'), data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Devis.objects.count(), 0)

    def test_devis_confirme_non_modifiable_ni_supprimable(self):
        devis = self.creer_devis([(self.chemise, 1)])
        self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        self.assertRedirects(self.client.get(reverse('devis_modifier', args=[devis.pk])),
                             reverse('devis_detail', args=[devis.pk]))
        self.client.post(reverse('devis_supprimer', args=[devis.pk]))
        self.assertTrue(Devis.objects.filter(pk=devis.pk).exists())

    def test_modifier_un_brouillon_recalcule_le_total(self):
        devis = self.creer_devis([(self.chemise, 1)])
        ligne = devis.lignes.get()
        data = {
            'client': self.c.pk,
            'lignes-TOTAL_FORMS': 2, 'lignes-INITIAL_FORMS': 1,
            'lignes-MIN_NUM_FORMS': 0, 'lignes-MAX_NUM_FORMS': 1000,
            'lignes-0-id': ligne.pk, 'lignes-0-devis': devis.pk,
            'lignes-0-produit': self.chemise.pk, 'lignes-0-quantite': 2,
            'lignes-1-produit': self.ceinture.pk, 'lignes-1-quantite': 1,
        }
        self.client.post(reverse('devis_modifier', args=[devis.pk]), data)
        devis.refresh_from_db()
        self.assertEqual(devis.total, 2 * 12500 + 5000)

    def test_client_ou_produit_utilise_dans_un_devis_non_supprimable(self):
        self.creer_devis([(self.chemise, 1)])
        self.client.post(reverse('client_supprimer', args=[self.c.pk]))
        self.client.post(reverse('produit_supprimer', args=[self.chemise.pk]))
        self.assertTrue(Client.objects.filter(pk=self.c.pk).exists())
        self.assertTrue(Produit.objects.filter(pk=self.chemise.pk).exists())

    def test_tableau_de_bord_chiffres(self):
        devis = self.creer_devis([(self.chemise, 1)])
        self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        r = self.client.get(reverse('tableau_de_bord'))
        self.assertContains(r, '12')
        self.assertContains(r, 'FCFA')


@SANS_MANIFESTE
class ComptabiliteTests(TestCase):
    """Module Comptabilité : indicateurs simplifiés, isolés par entreprise."""

    def setUp(self):
        self.u, self.e = creer_entreprise('c@compta.com', 'Fally Fashion',
                                          modules=('clients', 'produits', 'ventes', 'comptabilite'))
        self.c = Client.objects.create(entreprise=self.e, nom='DG Landry')
        self.p = Produit.objects.create(entreprise=self.e, nom='Chemise', prix=12500, quantite_stock=10)
        self.client.force_login(self.u)

    def vente(self, quantite, confirmer=True):
        self.client.post(reverse('devis_nouveau'), donnees_devis(self.c, [(self.p, quantite)]))
        devis = Devis.objects.filter(entreprise=self.e).order_by('-id').first()
        if confirmer:
            self.client.post(reverse('devis_confirmer', args=[devis.pk]))
        return devis

    def test_module_choisi_active_ses_dependances(self):
        u, e = creer_entreprise('d@d.com', 'D', modules=())
        self.client.force_login(u)
        self.client.post(reverse('modules'), {'modules': ['comptabilite']})
        self.assertEqual(e.codes_modules(), {'clients', 'produits', 'ventes', 'comptabilite'})

    def test_indicateurs_corrects(self):
        self.vente(2)                      # 25 000 confirmés, stock 10 -> 8
        self.vente(1)                      # 12 500 confirmés, stock 8 -> 7
        self.vente(3, confirmer=False)     # 37 500 en brouillon
        r = self.client.get(reverse('comptabilite'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['chiffre_affaires'], 37500)
        self.assertEqual(r.context['nb_ventes'], 2)
        self.assertEqual(r.context['panier_moyen'], 18750)
        self.assertEqual(r.context['brouillons_total'], 37500)
        self.assertEqual(r.context['valeur_stock'], 7 * 12500)
        self.assertEqual(len(r.context['par_mois']), 1)
        self.assertEqual(r.context['meilleurs_produits'][0]['quantite'], 3)

    def test_page_vide_sans_ventes(self):
        r = self.client.get(reverse('comptabilite'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Aucune vente confirmée')

    def test_isolation_des_chiffres(self):
        self.vente(2)
        ub, b = creer_entreprise('b@compta.com', 'Autre', modules=('clients', 'produits', 'ventes', 'comptabilite'))
        self.client.force_login(ub)
        r = self.client.get(reverse('comptabilite'))
        self.assertEqual(r.context['chiffre_affaires'], 0)
        self.assertEqual(r.context['valeur_stock'], 0)
        self.assertNotContains(r, 'DG Landry')

    def test_module_inactif_inaccessible(self):
        u, e = creer_entreprise('n@n.com', 'N', modules=('clients', 'produits', 'ventes'))
        self.client.force_login(u)
        self.assertRedirects(self.client.get(reverse('comptabilite')), reverse('tableau_de_bord'))
