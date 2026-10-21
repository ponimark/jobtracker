"""Canonical skill vocabulary and text extraction helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class SkillDefinition:
    canonical: str
    aliases: tuple[str, ...]


_SKILL_DEFINITIONS: tuple[SkillDefinition, ...] = (
    # Data engineering
    SkillDefinition("Python", ("python",)),
    SkillDefinition("SQL", ("sql", "structured query language")),
    SkillDefinition("dbt", ("dbt", "data build tool", "dbt cloud")),
    SkillDefinition("Airflow", ("airflow", "apache airflow")),
    SkillDefinition("Spark", ("spark", "apache spark", "pyspark")),
    SkillDefinition("Kafka", ("kafka", "apache kafka")),
    SkillDefinition("Flink", ("flink", "apache flink")),
    SkillDefinition("Snowflake", ("snowflake",)),
    SkillDefinition("BigQuery", ("bigquery", "google bigquery")),
    SkillDefinition("Databricks", ("databricks",)),
    SkillDefinition("Redshift", ("redshift", "amazon redshift")),
    SkillDefinition("AWS", ("aws", "amazon web services")),
    SkillDefinition("Azure", ("azure", "microsoft azure")),
    SkillDefinition("GCP", ("gcp", "google cloud", "google cloud platform")),
    SkillDefinition("Docker", ("docker",)),
    SkillDefinition("Kubernetes", ("kubernetes", "k8s")),
    SkillDefinition("PostgreSQL", ("postgresql", "postgres")),
    SkillDefinition("Redis", ("redis",)),
    SkillDefinition("Hadoop", ("hadoop", "apache hadoop")),
    SkillDefinition("Hive", ("hive", "apache hive")),
    SkillDefinition("Cassandra", ("cassandra",)),
    SkillDefinition("MongoDB", ("mongodb", "mongo")),
    SkillDefinition("MySQL", ("mysql",)),
    SkillDefinition("NoSQL", ("nosql", "no sql")),
    SkillDefinition("ETL", ("etl",)),
    SkillDefinition("ELT", ("elt",)),
    SkillDefinition("Data Modeling", ("data modeling", "data modelling")),
    SkillDefinition("Data Warehouse", ("data warehouse", "warehouse")),
    SkillDefinition("Data Lake", ("data lake",)),
    SkillDefinition("Lakehouse", ("lakehouse",)),
    SkillDefinition("OLAP", ("olap",)),
    SkillDefinition("OLTP", ("oltp",)),
    SkillDefinition("SCD Type 2", ("scd type 2", "slowly changing dimension type 2")),
    SkillDefinition("Parquet", ("parquet",)),
    SkillDefinition("Delta Lake", ("delta lake",)),
    SkillDefinition("Iceberg", ("iceberg", "apache iceberg")),
    SkillDefinition("Hudi", ("hudi", "apache hudi")),
    SkillDefinition("CI/CD", ("ci/cd", "cicd", "continuous integration", "continuous delivery")),
    SkillDefinition("Terraform", ("terraform",)),
    SkillDefinition("Linux", ("linux",)),
    SkillDefinition("Git", ("git", "github", "gitlab")),
    SkillDefinition("FastAPI", ("fastapi",)),
    SkillDefinition("Pandas", ("pandas", "pandas library")),
    SkillDefinition("NumPy", ("numpy", "np")),
    SkillDefinition("Matplotlib", ("matplotlib",)),
    SkillDefinition("Plotly", ("plotly",)),
    SkillDefinition("Seaborn", ("seaborn",)),
    SkillDefinition("Apache Beam", ("apache beam", "beam")),
    SkillDefinition("Prefect", ("prefect", "prefect cloud")),
    SkillDefinition("Dagster", ("dagster",)),
    SkillDefinition("Airbyte", ("airbyte",)),
    SkillDefinition("Fivetran", ("fivetran",)),
    SkillDefinition("MLflow", ("mlflow",)),
    SkillDefinition("S3", ("s3", "amazon s3")),
    SkillDefinition("Athena", ("athena", "amazon athena")),
    SkillDefinition("Glue", ("glue", "aws glue")),
    SkillDefinition("EMR", ("emr", "aws emr")),
    SkillDefinition("Lambda", ("lambda", "aws lambda")),
    # Analytics / BI / experimentation
    SkillDefinition("Tableau", ("tableau",)),
    SkillDefinition("Power BI", ("power bi", "powerbi")),
    SkillDefinition("Looker", ("looker",)),
    SkillDefinition("Looker Studio", ("looker studio", "google data studio")),
    SkillDefinition("Metabase", ("metabase",)),
    SkillDefinition("Sigma", ("sigma", "sigma computing")),
    SkillDefinition("Mode", ("mode", "mode analytics")),
    SkillDefinition("Qlik", ("qlik", "qlik sense", "qlikview")),
    SkillDefinition("MicroStrategy", ("microstrategy",)),
    SkillDefinition("Superset", ("superset", "apache superset")),
    SkillDefinition("DBT Metrics", ("metrics layer", "semantic layer")),
    SkillDefinition("Excel", ("excel", "microsoft excel")),
    SkillDefinition("A/B Testing", ("a/b testing", "ab testing", "experiment design")),
    SkillDefinition("Statistics", ("statistics",)),
    SkillDefinition("Statistical Modeling", ("statistical modeling", "statistical modelling")),
    SkillDefinition("Probability", ("probability",)),
    SkillDefinition("Causal Inference", ("causal inference",)),
    SkillDefinition("Data Visualization", ("data visualization", "data visualisation")),
    SkillDefinition("Visualization", ("visualization", "visualisation", "viz")),
    SkillDefinition("Data Quality", ("data quality",)),
    SkillDefinition("Product Analytics", ("product analytics",)),
    SkillDefinition("Experimentation", ("experimentation", "experiments")),
    SkillDefinition("Hypothesis Testing", ("hypothesis testing",)),
    SkillDefinition("Regression", ("regression", "linear regression", "logistic regression")),
    SkillDefinition("Classification", ("classification",)),
    SkillDefinition("Clustering", ("clustering",)),
    SkillDefinition("Time Series", ("time series",)),
    SkillDefinition("Forecasting", ("forecasting",)),
    SkillDefinition("Cohort Analysis", ("cohort analysis",)),
    SkillDefinition("Funnel Analysis", ("funnel analysis",)),

    # Machine learning / data science / AI
    SkillDefinition("Machine Learning", ("machine learning", "ml")),
    SkillDefinition("Deep Learning", ("deep learning",)),
    SkillDefinition("Applied Machine Learning", ("applied machine learning",)),
    SkillDefinition("Scikit-learn", ("scikit-learn", "sklearn")),
    SkillDefinition("TensorFlow", ("tensorflow",)),
    SkillDefinition("PyTorch", ("pytorch",)),
    SkillDefinition("Keras", ("keras",)),
    SkillDefinition("XGBoost", ("xgboost",)),
    SkillDefinition("LightGBM", ("lightgbm",)),
    SkillDefinition("CatBoost", ("catboost",)),
    SkillDefinition("Transformers", ("transformers", "hugging face transformers")),
    SkillDefinition("Hugging Face", ("hugging face", "huggingface")),
    SkillDefinition("NLP", ("nlp", "natural language processing")),
    SkillDefinition("Computer Vision", ("computer vision", "cv")),
    SkillDefinition("Reinforcement Learning", ("reinforcement learning", "rl")),
    SkillDefinition("Supervised Learning", ("supervised learning",)),
    SkillDefinition("Unsupervised Learning", ("unsupervised learning",)),
    SkillDefinition("Model Evaluation", ("model evaluation", "evaluation metrics")),
    SkillDefinition("Feature Selection", ("feature selection",)),
    SkillDefinition("Feature Engineering", ("feature engineering",)),
    SkillDefinition("Model Serving", ("model serving", "serving")),
    SkillDefinition("MLOps", ("mlops", "machine learning operations")),
    SkillDefinition("LLM", ("llm", "large language model", "large language models")),
    SkillDefinition("Generative AI", ("generative ai", "genai")),
    SkillDefinition("Prompt Engineering", ("prompt engineering",)),
    SkillDefinition("LangChain", ("langchain",)),
    SkillDefinition("LlamaIndex", ("llamaindex",)),
    SkillDefinition("Vector Database", ("vector database", "vector db")),
    SkillDefinition("Embeddings", ("embeddings",)),
    SkillDefinition("RAG", ("rag", "retrieval augmented generation")),
    SkillDefinition("Fine-tuning", ("fine-tuning", "finetuning")),
    SkillDefinition("Model Monitoring", ("model monitoring",)),
    SkillDefinition("ML Platform", ("ml platform", "machine learning platform")),

    # Software engineering / frontend / backend
    SkillDefinition("Java", ("java",)),
    SkillDefinition("Kotlin", ("kotlin",)),
    SkillDefinition("Scala", ("scala",)),
    SkillDefinition("Go", ("go", "golang")),
    SkillDefinition("Rust", ("rust",)),
    SkillDefinition("C", ("c",)),
    SkillDefinition("C++", ("c++", "cpp")),
    SkillDefinition("C#", ("c#", "c sharp")),
    SkillDefinition("TypeScript", ("typescript", "ts")),
    SkillDefinition("JavaScript", ("javascript", "js")),
    SkillDefinition("Ruby", ("ruby",)),
    SkillDefinition("PHP", ("php",)),
    SkillDefinition("Swift", ("swift",)),
    SkillDefinition("Objective-C", ("objective-c", "objective c")),
    SkillDefinition("R", ("r language", "r")),
    SkillDefinition("MATLAB", ("matlab",)),
    SkillDefinition("Bash", ("bash", "shell scripting")),
    SkillDefinition("PowerShell", ("powershell",)),
    SkillDefinition("Node.js", ("node.js", "nodejs", "node")),
    SkillDefinition("React", ("react", "reactjs")),
    SkillDefinition("React Native", ("react native",)),
    SkillDefinition("Vue", ("vue", "vue.js", "vuejs")),
    SkillDefinition("Angular", ("angular", "angularjs")),
    SkillDefinition("Next.js", ("next.js", "nextjs", "next")),
    SkillDefinition("Svelte", ("svelte",)),
    SkillDefinition("Remix", ("remix", "remix.run")),
    SkillDefinition("Express", ("express", "express.js", "expressjs")),
    SkillDefinition("NestJS", ("nestjs", "nest.js", "nest")),
    SkillDefinition("Django", ("django",)),
    SkillDefinition("Flask", ("flask",)),
    SkillDefinition("Fastify", ("fastify",)),
    SkillDefinition("Spring Boot", ("spring boot",)),
    SkillDefinition("ASP.NET", ("asp.net", "aspnet")),
    SkillDefinition(".NET", (".net", "dotnet")),
    SkillDefinition("Rails", ("rails", "ruby on rails")),
    SkillDefinition("Gin", ("gin", "gin-gonic")),
    SkillDefinition("Fiber", ("fiber", "gofiber")),
    SkillDefinition("GraphQL", ("graphql",)),
    SkillDefinition("REST", ("rest", "rest api", "api design")),
    SkillDefinition("gRPC", ("grpc",)),
    SkillDefinition("Microservices", ("microservices",)),
    SkillDefinition("Distributed Systems", ("distributed systems",)),
    SkillDefinition("Concurrency", ("concurrency", "parallelism")),
    SkillDefinition("Async IO", ("async io", "async", "asynchronous")),
    SkillDefinition("Algorithms", ("algorithms",)),
    SkillDefinition("Data Structures", ("data structures",)),
    SkillDefinition("System Design", ("system design",)),
    SkillDefinition("Object-Oriented Programming", ("object-oriented programming", "oop")),
    SkillDefinition("Observability", ("observability",)),
    SkillDefinition("Prometheus", ("prometheus",)),
    SkillDefinition("Grafana", ("grafana",)),
    SkillDefinition("Jenkins", ("jenkins",)),
    SkillDefinition("GitHub Actions", ("github actions",)),
    SkillDefinition("CircleCI", ("circleci",)),
    SkillDefinition("Argo CD", ("argo cd",)),
    SkillDefinition("Ansible", ("ansible",)),
    SkillDefinition("Chef", ("chef",)),
    SkillDefinition("Puppet", ("puppet",)),
    SkillDefinition("Helm", ("helm",)),
    SkillDefinition("Kustomize", ("kustomize",)),
    SkillDefinition("OpenTelemetry", ("opentelemetry", "otel")),
    SkillDefinition("Serverless", ("serverless", "serverless architecture")),
    SkillDefinition("Infrastructure as Code", ("infrastructure as code", "iac")),
    SkillDefinition("Distributed Tracing", ("distributed tracing",)),
    SkillDefinition("Feature Flags", ("feature flags", "feature flag")),

    # Specific enterprise / SaaS tools that are legitimately resume-listable
    SkillDefinition("Webhooks", ("webhooks", "webhook")),
    SkillDefinition("Jira", ("jira",)),
    SkillDefinition("Confluence", ("confluence",)),
    SkillDefinition("Salesforce", ("salesforce",)),
    SkillDefinition("NetSuite", ("netsuite", "oracle netsuite")),
    SkillDefinition("QuickBooks", ("quickbooks", "quickbooks online", "quickbooks desktop")),
    SkillDefinition("Sage Intacct", ("sage intacct",)),
    SkillDefinition("Xero", ("xero",)),
    SkillDefinition("Workday", ("workday",)),
    SkillDefinition("Coupa", ("coupa",)),
    SkillDefinition("SAP", ("sap",)),
    SkillDefinition("ServiceNow", ("servicenow",)),
    SkillDefinition("HubSpot", ("hubspot",)),
    SkillDefinition("Zendesk", ("zendesk",)),
    SkillDefinition("Intercom", ("intercom",)),
)

_NORMALIZE_RE = re.compile(r"[^a-z0-9+/.-]+")
_HTML_HINT_RE = re.compile(r"<[^>]+>")
_SECTION_HEADER_RE = re.compile(
    r"^(what you(?:'|)ll do(?: at .*)?|what you'll do|what you need|we(?:'|)d love to hear from you(?: if you have)?|"
    r"requirements?|qualifications?|preferred qualifications|minimum qualifications|must have|you have|"
    r"what you'll need|what you will need|about you|ideal candidate|desired qualifications?)[:\s]*$",
    re.IGNORECASE,
)
_SKILL_CANDIDATE_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b|\bor\b|\&)\s*", re.IGNORECASE)
_SKILL_PREFIX_RE = re.compile(
    r"^(?:experience|familiarity|knowledge|proficiency|fluency|expertise|comfort|comfortable|"
    r"working knowledge|working with|hands-?on experience|hands-?on|good understanding of|"
    r"strong understanding of|strong knowledge of|strong background in|background in|"
    r"strong programming skills in|strong skills in|programming skills in|"
    r"experience with|experience in|experience using|experience supporting|experience building|"
    r"experience developing|experience managing|experience leading|familiar with|"
    r"looking for|we need|we're looking for|must have|ability to|bonus experience in)\s*"
    r"(?:with|in|of|using|building|developing|supporting|managing|leading)?\s*",
    re.IGNORECASE,
)
_SKILL_TRAILING_RE = re.compile(
    r"(?:\s+(?:tools?|platforms?|platform|systems?|stack|experience|expertise|knowledge|skills?))+$",
    re.IGNORECASE,
)
_SKILL_SKIP_PHRASES = {
    "a plus",
    "ability to learn",
    "about you",
    "benefits",
    "communication skills",
    "employment type",
    "equal opportunity",
    "great things",
    "job code",
    "job information",
    "location",
    "minimum qualifications",
    "nice to have",
    "preferred qualifications",
    "regular",
    "problem-solving",
    "problem solving",
    "related discipline",
    "results-oriented",
    "self-driven",
    "strong analytical",
    "strong communication",
    "team player",
    "technology",
    "what you need",
    "what you'll do",
    "what you will need",
    "who you are",
    "why we love",
}
_REQUIREMENT_START_RE = re.compile(
    r"^(what you need|what you(?:'|)ll need|we(?:'|)d love to hear from you(?: if you have)?|"
    r"minimum qualifications|required qualifications|basic qualifications|"
    r"requirements?|qualifications?|must have|you have|ideal candidate|desired qualifications?)",
    re.IGNORECASE,
)
_REQUIREMENT_END_RE = re.compile(
    r"^(while not required|nice to have|preferred qualifications|bonus|bonus points|about the role|"
    r"what you(?:'|)ll do(?: at .*)?|pay transparency|equal opportunity|benefits?|"
    r"job information|job info|about (?:us|the company|the team)|how to apply|"
    r"application process|life at|perks?|compensation)",
    re.IGNORECASE,
)

# EEO / diversity / legal / benefits boilerplate — once any of this shows up,
# everything after it is legal text and must not be scanned for "skills".
_EEO_BOILERPLATE_RE = re.compile(
    r"("
    r"equal opportunity|equal employment|do not discriminate|without regard to|"
    r"race,?\s*color|national origin|sexual orientation|gender identity|"
    r"veteran status|disability status|marital status|protected class|protected veteran|"
    r"regardless of race|e-verify|eeo|affirmative action|"
    r"pay transparency|salary range|compensation range|base salary|"
    r"comprehensive benefits|competitive salary|competitive compensation|"
    r"by applying|by submitting|privacy policy|background check"
    r")",
    re.IGNORECASE,
)


def _normalize_phrase(text: str) -> str:
    text = text.lower().strip()
    text = _NORMALIZE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pattern_for(alias: str) -> re.Pattern[str]:
    parts = [_escape_token(part) for part in alias.split()]
    body = r"\s+".join(parts)
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _escape_token(token: str) -> str:
    return re.escape(token)


@lru_cache(maxsize=1)
def _registry() -> tuple[tuple[str, tuple[re.Pattern[str], ...]], dict[str, str]]:
    compiled: list[tuple[str, tuple[re.Pattern[str], ...]]] = []
    alias_to_canonical: dict[str, str] = {}
    for definition in _SKILL_DEFINITIONS:
        patterns = tuple(_pattern_for(alias) for alias in definition.aliases)
        compiled.append((definition.canonical, patterns))
        for alias in definition.aliases:
            alias_to_canonical[_normalize_phrase(alias)] = definition.canonical
        alias_to_canonical[_normalize_phrase(definition.canonical)] = definition.canonical
    return tuple(compiled), alias_to_canonical


def canonicalize_skill(skill: str) -> str:
    """Map a raw skill label to the canonical skill name if known."""
    _, alias_to_canonical = _registry()
    return alias_to_canonical.get(_normalize_phrase(skill), skill.strip())


def canonicalize_skills(skills: list[str]) -> list[str]:
    """Deduplicate and canonicalize a raw skill list."""
    result: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        canonical = canonicalize_skill(skill)
        if canonical and canonical not in seen:
            result.append(canonical)
            seen.add(canonical)
    return result


def extract_skills(text: str | None) -> list[str]:
    """Extract canonical skills found in free text using the master vocabulary."""
    if not text:
        return []

    text = _normalize_job_text(text)
    text = _extract_requirement_surface(text)
    compiled, _ = _registry()
    found: list[str] = []
    seen: set[str] = set()
    for canonical, patterns in compiled:
        if canonical in seen:
            continue
        if any(pattern.search(text) for pattern in patterns):
            found.append(canonical)
            seen.add(canonical)
    return found


def extract_unknown_skill_terms(text: str | None, *, limit: int = 20) -> list[str]:
    """Extract skill-like terms from requirement text not in the master vocabulary.

    Disabled for board display: Aggregator/JobSpy JDs mix page chrome (Location,
    Job Code, title fragments) with prose, and the heuristic regularly dumps
    that noise into missing_master. Prefer profile missing_skills instead.
    """
    return []


# Minimum "skill count" denominator so jobs with 1-2 detected skills can't score 1.00.
# A legit data engineering posting lists 5+ skills; short / off-topic postings don't.
_MIN_SKILL_FLOOR = 5


def skill_match_summary(
    job_text: str | None,
    profile_skills: list[str],
    *,
    company_name: str | None = None,
) -> tuple[list[str], list[str], list[str], float]:
    """Return (matched_skills, missing_profile_skills, missing_master_skills, keyword_score)."""
    job_skills = extract_skills(job_text)

    # Don't let the company name itself count as a skill (e.g. jobs AT Snowflake matching "Snowflake").
    if company_name:
        company_canonical = canonicalize_skill(company_name)
        job_skills = [s for s in job_skills if s != company_canonical]

    if not job_skills:
        return [], [], extract_unknown_skill_terms(job_text), 0.0

    profile_set = set(canonicalize_skills(profile_skills))
    matched = [skill for skill in job_skills if skill in profile_set]
    missing_profile = [skill for skill in job_skills if skill not in profile_set]
    missing_master = extract_unknown_skill_terms(job_text)
    score = len(matched) / max(_MIN_SKILL_FLOOR, len(job_skills))
    return matched, missing_profile, missing_master, score


def _normalize_job_text(text: str) -> str:
    if _HTML_HINT_RE.search(text):
        try:
            from jobtracker.normalize.html import html_to_text

            text = html_to_text(text)
        except Exception:
            pass
    # JobSpy / markdown scrapes escape punctuation: large\-scale, C\+\+
    text = (
        text.replace("\\-", "-")
        .replace("\\+", "+")
        .replace("\\*", "*")
        .replace("\\_", "_")
    )
    # Strip bold/italic markers so section headers still match.
    text = re.sub(r"\*{1,3}", "", text)
    return _strip_eeo_boilerplate(text)


def _strip_eeo_boilerplate(text: str) -> str:
    """Cut the text at the first EEO / benefits / legal boilerplate phrase.

    Everything from that phrase onward is legal text (equal-opportunity statements,
    salary ranges, privacy policies) and must not be scanned for skill-like terms.

    Operates on the raw string rather than line-by-line because some upstream
    cleaners (html_to_text) collapse the whole description into a single line.
    """
    match = _EEO_BOILERPLATE_RE.search(text)
    if match is None:
        return text
    cutoff = text.rfind("\n", 0, match.start())
    if cutoff == -1:
        cutoff = text.rfind(". ", 0, match.start())
    if cutoff == -1:
        cutoff = match.start()
    return text[:cutoff]


def _extract_requirement_surface(text: str) -> str:
    """Prefer the requirements block so we score against requirements, not marketing copy."""
    lines = [_strip_line_markup(line) for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if line]
    if not lines:
        return text

    surfaces: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _REQUIREMENT_START_RE.search(line):
            block: list[str] = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if _REQUIREMENT_END_RE.search(next_line):
                    break
                # Nested "Minimum Qualifications" under a bare "Qualifications"
                # header is still requirement content — don't cut the block.
                if _SECTION_HEADER_RE.search(next_line) and not _REQUIREMENT_START_RE.search(
                    next_line
                ):
                    break
                block.append(next_line)
                j += 1
            if block:
                surfaces.extend(block)
            i = j
            continue
        i += 1

    if surfaces:
        return "\n".join(surfaces)
    return text


def _has_requirement_section(text: str) -> bool:
    lines = [_strip_line_markup(line) for line in text.splitlines() if line.strip()]
    return any(_REQUIREMENT_START_RE.search(line) for line in lines)


def _strip_line_markup(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"^[•*\-–—]+\s*", "", line)
    line = re.sub(r"\*{1,3}", "", line)
    return line.strip()


def _iter_skill_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for line in text.splitlines():
        line = _strip_line_markup(line)
        if not line:
            continue
        pieces = _SKILL_CANDIDATE_SPLIT_RE.split(line)
        if not pieces:
            pieces = [line]
        for piece in pieces:
            piece = piece.strip(" .:;,-–—()[]{}")
            if piece:
                if "/" in piece and canonicalize_skill(piece) == piece.strip():
                    candidates.extend(
                        subpiece.strip(" .:;,-–—()[]{}")
                        for subpiece in piece.split("/")
                        if subpiece.strip()
                    )
                else:
                    candidates.append(piece)
    return candidates


def _clean_skill_candidate(candidate: str) -> str:
    text = candidate.strip()
    text = re.sub(r"^(?:and|or)\s+", "", text, flags=re.IGNORECASE)
    text = _SKILL_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"^(?:both|either|any|all|the|a|an)\s+", "", text, flags=re.IGNORECASE)
    text = _SKILL_TRAILING_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\\-", "-").replace("\\+", "+")
    return text.strip(" .:;,-–—()[]{}*")


_PROSE_NOISE_RE = re.compile(
    r"\b("
    r"who|whom|which|that|have|has|had|are|is|was|were|been|being|"
    r"completing|completed|recently|individuals|bachelor|degree|"
    r"foundation|understanding|curiosity|ability|oriented|driven|"
    r"especially|including|related|discipline|following|areas|"
    r"qualifications?|responsibilities|information|preferred|minimum|"
    r"combining|optimize|tackle|unlock|improve|develop|build"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_skill_candidate(candidate: str) -> bool:
    normalized = _normalize_phrase(candidate)
    if not normalized:
        return False
    if normalized in _SKILL_SKIP_PHRASES:
        return False
    if re.search(r"\b\d+\+?\s*years?\b", normalized):
        return False
    if "relevant field" in normalized or "relevant experience" in normalized:
        return False
    words = normalized.split()
    if len(words) > 5:
        return False
    if not re.search(r"[a-z0-9]", normalized):
        return False
    if normalized in {"and", "or", "with", "for", "from", "the", "a", "an"}:
        return False
    # Reject JD prose fragments / soft-skill fluff, keep short tech tokens.
    if _PROSE_NOISE_RE.search(normalized) and len(words) > 2:
        return False
    if _PROSE_NOISE_RE.fullmatch(normalized):
        return False
    if normalized.endswith(":**") or normalized.endswith(":"):
        return False
    # Job-portal metadata / city lines that sneak past section cuts.
    if re.fullmatch(r"[a-z]+(?: [a-z]+)?, [a-z]{2}(?: us)?", normalized):
        return False
    if re.fullmatch(r"a?\d+[a-z]?", normalized):  # job codes like a118976
        return False
    return True
