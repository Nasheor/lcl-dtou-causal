"""The memo, the slide and the README say what the spec requires and nothing it forbids."""
import re

MARKDOWN = ["README.md", "PREREGISTRATION.md", "LICENCE_CHECK.md", "docs/memo.md", "docs/partner_slide.md"]
DOCS = ("docs/memo.md", "docs/partner_slide.md", "README.md")
CLAIMS_RANDOMISED = [
    re.compile(r"assignment (to [^.]{0,40})?(was|is) randomi[sz]ed"),
    re.compile(r"(households|participants|customers) were randomi[sz]ed"),
    re.compile(r"randomly (assigned|allocated)"),
    re.compile(r"randomi[sz]ed (controlled )?trial"),
    re.compile(r"random assignment (was|is) (used|valid|in place)"),
]


def test_design_stated_plainly(repo_root):
    """Each document says the trial was opt-in and names the difference-in-differences, and none claims
    randomised assignment as a fact. Counterfactual wording ("under random assignment") is allowed."""
    for name in DOCS:
        text = (repo_root / name).read_text(encoding="utf-8").lower()
        assert "opt-in" in text, name
        assert "difference-in-differences" in text, name
        assert "not randomised" in text, name
        hits = [p.pattern for p in CLAIMS_RANDOMISED if p.search(text)]
        assert not hits, f"{name} claims randomised assignment as a fact: {hits}"


def test_no_semicolons_in_markdown(repo_root):
    for name in MARKDOWN:
        assert ";" not in (repo_root / name).read_text(encoding="utf-8"), name


def test_memo_sections_and_length(repo_root):
    text = (repo_root / "docs" / "memo.md").read_text(encoding="utf-8")
    for h in ("## Question", "## Data", "## Design", "## Results", "## Placebos", "## Caveats", "## What this means for a pilot"):
        assert h in text, h
    assert len(text.split()) <= 1100, "the memo must fit on two pages"


def test_no_forbidden_claims(repo_root):
    for name in ("docs/memo.md", "docs/partner_slide.md", "README.md"):
        text = (repo_root / name).read_text(encoding="utf-8").lower()
        assert "irish" not in text and "ireland" not in text, name
        assert not re.search(r"\bpresented\b", text), name
        assert "claude" not in text and "ai tool" not in text, name


def test_no_deviations_or_well_formed(repo_root):
    p = repo_root / "DEVIATIONS.md"
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    entries = re.findall(r"^## (D\d+) \((\d{4}-\d{2}-\d{2})\)\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    assert entries, "DEVIATIONS.md exists but holds no entry"
    for _, _, body in entries:
        assert "Reason:" in body
        for word in ("outcome", "group", "period", "estimator"):
            assert f"changes the {word}" not in body.lower()
