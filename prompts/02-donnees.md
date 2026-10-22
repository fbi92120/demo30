Dans ce dépôt, lis `SPECS.md` et `CLAUDE.md`, ainsi que le moteur déjà validé. Travaille uniquement sur `seed.py`, `config.yml` et `test_seed.py` ; adapte `.gitignore` seulement si nécessaire.

Écris d'abord des tests pour la priorité des chemins, le lecteur limité de `config.yml`, les erreurs lisibles, la création des quatre pipelines et des cinq exécutions, et l'absence d'écriture dans une autre base. Vérifie la phase rouge. Implémente ensuite `seed.py` selon le contrat de configuration de la section 4, sans dépendance YAML. Exécute la suite de tests et `git diff --check` ; utilise une base temporaire pour toute vérification de la commande.

Ne modifie pas le moteur validé et ne crée pas le dashboard. Ne fais pas de commit. Rapporte les résultats, les fichiers touchés et le diff. Si le contrat laisse une décision ouverte, arrête-toi avec `🚨 SPEC MANQUANTE : ...` et attends l'arbitrage humain.
