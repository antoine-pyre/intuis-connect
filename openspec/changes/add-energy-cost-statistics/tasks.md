# Tasks

Toutes les tâches d’implémentation restent ouvertes. Les documents présents ne constituent pas leur réalisation.

## 1. Tarifs et configuration

- [ ] 1.1 Définir devise, précision, unité, prix horaire historique, trous et convention du tarif fixe ; documenter l’approximation intra-horaire.
- [ ] 1.2 Implémenter options opt-in et sélecteurs valides, lecture du prix historique et validation des données sur les deux versions HA.

## 2. Statistiques et service

- [ ] 2.1 Ajouter séries/coûts d’affichage sans double writer, transaction acquittée et isolation multi-domicile.
- [ ] 2.2 Implémenter recalculate_cost_history avec ciblage, plages bornées et erreurs visibles ; utiliser une méthode de publication publique.
- [ ] 2.3 Tester tarifs négatifs valides le cas échéant, changements de prix/devise, trous, réimport, échec et annulation sans modifier les kWh.

## 3. Compatibilité et livraison

- [ ] 3.1 Inventorier les anciens schémas coût communautaires et tester noms accentués, renommages, collisions et absence de suppression étrangère.
- [ ] 3.2 Exécuter la matrice, Ruff et tests recorder ; documenter activation et usage tableau énergie, créditer TheFab21 et toute autre source effectivement reprise.
