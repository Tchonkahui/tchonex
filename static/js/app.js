/* TCHONEX — petits comportements de l'interface (aucune bibliothèque externe) */
document.addEventListener('DOMContentLoaded', function () {

  /* 1) Confirmation avant une action sensible (suppression, confirmation de devis) */
  document.querySelectorAll('form[data-confirmer]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (!window.confirm(form.dataset.confirmer)) { event.preventDefault(); }
    });
  });

  /* 2) Choix des modules : récapitulatif en direct et dépendance de Ventes */
  var selection = document.getElementById('selection-modules');
  if (selection) {
    var cartes = Array.prototype.slice.call(selection.querySelectorAll('label.module'));
    var liste = document.getElementById('liste-choix');
    var compteur = document.getElementById('compteur');
    var vide = document.getElementById('vide-choix');
    var valider = document.getElementById('valider-modules');
    var parCode = {};
    cartes.forEach(function (c) { parCode[c.dataset.code] = c; });

    var appliquerDependances = function () {
      var requis = {};
      cartes.forEach(function (c) {
        var cb = c.querySelector('input');
        if (cb.checked && c.dataset.depend) {
          c.dataset.depend.split(',').forEach(function (code) { if (code) { requis[code] = true; } });
        }
      });
      Object.keys(requis).forEach(function (code) {
        var cible = parCode[code];
        if (cible) { cible.querySelector('input').checked = true; }
      });
      return requis;
    };

    var rafraichir = function () {
      var requis = appliquerDependances();
      liste.innerHTML = '';
      var n = 0;
      cartes.forEach(function (c) {
        var cb = c.querySelector('input');
        if (!cb.checked) { return; }
        n += 1;
        var li = document.createElement('li');
        li.textContent = c.dataset.nom;
        if (requis[c.dataset.code]) {
          var petit = document.createElement('small');
          petit.textContent = 'Nécessaire pour un autre module choisi';
          li.appendChild(petit);
        }
        liste.appendChild(li);
      });
      compteur.textContent = n;
      vide.style.display = n ? 'none' : '';
      valider.disabled = n === 0;
      valider.style.opacity = n ? '1' : '.5';
    };

    selection.addEventListener('change', rafraichir);
    rafraichir();
  }

  /* 3) Devis : lignes dynamiques, prix unitaire et total en direct */
  var corps = document.getElementById('lignes-corps');
  if (corps) {
    var prix = JSON.parse(document.getElementById('prix-produits').textContent || '{}');
    var total = document.getElementById('total-devis');
    var modele = document.getElementById('modele-ligne');
    var compteTotal = document.querySelector('input[name$="-TOTAL_FORMS"]');

    var formater = function (n) {
      return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f') + '\u00a0FCFA';
    };

    var recalculer = function () {
      var somme = 0;
      corps.querySelectorAll('tr.ligne').forEach(function (tr) {
        if (tr.style.display === 'none') { return; }
        var select = tr.querySelector('select');
        var quantite = parseInt(tr.querySelector('input[type=number]').value, 10) || 0;
        var unitaire = select && select.value ? (prix[select.value] || 0) : 0;
        var montant = unitaire * quantite;
        tr.querySelector('.prix-unitaire').textContent = select && select.value ? formater(unitaire) : '—';
        tr.querySelector('.montant-ligne').textContent = select && select.value ? formater(montant) : '—';
        somme += montant;
      });
      total.textContent = formater(somme);
    };

    corps.addEventListener('input', recalculer);
    corps.addEventListener('change', recalculer);

    corps.addEventListener('click', function (event) {
      if (!event.target.classList.contains('retirer-ligne')) { return; }
      var tr = event.target.closest('tr');
      var suppression = tr.querySelector('input[type=checkbox][name$="-DELETE"]');
      var identifiant = tr.querySelector('input[name$="-id"]');
      if (suppression && identifiant && identifiant.value) {
        suppression.checked = true;      /* ligne déjà enregistrée : on la marque à supprimer */
        tr.style.display = 'none';
      } else {
        tr.parentNode.removeChild(tr);   /* nouvelle ligne : on l'enlève simplement */
        /* le formulaire garde son numéro ; Django ignore les lignes vides non modifiées */
      }
      recalculer();
    });

    document.getElementById('ajouter-ligne').addEventListener('click', function () {
      var index = parseInt(compteTotal.value, 10);
      var html = modele.innerHTML.replace(/__prefix__/g, index);
      var conteneur = document.createElement('tbody');
      conteneur.innerHTML = html;
      corps.appendChild(conteneur.firstElementChild || conteneur.querySelector('tr'));
      compteTotal.value = index + 1;
      var quantite = corps.lastElementChild.querySelector('input[type=number]');
      if (quantite && !quantite.value) { quantite.value = 1; }
      recalculer();
    });

    recalculer();
  }
});
