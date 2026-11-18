from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .access import ADMINISTRATOR, OFFICE_STAFF, role_for
from .models import (
    AcademicYear,
    AttendanceRecord,
    ClassSubject,
    Enrollment,
    Grade,
    Guardian,
    SchoolClass,
    Student,
    Subject,
    Teacher,
    UserProfile,
)


class SchoolAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return role_for(request.user) in (ADMINISTRATOR, OFFICE_STAFF)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    fields = ("role", "teacher", "student", "guardian")
    extra = 1
    max_num = 1


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class SchoolUserAdmin(DjangoUserAdmin):
    inlines = (UserProfileInline,)


@admin.register(AcademicYear)
class AcademicYearAdmin(SchoolAdmin):
    list_display = ("name", "start_date", "end_date", "is_current")
    list_filter = ("is_current",)
    search_fields = ("name",)


@admin.register(Teacher)
class TeacherAdmin(SchoolAdmin):
    list_display = ("last_name", "first_name", "email", "phone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("first_name", "last_name", "email")


@admin.register(Guardian)
class GuardianAdmin(SchoolAdmin):
    list_display = ("last_name", "first_name", "email", "phone")
    search_fields = ("first_name", "last_name", "email", "phone")


@admin.register(Student)
class StudentAdmin(SchoolAdmin):
    list_display = (
        "student_number",
        "last_name",
        "first_name",
        "guardian_phone",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = (
        "student_number",
        "first_name",
        "last_name",
        "guardian_name",
        "guardian_phone",
    )
    filter_horizontal = ("guardians",)


@admin.register(SchoolClass)
class SchoolClassAdmin(SchoolAdmin):
    list_display = (
        "name",
        "grade_level",
        "academic_year",
        "homeroom_teacher",
        "capacity",
    )
    list_filter = ("academic_year", "grade_level")
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(SchoolAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(ClassSubject)
class ClassSubjectAdmin(SchoolAdmin):
    list_display = ("school_class", "subject", "teacher")
    list_filter = ("school_class__academic_year", "subject")
    search_fields = ("school_class__name", "subject__name", "teacher__last_name")


@admin.register(Enrollment)
class EnrollmentAdmin(SchoolAdmin):
    list_display = ("student", "school_class", "academic_year", "enrolled_on", "status")
    list_filter = ("academic_year", "school_class", "status")
    search_fields = (
        "student__student_number",
        "student__first_name",
        "student__last_name",
    )
    autocomplete_fields = ("student", "school_class")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(SchoolAdmin):
    list_display = ("date", "enrollment", "status")
    list_filter = ("date", "status", "enrollment__school_class")
    search_fields = (
        "enrollment__student__student_number",
        "enrollment__student__last_name",
    )
    autocomplete_fields = ("enrollment",)
    date_hierarchy = "date"


@admin.register(Grade)
class GradeAdmin(SchoolAdmin):
    list_display = (
        "assessed_on",
        "enrollment",
        "class_subject",
        "assessment",
        "score",
        "maximum_score",
    )
    list_filter = (
        "assessed_on",
        "class_subject__subject",
        "enrollment__school_class",
    )
    search_fields = (
        "enrollment__student__student_number",
        "enrollment__student__last_name",
        "assessment",
    )
    autocomplete_fields = ("enrollment", "class_subject")
    date_hierarchy = "assessed_on"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "teacher", "student", "guardian")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "teacher", "student", "guardian")


admin.site.site_header = "School management"
admin.site.site_title = "School management"
admin.site.index_title = "Administration"
