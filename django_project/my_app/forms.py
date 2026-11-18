from django import forms

from .models import (
    AttendanceRecord,
    Enrollment,
    Grade,
    Student,
)


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = (
            "student_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "guardian_name",
            "guardian_phone",
            "guardians",
            "address",
            "is_active",
        )
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "guardians": forms.CheckboxSelectMultiple(),
        }


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ("student", "school_class", "academic_year", "enrolled_on", "status")
        widgets = {"enrolled_on": forms.DateInput(attrs={"type": "date"})}


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ("enrollment", "date", "status", "note")
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, enrollments=None, **kwargs):
        super().__init__(*args, **kwargs)
        if enrollments is not None:
            self.fields["enrollment"].queryset = enrollments


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = (
            "enrollment",
            "class_subject",
            "assessment",
            "score",
            "maximum_score",
            "assessed_on",
        )
        widgets = {"assessed_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(
        self, *args, enrollments=None, assignments=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if enrollments is not None:
            self.fields["enrollment"].queryset = enrollments
        if assignments is not None:
            self.fields["class_subject"].queryset = assignments
