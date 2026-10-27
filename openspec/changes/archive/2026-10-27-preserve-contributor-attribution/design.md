# Design

## Context

Les adaptations des PRs pourraient masquer l’origine du code et des idées si elles sont livrées sous de nouveaux commits. Les liens documentaires du dépôt restent également incohérents.

Socle : `f92e3e4`, 334 tests sur HA 2024.6.4 et 2026.10.4. README.md, CONTRIBUTORS.md, docs/pr-integration-plan.md et journal de provenance ; aucun changement Python.

## Goals / Non-Goals

**Goals:** Créer un registre durable des auteurs, PRs, commits sources, fonctionnalités et statut de reprise. Relier README, notes de version, descriptions de livraison et commits adaptés à ce registre. Harmoniser les liens d’installation et préserver les mentions de licence et notices présentes dans les sources reprises.

**Non-Goals:** fusion globale des anciennes branches, modification d’équipements réels pendant les tests, modification implicite des IDs ou suppression de données utilisateur.

## Decisions

1. Utiliser les logins et liens GitHub vérifiés ; ne pas déduire d’adresse de messagerie ni inventer de trailer Co-authored-by.

2. Conserver l’auteur des commits lorsqu’un cherry-pick est réellement utilisable ; pour une adaptation, garder l’auteur du travail d’adaptation et ajouter Adapted-from: URL et Original-author: @login. La description explique le périmètre réellement repris.

3. Distinguer contribution fusionnée, besoin couvert autrement, proposition source et adaptation effectivement livrée. La planification ne transforme pas une PR ouverte en fonctionnalité livrée.

4. Conserver le fichier LICENSE et les notices originales des fichiers repris ; réexaminer toute source additionnelle avant copie. Créditer le fork uniquement pour les éléments réellement consultés ou repris, avec lien et révision.

5. Corriger les badges et liens HACS sur le dépôt actuel. Ne pas modifier le domaine ni les identifiants.

## Risks / Trade-offs

Les garanties recorder, les sélecteurs et la vue HTTP doivent être validés sur les deux versions HA. La compatibilité cloud réelle et le comportement matériel ne sont pas prouvés par des tests hors ligne. Les changements d’API HA futurs exigent une nouvelle validation. Les modifications externes simultanées de planning ne disposent pas d’un compare-and-swap cloud.

## Migration Plan

1. Premier lot, puis attribution complétée dans chaque lot fonctionnel.
2. Vérifier les contrats du socle puis implémenter et tester uniquement le lot.
3. Préserver configuration, identifiants, données et défauts des fonctions existantes ; activation des nouvelles fonctions explicite quand applicable.
4. Vérifier crédits, provenance, documentation et matrice avant livraison.
5. Un retour de code ne supprime pas des statistiques déjà confirmées ; ne jamais supprimer des données pour revenir à une version précédente.
