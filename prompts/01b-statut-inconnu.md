Dans ce dépôt, lis `SPECS.md` v1.5 et `CLAUDE.md`. L'humain a arbitré la règle 5 : un statut d'exécution autre que `VALIDE` ou `EN_ERREUR` est une erreur visible pour le pipeline concerné ; le dashboard continuera d'afficher les autres pipelines à l'étape 3.

Reste dans le module moteur. Ajoute d'abord dans `test_freshness.py` un test qui vérifie qu'un statut inconnu provoque un `ValueError` mentionnant le code du pipeline et le statut reçu, même s'il existe aussi une exécution valide. Lance le test et montre la phase rouge. Modifie ensuite `freshness.py` pour satisfaire ce test, sans changer les autres règles ni les autres modules. Exécute toute la suite de tests et `git diff --check`.

Ne modifie pas `seed.py`, `app.py` ou les specs, et ne fais pas de commit. Rapporte le résultat, les fichiers touchés et le diff. Si une autre décision manque, arrête-toi avec `🚨 SPEC MANQUANTE : ...` et attends l'arbitrage humain.
