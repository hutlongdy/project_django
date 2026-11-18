import csv
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import (
    ADMINISTRATOR,
    OFFICE_STAFF,
    PARENT,
    STUDENT,
    TEACHER,
    role_for,
    role_required,
)
from .forms import (
    AttendanceRecordForm,
    EnrollmentForm,
    GradeForm,
    StudentForm,
)
from .models import (
    AcademicYear,
    AttendanceRecord,
    ClassSubject,
    Enrollment,
    Grade,
    SchoolClass,
    Student,
    Teacher,
)


login = auth_views.LoginView.as_view(template_name="my_app/login.html")
logout = auth_views.LogoutView.as_view()


def _profile_for(user):
    try:
        return user.school_profile
    except ObjectDoesNotExist:
        return None


def _teacher_enrollments(teacher):
    return (
        Enrollment.objects.filter(
            status=Enrollment.Status.ACTIVE,
            academic_year__is_current=True,
        )
        .filter(
            Q(school_class__homeroom_teacher=teacher)
            | Q(school_class__subject_assignments__teacher=teacher)
        )
        .distinct()
    )


def _student_portal_data(student, current_year):
    if not current_year:
        return {"student": student, "enrollment": None}
    enrollments = student.enrollments.filter(
        status=Enrollment.Status.ACTIVE
    ).select_related("school_class", "academic_year")
    enrollments = enrollments.filter(academic_year=current_year)
    enrollment = enrollments.first()
    if not enrollment:
        return {"student": student, "enrollment": None}
    return {
        "student": student,
        "enrollment": enrollment,
        "attendance_records": enrollment.attendance_records.select_related(
            "enrollment"
        )[:10],
        "grades": enrollment.grades.select_related(
            "class_subject__subject"
        )[:10],
    }


@role_required(ADMINISTRATOR, OFFICE_STAFF, TEACHER, PARENT, STUDENT)
def dashboard(request):
    role = role_for(request.user)
    profile = _profile_for(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()
    context = {
        "role": role,
        "current_year": current_year,
        "can_manage": role in (ADMINISTRATOR, OFFICE_STAFF),
    }

    if role in (ADMINISTRATOR, OFFICE_STAFF):
        context.update(
            {
                "student_count": Student.objects.filter(is_active=True).count(),
                "teacher_count": Teacher.objects.filter(is_active=True).count(),
                "class_count": SchoolClass.objects.count(),
                "enrollment_count": Enrollment.objects.filter(
                    status=Enrollment.Status.ACTIVE
                ).count(),
                "recent_students": Student.objects.filter(is_active=True)
                .order_by("-created_at")[:8],
            }
        )
    elif role == TEACHER:
        if not profile or not profile.teacher_id:
            raise PermissionDenied("This account is not linked to a teacher record.")
        classes = SchoolClass.objects.filter(
            Q(homeroom_teacher=profile.teacher)
            | Q(subject_assignments__teacher=profile.teacher),
            academic_year__is_current=True,
        ).distinct()
        context.update(
            {
                "teacher": profile.teacher,
                "classes": classes,
                "enrollment_count": _teacher_enrollments(profile.teacher).count(),
            }
        )
    elif role == PARENT:
        if not profile or not profile.guardian_id:
            raise PermissionDenied("This account is not linked to a guardian record.")
        context["portals"] = [
            _student_portal_data(student, current_year)
            for student in profile.guardian.students.filter(is_active=True)
        ]
    elif role == STUDENT:
        if not profile or not profile.student_id:
            raise PermissionDenied("This account is not linked to a student record.")
        context["portals"] = [
            _student_portal_data(profile.student, current_year)
        ]

    return render(request, "my_app/dashboard.html", context)


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def student_list(request):
    page = Paginator(
        Student.objects.prefetch_related("guardians"), 25
    ).get_page(request.GET.get("page"))
    return render(request, "my_app/student_list.html", {"page": page})


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def student_create(request):
    form = StudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        messages.success(request, f"Student {student.student_number} was added.")
        return redirect("student-list")
    return render(
        request, "my_app/record_form.html", {"form": form, "title": "Add student"}
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def student_update(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Student record was updated.")
        return redirect("student-list")
    return render(
        request, "my_app/record_form.html", {"form": form, "title": "Edit student"}
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def student_delete(request, student_id):
    if request.method != "POST":
        raise PermissionDenied
    student = get_object_or_404(Student, pk=student_id)
    student.is_active = False
    student.save(update_fields=["is_active"])
    messages.success(request, "Student was marked inactive.")
    return redirect("student-list")


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def enrollment_list(request):
    enrollments = Enrollment.objects.select_related(
        "student", "school_class", "academic_year"
    )
    page = Paginator(enrollments, 25).get_page(request.GET.get("page"))
    return render(request, "my_app/enrollment_list.html", {"page": page})


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def enrollment_create(request):
    form = EnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        enrollment = form.save()
        messages.success(request, f"Enrolled {enrollment.student}.")
        return redirect("enrollment-list")
    return render(
        request,
        "my_app/record_form.html",
        {"form": form, "title": "Enroll student"},
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF, TEACHER)
def attendance(request):
    role = role_for(request.user)
    profile = _profile_for(request.user)
    if role == TEACHER:
        if not profile or not profile.teacher_id:
            raise PermissionDenied("This account is not linked to a teacher record.")
        enrollments = _teacher_enrollments(profile.teacher)
    else:
        enrollments = Enrollment.objects.filter(
            status=Enrollment.Status.ACTIVE, academic_year__is_current=True
        )

    form = AttendanceRecordForm(
        request.POST or None, enrollments=enrollments
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Attendance was recorded.")
        return redirect("attendance")
    records = AttendanceRecord.objects.filter(
        enrollment__in=enrollments
    ).select_related("enrollment__student", "enrollment__school_class")[:100]
    return render(
        request,
        "my_app/records.html",
        {
            "form": form,
            "records": records,
            "title": "Attendance",
            "record_kind": "attendance",
            "can_manage_students": role in (ADMINISTRATOR, OFFICE_STAFF),
        },
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF, TEACHER)
@require_POST
def attendance_scan(request):
    student_number = request.POST.get("student_number", "").strip()
    action = request.POST.get("action")
    if not student_number or action not in ("check_in", "check_out", "auto"):
        return JsonResponse(
            {"message": "Scan a student QR code and select check-in or check-out."},
            status=400,
        )

    role = role_for(request.user)
    profile = _profile_for(request.user)
    if role == TEACHER:
        if not profile or not profile.teacher_id:
            return JsonResponse(
                {"message": "This account is not linked to a teacher record."},
                status=403,
            )
        enrollments = _teacher_enrollments(profile.teacher)
    else:
        enrollments = Enrollment.objects.filter(
            status=Enrollment.Status.ACTIVE, academic_year__is_current=True
        )

    enrollment = (
        enrollments.filter(
            student__student_number=student_number, student__is_active=True
        )
        .select_related("student", "school_class")
        .first()
    )
    if not enrollment:
        return JsonResponse(
            {"message": "No active enrollment found for that QR code."},
            status=404,
        )

    today = timezone.localdate()
    with transaction.atomic():
        record, _ = AttendanceRecord.objects.select_for_update().get_or_create(
            enrollment=enrollment,
            date=today,
            defaults={"status": AttendanceRecord.Status.PRESENT},
        )
        if action == "auto":
            if not record.checked_in_at:
                action = "check_in"
            elif record.checked_out_at:
                return JsonResponse(
                    {"message": "This student has already checked out today."},
                    status=409,
                )
            else:
                action = "check_out"

        if action == "check_in":
            if record.checked_in_at:
                return JsonResponse(
                    {"message": "This student has already checked in today."},
                    status=409,
                )
            timestamp = timezone.now()
            record.status = AttendanceRecord.Status.PRESENT
            record.checked_in_at = timestamp
            record.save(update_fields=["status", "checked_in_at"])
            message = "Checked in"
        else:
            if not record.checked_in_at:
                return JsonResponse(
                    {"message": "This student must check in before checking out."},
                    status=409,
                )
            if record.checked_out_at:
                return JsonResponse(
                    {"message": "This student has already checked out today."},
                    status=409,
                )
            timestamp = timezone.now()
            record.checked_out_at = timestamp
            record.save(update_fields=["checked_out_at"])
            message = "Checked out"

    student = enrollment.student
    return JsonResponse(
        {
            "message": message,
            "student": f"{student.first_name} {student.last_name}",
            "student_number": student.student_number,
            "action": action,
            "next_action": "check_out" if action == "check_in" else "check_in",
            "enrollment_id": enrollment.pk,
            "class_name": enrollment.school_class.name,
            "date": record.date.isoformat(),
            "status": record.get_status_display(),
            "time": timezone.localtime(timestamp).strftime("%H:%M:%S"),
            "checked_in_time": (
                timezone.localtime(record.checked_in_at).strftime("%H:%M")
                if record.checked_in_at
                else ""
            ),
            "checked_out_time": (
                timezone.localtime(record.checked_out_at).strftime("%H:%M")
                if record.checked_out_at
                else ""
            ),
        }
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def student_qr_code(_request, student_id):
    student = get_object_or_404(Student, pk=student_id, is_active=True)
    qr_code = qrcode.QRCode(box_size=8, border=4)
    qr_code.add_data(student.student_number)
    qr_code.make(fit=True)
    image = qr_code.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    return HttpResponse(output.getvalue(), content_type="image/svg+xml")


@role_required(ADMINISTRATOR, OFFICE_STAFF, TEACHER)
def grades(request):
    role = role_for(request.user)
    profile = _profile_for(request.user)
    if role == TEACHER:
        if not profile or not profile.teacher_id:
            raise PermissionDenied("This account is not linked to a teacher record.")
        enrollments = _teacher_enrollments(profile.teacher)
        assignments = ClassSubject.objects.filter(
            teacher=profile.teacher, school_class__academic_year__is_current=True
        )
    else:
        enrollments = Enrollment.objects.filter(
            status=Enrollment.Status.ACTIVE, academic_year__is_current=True
        )
        assignments = ClassSubject.objects.filter(
            school_class__academic_year__is_current=True
        )

    form = GradeForm(
        request.POST or None,
        enrollments=enrollments,
        assignments=assignments,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grade was recorded.")
        return redirect("grades")
    records = Grade.objects.filter(
        enrollment__in=enrollments
    ).select_related(
        "enrollment__student", "enrollment__school_class", "class_subject__subject"
    )[:100]
    return render(
        request,
        "my_app/records.html",
        {
            "form": form,
            "records": records,
            "title": "Grades",
            "record_kind": "grades",
        },
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def reports(request):
    summaries = AttendanceRecord.objects.values(
        "enrollment__school_class__name"
    ).annotate(
        present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
        late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
        excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
    ).order_by("enrollment__school_class__name")
    return render(
        request,
        "my_app/reports.html",
        {"attendance_summaries": summaries},
    )


@role_required(ADMINISTRATOR, OFFICE_STAFF)
def attendance_csv(_request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="attendance-report.csv"'
    writer = csv.writer(response)
    writer.writerow(
        (
            "Date",
            "Student number",
            "Student",
            "Class",
            "Status",
            "Check-in",
            "Check-out",
            "Note",
        )
    )
    records = AttendanceRecord.objects.select_related(
        "enrollment__student", "enrollment__school_class"
    )
    for record in records.iterator():
        student = record.enrollment.student
        writer.writerow(
            (
                record.date,
                student.student_number,
                f"{student.first_name} {student.last_name}",
                record.enrollment.school_class.name,
                record.get_status_display(),
                timezone.localtime(record.checked_in_at).strftime("%H:%M:%S")
                if record.checked_in_at
                else "",
                timezone.localtime(record.checked_out_at).strftime("%H:%M:%S")
                if record.checked_out_at
                else "",
                record.note,
            )
        )
    return response


def health(_request):
    return JsonResponse({"status": "ok"})
