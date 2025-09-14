"""
projsize.py - One-file Python project report

Metrics (1–8) + Static Checks:
 1) SLOC（総計 / src-only / tests-only）
 2) LLOC（論理行 = AST statements）
 3) Files / Packages（`__init__.py`）
 4) Functions / Classes / Methods
 5) Cyclomatic Complexity（avg / p95 / max）
 6) Dependencies（Direct from pyproject/requirements; Transitive best-effort）
 7) Type Hint Coverage（定義完全注釈・引数注釈）
 8) Docstring Coverage（module/class/function）
 +) Static Checks（技術向けの追加入り口）
    - mypy エラー密度（件 / kSLOC）
    - Ruff 違反密度（件 / kSLOC）

Usage:
  python projsize.py [-p PATH] [-o md|json] [--tests-dir tests]
"""

import argparse
import ast
import json
import re
import shutil
import subprocess
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Optional, Set

try:
    # Python 3.8+: importlib_metadata backport fallback
    from importlib.metadata import PackageNotFoundError, distribution
except Exception:  # pragma: no cover
    try:
        from importlib_metadata import PackageNotFoundError, distribution  # type: ignore
    except Exception:
        distribution = None  # type: ignore
        PackageNotFoundError = Exception  # type: ignore


EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    "venv",
    ".venv",
    "site-packages",
    ".tox",
    ".eggs",
}
TEST_DIR_DEFAULT = "tests"


# ---------- Helpers ----------
def is_test_path(path: Path, tests_dir_name: str) -> bool:
    p = str(path).replace("\\", "/")
    name = path.name
    if (
        f"/{tests_dir_name}/" in p
        or p.endswith(f"/{tests_dir_name}")
        or p.startswith(f"{tests_dir_name}/")
    ):
        return True
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if re.search(r"/tests?/", p):
        return True
    return False


def iter_py_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


# ---------- SLOC ----------
import tokenize as _tokenize


def count_sloc(py_path: Path) -> int:
    try:
        with open(py_path, "rb") as f:
            tokens = _tokenize.tokenize(f.readline)
            seen_lines: Set[int] = set()
            for tok in tokens:
                if tok.type in (
                    _tokenize.NL,
                    _tokenize.NEWLINE,
                    _tokenize.COMMENT,
                    _tokenize.INDENT,
                    _tokenize.DEDENT,
                    _tokenize.ENCODING,
                    _tokenize.ENDMARKER,
                ):
                    continue
                if tok.start:
                    seen_lines.add(tok.start[0])
            return len(seen_lines)
    except Exception:
        try:
            text = py_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0
        return sum(
            1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
        )


# ---------- AST utilities ----------
STMT_TYPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Return,
    ast.Delete,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.Raise,
    ast.Try,
    ast.Assert,
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Expr,
    ast.Match,  # py3.10+
)


def is_docstring_expr(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Str)


def count_lloc(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, STMT_TYPES):
            if isinstance(node, ast.Expr) and is_docstring_expr(node):
                continue
            count += 1
    return count


# Cyclomatic Complexity（簡易McCabe）
DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.ExceptHandler,
    ast.IfExp,
)


def function_complexity(fn: ast.AST) -> int:
    comp = 1
    for node in ast.walk(fn):
        if isinstance(node, DECISION_NODES):
            comp += 1
        elif isinstance(node, ast.BoolOp):
            comp += max(0, len(node.values) - 1)
        elif isinstance(node, ast.Try):
            comp += len(node.handlers)
        elif isinstance(node, ast.comprehension):
            comp += len(node.ifs)
        elif hasattr(ast, "Match") and isinstance(node, getattr(ast, "Match", ())):
            comp += len(getattr(node, "cases", []))
    return comp


# Type hint coverage
@dataclass
class TypeHintStats:
    total_defs: int = 0
    fully_typed_defs: int = 0
    total_params: int = 0
    typed_params: int = 0

    @property
    def def_coverage(self) -> float:
        return (self.fully_typed_defs / self.total_defs) * 100 if self.total_defs else 0.0

    @property
    def param_coverage(self) -> float:
        return (self.typed_params / self.total_params) * 100 if self.total_params else 0.0


@dataclass
class DocstringStats:
    modules_total: int = 0
    modules_with: int = 0
    classes_total: int = 0
    classes_with: int = 0
    funcs_total: int = 0
    funcs_with: int = 0

    @property
    def module_cov(self) -> float:
        return (self.modules_with / self.modules_total) * 100 if self.modules_total else 0.0

    @property
    def class_cov(self) -> float:
        return (self.classes_with / self.classes_total) * 100 if self.classes_total else 0.0

    @property
    def func_cov(self) -> float:
        return (self.funcs_with / self.funcs_total) * 100 if self.funcs_total else 0.0


@dataclass
class ComplexityStats:
    per_function: List[int]

    @property
    def avg(self) -> float:
        return mean(self.per_function) if self.per_function else 0.0

    @property
    def p95(self) -> float:
        if not self.per_function:
            return 0.0
        arr = sorted(self.per_function)
        idx = int((0.95 * len(arr) + 0.9999)) - 1
        idx = max(0, min(idx, len(arr) - 1))
        return float(arr[idx])

    @property
    def max(self) -> int:
        return max(self.per_function) if self.per_function else 0


# ---------- Dependency parsing ----------
REQ_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")


def parse_requirements_txt(path: Path) -> List[str]:
    deps: List[str] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            pkg = re.split(r"[<>=!~\[]", line)[0].strip()
            if pkg:
                deps.append(pkg.lower())
    except Exception:
        pass
    return deps


def parse_pyproject_toml(path: Path) -> List[str]:
    deps: List[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return deps
    proj_deps = re.findall(r"^\s*dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
    if proj_deps:
        deps_str = proj_deps[0]
        for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', deps_str):
            token = m.group(1) or m.group(2) or ""
            pkg = re.split(r"[<>=!~\[]", token)[0].strip()
            if pkg:
                deps.append(pkg.lower())
    m = re.search(r"^\s*\[tool\.poetry\.dependencies\]\s*(.*?)^\s*\[", text + "\n[", re.M | re.S)
    if m:
        body = m.group(1)
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = re.match(r"^([A-Za-z0-9_.\-]+)\s*=", line)
            if key:
                name = key.group(1)
                if name.lower() != "python":
                    deps.append(name.lower())
    return sorted(set(deps))


def collect_direct_deps(root: Path) -> List[str]:
    out: Set[str] = set()
    p = root / "pyproject.toml"
    if p.exists():
        out.update(parse_pyproject_toml(p))
    for req in root.glob("requirements*.txt"):
        out.update(parse_requirements_txt(req))
    req_dir = root / "requirements"
    if req_dir.exists():
        for req in req_dir.glob("*.txt"):
            out.update(parse_requirements_txt(req))
    return sorted(out)


def find_project_root(start: Path) -> Path:
    """Walk up from start to find a directory that looks like the project root."""
    cur = start.resolve()
    for p in [cur] + list(cur.parents):
        try:
            entries = {e.name for e in p.iterdir()}
        except Exception:
            continue
        if ("pyproject.toml" in entries) or ("poetry.lock" in entries):
            return p
        if ("requirements" in entries) or any(
            name.startswith("requirements") and name.endswith(".txt") for name in entries
        ):
            return p
    return start


def resolve_transitive_count(direct: List[str]) -> int:
    """Best-effort transitive dependency count using installed distributions metadata."""
    if not direct or distribution is None:
        return 0
    seen: Set[str] = set()
    q = deque([d for d in direct])
    while q:
        name = q.popleft()
        lname = name.lower()
        if lname in seen:
            continue
        seen.add(lname)
        try:
            dist = distribution(name)  # type: ignore
        except PackageNotFoundError:
            continue
        requires = dist.requires or []
        for req in requires:
            pkg = re.split(r"[<>=!~;\s\[]", req.strip())[0]
            if pkg:
                q.append(pkg)
    return max(0, len(seen) - len(set(d.lower() for d in direct)))


# ---------- Static checks: mypy / ruff ----------
def run_mypy_error_count(path_arg: Path, cwd: Path) -> Optional[int]:
    if not shutil.which("mypy"):
        return None
    try:
        # Run in project root (so that mypy.ini/pyproject is honored)
        cmd = [
            "mypy",
            str(path_arg),
            "--hide-error-context",
            "--no-color-output",
            "--show-error-codes",
        ]
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(cwd),
            check=False,
        )
        m = re.search(r"Found\s+(\d+)\s+error", p.stdout)
        if m:
            return int(m.group(1))
        # If no "Found N errors" line, assume 0 if exit code is 0
        return 0 if p.returncode == 0 else None
    except Exception:
        return None


def run_ruff_violation_count(path_arg: Path, cwd: Path) -> Optional[int]:
    if not shutil.which("ruff"):
        return None
    try:
        cmd = ["ruff", "check", str(path_arg), "--output-format=json"]
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(cwd),
            check=False,
        )
        data = json.loads(p.stdout or "[]")
        if isinstance(data, list):
            return len(data)
        return None
    except Exception:
        return None


# ---------- Analysis ----------
@dataclass
class FileStats:
    path: str
    is_test: bool
    sloc: int
    lloc: int
    functions: int
    classes: int
    methods: int
    func_complexities: List[int]
    has_module_doc: bool
    type_stats: "TypeHintStats"
    doc_stats: "DocstringStats"


def analyze_file(path: Path, tests_dir_name: str) -> Optional["FileStats"]:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return None

    is_test = is_test_path(path, tests_dir_name)
    sloc = count_sloc(path)
    lloc = count_lloc(tree)

    func_count = 0
    class_count = 0
    method_count = 0
    func_complexities: List[int] = []
    type_stats = TypeHintStats()
    doc_stats = DocstringStats(modules_total=1, modules_with=1 if ast.get_docstring(tree) else 0)

    # set parent pointers to detect methods
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            setattr(child, "parent", node)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_count += 1
            if isinstance(getattr(node, "parent", None), ast.ClassDef):
                method_count += 1
            func_complexities.append(function_complexity(node))
            type_stats.total_defs += 1

            ann_all = True
            params = []
            args = node.args
            params.extend(args.posonlyargs or [])
            params.extend(args.args or [])
            if args.vararg:
                params.append(args.vararg)
            params.extend(args.kwonlyargs or [])
            if args.kwarg:
                params.append(args.kwarg)
            for a in params:
                name = getattr(a, "arg", "")
                if name in ("self", "cls"):
                    continue
                type_stats.total_params += 1
                if getattr(a, "annotation", None) is not None:
                    type_stats.typed_params += 1
                else:
                    ann_all = False
            if node.returns is None:
                ann_all = False
            if ann_all:
                type_stats.fully_typed_defs += 1

            doc_stats.funcs_total += 1
            if ast.get_docstring(node):
                doc_stats.funcs_with += 1

        elif isinstance(node, ast.ClassDef):
            class_count += 1
            doc_stats.classes_total += 1
            if ast.get_docstring(node):
                doc_stats.classes_with += 1

    return FileStats(
        path=str(path),
        is_test=is_test,
        sloc=sloc,
        lloc=lloc,
        functions=func_count,
        classes=class_count,
        methods=method_count,
        func_complexities=func_complexities,
        has_module_doc=bool(ast.get_docstring(tree)),
        type_stats=type_stats,
        doc_stats=doc_stats,
    )


def count_packages(root: Path, tests_dir_name: str) -> int:
    count = 0
    for d in root.rglob("__init__.py"):
        if any(part in EXCLUDE_DIRS for part in d.parts):
            continue
        if is_test_path(d, tests_dir_name):
            continue
        count += 1
    return count


# ---------- Coverage XML ----------
def read_coverage_xml(root: Path) -> Optional[float]:
    candidates = [root / "coverage.xml", root / "reports" / "coverage.xml"]
    for p in candidates:
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'line-rate="([0-9.]+)"', text)
                if m:
                    return float(m.group(1)) * 100.0
            except Exception:
                pass
    return None


# ---------- Reporting ----------
@dataclass
class Summary:
    root: str
    total_files: int
    total_modules: int
    total_packages: int

    sloc_total: int
    sloc_src: int
    sloc_tests: int

    lloc_total: int

    functions: int
    classes: int
    methods: int

    cc_avg: float
    cc_p95: float
    cc_max: int
    cc_functions_measured: int

    direct_deps: int
    transitive_deps: int
    direct_dep_names: List[str]

    type_def_cov: float
    type_param_cov: float

    doc_module_cov: float
    doc_class_cov: float
    doc_func_cov: float

    test_coverage_percent: Optional[float]

    # --- Static checks ---
    mypy_errors: Optional[int]
    mypy_errors_per_kSLOC: Optional[float]
    ruff_violations: Optional[int]
    ruff_violations_per_kSLOC: Optional[float]


def format_md(summary: Summary) -> str:
    lines = []
    lines.append(f"# Project Size Report: `{summary.root}`")
    lines.append("")
    lines.append("## Size & Structure")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Files (.py) | {summary.total_files} |")
    lines.append(f"| Packages (dirs with `__init__.py`) | {summary.total_packages} |")
    lines.append(f"| SLOC (total) | {summary.sloc_total} |")
    lines.append(f"| SLOC (src only) | {summary.sloc_src} |")
    lines.append(f"| SLOC (tests only) | {summary.sloc_tests} |")
    lines.append(f"| LLOC (total statements) | {summary.lloc_total} |")
    lines.append(
        f"| Functions / Methods / Classes | {summary.functions} / {summary.methods} / {summary.classes} |"
    )
    lines.append("")
    lines.append("## Complexity (Cyclomatic)")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Functions measured | {summary.cc_functions_measured} |")
    lines.append(f"| CC average | {summary.cc_avg:.2f} |")
    lines.append(f"| CC p95 | {summary.cc_p95:.2f} |")
    lines.append(f"| CC max | {summary.cc_max} |")
    lines.append("")
    lines.append("## Dependencies")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Direct dependencies | {summary.direct_deps} |")
    lines.append(f"| Transitive dependencies (best-effort) | {summary.transitive_deps} |")
    if summary.direct_dep_names:
        lines.append("")
        lines.append("<details><summary>Direct dependency names</summary>")
        lines.append("")
        lines.append(", ".join(sorted(summary.direct_dep_names)))
        lines.append("")
        lines.append("</details>")
    lines.append("")
    lines.append("## Coverage & Docs")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    cov = (
        f"{summary.test_coverage_percent:.1f}%"
        if summary.test_coverage_percent is not None
        else "N/A"
    )
    lines.append(f"| Test coverage (from coverage.xml) | {cov} |")
    lines.append(f"| Type hint coverage (defs fully typed) | {summary.type_def_cov:.1f}% |")
    lines.append(f"| Type hint coverage (parameters) | {summary.type_param_cov:.1f}% |")
    lines.append(
        f"| Docstring coverage (modules/classes/functions) | {summary.doc_module_cov:.1f}% / {summary.doc_class_cov:.1f}% / {summary.doc_func_cov:.1f}% |"
    )
    lines.append("")
    lines.append("## Static Checks (Engineering)")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    me = "N/A" if summary.mypy_errors is None else str(summary.mypy_errors)
    mdens = (
        "N/A" if summary.mypy_errors_per_kSLOC is None else f"{summary.mypy_errors_per_kSLOC:.2f}"
    )
    rv = "N/A" if summary.ruff_violations is None else str(summary.ruff_violations)
    rdens = (
        "N/A"
        if summary.ruff_violations_per_kSLOC is None
        else f"{summary.ruff_violations_per_kSLOC:.2f}"
    )
    lines.append(f"| mypy errors | {me} |")
    lines.append(f"| mypy errors / kSLOC | {mdens} |")
    lines.append(f"| ruff violations | {rv} |")
    lines.append(f"| ruff violations / kSLOC | {rdens} |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Python project report")
    ap.add_argument("-p", "--path", default=".", help="Analysis root path (default: .)")
    ap.add_argument("-o", "--output", default="md", choices=["md", "json"], help="Output format")
    ap.add_argument(
        "--tests-dir",
        default=TEST_DIR_DEFAULT,
        help=f"Tests directory name (default: {TEST_DIR_DEFAULT})",
    )
    args = ap.parse_args()

    root = Path(args.path).resolve()
    py_files = list(iter_py_files(root))

    file_stats: List["FileStats"] = []
    for f in py_files:
        st = analyze_file(f, args.tests_dir)
        if st:
            file_stats.append(st)

    total_files = len(file_stats)
    total_packages = count_packages(root, args.tests_dir)

    sloc_total = sum(s.sloc for s in file_stats)
    sloc_tests = sum(s.sloc for s in file_stats if s.is_test)
    sloc_src = sloc_total - sloc_tests

    lloc_total = sum(s.lloc for s in file_stats)

    functions = sum(s.functions for s in file_stats)
    classes = sum(s.classes for s in file_stats)
    methods = sum(s.methods for s in file_stats)
    cc_list = [cc for s in file_stats for cc in s.func_complexities]
    cc_stats = ComplexityStats(cc_list)

    # Type hints
    ts = TypeHintStats()
    for s in file_stats:
        ts.total_defs += s.type_stats.total_defs
        ts.fully_typed_defs += s.type_stats.fully_typed_defs
        ts.total_params += s.type_stats.total_params
        ts.typed_params += s.type_stats.typed_params

    # Docstrings
    ds = DocstringStats()
    for s in file_stats:
        ds.modules_total += s.doc_stats.modules_total
        ds.modules_with += s.doc_stats.modules_with
        ds.classes_total += s.doc_stats.classes_total
        ds.classes_with += s.doc_stats.classes_with
        ds.funcs_total += s.doc_stats.funcs_total
        ds.funcs_with += s.doc_stats.funcs_with

    # Dependencies & coverage
    proj_root_for_deps = find_project_root(root)
    direct_dep_names = collect_direct_deps(proj_root_for_deps)
    transitive = resolve_transitive_count(direct_dep_names)
    coverage_percent = read_coverage_xml(root) or read_coverage_xml(proj_root_for_deps)

    # Static checks (run in project root so config is効く)
    # Target path for tools: make it relative to project root if possible
    try:
        path_arg = str(root.relative_to(proj_root_for_deps))
    except ValueError:
        path_arg = str(root)
    mypy_errors = run_mypy_error_count(Path(path_arg), proj_root_for_deps)
    ruff_viol = run_ruff_violation_count(Path(path_arg), proj_root_for_deps)

    ks = max(sloc_src / 1000.0, 1e-9)
    mypy_density = (mypy_errors / ks) if (mypy_errors is not None) else None
    ruff_density = (ruff_viol / ks) if (ruff_viol is not None) else None

    summary = Summary(
        root=str(root),
        total_files=total_files,
        total_modules=total_files,
        total_packages=total_packages,
        sloc_total=sloc_total,
        sloc_src=sloc_src,
        sloc_tests=sloc_tests,
        lloc_total=lloc_total,
        functions=functions,
        classes=classes,
        methods=methods,
        cc_avg=round(cc_stats.avg, 2),
        cc_p95=round(cc_stats.p95, 2),
        cc_max=cc_stats.max,
        cc_functions_measured=len(cc_list),
        direct_deps=len(direct_dep_names),
        transitive_deps=transitive,
        direct_dep_names=sorted(direct_dep_names),
        type_def_cov=round(ts.def_coverage, 1),
        type_param_cov=round(ts.param_coverage, 1),
        doc_module_cov=round(ds.module_cov, 1),
        doc_class_cov=round(ds.class_cov, 1),
        doc_func_cov=round(ds.func_cov, 1),
        test_coverage_percent=coverage_percent,
        mypy_errors=mypy_errors,
        mypy_errors_per_kSLOC=(round(mypy_density, 2) if mypy_density is not None else None),
        ruff_violations=ruff_viol,
        ruff_violations_per_kSLOC=(round(ruff_density, 2) if ruff_density is not None else None),
    )

    if args.output == "json":
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    else:
        print(format_md(summary))


if __name__ == "__main__":
    main()
