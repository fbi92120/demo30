Dans ce dépôt, lis `SPECS.md` et `CLAUDE.md`. Travaille uniquement sur le moteur de fraîcheur : `test_freshness.py` puis `freshness.py`.

Écris d'abord les tests du contrat de `Execution`, `FreshnessResult` et `evaluate_pipeline` : les quatre scénarios d'acceptation, le calcul depuis `date_validation` même si `date_debut` est antérieure, les bornes 30/31/60/61 minutes, et le cas `VALIDE` sans date de validation. Lance les tests et montre la phase rouge attendue avant de coder le moteur. Implémente ensuite le minimum conforme aux règles 1B à 4A. Exécute les tests et `git diff --check`.

Ne crée ni base SQLite, ni `seed.py`, ni dashboard dans cette étape. Ne fais pas de commit. Rapporte les résultats, les fichiers touchés et le diff. Si le contrat laisse une décision ouverte, arrête-toi avec `🚨 SPEC MANQUANTE : ...` et attends l'arbitrage humain.
