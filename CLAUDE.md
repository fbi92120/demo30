# Gouvernance de demo30bis — Vibe Coding Governed

Lis `SPECS.md` avant toute modification. Ce dépôt sert à reconstruire l'application depuis la spec, sans recopier le code de `demo30`.

- L'humain tranche le besoin, les règles et les choix d'architecture. N'en décide aucun à sa place.
- Travaille uniquement sur le module demandé dans le prompt courant. Un prompt = un module, avec ses tests.
- Pour un module dont le contrat est fixé, écris les tests avant le code. Ne modifie pas les tests pour les adapter au code produit.
- Si une décision manque ou si la spec doit changer, arrête-toi sans modifier l'implémentation concernée et signale exactement : `🚨 SPEC MANQUANTE : ...`. Attends l'arbitrage humain.
- N'ajoute ni fonctionnalité ni dépendance hors de `SPECS.md`.
- Respecte `config.yml` et la variable d'environnement définies dans la spec. Ne lis pas `.env` directement ; ce fichier reste ignoré par Git.
- À la fin de chaque module, donne le résultat des tests, les fichiers touchés, le diff et les éventuelles limites. Ne fais pas de commit sans demande explicite.
