import cv2
import time
import gspread
import numpy as np
from datetime import datetime, timedelta, time as dt_time
from oauth2client.service_account import ServiceAccountCredentials

DAILY_SHEET = "sheet_id_here"  # Replace with your actual sheet ID
FACULTY_SHEET = "sheet_id_here"  # Replace with your actual sheet ID
DAILY_SHEET_NAME = datetime.now().strftime("%d %b")
FACULTY_SHEET_NAME = "sheet_name_here"  # Replace with your actual sheet name

MORNING_START = dt_time(9, 0)
MORNING_END = dt_time(13, 0)
AFTERNOON_START = dt_time(14, 0)
AFTERNOON_END = dt_time(19, 0)

BUFFER_TIME = 1800

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("new-creds.json", scope) # Replace with your actual credentials file
client = gspread.authorize(creds)

spreadsheet1 = client.open_by_key(DAILY_SHEET)
spreadsheet2 = client.open_by_key(FACULTY_SHEET)

sheet1 = spreadsheet1.worksheet(DAILY_SHEET_NAME)
sheet2 = spreadsheet2.worksheet(FACULTY_SHEET_NAME)

scanned_history = []

def get_session_columns(current_time_obj):
    current_time = current_time_obj.time()
    if MORNING_START <= current_time < MORNING_END:
        return "Morning IN", "Morning OUT"
    elif AFTERNOON_START <= current_time < AFTERNOON_END:
        return "Afternoon IN", "Afternoon OUT"
    else:
        if current_time < MORNING_START:
            return "Morning IN", "Morning OUT"
        elif MORNING_END <= current_time < AFTERNOON_START:
            return "Morning OUT", "Afternoon IN"
        else:
            return "Afternoon IN", "Afternoon OUT"

def get_session_status():
    now = datetime.now().time()
    if MORNING_START <= now < MORNING_END:
        return "Morning Session Active"
    elif AFTERNOON_START <= now < AFTERNOON_END:
        return "Afternoon Session Active"
    elif now < MORNING_START:
        minutes_to_start = (datetime.combine(datetime.today(), MORNING_START) - 
                           datetime.combine(datetime.today(), now)).seconds // 60
        return f"Morning Session starts in {minutes_to_start} minutes"
    elif MORNING_END <= now < AFTERNOON_START:
        minutes_to_start = (datetime.combine(datetime.today(), AFTERNOON_START) - 
                           datetime.combine(datetime.today(), now)).seconds // 60
        return f"Afternoon Session starts in {minutes_to_start} minutes"
    else:
        return "All Sessions Ended for Today"

def time_difference_seconds(time1_str, time2_str):
    time1 = datetime.strptime(time1_str, "%H:%M:%S")
    time2 = datetime.strptime(time2_str, "%H:%M:%S")
    return abs((time2 - time1).total_seconds())

def update_attendance(unique_id):
    current_time = datetime.now()
    current_time_str = current_time.strftime("%H:%M:%S")
    current_date = current_time.strftime("%d %b")
    in_column, out_column = get_session_columns(current_time)
    current_time_obj = current_time.time()
    is_valid_session_time = ((MORNING_START <= current_time_obj < MORNING_END and in_column == "Morning IN") or
                            (AFTERNOON_START <= current_time_obj < AFTERNOON_END and in_column == "Afternoon IN"))
    is_valid_checkout_time = ((MORNING_START <= current_time_obj < MORNING_END and out_column == "Morning OUT") or
                             (AFTERNOON_START <= current_time_obj < AFTERNOON_END and out_column == "Afternoon OUT"))
    records = sheet1.get_all_values()
    headers = records[0]
    records = records[1:]
    ids = [row[0] for row in records]
    names = {row[0]: row[1] for row in records}
    try:
        in_col_idx = headers.index(in_column) + 1
        out_col_idx = headers.index(out_column) + 1
    except ValueError:
        in_col_idx = len(headers) + 1
        out_col_idx = in_col_idx + 1
        sheet1.update_cell(1, in_col_idx, in_column)
        sheet1.update_cell(1, out_col_idx, out_column)
    if unique_id in ids:
        row_index = ids.index(unique_id) + 2
        name = names.get(unique_id, "Unknown")
        in_value = sheet1.cell(row_index, in_col_idx).value
        out_value = sheet1.cell(row_index, out_col_idx).value
        if not in_value:
            if not is_valid_session_time and in_column in ["Morning IN", "Afternoon IN"]:
                session_name = "Morning" if in_column == "Morning IN" else "Afternoon"
                scanned_history.append(f"{name}: Invalid check-in time for {session_name} session.")
                return
            sheet1.update_cell(row_index, in_col_idx, current_time_str)
            check_status = "Check-In"
            column_used = in_column
        elif not out_value:
            if time_difference_seconds(in_value, current_time_str) < BUFFER_TIME:
                buffer_remaining = BUFFER_TIME - time_difference_seconds(in_value, current_time_str)
                scanned_history.append(f"{name}: Checking out too soon!!! Please wait {int(buffer_remaining//60)}m {int(buffer_remaining%60)}s.")
                return
            if not is_valid_checkout_time and out_column in ["Morning OUT", "Afternoon OUT"]:
                session_name = "Morning" if out_column == "Morning OUT" else "Afternoon"
                if (out_column == "Morning OUT" and current_time_obj >= MORNING_END) or \
                   (out_column == "Afternoon OUT" and current_time_obj >= AFTERNOON_END):
                    pass
                else:
                    scanned_history.append(f"{name}: Invalid check-out time for {session_name} session.")
                    return
            sheet1.update_cell(row_index, out_col_idx, current_time_str)
            check_status = "Check-Out"
            column_used = out_column
        else:
            if current_time_obj >= AFTERNOON_START and in_column == "Afternoon IN" and out_column == "Afternoon OUT":
                sheet1.update_cell(row_index, in_col_idx, current_time_str)
                check_status = "Check-In"
                column_used = in_column
            else:
                scanned_history.append(f"{name} already completed {in_column}/{out_column} session.")
                return
        scanned_history.append(f"{name} {check_status} recorded in {column_used}.")
    else:
        if not is_valid_session_time and in_column in ["Morning IN", "Afternoon IN"]:
            session_name = "Morning" if in_column == "Morning IN" else "Afternoon"
            scanned_history.append(f"New User: Invalid check-in time for {session_name} session.")
            return
        new_row = [unique_id, "Unknown"] + [""] * (len(headers) - 2)
        row_index = len(records) + 2
        sheet1.insert_row(new_row, row_index)
        sheet1.update_cell(row_index, in_col_idx, current_time_str)
        scanned_history.append(f"New user {unique_id} Check-In recorded in {in_column}.")
        check_status = "Check-In"
    if check_status == "Check-In" and in_column == "Morning IN":
        sheet2_records = sheet2.get_all_values()
        headers = sheet2_records[0]
        sheet2_records = sheet2_records[1:]
        FACULTY_SHEETs = [row[0] for row in sheet2_records]
        if current_date in headers:
            date_column_index = headers.index(current_date) + 1
        else:
            sheet2.update_cell(1, len(headers) + 1, current_date)
            date_column_index = len(headers) + 1
        if unique_id in FACULTY_SHEETs:
            row_index = FACULTY_SHEETs.index(unique_id) + 2
            sheet2.update_cell(row_index, date_column_index, "Present")
            scanned_history.append(f"{names.get(unique_id, 'Unknown')} marked Present for {current_date}.")
        else:
            new_row = [unique_id, names.get(unique_id, "Unknown")] + [""] * (len(headers) - 2)
            new_row.append("Present")
            sheet2.append_row(new_row)
            scanned_history.append(f"New user marked Present for {current_date}.")

def scan_qr():
    cap = cv2.VideoCapture(0)
    qr_detector = cv2.QRCodeDetector()
    cv2.namedWindow("QR Scanner", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("QR Scanner", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    COOLDOWN_PERIOD = 8
    last_scan_time = 0
    is_in_cooldown = False
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        screen_width = 1920
        screen_height = 1080
        video_width = int(screen_width * 0.7)
        log_width = screen_width - video_width
        frame_resized = cv2.resize(frame, (video_width, screen_height))
        frame_resized = cv2.convertScaleAbs(frame_resized, alpha=1.2, beta=30)
        log_panel = np.zeros((screen_height, log_width, 3), dtype=np.uint8)
        log_panel[:] = (30, 30, 30)
        current_time = time.time()
        if not is_in_cooldown:
            data, points, _ = qr_detector.detectAndDecode(frame_resized)
            if points is not None and len(points) > 0 and data:
                unique_id = data.strip()
                update_attendance(unique_id)
                last_scan_time = current_time
                is_in_cooldown = True
                if points is not None:
                    points = np.int32(points).reshape(-1, 2)
                    cv2.polylines(frame_resized, [points], isClosed=True, color=(0, 255, 0), thickness=2)
        else:
            remaining_time = COOLDOWN_PERIOD - (current_time - last_scan_time)
            if remaining_time <= 0:
                is_in_cooldown = False
            else:
                text = f"Please wait: {remaining_time:.1f}s"
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 3
                thickness = 7
                text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
                text_x = (video_width - text_size[0]) // 2
                text_y = screen_height // 2
                padding = 20
                rect_x = text_x - padding
                rect_y = text_y - text_size[1] - padding
                rect_width = text_size[0] + (2 * padding)
                rect_height = text_size[1] + (2 * padding)
                cv2.rectangle(frame_resized, 
                            (rect_x, rect_y), 
                            (rect_x + rect_width, rect_y + rect_height), 
                            (0, 0, 0), 
                            -1)
                cv2.putText(frame_resized, text, (text_x, text_y), 
                            font, font_scale, (0, 0, 255), thickness)
        y_offset = 50
        for i, text in enumerate(scanned_history[-10:]):
            cv2.putText(log_panel, text, (10, y_offset + i * 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 2)
        session_status = get_session_status()
        session_color = (0, 255, 0) if "Active" in session_status else (0, 165, 255)
        current_datetime = datetime.now().strftime("%d %b %Y - %H:%M:%S")
        cv2.putText(log_panel, current_datetime, (10, screen_height - 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(log_panel, f"Morning: {MORNING_START.strftime('%H:%M')} - {MORNING_END.strftime('%H:%M')}", 
                   (10, screen_height - 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(log_panel, f"Afternoon: {AFTERNOON_START.strftime('%H:%M')} - {AFTERNOON_END.strftime('%H:%M')}", 
                   (10, screen_height - 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(log_panel, session_status, (10, screen_height - 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, session_color, 2)
        status_text = "Ready to scan" if not is_in_cooldown else "Cooling down..."
        cv2.putText(frame_resized, status_text, (10, 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.3, (231, 76, 60), 5)
        combined_display = np.hstack((frame_resized, log_panel))
        cv2.imshow("QR Scanner", combined_display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    scan_qr()
