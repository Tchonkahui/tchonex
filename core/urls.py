from django.urls import path

from . import views

urlpatterns = [
    # Pages publiques
    path('', views.home, name='home'),
    path('inscription/', views.inscription, name='inscription'),
    path('connexion/', views.ConnexionView.as_view(), name='connexion'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),

    # Parcours : entreprise puis modules
    path('entreprise/creer/', views.entreprise_creer, name='entreprise_creer'),
    path('modules/', views.modules, name='modules'),

    # Espace de travail
    path('tableau-de-bord/', views.tableau_de_bord, name='tableau_de_bord'),
    path('parametres/', views.parametres, name='parametres'),

    # Module Clients
    path('clients/', views.clients, name='clients'),
    path('clients/nouveau/', views.client_form, name='client_nouveau'),
    path('clients/<int:pk>/modifier/', views.client_form, name='client_modifier'),
    path('clients/<int:pk>/supprimer/', views.client_supprimer, name='client_supprimer'),

    # Module Produits & Stock
    path('produits/', views.produits, name='produits'),
    path('produits/nouveau/', views.produit_form, name='produit_nouveau'),
    path('produits/<int:pk>/modifier/', views.produit_form, name='produit_modifier'),
    path('produits/<int:pk>/supprimer/', views.produit_supprimer, name='produit_supprimer'),

    # Module Ventes
    path('ventes/', views.ventes, name='ventes'),
    path('ventes/nouveau/', views.devis_form, name='devis_nouveau'),
    path('ventes/<int:pk>/', views.devis_detail, name='devis_detail'),
    path('ventes/<int:pk>/modifier/', views.devis_form, name='devis_modifier'),
    path('ventes/<int:pk>/confirmer/', views.devis_confirmer, name='devis_confirmer'),
    path('ventes/<int:pk>/supprimer/', views.devis_supprimer, name='devis_supprimer'),
]
