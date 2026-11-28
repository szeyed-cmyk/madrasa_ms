"""Grade scales, GPA and result calculation."""

from __future__ import annotations

# (minimum percentage, letter, grade point)
SCALES: dict[str, dict] = {
    "standard": {
        "label": "Standard 4.00 scale (A+ = 80%+)",
        "max_gp": 4.0,
        "bands": [
            (80, "A+", 4.00),
            (75, "A", 3.75),
            (70, "A-", 3.50),
            (65, "B+", 3.25),
            (60, "B", 3.00),
            (55, "B-", 2.75),
            (50, "C", 2.50),
            (45, "C-", 2.25),
            (40, "D", 2.00),
            (0, "F", 0.00),
        ],
    },
    "bd5": {
        "label": "Bangladesh GPA 5.00 scale (A+ = 80%+, pass 33%)",
        "max_gp": 5.0,
        "bands": [
            (80, "A+", 5.00),
            (70, "A", 4.00),
            (60, "A-", 3.50),
            (50, "B", 3.00),
            (40, "C", 2.00),
            (33, "D", 1.00),
            (0, "F", 0.00),
        ],
    },
}
DEFAULT_SCALE = "standard"


def scale(name: str | None) -> dict:
    return SCALES.get(name or DEFAULT_SCALE, SCALES[DEFAULT_SCALE])


def subject_grade(obtained: float | None, max_marks: float, pass_marks: float | None, scale_name: str | None):
    """Return (letter, grade_point, passed) for one subject. None marks -> ('-', None, None)."""
    if obtained is None or not max_marks:
        return "-", None, None
    pct = obtained / max_marks * 100
    letter, gp = "F", 0.0
    for minimum, band_letter, band_gp in scale(scale_name)["bands"]:
        if pct >= minimum:
            letter, gp = band_letter, band_gp
            break
    if pass_marks is not None and obtained < pass_marks:
        letter, gp = "F", 0.0
    return letter, gp, letter != "F"


def letter_for_gpa(gpa: float, scale_name: str | None) -> str:
    for _minimum, band_letter, band_gp in scale(scale_name)["bands"]:
        if gpa >= band_gp:
            return band_letter
    return "F"


def summarize(subjects: list[dict], scale_name: str | None) -> dict:
    """subjects: dicts with marks, max, credits, grade_point, passed."""
    marked = [s for s in subjects if s.get("marks") is not None]
    total_ob = sum(s["marks"] for s in marked)
    total_max = sum(s["max"] for s in marked)
    pct = round(total_ob / total_max * 100, 2) if total_max else 0.0
    failed = any(s.get("passed") is False for s in marked)
    credits = sum((s.get("credits") or 0) for s in marked)
    weighted = sum((s.get("credits") or 0) * (s.get("grade_point") or 0) for s in marked)
    gpa = round(weighted / credits, 2) if credits else 0.0
    complete = bool(subjects) and len(marked) == len(subjects)
    if not marked:
        status = "No marks"
        gpa = 0.0
        letter = "-"
    elif failed:
        status = "Fail"
        if scale_name == "bd5":
            gpa = 0.0  # board rule: any failed subject gives GPA 0.00
        letter = "F"
    else:
        status = "Pass" if complete else "Incomplete"
        letter = letter_for_gpa(gpa, scale_name)
    return {
        "total_obtained": round(total_ob, 2),
        "total_max": round(total_max, 2),
        "percentage": pct,
        "gpa": gpa,
        "grade": letter,
        "status": status,
        "subjects_marked": len(marked),
        "subjects_total": len(subjects),
    }
