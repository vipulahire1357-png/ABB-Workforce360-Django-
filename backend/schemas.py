import re
from datetime import date
from pydantic import BaseModel, Field, field_validator

class WorkerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    contractor_name: str = Field(min_length=1, max_length=120)
    joining_date: date
    contact_no: str
    emergency_contact: str
    aadhaar_no: str

    @field_validator("name", "contractor_name")
    @classmethod
    def clean_text(cls, v):
        v = " ".join(v.split())
        if not v: raise ValueError("This field is required")
        return v
    @field_validator("contact_no", "emergency_contact")
    @classmethod
    def phone(cls, v):
        v = re.sub(r"[\s()+-]", "", v)
        if not re.fullmatch(r"\d{10,15}", v): raise ValueError("Enter 10 to 15 digits")
        return v
    @field_validator("aadhaar_no")
    @classmethod
    def aadhaar(cls, v):
        digits = re.sub(r"\s", "", v)
        if not re.fullmatch(r"\d{12}", digits): raise ValueError("Enter a 12-digit Aadhaar number")
        return digits

class StatusUpdate(BaseModel):
    status: str
    @field_validator("status")
    @classmethod
    def status_value(cls, v):
        if v not in ("Active", "Inactive"): raise ValueError("Status must be Active or Inactive")
        return v

class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class VisitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company_name: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=255)
    contact_no: str
    aadhaar_no: str

    @field_validator("name", "company_name", "location", "host", "purpose")
    @classmethod
    def clean_text(cls, v):
        v = " ".join(v.split())
        if not v:
            raise ValueError("This field is required")
        return v

    @field_validator("contact_no")
    @classmethod
    def phone(cls, v):
        v = re.sub(r"[\s()+-]", "", v)
        if not re.fullmatch(r"\d{10,15}", v):
            raise ValueError("Enter 10 to 15 digits")
        return v

    @field_validator("aadhaar_no")
    @classmethod
    def aadhaar(cls, v):
        digits = re.sub(r"\s", "", v)
        if not re.fullmatch(r"\d{12}", digits):
            raise ValueError("Enter a 12-digit Aadhaar number")
        return digits


