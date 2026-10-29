"""Pydantic models: tool inputs and the agent's result."""
from typing import Literal, Optional
import re
from pydantic import BaseModel, Field, model_validator


class TicketInput(BaseModel):
    category: Literal["fee", "scholarship", "course_change", "portal", "other"]
    description: str = Field(min_length=5, max_length=300)


class MemoryInput(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=150)


class ChangeInput(BaseModel):
    """A sensitive change to the student's own contact record (needs staff approval)."""
    field: Literal["email", "phone"]
    new_value: str = Field(min_length=5, max_length=80)

    @model_validator(mode="after")
    def check_format(self):
        v = self.new_value.strip()
        if self.field == "email" and not re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", v):
            raise ValueError("invalid email")
        if self.field == "phone" and not re.fullmatch(r"\d{10}", v):
            raise ValueError("phone must be 10 digits")
        self.new_value = v
        return self


class AgentResult(BaseModel):
    answer: str
    tools_called: list[dict] = []        # [{name, args, ok}]
    chunks: list[dict] = []              # retrieved policy evidence
    audit: list[dict] = []               # audit records created by this run
    memory_used: list[int] = []          # memory record ids placed in the context
    llm_seconds: float = 0.0
    total_seconds: float = 0.0
    input_tokens: Optional[int] = None   # None = unavailable
    output_tokens: Optional[int] = None
    trace_id: Optional[str] = None
    error: Optional[str] = None
    suggested_questions: list[str] = []  # follow-up buttons that can be answered properly
