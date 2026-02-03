"""Project analyzer - scans codebase to generate initial context."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Convention, ProjectContext, TechStack

# File patterns for tech detection
TECH_PATTERNS: dict[str, dict[str, list[str]]] = {
    "languages": {
        "Python": ["*.py", "requirements.txt", "pyproject.toml", "setup.py"],
        "JavaScript": ["*.js", "*.mjs", "package.json"],
        "TypeScript": ["*.ts", "*.tsx", "tsconfig.json"],
        "Java": ["*.java", "pom.xml", "build.gradle"],
        "Go": ["*.go", "go.mod"],
        "Rust": ["*.rs", "Cargo.toml"],
        "Ruby": ["*.rb", "Gemfile"],
        "PHP": ["*.php", "composer.json"],
        "C#": ["*.cs", "*.csproj"],
        "Kotlin": ["*.kt", "*.kts"],
        "Swift": ["*.swift", "Package.swift"],
    },
    "frameworks": {
        "React": ["package.json:react", "*.jsx", "*.tsx"],
        "Vue": ["package.json:vue", "*.vue"],
        "Angular": ["package.json:@angular", "angular.json"],
        "FastAPI": ["requirements.txt:fastapi", "pyproject.toml:fastapi"],
        "Django": ["requirements.txt:django", "manage.py"],
        "Flask": ["requirements.txt:flask"],
        "Spring": ["pom.xml:spring", "build.gradle:spring"],
        "Express": ["package.json:express"],
        "Next.js": ["package.json:next", "next.config.js"],
        "NestJS": ["package.json:@nestjs"],
    },
    "databases": {
        "PostgreSQL": ["*postgres*", "*psycopg*", "*pg_*"],
        "MySQL": ["*mysql*", "*mariadb*"],
        "MongoDB": ["*mongo*", "*pymongo*"],
        "Redis": ["*redis*"],
        "SQLite": ["*.sqlite", "*sqlite3*"],
        "Elasticsearch": ["*elastic*"],
    },
    "tools": {
        "Docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
        "Kubernetes": ["*.yaml:kind: Deployment", "k8s/", "kubernetes/"],
        "GitHub Actions": [".github/workflows/"],
        "GitLab CI": [".gitlab-ci.yml"],
        "Terraform": ["*.tf", "terraform/"],
        "AWS": ["*boto3*", "*aws*", "cloudformation/"],
        "pytest": ["pytest.ini", "conftest.py", "*pytest*"],
        "Jest": ["jest.config.*", "package.json:jest"],
    },
}

# Ignore patterns
IGNORE_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".idea",
    ".vscode",
    ".kira",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
}

IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
}


@dataclass
class AnalysisResult:
    """Result of project analysis."""

    project_name: str
    tech_stack: TechStack
    file_count: int
    primary_language: str
    structure: dict[str, Any] = field(default_factory=dict)
    conventions: list[Convention] = field(default_factory=list)
    overview: str = ""


class ProjectAnalyzer:
    """Analyzes a project directory to extract context."""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self._file_cache: list[Path] = []

    def analyze(self) -> AnalysisResult:
        """Perform full project analysis."""
        # Scan files
        self._scan_files()

        # Detect technologies
        tech_stack = self._detect_tech_stack()

        # Analyze structure
        structure = self._analyze_structure()

        # Detect conventions
        conventions = self._detect_conventions()

        # Determine primary language
        primary_language = self._get_primary_language(tech_stack)

        # Generate overview
        overview = self._generate_overview(tech_stack, structure, primary_language)

        return AnalysisResult(
            project_name=self.project_dir.name,
            tech_stack=tech_stack,
            file_count=len(self._file_cache),
            primary_language=primary_language,
            structure=structure,
            conventions=conventions,
            overview=overview,
        )

    def analyze_to_context(self) -> ProjectContext:
        """Analyze and return a ProjectContext."""
        result = self.analyze()

        return ProjectContext(
            name=result.project_name,
            overview=result.overview,
            tech_stack=result.tech_stack,
            conventions=result.conventions,
            architecture=self._generate_architecture_description(result),
        )

    def _scan_files(self) -> None:
        """Scan project for files."""
        self._file_cache = []

        for root, dirs, files in os.walk(self.project_dir):
            # Filter ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            root_path = Path(root)
            for file in files:
                # Skip ignored files
                if any(file.endswith(p.replace("*", "")) for p in IGNORE_FILES if "*" in p):
                    continue
                if file in IGNORE_FILES:
                    continue

                self._file_cache.append(root_path / file)

    def _detect_tech_stack(self) -> TechStack:
        """Detect technologies used in the project."""
        stack = TechStack()

        for category, techs in TECH_PATTERNS.items():
            detected = self._detect_category(techs)
            if category == "languages":
                stack.languages = detected
            elif category == "frameworks":
                stack.frameworks = detected
            elif category == "databases":
                stack.databases = detected
            elif category == "tools":
                stack.tools = detected

        return stack

    def _detect_category(self, techs: dict[str, list[str]]) -> list[str]:
        """Detect technologies in a category."""
        detected = []

        for tech_name, patterns in techs.items():
            if self._matches_patterns(patterns):
                detected.append(tech_name)

        return detected

    def _matches_patterns(self, patterns: list[str]) -> bool:
        """Check if any pattern matches project files."""
        for pattern in patterns:
            # Pattern with file content check
            if ":" in pattern:
                file_pattern, content = pattern.split(":", 1)
                if self._check_file_content(file_pattern, content):
                    return True
            # Directory pattern
            elif pattern.endswith("/"):
                dir_name = pattern[:-1]
                if (self.project_dir / dir_name).is_dir():
                    return True
            # Glob pattern
            elif "*" in pattern:
                if any(f.match(pattern) for f in self._file_cache):
                    return True
            # Exact file
            else:
                if (self.project_dir / pattern).exists():
                    return True

        return False

    def _check_file_content(self, file_pattern: str, content: str) -> bool:
        """Check if a file contains specific content."""
        # Find matching files
        for file_path in self._file_cache:
            if file_path.match(file_pattern) or file_path.name == file_pattern:
                try:
                    file_content = file_path.read_text(errors="ignore")
                    if content.lower() in file_content.lower():
                        return True
                except Exception:
                    pass
        return False

    def _analyze_structure(self) -> dict[str, Any]:
        """Analyze project structure."""
        structure: dict[str, Any] = {
            "directories": [],
            "entry_points": [],
            "test_dirs": [],
            "config_files": [],
        }

        # Find top-level directories
        for item in self.project_dir.iterdir():
            if item.is_dir() and item.name not in IGNORE_DIRS:
                structure["directories"].append(item.name)

        # Find entry points
        entry_point_patterns = [
            "main.py",
            "app.py",
            "index.py",
            "__main__.py",
            "index.js",
            "index.ts",
            "main.js",
            "main.ts",
            "src/main.*",
            "src/index.*",
            "src/app.*",
        ]
        for pattern in entry_point_patterns:
            matches = list(self.project_dir.glob(pattern))
            for match in matches:
                rel_path = match.relative_to(self.project_dir)
                structure["entry_points"].append(str(rel_path))

        # Find test directories
        test_patterns = ["tests", "test", "spec", "__tests__"]
        for pattern in test_patterns:
            if (self.project_dir / pattern).is_dir():
                structure["test_dirs"].append(pattern)

        # Find config files
        config_patterns = [
            "*.yaml",
            "*.yml",
            "*.json",
            "*.toml",
            "*.ini",
            "*.cfg",
            ".env*",
            "Makefile",
            "Dockerfile",
        ]
        for pattern in config_patterns:
            for match in self.project_dir.glob(pattern):
                if match.is_file():
                    structure["config_files"].append(match.name)

        return structure

    def _detect_conventions(self) -> list[Convention]:
        """Detect coding conventions from the project."""
        conventions = []

        # Check for linting configs
        if (self.project_dir / ".eslintrc.js").exists() or (
            self.project_dir / ".eslintrc.json"
        ).exists():
            conventions.append(
                Convention("linting", "ESLint is configured for JavaScript/TypeScript")
            )

        if (self.project_dir / "pyproject.toml").exists():
            content = (self.project_dir / "pyproject.toml").read_text(errors="ignore")
            if "ruff" in content:
                conventions.append(Convention("linting", "Ruff is configured for Python linting"))
            if "black" in content:
                conventions.append(Convention("formatting", "Black is used for Python formatting"))
            if "mypy" in content:
                conventions.append(Convention("typing", "MyPy is configured for type checking"))

        if (self.project_dir / ".prettierrc").exists() or (
            self.project_dir / ".prettierrc.json"
        ).exists():
            conventions.append(
                Convention("formatting", "Prettier is configured for code formatting")
            )

        # Check test structure
        if (self.project_dir / "tests").is_dir():
            conventions.append(Convention("testing", "Tests are in the tests/ directory"))

        if (self.project_dir / "conftest.py").exists():
            conventions.append(Convention("testing", "pytest fixtures are defined in conftest.py"))

        # Check for src layout
        if (self.project_dir / "src").is_dir():
            conventions.append(Convention("structure", "Uses src/ layout for source code"))

        return conventions

    def _get_primary_language(self, tech_stack: TechStack) -> str:
        """Determine the primary programming language."""
        if not tech_stack.languages:
            return "Unknown"

        # Count files by extension
        ext_counts: Counter[str] = Counter()
        lang_exts = {
            "Python": [".py"],
            "JavaScript": [".js", ".jsx", ".mjs"],
            "TypeScript": [".ts", ".tsx"],
            "Java": [".java"],
            "Go": [".go"],
            "Rust": [".rs"],
            "Ruby": [".rb"],
            "PHP": [".php"],
            "C#": [".cs"],
        }

        for file_path in self._file_cache:
            ext = file_path.suffix.lower()
            for lang, exts in lang_exts.items():
                if ext in exts and lang in tech_stack.languages:
                    ext_counts[lang] += 1

        if ext_counts:
            return ext_counts.most_common(1)[0][0]

        return tech_stack.languages[0]

    def _generate_overview(
        self,
        tech_stack: TechStack,
        structure: dict[str, Any],
        primary_language: str,
    ) -> str:
        """Generate a project overview."""
        lines = []

        # Project type description
        if tech_stack.frameworks:
            frameworks_str = ", ".join(tech_stack.frameworks[:3])
            lines.append(f"A {primary_language} project using {frameworks_str}.")
        else:
            lines.append(f"A {primary_language} project.")

        # Structure info
        if structure.get("entry_points"):
            entry = structure["entry_points"][0]
            lines.append(f"Main entry point: `{entry}`.")

        if structure.get("test_dirs"):
            test_dir = structure["test_dirs"][0]
            lines.append(f"Tests are located in `{test_dir}/`.")

        # File count
        lines.append(f"Contains {len(self._file_cache)} source files.")

        return " ".join(lines)

    def _generate_architecture_description(self, result: AnalysisResult) -> str:
        """Generate architecture description."""
        lines = []

        if result.structure.get("directories"):
            lines.append("**Directory Structure:**")
            for dir_name in sorted(result.structure["directories"])[:10]:
                lines.append(f"- `{dir_name}/`")
            lines.append("")

        if result.structure.get("entry_points"):
            lines.append("**Entry Points:**")
            for entry in result.structure["entry_points"][:5]:
                lines.append(f"- `{entry}`")
            lines.append("")

        if result.tech_stack.databases:
            lines.append("**Data Storage:**")
            for db in result.tech_stack.databases:
                lines.append(f"- {db}")

        return "\n".join(lines) if lines else "*Run `/context refresh` for detailed analysis.*"


def analyze_project(project_dir: Path | None = None) -> AnalysisResult:
    """Analyze a project directory."""
    analyzer = ProjectAnalyzer(project_dir)
    return analyzer.analyze()
