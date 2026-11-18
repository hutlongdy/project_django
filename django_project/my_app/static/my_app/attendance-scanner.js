(() => {
    const scanner = document.querySelector("[data-attendance-scanner]");
    if (!scanner) return;

    const video = scanner.querySelector("[data-camera-preview]");
    const status = scanner.querySelector("[data-scan-status]");
    const scanButton = scanner.querySelector("[data-scan-toggle]");
    const csrfField = scanner.querySelector("[name=csrfmiddlewaretoken]");
    const recordsBody = document.querySelector("[data-attendance-records]");
    if (!video || !status || !scanButton || !csrfField) {
        if (status) {
            status.textContent = "Scanner controls did not load. Refresh the page and try again.";
            status.classList.add("scan-status-error");
        }
        return;
    }

    const csrfToken = csrfField.value;
    const canvas = document.createElement("canvas");
    const canvasContext = canvas.getContext("2d", { willReadFrequently: true });
    let nextAction = "check_in";
    let cameraStream = null;
    let cameraStarting = false;
    let requestPending = false;
    let detector = null;
    let lastDecodeAt = 0;

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.classList.toggle("scan-status-error", isError);
    }

    function updateAttendanceTable(record) {
        if (!recordsBody) return;

        let row = Array.from(recordsBody.querySelectorAll("[data-enrollment-id]"))
            .find((candidate) =>
                candidate.dataset.enrollmentId === String(record.enrollment_id) &&
                candidate.dataset.attendanceDate === record.date
            );
        if (!row) {
            recordsBody.querySelector("[data-empty-attendance]")?.remove();
            row = document.createElement("tr");
            row.dataset.enrollmentId = record.enrollment_id;
            row.dataset.attendanceDate = record.date;
            for (const field of [
                "date",
                "student",
                "class_name",
                "status",
                "checked_in_time",
                "checked_out_time",
                "note",
            ]) {
                const cell = document.createElement("td");
                cell.dataset.attendanceField = field;
                row.append(cell);
            }
            recordsBody.prepend(row);
        }

        const values = {
            date: record.date,
            student: record.student,
            class_name: record.class_name,
            status: record.status,
            checked_in_time: record.checked_in_time || "—",
            checked_out_time: record.checked_out_time || "—",
            note: "",
        };
        for (const [field, value] of Object.entries(values)) {
            const cell = row.querySelector(`[data-attendance-field="${field}"]`);
            if (cell) cell.textContent = value;
        }
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach((track) => track.stop());
            cameraStream = null;
        }
        video.srcObject = null;
        video.hidden = true;
        scanButton.disabled = false;
        scanButton.setAttribute("aria-pressed", "false");
        scanButton.textContent = nextAction === "check_in" ? "Check in" : "Check out";
    }

    async function submitScan(studentNumber) {
        requestPending = true;
        try {
            const response = await fetch(scanner.dataset.endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": csrfToken,
                },
                body: new URLSearchParams({
                    action: "auto",
                    student_number: studentNumber,
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || "Attendance scan failed.");

            nextAction = result.next_action;
            stopCamera();
            setStatus(
                `${result.message}: ${result.student} (${result.student_number}), ` +
                `${result.class_name} at ${result.time}.`
            );
            updateAttendanceTable(result);
        } catch (error) {
            setStatus(error.message || "Could not save this attendance scan.", true);
        } finally {
            window.setTimeout(() => {
                requestPending = false;
            }, 1200);
        }
    }

    async function scanFrame() {
        if (!cameraStream) return;
        try {
            if (
                !requestPending &&
                video.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA &&
                performance.now() - lastDecodeAt >= 180
            ) {
                lastDecodeAt = performance.now();
                let studentNumber;
                if (detector) {
                    try {
                        const codes = await detector.detect(video);
                        studentNumber = codes.find((code) => code.rawValue)?.rawValue;
                    } catch (_error) {
                        detector = null;
                    }
                }
                if (!studentNumber && window.jsQR && canvasContext) {
                    const scale = Math.min(1, 640 / video.videoWidth);
                    canvas.width = Math.round(video.videoWidth * scale);
                    canvas.height = Math.round(video.videoHeight * scale);
                    canvasContext.drawImage(video, 0, 0, canvas.width, canvas.height);
                    const frame = canvasContext.getImageData(0, 0, canvas.width, canvas.height);
                    studentNumber = window.jsQR(
                        frame.data,
                        frame.width,
                        frame.height,
                        { inversionAttempts: "dontInvert" }
                    )?.data;
                }
                if (studentNumber) await submitScan(studentNumber);
            }
        } catch (error) {
            setStatus(error.message || "The camera could not read a QR code.", true);
            stopCamera();
            return;
        }
        if (cameraStream) window.requestAnimationFrame(scanFrame);
    }

    scanButton.addEventListener("click", async () => {
        if (cameraStream) {
            stopCamera();
            setStatus("Camera stopped.");
            return;
        }
        if (cameraStarting) return;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            setStatus("Camera access requires HTTPS and a supported browser.", true);
            return;
        }

        cameraStarting = true;
        scanButton.disabled = true;
        try {
            if ("BarcodeDetector" in window) {
                try {
                    detector = new BarcodeDetector({ formats: ["qr_code"] });
                } catch (_error) {
                    detector = null;
                }
            }
            if (!detector && !window.jsQR) {
                throw new Error("The QR decoder did not load. Refresh the page and try again.");
            }
            if (!canvasContext) {
                throw new Error("This browser cannot prepare camera frames for QR scanning.");
            }
            cameraStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: { ideal: "environment" },
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
            });
            video.srcObject = cameraStream;
            video.hidden = false;
            await video.play();
            cameraStarting = false;
            scanButton.disabled = false;
            scanButton.textContent = "Cancel scan";
            scanButton.setAttribute("aria-pressed", "true");
            setStatus("Camera is on. Hold a student QR code in view.");
            window.requestAnimationFrame(scanFrame);
        } catch (error) {
            cameraStarting = false;
            stopCamera();
            setStatus(error.message || "Could not start the camera.", true);
        }
    });
})();
