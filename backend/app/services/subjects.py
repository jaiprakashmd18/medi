"""Built-in subjects and local keyword-based subject suggestion."""
from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Subject

BUILTIN_SUBJECTS: list[tuple[str, str, str, list[str]]] = [
    ("Anatomy", "Structure of the human body", "#22d3ee",
     ["artery", "vein", "nerve", "muscle", "bone", "ligament", "plexus", "fossa", "foramen", "anterior",
      "posterior", "lateral", "medial", "superior", "inferior", "joint", "tendon", "vertebra", "skull",
      "thorax", "abdomen", "pelvis", "limb", "ventricle", "atrium", "valve", "lobe", "duct"]),
    ("Histology", "Microscopic structure of tissues", "#2dd4bf",
     ["epithelium", "epithelial", "connective tissue", "stain", "h&e", "microscopic", "squamous",
      "columnar", "cuboidal", "goblet", "lamina propria", "basement membrane", "gland", "cartilage",
      "histology", "tissue section", "eosin", "hematoxylin"]),
    ("Cell Biology", "Cells, organelles and cellular processes", "#38bdf8",
     ["cell membrane", "organelle", "mitochondria", "ribosome", "endoplasmic reticulum", "golgi",
      "cytoskeleton", "mitosis", "meiosis", "cell cycle", "apoptosis", "lysosome", "nucleus", "vesicle",
      "endocytosis", "exocytosis"]),
    ("Physiology", "Normal function of body systems", "#60a5fa",
     ["cardiac output", "blood pressure", "action potential", "homeostasis", "filtration", "ventilation",
      "perfusion", "hormone", "receptor", "membrane potential", "contraction", "renal", "glomerular",
      "respiration", "baroreceptor", "stroke volume", "physiology"]),
    ("Biochemistry", "Chemical processes within living organisms", "#a78bfa",
     ["enzyme", "glycolysis", "krebs", "citric acid", "atp", "metabolism", "amino acid", "protein",
      "lipid", "carbohydrate", "substrate", "coenzyme", "oxidation", "phosphorylation", "gluconeogenesis",
      "biochemistry", "michaelis"]),
    ("Medical Biophysics", "Physics applied to biological systems", "#818cf8",
     ["diffusion", "osmosis", "biophysics", "radiation", "ultrasound", "x-ray", "pressure gradient",
      "viscosity", "laminar", "poiseuille", "nernst", "electrical", "optics", "wavelength", "frequency"]),
    ("Molecular Biology", "DNA, RNA and gene expression", "#c084fc",
     ["dna", "rna", "transcription", "translation", "replication", "polymerase", "promoter", "codon",
      "mrna", "trna", "pcr", "gene expression", "plasmid", "splicing", "epigenetic"]),
    ("Genetics", "Inheritance and genetic variation", "#e879f9",
     ["allele", "genotype", "phenotype", "autosomal", "recessive", "dominant", "x-linked", "chromosome",
      "mutation", "inheritance", "pedigree", "karyotype", "trisomy", "mendelian", "genetic"]),
    ("Pathology", "Disease processes and mechanisms", "#f472b6",
     ["inflammation", "necrosis", "neoplasia", "tumour", "tumor", "carcinoma", "infarction", "thrombosis",
      "embolism", "pathology", "pathogenesis", "metaplasia", "dysplasia", "granuloma", "oedema", "edema"]),
    ("Pharmacology", "Drugs and their actions", "#fb7185",
     ["drug", "dose", "agonist", "antagonist", "pharmacokinetics", "pharmacodynamics", "half-life",
      "bioavailability", "clearance", "adverse effect", "contraindication", "inhibitor", "mg", "receptor blocker"]),
    ("Microbiology", "Microorganisms and infection", "#fbbf24",
     ["bacteria", "bacterial", "virus", "viral", "fungal", "parasite", "gram-positive", "gram-negative",
      "antibiotic", "infection", "pathogen", "culture", "spore", "toxin", "microbiology"]),
    ("Clinical Medicine", "Clinical presentation, diagnosis and management", "#34d399",
     ["patient", "diagnosis", "symptom", "sign", "clinical", "examination", "management", "treatment",
      "presentation", "investigation", "differential", "history taking", "prognosis"]),
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:120] or "subject"


def seed_subjects(db: Session) -> None:
    existing = {s.slug for s in db.scalars(select(Subject).where(Subject.user_id.is_(None)))}
    for name, desc, color, _ in BUILTIN_SUBJECTS:
        slug = slugify(name)
        if slug not in existing:
            db.add(Subject(user_id=None, name=name, slug=slug, description=desc, color=color, is_custom=False))
    db.commit()


def visible_subjects_query(user_id: str):
    return select(Subject).where(or_(Subject.user_id.is_(None), Subject.user_id == user_id))


def suggest_subject(db: Session, text: str) -> tuple[Subject | None, dict[str, int]]:
    """Score text against subject keyword lists. Deterministic and fully local."""
    lowered = text.lower()
    scores: Counter[str] = Counter()
    for name, _, _, keywords in BUILTIN_SUBJECTS:
        for kw in keywords:
            n = len(re.findall(r"\b" + re.escape(kw) + r"\b", lowered))
            if n:
                scores[name] += min(n, 15)
    if not scores:
        return None, {}
    best, score = scores.most_common(1)[0]
    if score < 3:
        return None, dict(scores)
    subj = db.scalar(select(Subject).where(Subject.user_id.is_(None), Subject.slug == slugify(best)))
    return subj, dict(scores)
