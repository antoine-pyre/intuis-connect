# Intuis Connect 2.2.0 bêta — préparation FP4

Branche de validation préparée sur la 2.1.0 bêta. Publication différée jusqu'au
retour de l'utilisateur de #27 et à la décision de lancer la validation matérielle.
Le push de codex/2.2.0-beta exécute les tests mais ne publie aucune release.

## Support fil pilote — #27

- Détection des pièces de type FP sans température mesurée ni consigne, avec un
  ordre therm_setpoint_fp reconnu. Les FP avec températures gardent le thermostat.
- Presets Comfort, Eco et Hors-gel, sans cadran de température. Heat sélectionne
  Comfort manuel ; Auto reprend le planning ; Off conserve la commande existante.
- Commandes manual avec ordre comfort/away/frost_guard, échéance et aucune
  température numérique. Boost et consignes de température sont refusés pour
  les seules pièces fil pilote.
- Verrou partagé, affichage optimiste borné, acquittement vérifiant l'ordre et
  l'échéance, stockage/rechargement et réapplication des intentions fil pilote.
- Conservation des identifiants d'entités et des anciennes intentions thermiques.

## Robustesse des données partielles

Pièces sans définition ignorées sans crash, températures nulles conservées comme
inconnues, disponibilité climate liée à la présence de la pièce. Une réponse de
statut incomplète ne supprime pas les intentions des pièces encore définies.

## Héritage de la 2.1.0 bêta

Cette branche inclut les correctifs client API 2.0.2, les protections planning de
#31 et les diagnostics/imports de #23. Le périmètre propre au FP4 est séparé dans
les commits et ne modifie pas la release 2.1.0 bêta.

## Crédits et limites

Adaptation de la proposition **apeyrat #27**, de sa mise en œuvre 6eb642b735 et des
corrections de détection 04b79ef755/données partielles 598e635929 par **adrienvsj**.
Les sources exactes sont dans CONTRIBUTORS.md et docs/15-pilot-wire.md.
La détection reste une heuristique au démarrage. Les tests hors ligne ne prouvent
pas l'acceptation des ordres par les radiateurs réels : cette préversion reste
préparée, sans publication ni message envoyé à l'utilisateur de #27.

## Validation locale de la branche préparée

570 tests passent sur HA 2024.6.4 / Python 3.12 et 570 sur HA 2026.10.4 / Python
3.14 ; Ruff et git diff --check passent. Ces résultats ne remplacent pas les
essais FP4 matériels attendus après le retour de l'utilisateur.
