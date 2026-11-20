"""Everyday-language wording for model results (aim: clear to a reader with no medical or statistics background).

Rules used throughout the app:
* Say "about 18 in 100 people", never "18 % calibrated probability".
* Describe patterns, not causes, and never present a result as a diagnosis.
* Give a calm, practical next step.
"""
from __future__ import annotations

AGE_BANDS = ["18–24", "25–29", "30–34", "35–39", "40–44", "45–49", "50–54", "55–59", "60–64", "65–69", "70–74",
             "75–79", "80 or older"]
HEALTH_WORDS = {1: "Excellent", 2: "Very good", 3: "Good", 4: "Fair", 5: "Poor"}
EDUCATION = {1: "Never attended school", 2: "Primary school", 3: "Some secondary school", 4: "Finished secondary school",
             5: "Some college", 6: "College graduate"}
INCOME = {1: "Under $10,000", 2: "$10,000–15,000", 3: "$15,000–20,000", 4: "$20,000–25,000", 5: "$25,000–35,000",
          6: "$35,000–50,000", 7: "$50,000–75,000", 8: "$75,000 or more"}
WEIGHT_CATEGORY = {"underweight": "Underweight", "normal": "Healthy weight", "overweight": "Overweight",
                   "obese_I": "Obesity (class 1)", "obese_II": "Obesity (class 2)", "obese_III": "Obesity (class 3)"}

YES_NO = {0: "No", 1: "Yes"}

# feature -> (plain label, value formatter)
_PLAIN: dict[str, tuple[str, callable]] = {
    "GenHlth": ("How you rate your overall health", lambda v: HEALTH_WORDS.get(int(float(v)), str(v))),
    "Age": ("Your age", lambda v: AGE_BANDS[int(float(v)) - 1] if 1 <= int(float(v)) <= 13 else str(v)),
    "BMI": ("Your weight for your height (BMI)", lambda v: f"{float(v):.0f}"),
    "bmi_category": ("Your weight group", lambda v: WEIGHT_CATEGORY.get(str(v), str(v))),
    "cardiometabolic_count": ("Heart and blood-pressure conditions you have", lambda v: f"{int(float(v))} of 4"),
    "HighBP": ("High blood pressure", lambda v: YES_NO[int(float(v))]),
    "HighChol": ("High cholesterol", lambda v: YES_NO[int(float(v))]),
    "CholCheck": ("Had your cholesterol checked in the last 5 years", lambda v: YES_NO[int(float(v))]),
    "Smoker": ("Has smoked 100+ cigarettes in their life", lambda v: YES_NO[int(float(v))]),
    "Stroke": ("Ever had a stroke", lambda v: YES_NO[int(float(v))]),
    "HeartDiseaseorAttack": ("Heart disease or heart attack", lambda v: YES_NO[int(float(v))]),
    "PhysActivity": ("Exercised in the last month", lambda v: YES_NO[int(float(v))]),
    "Fruits": ("Eats fruit every day", lambda v: YES_NO[int(float(v))]),
    "Veggies": ("Eats vegetables every day", lambda v: YES_NO[int(float(v))]),
    "HvyAlcoholConsump": ("Drinks a lot of alcohol", lambda v: YES_NO[int(float(v))]),
    "AnyHealthcare": ("Has health insurance or coverage", lambda v: YES_NO[int(float(v))]),
    "NoDocbcCost": ("Skipped a doctor visit because of cost", lambda v: YES_NO[int(float(v))]),
    "MentHlth": ("Days of poor mental health (last 30)", lambda v: f"{int(float(v))}"),
    "PhysHlth": ("Days of poor physical health (last 30)", lambda v: f"{int(float(v))}"),
    "DiffWalk": ("Trouble walking or climbing stairs", lambda v: YES_NO[int(float(v))]),
    "Sex": ("Sex", lambda v: "Male" if int(float(v)) == 1 else "Female"),
    "Education": ("Education", lambda v: EDUCATION.get(int(float(v)), str(v))),
    "Income": ("Household income", lambda v: INCOME.get(int(float(v)), str(v))),
    "poor_health_days": ("Days you felt unwell (last 30)", lambda v: f"{int(float(v))}"),
    "lifestyle_score": ("Healthy habits", lambda v: f"{int(float(v))} out of 5"),
    "access_barrier": ("Trouble getting to a doctor (cost or no coverage)", lambda v: YES_NO[int(float(v))]),
}


def plain_factor(feature: str, value) -> tuple[str, str]:
    label, fmt = _PLAIN.get(feature, (feature, str))
    try:
        return label, fmt(value)
    except (ValueError, TypeError, IndexError, KeyError):
        return label, str(value)


def plain_label(feature: str) -> str:
    return _PLAIN.get(feature, (feature, str))[0]


def annotate(contribs: list[dict]) -> list[dict]:
    """Adds `plain_label` and `plain_value` to each contribution (the originals are kept for the detail views)."""
    for c in contribs:
        c["plain_label"], c["plain_value"] = plain_factor(c["feature"], c["value"])
    return contribs


def in_100(p: float) -> str:
    n = p * 100
    if n < 1:
        return "fewer than 1 in 100"
    if n > 99:
        return "more than 99 in 100"
    return f"about {round(n)} in 100"


def band_headline(band: str) -> str:
    return {"lower": "Your answers point to a lower chance",
            "elevated": "Your answers point to a higher-than-average chance",
            "high": "Your answers point to a much higher chance"}[band]


NEXT_STEP = {
    "lower": ("Your answers look similar to people who are less likely to have diabetes or prediabetes. "
              "Keep up healthy habits and have regular check-ups."),
    "elevated": ("Your answers look similar to people who more often have diabetes or prediabetes. A simple blood sugar "
                 "test from a doctor or pharmacist can tell for sure. It is worth asking about one at your next visit."),
    "high": ("Your answers look a lot like people who have diabetes or prediabetes. Please consider booking a blood "
             "sugar test with a doctor soon. This check cannot tell you whether you have diabetes; only a test can."),
}

LIMITATIONS = [
    "This is not a diagnosis. Only a blood test from a doctor or pharmacist can show whether someone has diabetes.",
    "It was built from a 2015 US health survey where people described their own health. It may work less well for "
    "other countries, ages or years.",
    "It does not use blood tests, so it can miss some people and flag others who are fine.",
    "The things it points out are patterns in the data. They do not prove what is causing a result.",
    "If you are worried about your health, please talk to a doctor or pharmacist.",
]


def explanation_text(p: float, prevalence: float, contribs: list[dict]) -> str:
    up = [c for c in contribs if c["direction"] == "increases"][:3]
    down = [c for c in contribs if c["direction"] == "decreases"][:3]
    fmt = lambda cs: "; ".join(f"{c['plain_label']}: {c['plain_value']}" for c in cs)  # noqa: E731
    parts = [f"{in_100(p).capitalize()} people with answers like yours said they have diabetes or prediabetes. "
             f"For comparison, about {round(prevalence * 100)} in 100 people overall said so in the survey this check is based on."]
    if up:
        parts.append(f"What raised your result the most: {fmt(up)}.")
    if down:
        parts.append(f"What lowered it the most: {fmt(down)}.")
    parts.append("These are patterns in survey data. They do not prove what is causing anything.")
    return " ".join(parts)


def accuracy_summary(recall: float, specificity: float) -> str:
    """Plain-language version of recall / specificity for a group of 100 people who answered the survey."""
    found = round(recall * 100)
    false_alarm = round((1 - specificity) * 100)
    return (f"In testing, among 100 people who really had diabetes or prediabetes, the check flagged about {found}. "
            f"Among 100 people who did not, it still flagged about {false_alarm}. It is a screening aid that leans "
            "towards catching people, so it raises some false alarms.")
