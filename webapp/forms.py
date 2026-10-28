"""Django HTML forms backed by the existing normalization/business validators."""
from django import forms
from backend.schemas import WorkerCreate, VisitorCreate


class WorkerRegistrationForm(forms.Form):
    name = forms.CharField(max_length=120)
    contractor_name = forms.CharField(max_length=120)
    joining_date = forms.DateField(input_formats=["%Y-%m-%d"])
    contact_no = forms.CharField(max_length=20)
    emergency_contact = forms.CharField(max_length=20)
    aadhaar_no = forms.CharField(max_length=20)
    photo = forms.FileField()

    def clean(self):
        cleaned = super().clean()
        fields = ("name", "contractor_name", "joining_date", "contact_no", "emergency_contact", "aadhaar_no")
        if any(name not in cleaned for name in fields):
            return cleaned
        try:
            self.domain_value = WorkerCreate(**{name: cleaned[name] for name in fields})
        except (TypeError, ValueError) as error:
            raise forms.ValidationError("Invalid registration details") from error
        return cleaned


class VisitorRegistrationForm(forms.Form):
    name = forms.CharField(max_length=120)
    company_name = forms.CharField(max_length=120)
    location = forms.CharField(max_length=120)
    host = forms.CharField(max_length=120)
    purpose = forms.CharField(max_length=255)
    contact_no = forms.CharField(max_length=20)
    aadhaar_no = forms.CharField(max_length=20)
    photo = forms.FileField(required=False)

    def clean(self):
        cleaned = super().clean()
        fields = ("name", "company_name", "location", "host", "purpose", "contact_no", "aadhaar_no")
        if any(name not in cleaned for name in fields):
            return cleaned
        try:
            self.domain_value = VisitorCreate(**{name: cleaned[name] for name in fields})
        except (TypeError, ValueError) as error:
            raise forms.ValidationError("Invalid visitor details") from error
        return cleaned


class WorkerStatusForm(forms.Form):
    status = forms.ChoiceField(choices=(("Active", "Active"), ("Inactive", "Inactive")))
