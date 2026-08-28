"""
Deterministic ATS analysis: pull the keywords that matter out of a job
description, check them against a parsed resume, and score the document the way
an applicant tracking system would experience it.

No network calls, no model required — the optional LLM pass in llm.py layers on
top of this, it does not replace it.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .resume_parse import ParsedResume

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

STOPWORDS = {
    "a", "about", "above", "across", "after", "again", "against", "all", "also", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "cannot", "could", "did", "do", "does", "doing",
    "down", "during", "each", "either", "else", "etc", "even", "ever", "every", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "him",
    "his", "how", "however", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "like", "make", "many", "may", "me", "might", "more", "most", "much", "must", "my",
    "neither", "no", "nor", "not", "now", "of", "off", "on", "once", "one", "only", "or",
    "other", "others", "ought", "our", "ours", "out", "over", "own", "per", "same", "shall",
    "she", "should", "since", "so", "some", "such", "than", "that", "the", "their", "theirs",
    "them", "then", "there", "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "upon", "us", "use", "used", "using", "very", "was", "we", "well", "were",
    "what", "when", "where", "whether", "which", "while", "who", "whom", "why", "will", "with",
    "within", "without", "would", "you", "your", "yours",
    # resume/JD filler that carries no signal
    "ability", "able", "across", "applicant", "apply", "benefits", "candidate", "candidates",
    "company", "day", "description", "employee", "employees", "employer", "equal", "experience",
    "great", "help", "hiring", "hour", "job", "join", "looking", "love", "new", "office",
    "opportunity", "part", "please", "position", "prefer", "preferred", "required",
    "requirement", "requirements", "responsibilities", "responsibility", "role", "salary",
    "seeking", "skills", "strong", "team", "teams", "time", "want", "work", "working", "year",
    "years", "plus", "must", "nice", "good", "excellent", "including", "include", "includes",
    "ideal", "successful", "life", "health", "insurance", "paid", "leave", "remote", "onsite",
    "hybrid", "full", "level", "senior", "junior", "mid", "please", "note", "us",
    # qualifier words that turn a real term into a sentence fragment
    "highly", "proven", "solid", "demonstrated", "familiar", "familiarity", "comfortable",
    "desirable", "willingness", "passion", "passionate", "eager", "deep", "extensive",
    "practical", "hands", "on", "track", "record", "understanding", "knowledge", "exposure",
}

# canonical term -> aliases (all matched case-insensitively, word-boundary aware)
SKILL_LEXICON: dict[str, list[str]] = {
    # languages
    "python": ["python", "python3"],
    "javascript": ["javascript", "java script", "js", "es6", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "java": ["java"],
    "c#": ["c#", "csharp", "c sharp"],
    "c++": ["c++", "cpp"],
    "go": ["golang", "go lang"],
    "rust": ["rust"],
    "ruby": ["ruby"],
    "php": ["php"],
    "swift": ["swift"],
    "kotlin": ["kotlin"],
    "scala": ["scala"],
    "sql": ["sql", "t-sql", "pl/sql"],
    "r": ["rstats"],
    "bash": ["bash", "shell scripting", "shell script"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "sass", "scss", "less"],
    "solidity": ["solidity"],
    "dart": ["dart"],
    # frontend
    "react": ["react", "react.js", "reactjs"],
    "next.js": ["next.js", "nextjs"],
    "vue": ["vue", "vue.js", "vuejs"],
    "angular": ["angular", "angularjs"],
    "svelte": ["svelte", "sveltekit"],
    "redux": ["redux", "redux toolkit", "zustand"],
    "tailwind": ["tailwind", "tailwindcss", "tailwind css"],
    "react native": ["react native"],
    "flutter": ["flutter"],
    "responsive design": ["responsive design", "responsive web"],
    "accessibility": ["accessibility", "wcag", "a11y", "aria"],
    # backend
    "node.js": ["node.js", "nodejs", "node js", "node"],
    "express": ["express", "express.js", "expressjs"],
    "nestjs": ["nestjs", "nest.js"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi", "fast api"],
    "spring boot": ["spring boot", "springboot", "spring"],
    ".net": [".net", "dotnet", "asp.net"],
    "laravel": ["laravel"],
    "rails": ["ruby on rails", "rails"],
    "graphql": ["graphql", "apollo"],
    "rest api": ["rest api", "restful", "rest apis", "rest"],
    "grpc": ["grpc"],
    "websocket": ["websocket", "websockets", "socket.io", "socketio"],
    "microservices": ["microservice", "microservices"],
    "api design": ["api design", "api development"],
    # data
    "mongodb": ["mongodb", "mongo", "mongoose"],
    "postgresql": ["postgresql", "postgres", "psql"],
    "mysql": ["mysql", "mariadb"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "dynamodb": ["dynamodb"],
    "firebase": ["firebase", "firestore"],
    "sqlite": ["sqlite"],
    "snowflake": ["snowflake"],
    "bigquery": ["bigquery", "big query"],
    "etl": ["etl", "elt", "data pipeline", "data pipelines"],
    "airflow": ["airflow"],
    "kafka": ["kafka"],
    "spark": ["spark", "pyspark"],
    "data warehouse": ["data warehouse", "data warehousing"],
    "data modeling": ["data modeling", "data modelling", "schema design"],
    # cloud / devops
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "docker": ["docker", "containerization", "containerisation"],
    "kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
    "terraform": ["terraform", "infrastructure as code", "iac"],
    "ansible": ["ansible"],
    "ci/cd": ["ci/cd", "cicd", "continuous integration", "continuous delivery",
              "continuous deployment", "github actions", "jenkins", "gitlab ci", "circleci"],
    "linux": ["linux", "unix", "ubuntu"],
    "nginx": ["nginx", "apache"],
    "monitoring": ["monitoring", "observability", "prometheus", "grafana", "datadog", "sentry"],
    "serverless": ["serverless"],
    "git": ["git", "github", "gitlab", "bitbucket", "version control"],
    # ai / ml
    "machine learning": ["machine learning", "ml", "predictive model", "predictive modeling"],
    "deep learning": ["deep learning", "neural network", "neural networks"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "opencv", "image recognition", "facial recognition"],
    "llm": ["llm", "llms", "large language model", "generative ai", "genai", "gpt", "rag",
            "prompt engineering", "langchain"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "keras"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "pandas": ["pandas", "numpy"],
    "data science": ["data science", "data scientist"],
    "data analysis": ["data analysis", "data analytics", "analytics"],
    "mlops": ["mlops", "model deployment"],
    "statistics": ["statistics", "statistical analysis", "a/b testing", "ab testing"],
    "recommendation systems": ["recommendation system", "recommender system", "recommendation engine"],
    # product / process
    "agile": ["agile", "scrum", "kanban", "sprint", "sprints"],
    "jira": ["jira", "confluence", "asana", "trello", "linear"],
    "code review": ["code review", "code reviews", "pull request", "pull requests"],
    "unit testing": ["unit test", "unit testing", "jest", "pytest", "mocha", "vitest", "junit"],
    "test automation": ["test automation", "automated testing", "selenium", "cypress", "playwright"],
    "tdd": ["tdd", "test driven development", "bdd"],
    "system design": ["system design", "architecture", "software architecture", "distributed systems"],
    "performance optimization": ["performance optimization", "performance optimisation",
                                 "performance tuning", "optimization", "scalability", "caching"],
    "security": ["security", "owasp", "penetration testing", "encryption", "authentication",
                 "authorization", "oauth", "jwt", "sso"],
    "documentation": ["documentation", "technical writing"],
    "mentoring": ["mentoring", "mentorship", "coaching", "onboarding"],
    "stakeholder management": ["stakeholder", "stakeholders", "cross-functional", "cross functional"],
    "communication": ["communication", "communicate", "written communication", "verbal communication"],
    "problem solving": ["problem solving", "problem-solving", "troubleshooting", "debugging"],
    "leadership": ["leadership", "team lead", "tech lead", "led a team"],
    "ownership": ["ownership", "end-to-end", "end to end", "self-starter"],
    "collaboration": ["collaboration", "collaborate", "teamwork", "pair programming"],
    # domain
    "payments": ["payment", "payments", "stripe", "paypal", "billing", "checkout", "transactions"],
    "fintech": ["fintech", "financial services", "banking", "wallet", "kyc", "aml"],
    "e-commerce": ["e-commerce", "ecommerce", "shopify", "marketplace"],
    "healthcare": ["healthcare", "healthtech", "telemedicine", "hipaa", "ehr", "emr", "patient"],
    "saas": ["saas", "b2b saas", "multi-tenant", "multi tenant", "subscription"],
    "crm": ["crm", "salesforce", "hubspot"],
    "erp": ["erp", "sap", "odoo"],
    "seo": ["seo", "search engine optimization"],
    "ux": ["ux", "user experience", "ui/ux", "usability", "user research"],
    "ui design": ["ui design", "figma", "sketch", "adobe xd", "wireframe", "wireframes", "prototyping"],
    "cms": ["cms", "wordpress", "contentful", "strapi"],
    "real-time": ["real-time", "real time", "realtime", "streaming", "live updates"],
    "mobile": ["mobile", "ios", "android", "mobile app"],
    "blockchain": ["blockchain", "web3", "smart contract", "smart contracts", "ethereum"],
    "excel": ["excel", "spreadsheet", "vlookup", "pivot table"],
    "power bi": ["power bi", "powerbi", "tableau", "looker", "dashboards", "data visualization"],
}

ALIAS_TO_CANON: dict[str, str] = {}
for _canon, _aliases in SKILL_LEXICON.items():
    ALIAS_TO_CANON[_canon] = _canon
    for _a in _aliases:
        ALIAS_TO_CANON[_a] = _canon

SOFT_SKILLS = {
    "communication", "problem solving", "leadership", "ownership", "collaboration",
    "mentoring", "stakeholder management", "agile", "documentation", "code review",
}

CATEGORY_OF: dict[str, str] = {}
for _c in SKILL_LEXICON:
    CATEGORY_OF[_c] = "soft" if _c in SOFT_SKILLS else "hard"

ACTION_VERBS = {
    "achieved", "architected", "authored", "automated", "built", "collaborated", "consolidated",
    "converted", "created", "cut", "decreased", "delivered", "deployed", "designed", "developed",
    "diagnosed", "directed", "drove", "eliminated", "engineered", "enhanced", "established",
    "executed", "expanded", "grew", "implemented", "improved", "increased", "initiated",
    "integrated", "introduced", "launched", "led", "maintained", "managed", "migrated",
    "modernized", "negotiated", "optimized", "orchestrated", "overhauled", "owned", "partnered",
    "pioneered", "planned", "produced", "programmed", "rearchitected", "rebuilt", "reduced",
    "refactored", "released", "resolved", "restructured", "revamped", "scaled", "shipped",
    "simplified", "solved", "spearheaded", "standardized", "streamlined", "supported",
    "tested", "trained", "transformed", "upgraded", "wrote",
}

WEAK_OPENERS = {
    "responsible", "helped", "worked", "assisted", "participated", "involved", "tasked",
    "duties", "handled", "various", "etc",
}

REQUIREMENT_HEADINGS = re.compile(
    r"^\s*(what you.{0,20}(bring|need|have)|requirements?|qualifications?|must have|"
    r"you (will )?(have|bring)|skills? (and|&) experience|who you are|about you|"
    r"minimum qualifications?|basic qualifications?|we.{0,5}re looking for)\b",
    re.I,
)
NICE_HEADINGS = re.compile(
    r"^\s*(nice to have|bonus|preferred|plus(es)?|good to have|desirable)\b", re.I
)


# --------------------------------------------------------------------------
# Job description analysis
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    t = text.lower()
    t = t.replace("’", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9+#./&' -]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _alias_pattern(alias: str) -> re.Pattern:
    escaped = re.escape(alias)
    lead = r"(?<![a-z0-9+#])" if alias[0].isalnum() else r"(?<![a-z0-9])"
    trail = r"(?![a-z0-9+#])" if alias[-1].isalnum() else r"(?![a-z0-9])"
    return re.compile(lead + escaped + trail)


_ALIAS_PATTERNS = {alias: _alias_pattern(alias) for alias in ALIAS_TO_CANON}


def _find_lexicon_hits(norm_text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for alias, canon in ALIAS_TO_CANON.items():
        n = len(_ALIAS_PATTERNS[alias].findall(norm_text))
        if n:
            hits[canon] = hits.get(canon, 0) + n
    return hits


def _guess_job_title(jd_text: str) -> str:
    for raw in jd_text.split("\n")[:12]:
        s = raw.strip(" #*-•\t")
        if not s or len(s) > 90:
            continue
        low = s.lower()
        if re.search(r"\b(engineer|developer|scientist|analyst|manager|designer|architect|"
                     r"lead|specialist|consultant|administrator|intern|associate|director)\b", low):
            return re.sub(r"\s+", " ", s)
    return ""


def _requirement_spans(jd_text: str) -> tuple[str, str]:
    """Split the JD into (must-have text, nice-to-have text)."""
    must: list[str] = []
    nice: list[str] = []
    mode = None
    for line in jd_text.split("\n"):
        if REQUIREMENT_HEADINGS.match(line.strip(" #*-•\t")):
            mode = "must"
            continue
        if NICE_HEADINGS.match(line.strip(" #*-•\t")):
            mode = "nice"
            continue
        if re.match(r"^\s*(benefits|perks|about (us|the company)|why join|equal opportunity)\b",
                    line.strip(" #*-•\t"), re.I):
            mode = None
            continue
        if mode == "must":
            must.append(line)
        elif mode == "nice":
            nice.append(line)
    return "\n".join(must), "\n".join(nice)


# Words that make a phrase a fragment of a sentence rather than a term.
CONNECTORS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "for", "from",
    "in", "into", "is", "of", "on", "or", "our", "over", "that", "the", "their", "them",
    "these", "this", "those", "to", "was", "were", "which", "who", "will", "with", "within",
    "you", "your", "its", "it", "not", "no", "if", "when", "while", "than", "then", "so",
}


# Sentence/bullet boundaries. A period only splits when it ends a word, so
# "node.js" and ".net" survive intact.
CLAUSE_SPLIT = re.compile(r"[,;:!?\n\r•·()\[\]]+|(?<=\w)\.(?=\s|$)")


def _ngram_candidates(raw_text: str, max_n: int = 3) -> Counter:
    counts: Counter = Counter()
    for clause in CLAUSE_SPLIT.split(raw_text or ""):
        tokens = [t.strip(".") or t for t in _norm(clause).split(" ") if t]
        for n in range(1, max_n + 1):
            for i in range(len(tokens) - n + 1):
                gram = tokens[i:i + n]
                if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
                    continue
                if n > 1 and any(t in CONNECTORS for t in gram):
                    continue
                if any(len(t) < 2 for t in gram):
                    continue
                if all(t.isdigit() for t in gram):
                    continue
                phrase = " ".join(gram)
                if len(phrase) < 3:
                    continue
                counts[phrase] += 1
    return counts


def _drop_redundant(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    'hubspot marketing automation' and 'hubspot marketing' are the same
    requirement counted twice. Keep the higher-weighted phrase only.
    """
    kept: list[dict[str, Any]] = []
    for kw in ranked:
        term = kw["term"]
        if kw["category"] != "context":
            kept.append(kw)
            continue
        redundant = any(
            k["category"] == "context"
            and (f" {term} " in f" {k['term']} " or f" {k['term']} " in f" {term} ")
            for k in kept
        )
        if not redundant:
            kept.append(kw)
    return kept


def analyze_jd(jd_text: str, max_keywords: int = 34) -> dict[str, Any]:
    norm_all = _norm(jd_text)
    must_text, nice_text = _requirement_spans(jd_text)
    norm_must = _norm(must_text)
    norm_nice = _norm(nice_text)
    title = _guess_job_title(jd_text)
    norm_title = _norm(title)

    lex_all = _find_lexicon_hits(norm_all)
    lex_must = _find_lexicon_hits(norm_must) if norm_must else {}
    lex_nice = _find_lexicon_hits(norm_nice) if norm_nice else {}
    lex_title = _find_lexicon_hits(norm_title) if norm_title else {}

    keywords: dict[str, dict[str, Any]] = {}
    for canon, freq in lex_all.items():
        weight = 2.4 + min(freq - 1, 4) * 0.35
        if canon in lex_must:
            weight += 1.4
        if canon in lex_title:
            weight += 2.0
        if canon in lex_nice and canon not in lex_must:
            weight -= 0.8
        keywords[canon] = {
            "term": canon,
            "weight": round(max(weight, 0.6), 2),
            "frequency": freq,
            "category": CATEGORY_OF.get(canon, "hard"),
            "source": "must-have" if canon in lex_must else ("nice-to-have" if canon in lex_nice else "body"),
            "aliases": SKILL_LEXICON.get(canon, [canon]),
        }

    # Fill remaining slots with high-signal phrases the lexicon does not know.
    # The lexicon is tech-heavy, so a thin harvest (non-technical role, or a
    # domain it has never seen) relaxes the thresholds and reads the whole post.
    thin = len(keywords) < 12
    grams = _ngram_candidates(jd_text if thin else (must_text or jd_text))
    min_single = 2 if thin else 3
    min_multi = 1 if thin else 2
    covered = " ".join(
        alias for canon in keywords for alias in SKILL_LEXICON.get(canon, [canon])
    )
    for phrase, freq in grams.most_common(260):
        if len(keywords) >= max_keywords + 12:
            break
        if phrase in keywords or phrase in ALIAS_TO_CANON:
            continue
        if phrase in covered:
            continue
        words = phrase.split(" ")
        if len(words) == 1 and (freq < min_single or len(phrase) < 4 or phrase in STOPWORDS):
            continue
        if len(words) > 1 and freq < min_multi:
            continue
        if any(w in STOPWORDS for w in words) and len(words) == 1:
            continue
        weight = 1.0 + min(freq - 1, 3) * 0.3 + (0.5 if len(words) > 1 else 0.0)
        if norm_title and phrase in norm_title:
            weight += 1.2
        in_must = bool(norm_must) and phrase in norm_must
        if in_must:
            weight += 0.4
        keywords[phrase] = {
            "term": phrase,
            "weight": round(weight, 2),
            "frequency": freq,
            "category": "context",
            "source": "must-have" if in_must else "body",
            "aliases": [phrase],
        }

    ranked = sorted(keywords.values(), key=lambda k: (-k["weight"], -k["frequency"], k["term"]))
    ranked = _drop_redundant(ranked)[:max_keywords]

    years = 0
    m = re.search(r"(\d{1,2})\s*\+?\s*(?:-|to)?\s*(?:\d{1,2})?\s*years?", norm_all)
    if m:
        try:
            years = int(m.group(1))
        except ValueError:
            years = 0

    return {
        "title": title,
        "keywords": ranked,
        "yearsRequired": years,
        "wordCount": len(norm_all.split(" ")) if norm_all else 0,
        "hasRequirementsSection": bool(norm_must),
    }


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def match_keywords(resume_text: str, jd: dict[str, Any]) -> dict[str, Any]:
    norm_resume = _norm(resume_text)
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for kw in jd["keywords"]:
        hit_alias = None
        count = 0
        for alias in kw["aliases"]:
            pat = _ALIAS_PATTERNS.get(alias) or _alias_pattern(alias)
            n = len(pat.findall(norm_resume))
            if n:
                count += n
                hit_alias = hit_alias or alias
        record = {**{k: v for k, v in kw.items() if k != "aliases"}, "resumeCount": count}
        if count:
            record["matchedAs"] = hit_alias
            matched.append(record)
        else:
            missing.append(record)

    total_w = sum(k["weight"] for k in jd["keywords"]) or 1.0
    matched_w = sum(k["weight"] for k in matched)

    # Hard tech skills drive ATS filters (80% weight), general context/phrases 20%
    hard_keywords = [k for k in jd["keywords"] if k.get("category") == "hard"]
    hard_matched = [k for k in matched if k.get("category") == "hard"]

    if hard_keywords:
        hard_cov = sum(k["weight"] for k in hard_matched) / sum(k["weight"] for k in hard_keywords)
        overall_cov = matched_w / total_w
        blended_coverage = round((0.80 * hard_cov) + (0.20 * overall_cov), 4)
    else:
        blended_coverage = round(matched_w / total_w, 4)

    return {
        "matched": matched,
        "missing": sorted(missing, key=lambda k: (-(2 if k.get("category") == "hard" else 1), -k["weight"])),
        "coverage": blended_coverage,
        "countCoverage": round(len(matched) / max(len(jd["keywords"]), 1), 4),
    }


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

SEVERITY_PENALTY = {"critical": 20, "high": 7, "medium": 4, "low": 2}


def _all_bullets(parsed: ParsedResume) -> list[str]:
    bullets: list[str] = []
    for entry in parsed.experience + parsed.projects:
        bullets.extend(entry.bullets)
    if not bullets:
        for line in parsed.lines:
            if len(line.split()) >= 6:
                bullets.append(line)
    return bullets


def _impact_stats(bullets: list[str]) -> dict[str, Any]:
    if not bullets:
        return {"total": 0, "quantified": 0, "actionStart": 0, "weakStart": 0, "avgWords": 0,
                "tooLong": 0, "quantifiedRatio": 0.0, "actionRatio": 0.0}
    quantified = 0
    action = 0
    weak = 0
    too_long = 0
    words_total = 0
    for b in bullets:
        words = b.split()
        words_total += len(words)
        if len(words) > 34:
            too_long += 1
        if re.search(r"(\d+(\.\d+)?\s*%|\$\s?\d|\b\d{2,}\b|\b\d+(\.\d+)?\s*(k|m|bn|x|hrs?|hours?|days?|weeks?|months?)\b)",
                     b, re.I):
            quantified += 1
        first = re.sub(r"[^a-z]", "", words[0].lower()) if words else ""
        if first in ACTION_VERBS:
            action += 1
        elif first in WEAK_OPENERS:
            weak += 1
    n = len(bullets)
    return {
        "total": n,
        "quantified": quantified,
        "actionStart": action,
        "weakStart": weak,
        "tooLong": too_long,
        "avgWords": round(words_total / n, 1),
        "quantifiedRatio": round(quantified / n, 3),
        "actionRatio": round(action / n, 3),
    }


def score_resume(parsed: ParsedResume, jd: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    fixes: list[dict[str, str]] = []

    # 1. Keyword coverage (35)
    kw_score = round(min(match["coverage"] / 0.75, 1.0) * 35, 1)
    components.append({
        "id": "keywords",
        "label": "Keyword match",
        "score": kw_score,
        "max": 35,
        "detail": f"{len(match['matched'])} of {len(jd['keywords'])} job-description terms appear in "
                  f"your resume ({round(match['coverage'] * 100)}% weighted coverage).",
    })
    top_missing = [m["term"] for m in match["missing"][:6]]
    if top_missing:
        fixes.append({
            "priority": "high" if kw_score < 24 else "medium",
            "title": "Work the missing keywords into real bullets",
            "detail": "Highest-weighted terms absent from your resume: " + ", ".join(top_missing) +
                      ". Only add the ones you have actually done — put them in the bullet that "
                      "describes that work, not in a keyword dump.",
        })

    # 2. Section structure (15)
    sec_score = 0.0
    have = parsed.sections
    for name, pts in (("experience", 6), ("education", 3), ("skills", 3), ("summary", 3)):
        if have.get(name):
            sec_score += pts
    missing_sections = [n for n in ("summary", "skills", "experience", "education") if not have.get(n)]
    components.append({
        "id": "sections",
        "label": "Section structure",
        "score": round(sec_score, 1),
        "max": 15,
        "detail": "Found: " + (", ".join(sorted(have)) if have else "no standard sections") +
                  (". Missing: " + ", ".join(missing_sections) if missing_sections else "."),
    })
    if missing_sections:
        fixes.append({
            "priority": "high",
            "title": f"Add a clearly labelled {missing_sections[0].upper()} section",
            "detail": "Parsers key off standard headings. Missing: " + ", ".join(missing_sections) +
                      ". Use plain wording — SKILLS, PROFESSIONAL EXPERIENCE, EDUCATION.",
        })

    # 3. Parseability (20)
    parse_score = 20.0
    for w in parsed.layout_warnings:
        parse_score -= SEVERITY_PENALTY.get(w.get("severity", "low"), 2)
    parse_score = max(parse_score, 0.0)
    components.append({
        "id": "parseability",
        "label": "Parseability",
        "score": round(parse_score, 1),
        "max": 20,
        "detail": (f"{len(parsed.layout_warnings)} layout issue(s) that can corrupt automated parsing."
                   if parsed.layout_warnings else "Clean, linear layout — no parser traps detected."),
    })
    for w in parsed.layout_warnings:
        if w.get("severity") in ("critical", "high"):
            fixes.append({
                "priority": "high",
                "title": w["title"],
                "detail": w["detail"],
            })

    # 4. Contact block (10)
    c = parsed.contact
    contact_score = 0.0
    contact_score += 4 if c.get("email") else 0
    contact_score += 3 if c.get("phone") else 0
    contact_score += 2 if c.get("linkedin") else 0
    contact_score += 1 if c.get("location") else 0
    missing_contact = [k for k in ("email", "phone", "linkedin", "location") if not c.get(k)]
    components.append({
        "id": "contact",
        "label": "Contact details",
        "score": round(contact_score, 1),
        "max": 10,
        "detail": ("All key contact fields readable." if not missing_contact
                   else "Not detected in the document body: " + ", ".join(missing_contact) + "."),
    })
    if missing_contact:
        fixes.append({
            "priority": "high" if "email" in missing_contact else "medium",
            "title": "Complete the contact block",
            "detail": "Missing or unparseable: " + ", ".join(missing_contact) +
                      ". Put these as plain text at the top of the page — never inside a header, "
                      "text box, table or image.",
        })

    # 5. Impact of bullets (10)
    stats = _impact_stats(_all_bullets(parsed))
    impact = 0.0
    impact += min(stats["quantifiedRatio"] / 0.4, 1.0) * 5
    impact += min(stats["actionRatio"] / 0.7, 1.0) * 3
    if stats["total"]:
        impact += 2 if stats["tooLong"] / stats["total"] < 0.2 else 0.5
    components.append({
        "id": "impact",
        "label": "Bullet quality",
        "score": round(impact, 1),
        "max": 10,
        "detail": (f"{stats['quantified']}/{stats['total']} bullets carry a number; "
                   f"{stats['actionStart']}/{stats['total']} open with a strong action verb; "
                   f"average length {stats['avgWords']} words."
                   if stats["total"] else "No bullet points detected."),
    })
    if stats["total"] and stats["quantifiedRatio"] < 0.35:
        fixes.append({
            "priority": "medium",
            "title": "Quantify more bullets",
            "detail": f"Only {stats['quantified']} of {stats['total']} bullets contain a number. "
                      "Recruiters and scoring models both weight measurable outcomes — add users "
                      "served, latency cut, revenue moved, time saved.",
        })
    if stats["weakStart"] > 0:
        fixes.append({
            "priority": "low",
            "title": f"Rewrite {stats['weakStart']} bullet(s) that start weakly",
            "detail": "Openers like \"Responsible for\" or \"Helped with\" describe a job description, "
                      "not an achievement. Start with what you did: Built, Shipped, Cut, Automated.",
        })

    # 6. Format hygiene (10)
    hygiene = 0.0
    wc = parsed.word_count
    if 350 <= wc <= 950:
        hygiene += 4
    elif 250 <= wc < 350 or 950 < wc <= 1200:
        hygiene += 2.5
    else:
        hygiene += 1
    pronouns = len(re.findall(r"\b(i|me|my|myself)\b", parsed.raw_text, re.I))
    hygiene += 2 if pronouns <= 3 else (1 if pronouns <= 10 else 0)
    hygiene += 2 if parsed.source in ("pdf", "docx") else 1
    hygiene += 1 if not re.search(r"references available upon request", parsed.raw_text, re.I) else 0
    dated = sum(1 for e in parsed.experience if e.period)
    hygiene += 1 if (dated or not parsed.experience) else 0
    components.append({
        "id": "hygiene",
        "label": "Format hygiene",
        "score": round(min(hygiene, 10), 1),
        "max": 10,
        "detail": f"{wc} words, {pronouns} first-person pronoun(s), source .{parsed.source}, "
                  f"{dated}/{len(parsed.experience) or 0} roles with a parseable date range.",
    })
    if wc < 300:
        fixes.append({
            "priority": "medium",
            "title": "The resume is thin",
            "detail": f"Only {wc} readable words. Either content is missing or the file did not parse "
                      "properly — both look identical to an ATS.",
        })
    if not dated and parsed.experience:
        fixes.append({
            "priority": "medium",
            "title": "Add explicit date ranges to every role",
            "detail": "Use a consistent, machine-readable form such as \"Mar 2023 – Present\". Missing "
                      "dates break the tenure calculation most systems run.",
        })

    total = round(sum(c["score"] for c in components), 1)
    if total >= 85:
        band, verdict = "excellent", "This will parse cleanly and match strongly."
    elif total >= 70:
        band, verdict = "good", "Solid. A few targeted edits will push it into the top band."
    elif total >= 55:
        band, verdict = "fair", "It will get through parsing, but it is losing points on match and structure."
    else:
        band, verdict = "poor", "Likely to be filtered before a human reads it."

    order = {"high": 0, "medium": 1, "low": 2}
    fixes.sort(key=lambda f: order.get(f["priority"], 3))

    return {
        "total": total,
        "band": band,
        "verdict": verdict,
        "components": components,
        "fixes": fixes,
        "bulletStats": stats,
    }


def analyze(parsed: ParsedResume, jd_text: str) -> dict[str, Any]:
    jd = analyze_jd(jd_text)
    match = match_keywords(parsed.raw_text, jd)
    score = score_resume(parsed, jd, match)
    return {
        "jd": {
            "title": jd["title"],
            "yearsRequired": jd["yearsRequired"],
            "wordCount": jd["wordCount"],
            "hasRequirementsSection": jd["hasRequirementsSection"],
            "keywordCount": len(jd["keywords"]),
        },
        "_jd": jd,
        "resume": parsed.to_dict(),
        "match": match,
        "score": score,
    }
