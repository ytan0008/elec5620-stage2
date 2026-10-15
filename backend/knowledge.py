"""Transparent learning ontology with learner-specific, verified score overlays."""

SKILL_CONCEPTS = {
    "listening": [("detail", "Detail recognition"), ("signposts", "Speaker signposts"), ("inference", "Meaning and inference")],
    "reading": [("scan", "Evidence scanning"), ("paraphrase", "Paraphrase matching"), ("inference", "Reading inference")],
    "writing": [("task", "Task response"), ("structure", "Coherence and structure"), ("language", "Vocabulary and grammar")],
    "speaking": [("fluency", "Fluency"), ("ideas", "Idea development"), ("language", "Vocabulary and grammar")],
}


def build_graph(profile: dict, progress: dict, material_counts: dict[str, int]) -> dict:
    scores = progress.get("skill_scores", {})
    priorities = set(profile["priority_skills"])
    nodes = [{"id": "goal", "label": f"{profile['exam']} target {profile['target_score']}", "type": "goal", "skill": None, "score": None, "priority": False}]
    edges = []
    for skill, concepts in SKILL_CONCEPTS.items():
        score = scores.get(skill)
        nodes.append({"id": skill, "label": skill.title(), "type": "skill", "skill": skill, "score": score,
                      "priority": skill in priorities, "resource_count": material_counts.get(skill, 0)})
        edges.append({"source": skill, "target": "goal", "relation": "contributes_to"})
        for code, label in concepts:
            node_id = f"{skill}.{code}"
            nodes.append({"id": node_id, "label": label, "type": "concept", "skill": skill,
                          "score": None, "priority": skill in priorities, "resource_count": material_counts.get(skill, 0)})
            edges.append({"source": node_id, "target": skill, "relation": "develops"})
    return {"nodes": nodes, "edges": edges, "score_note": "Skill scores come only from released practice results. Concept-level mastery is not measured.",
            "source_mode": "CURATED_ONTOLOGY", "sample_count": progress.get("sample_count", 0)}
