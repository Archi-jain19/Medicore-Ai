from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Binary = Literal[0, 1]


class PatientInput(BaseModel):
    """Survey-style attributes supported by the CDC BRFSS-derived training dataset.
    Field names match the dataset's data dictionary for transparency."""

    model_config = ConfigDict(extra="forbid")

    HighBP: Binary = Field(description="Ever told by a health professional they have high blood pressure")
    HighChol: Binary = Field(description="Ever told they have high cholesterol")
    CholCheck: Binary = Field(description="Cholesterol check within past 5 years")
    BMI: float = Field(ge=12, le=98, description="Body mass index (kg/m²)")
    Smoker: Binary = Field(description="Smoked at least 100 cigarettes in entire life")
    Stroke: Binary = Field(description="Ever told they had a stroke")
    HeartDiseaseorAttack: Binary = Field(description="Coronary heart disease or myocardial infarction")
    PhysActivity: Binary = Field(description="Physical activity in past 30 days (not job)")
    Fruits: Binary = Field(description="Consumes fruit 1+ times per day")
    Veggies: Binary = Field(description="Consumes vegetables 1+ times per day")
    HvyAlcoholConsump: Binary = Field(description="Heavy drinking (men >14, women >7 drinks/week)")
    AnyHealthcare: Binary = Field(description="Has any kind of health care coverage")
    NoDocbcCost: Binary = Field(description="Could not see a doctor in past 12 months because of cost")
    GenHlth: int = Field(ge=1, le=5, description="General health: 1=excellent … 5=poor")
    MentHlth: int = Field(ge=0, le=30, description="Days of poor mental health in past 30 days")
    PhysHlth: int = Field(ge=0, le=30, description="Days of poor physical health in past 30 days")
    DiffWalk: Binary = Field(description="Serious difficulty walking or climbing stairs")
    Sex: Binary = Field(description="0=female, 1=male (as recorded in BRFSS 2015)")
    Age: int = Field(ge=1, le=13, description="Age band: 1=18–24, 2=25–29 … 12=75–79, 13=80+")
    Education: int = Field(ge=1, le=6, description="1=never attended … 6=college graduate")
    Income: int = Field(ge=1, le=8, description="1=<$10k … 8=$75k+ (2015 USD)")


class Contribution(BaseModel):
    feature: str
    label: str
    value: float | int | str | None
    shap_value: float
    direction: Literal["increases", "decreases", "neutral"]
    plain_label: str | None = None
    plain_value: str | None = None


class PredictionOut(BaseModel):
    id: int | None = None
    predicted_class: int
    predicted_label: str
    headline: str
    chance_text: str
    next_step: str
    probability: float
    threshold: float
    risk_band: Literal["lower", "elevated", "high"]
    population_base_rate: float
    model_name: str
    model_version: str
    algorithm: str
    top_contributions: list[Contribution]
    explanation: str
    limitations: list[str]
    created_at: datetime | None = None


class ExplanationOut(BaseModel):
    probability: float
    base_value: float
    output_space: str
    contributions: list[Contribution]
    explanation: str
    note: str


class PredictionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    probability: float
    predicted_class: int
    risk_band: str
    threshold: float
    created_at: datetime
    inputs: dict
