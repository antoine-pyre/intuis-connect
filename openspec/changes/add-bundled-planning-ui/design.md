# Design

## Context

L’éditeur HTML de TheFab21 et sa distribution automatique #24 sont absents. Ils doivent consommer les services actuels étendus plutôt que réintroduire les anciens handlers et capteurs.

Socle : `f92e3e4`, 334 tests sur HA 2024.6.4 et 2026.10.4. resources/intuis_planning.html et éventuels fichiers UI isolés, module de vue HTTP, __init__.py, manifest, exemples et tests HTTP/JS ; source TheFab21 #17/#22/#24.

## Goals / Non-Goals

**Goals:** Adapter la grille hebdomadaire, les zones, les horaires et la sauvegarde de l’éditeur source. Servir le fichier embarqué à /api/intuis_connect/planning avec gestion de cache/version. Conserver les modes intégré et navigateur autonome, avec configuration explicite et affichage des erreurs.

**Non-Goals:** fusion globale des anciennes branches, modification d’équipements réels pendant les tests, modification implicite des IDs ou suppression de données utilisateur.

## Decisions

1. Conserver l’URL /api/intuis_connect/planning et distribuer les assets dans le composant. Enregistrer la route une seule fois pour plusieurs entrées, sans mélange de données ni duplication au reload ; tests de dernier unload et rechargement.

2. La route peut servir une coque HTML statique sans données ni secrets ; toutes les lectures et commandes passent par l’authentification HA. Aucun proxy de données non authentifié. En iframe utiliser la session HA disponible ; en mode autonome exiger URL et token et traiter les origines sans ouvrir globalement CORS.

3. Ne pas stocker un token durable par défaut : mémoire/session, option explicite Remember pour le stockage local, suppression via déconnexion et absence de token dans URL/logs. Les noms et erreurs issus du cloud sont rendus par textContent ou échappement sûr.

4. Conserver la grille sept jours, transitions multi-jours/minuit, zones et températures 0,5 °C, away/hg, sélection du planning et domicile, avertissement de modifications non enregistrées, rafraîchissement, thème clair/sombre, erreurs et reconnexion bornée jusqu’à 45 secondes.

5. La sauvegarde complète est une commande atomique par planning côté service ; les réglages par pièce utilisent les services confirmés. Si plusieurs requêtes UI sont nécessaires, signaler succès partiel et garder les changements non enregistrés ; ne pas annoncer une transaction globale inexistante.

6. Utiliser ETag lié à la version/contenu, 304 testé, lectures fichier hors event loop et compatibilité iframe Firefox/Chromium. Supprimer code mort et logs de debug source superflus sans supprimer les fonctions utilisateur.

7. Afficher un crédit discret TheFab21 avec liens sources dans l’aide/à propos du planning, en plus du README/CONTRIBUTORS et des descriptions de livraison. Documenter installation dashboard, usage autonome et remplacement facultatif des anciennes copies /config/www.

## Risks / Trade-offs

Les garanties recorder, les sélecteurs et la vue HTTP doivent être validés sur les deux versions HA. La compatibilité cloud réelle et le comportement matériel ne sont pas prouvés par des tests hors ligne. Les changements d’API HA futurs exigent une nouvelle validation. Les modifications externes simultanées de planning ne disposent pas d’un compare-and-swap cloud.

## Migration Plan

1. extend-schedule-editing et attribution ; aucune dépendance au calcul d’énergie ou de coûts.
2. Vérifier les contrats du socle puis implémenter et tester uniquement le lot.
3. Préserver configuration, identifiants, données et défauts des fonctions existantes ; activation des nouvelles fonctions explicite quand applicable.
4. Vérifier crédits, provenance, documentation et matrice avant livraison.
5. Un retour de code ne supprime pas des statistiques déjà confirmées ; ne jamais supprimer des données pour revenir à une version précédente.
