"""French translation strings."""

from __future__ import annotations

STRINGS: dict[str, str] = {
    # ── CLI ──────────────────────────────────────────────────────────────
    "cli.app_help": "Speks — Générateur interactif d'analyses fonctionnelles",
    "cli.dir_exists": "Le répertoire '{name}' existe déjà.",
    "cli.workspace_created": "Espace de travail créé dans",
    "cli.run_hint": "Exécutez",
    "cli.building_mkdocs": "Construction du site avec MkDocs …",
    "cli.serving_at": "Disponible sur",
    "cli.stop_hint": "(Ctrl+C pour arrêter)",
    "cli.watching": "Surveillance de {dirs} pour les changements …",
    "cli.rebuilding": "Changement détecté, reconstruction …",
    "cli.rebuild_done": "Reconstruction terminée.",
    "cli.rebuild_error": "Reconstruction échouée : {error}",

    # ── Contract table ───────────────────────────────────────────────────
    "contract.parameter": "Paramètre",
    "contract.type": "Type",
    "contract.default": "Défaut",
    "contract.description": "Description",
    "contract.return": "Retour",
    "contract.no_params": "Aucun paramètre",
    "contract.inputs": "Entrées",
    "contract.output": "Sortie",

    # ── Playground ───────────────────────────────────────────────────────
    "playground.title": "Playground",
    "playground.view_source": "Voir le code source",
    "playground.run_button": "Tester la règle",
    "playground.disabled_tooltip": "Disponible uniquement via speks serve",
    "playground.mock_config": "Configuration des mocks",
    "playground.simulate_error": "Simuler une erreur",

    # ── Playground JS (embedded in HTML) ─────────────────────────────────
    "js.invalid_json": "Erreur : JSON invalide dans la configuration des mocks.",
    "js.running": "Exécution en cours…",
    "js.error_prefix": "Erreur : ",
    "js.network_error": "Erreur réseau : ",
    "js.inputs_label": "Entrées :",
    "js.result_label": "Résultat :",
    "js.calls_label": "Appels externes (mockés) :",

    # ── PlantUML ─────────────────────────────────────────────────────────
    "plantuml.alt": "Diagramme PlantUML",
    "plantuml.source_label": "Source PlantUML",
    "plantuml.file_not_found": "PlantUML : {arg} (fichier non trouvé)",

    # ── Dependencies legend ──────────────────────────────────────────────
    "deps.entry_point": "point d'entrée",
    "deps.internal_func": "Fonction métier interne",
    "deps.external_svc": "Service externe (blackbox)",
    "deps.legend_title": "Légende",

    # ── Test cases ────────────────────────────────────────────────────────
    "tc.panel_title": "Cas de test",
    "tc.no_testcases": "Aucun cas de test enregistré.",
    "tc.save": "Sauvegarder comme cas de test",
    "tc.replay": "Rejouer",
    "tc.replay_all": "Tout rejouer",
    "tc.delete": "Supprimer",
    "tc.name_prompt": "Nom du cas de test :",
    "tc.expected_prompt": "Résultat attendu (JSON) :",
    "tc.saved": "Cas de test sauvegardé.",
    "tc.confirm_delete": "Supprimer ce cas de test ?",
    "tc.pass": "PASS",
    "tc.fail": "FAIL",
    "tc.expected": "Attendu :",
    "tc.actual": "Obtenu :",
    "tc.summary": "{passed}/{total} réussi(s)",

    # ── Sequence diagram ─────────────────────────────────────────────────
    "sequence.title": "Diagramme de séquence",

    # ── Versioning ────────────────────────────────────────────────────────
    "versioning.current_version": "Actuel (copie de travail)",
    "versioning.compare_versions": "Comparer les versions",
    "versioning.compare_title": "Comparer les versions de la documentation",
    "versioning.from_version": "De :",
    "versioning.to_version": "Vers :",
    "versioning.run_compare": "Comparer",
    "versioning.loading_diff": "Calcul du diff en cours…",
    "versioning.diff_error": "Impossible de calculer le diff",
    "versioning.no_changes": "Aucun changement entre ces versions.",
    "cli.building_version": "Construction de la version {sha} …",
    "cli.no_git_repo": "Pas un dépôt git — construction des versions ignorée.",

    # ── Server ───────────────────────────────────────────────────────────
    "server.title": "Speks — Serveur de développement",
    "server.func_not_found": "Fonction '{name}' introuvable",
    "server.timeout": "Exécution interrompue après {seconds}s (timeout)",
}
