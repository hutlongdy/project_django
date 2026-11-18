from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class AcademicYear(models.Model):
    name = models.CharField(max_length=20, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="academic_year_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="one_current_academic_year",
            ),
        ]

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})

    def __str__(self):
        return self.name


class Teacher(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Guardian(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Student(models.Model):
    student_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    guardian_name = models.CharField(max_length=200)
    guardian_phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    guardians = models.ManyToManyField(
        Guardian, blank=True, related_name="students"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.student_number} — {self.first_name} {self.last_name}"


class SchoolClass(models.Model):
    name = models.CharField(max_length=80)
    grade_level = models.PositiveSmallIntegerField()
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="classes"
    )
    homeroom_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homeroom_classes",
    )
    capacity = models.PositiveSmallIntegerField(default=30)

    class Meta:
        ordering = ["academic_year__start_date", "grade_level", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "academic_year"], name="unique_class_per_year"
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1), name="school_class_capacity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class ClassSubject(models.Model):
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="subject_assignments"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="class_assignments"
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subject_assignments",
    )

    class Meta:
        ordering = ["school_class", "subject"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "subject"],
                name="unique_subject_per_class",
            )
        ]

    def __str__(self):
        return f"{self.school_class}: {self.subject}"


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WITHDRAWN = "withdrawn", "Withdrawn"
        COMPLETED = "completed", "Completed"

    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="enrollments"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, related_name="enrollments"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="enrollments"
    )
    enrolled_on = models.DateField(default=timezone.localdate)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ["school_class", "student"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                name="one_enrollment_per_student_year",
            )
        ]

    def clean(self):
        if (
            self.school_class_id
            and self.academic_year_id
            and self.school_class.academic_year_id != self.academic_year_id
        ):
            raise ValidationError(
                {"academic_year": "The selected year must match the class year."}
            )

    def __str__(self):
        return f"{self.student} — {self.school_class}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices)
    note = models.CharField(max_length=255, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "enrollment__student"]
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "date"], name="one_attendance_per_day"
            )
        ]

    def __str__(self):
        return f"{self.enrollment.student} — {self.date}: {self.get_status_display()}"


class Grade(models.Model):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="grades"
    )
    class_subject = models.ForeignKey(
        ClassSubject, on_delete=models.PROTECT, related_name="grades"
    )
    assessment = models.CharField(max_length=100)
    score = models.DecimalField(max_digits=6, decimal_places=2)
    maximum_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("100.00")
    )
    assessed_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-assessed_on", "enrollment__student"]
        constraints = [
            models.CheckConstraint(
                condition=Q(score__gte=0),
                name="grade_score_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(maximum_score__gt=0),
                name="grade_maximum_positive",
            ),
            models.CheckConstraint(
                condition=Q(score__lte=models.F("maximum_score")),
                name="grade_score_at_most_maximum",
            ),
        ]

    def clean(self):
        if (
            self.enrollment_id
            and self.class_subject_id
            and self.enrollment.school_class_id
            != self.class_subject.school_class_id
        ):
            raise ValidationError(
                {"class_subject": "The subject assignment must belong to the student's class."}
            )

    def __str__(self):
        return f"{self.enrollment.student} — {self.assessment}: {self.score}"


class UserProfile(models.Model):
    class Role(models.TextChoices):
        OFFICE_STAFF = "office_staff", "Office staff"
        TEACHER = "teacher", "Teacher"
        PARENT = "parent", "Parent/guardian"
        STUDENT = "student", "Student"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_profile",
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.OFFICE_STAFF
    )
    teacher = models.OneToOneField(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
    )
    student = models.OneToOneField(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
    )
    guardian = models.OneToOneField(
        Guardian,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
    )

    class Meta:
        ordering = ["user__username"]

    def clean(self):
        role_relation = {
            self.Role.TEACHER: ("teacher", self.teacher_id),
            self.Role.STUDENT: ("student", self.student_id),
            self.Role.PARENT: ("guardian", self.guardian_id),
        }
        required_relation = role_relation.get(self.role)
        if required_relation and not required_relation[1]:
            raise ValidationError(
                {required_relation[0]: "Select the person record for this account."}
            )
        expected_relation = required_relation[0] if required_relation else None
        unrelated_links = {
            "teacher": self.teacher_id,
            "student": self.student_id,
            "guardian": self.guardian_id,
        }
        if any(
            relation_id
            for relation, relation_id in unrelated_links.items()
            if relation != expected_relation
        ):
            raise ValidationError(
                "An account can only be linked to the record matching its role."
            )

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        is_office_staff = self.role == self.Role.OFFICE_STAFF
        if self.user.is_staff != is_office_staff and not self.user.is_superuser:
            self.user.is_staff = is_office_staff
            self.user.save(update_fields=["is_staff"])
        return result

    def delete(self, *args, **kwargs):
        if self.role == self.Role.OFFICE_STAFF and not self.user.is_superuser:
            self.user.is_staff = False
            self.user.save(update_fields=["is_staff"])
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"
