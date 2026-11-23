from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.forms import inlineformset_factory

from .models import Client, Contact, Devis, Entreprise, Evenement, LigneDevis, Produit

User = get_user_model()


class InscriptionForm(forms.Form):
    email = forms.EmailField(label='Adresse e-mail')
    mot_de_passe = forms.CharField(label='Mot de passe', widget=forms.PasswordInput)
    confirmation = forms.CharField(label='Confirmer le mot de passe', widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError('Un compte existe déjà avec cette adresse e-mail.')
        return email

    def clean(self):
        data = super().clean()
        mdp, conf = data.get('mot_de_passe'), data.get('confirmation')
        if mdp and conf and mdp != conf:
            self.add_error('confirmation', 'Les deux mots de passe ne sont pas identiques.')
        elif mdp:
            try:
                validate_password(mdp)
            except forms.ValidationError as erreur:
                self.add_error('mot_de_passe', erreur)
        return data

    def enregistrer(self):
        email = self.cleaned_data['email']
        return User.objects.create_user(
            username=email, email=email, password=self.cleaned_data['mot_de_passe'])


class ConnexionForm(AuthenticationForm):
    username = forms.CharField(label='Adresse e-mail')

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ['nom', 'secteur', 'adresse', 'telephone']
        widgets = {
            'secteur': forms.TextInput(attrs={'placeholder': 'Ex. : commerce, restauration, services'}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['nom', 'telephone', 'email', 'adresse']


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'prix', 'quantite_stock']


class DevisForm(forms.ModelForm):
    class Meta:
        model = Devis
        fields = ['client']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Isolation : on ne propose que les clients de SON entreprise
        self.fields['client'].queryset = Client.objects.filter(entreprise=entreprise)
        self.fields['client'].empty_label = 'Choisir un client…'


class LigneDevisForm(forms.ModelForm):
    class Meta:
        model = LigneDevis
        fields = ['produit', 'quantite']

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Isolation : on ne propose que les produits de SON entreprise
        self.fields['produit'].queryset = Produit.objects.filter(entreprise=entreprise)
        self.fields['produit'].empty_label = 'Choisir un produit…'
        self.fields['quantite'].initial = 1
        self.fields['quantite'].min_value = 1
        self.fields['quantite'].widget.attrs['min'] = 1


LigneDevisFormSet = inlineformset_factory(
    Devis, LigneDevis, form=LigneDevisForm, extra=1, can_delete=True)


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['nom', 'societe', 'fonction', 'categorie', 'telephone', 'email', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}


class EvenementForm(forms.ModelForm):
    class Meta:
        model = Evenement
        fields = ['titre', 'date', 'heure', 'lieu', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'heure': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
