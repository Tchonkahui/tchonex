from django.shortcuts import render


def home(request):
    """
    Page d'accueil publique de TCHONEX.
    """
    return render(request, 'core/home.html')
