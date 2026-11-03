import os
import re
import urllib.request
from typing import Dict, List, Optional
from pypdf import PdfReader
from config import DRIVE_FOLDER_URL, GROUP_ALIASES

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache_pdf")
os.makedirs(CACHE_DIR, exist_ok=True)

def fetch_drive_file_list() -> List[Dict[str, str]]:
    """
    Scrapes the public Google Drive folder page to find all PDF files.
    Returns a list of dicts: [{'filename': '02.11.2026.pdf', 'file_id': '...'}]
    """
    req = urllib.request.Request(
        DRIVE_FOLDER_URL,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching Google Drive folder: {e}")
        return []

    files = []
    seen_ids = set()

    pattern1 = re.compile(
        r'aria-label="([0-9]{2}\.[0-9]{2}\.[0-9]{4}\.pdf)[^"]*"[^>]*data-handled-by-drag-and-drop="true"[^>]*>[\s\S]*?data-id="([a-zA-Z0-9_-]{25,})"'
    )
    for m in pattern1.finditer(html):
        fname, fid = m.group(1), m.group(2)
        if fid not in seen_ids:
            seen_ids.add(fid)
            files.append({'filename': fname, 'file_id': fid})

    if not files:
        pattern2 = re.compile(
            r'data-id="([a-zA-Z0-9_-]{25,})"[^>]*aria-label="([0-9]{2}\.[0-9]{2}\.[0-9]{4}\.pdf)'
        )
        for m in pattern2.finditer(html):
            fid, fname = m.group(1), m.group(2)
            if fid not in seen_ids:
                seen_ids.add(fid)
                files.append({'filename': fname, 'file_id': fid})

    def get_date_tuple(f):
        m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', f['filename'])
        if m:
            return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return (0, 0, 0)

    files.sort(key=get_date_tuple, reverse=True)
    return files


def download_drive_file(file_id: str, filename: str) -> Optional[str]:
    """
    Downloads file from Google Drive direct download URL.
    Returns the local path or None on failure.
    """
    local_path = os.path.join(CACHE_DIR, filename)
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp, open(local_path, 'wb') as out_f:
            out_f.write(resp.read())
        return local_path
    except Exception as e:
        print(f"Error downloading file {filename} ({file_id}): {e}")
        return None


def parse_lessons_range(lessons_str: str) -> List[int]:
    lessons = []
    lessons_str = lessons_str.strip()
    if 'общ' in lessons_str.lower():
        return list(range(1, 11))
    parts = lessons_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            bounds = part.split('-')
            try:
                start = int(bounds[0].strip())
                end = int(bounds[1].strip())
                lessons.extend(range(start, end + 1))
            except ValueError:
                pass
        else:
            try:
                lessons.append(int(part))
            except ValueError:
                pass
    return lessons


def parse_teacher_rooms(teachers_text: str) -> Dict[str, Dict[int, str]]:
    teacher_rooms = {}
    current_teacher = None

    lines = [l.strip() for l in teachers_text.splitlines() if l.strip() and '__________' not in l]

    for line in lines:
        m = re.match(r'^([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.[А-ЯЁ]\.)?)\s*(.*)$', line)
        if m and any(part in line for part in ['(', ')']):
            current_teacher = m.group(1).strip()
            rest = m.group(2).strip()
            _extract_rooms(current_teacher, rest, teacher_rooms)
        elif m and not any(c.isdigit() for c in line):
            current_teacher = m.group(1).strip()
        else:
            if current_teacher:
                _extract_rooms(current_teacher, line, teacher_rooms)

    return teacher_rooms


def _extract_rooms(teacher: str, text: str, teacher_rooms: Dict[str, Dict[int, str]]):
    matches = re.findall(r'([A-Za-zА-Яа-я0-9\-\.\s]+?)\s*\(([^)]+)\)', text)
    if not matches:
        return
    if teacher not in teacher_rooms:
        teacher_rooms[teacher] = {}
    for room, lessons_str in matches:
        room = room.strip()
        for les in parse_lessons_range(lessons_str):
            teacher_rooms[teacher][les] = room


def parse_pdf_substitutions(pdf_path: str) -> Dict:
    reader = PdfReader(pdf_path)
    full_text = "\n".join(p.extract_text() for p in reader.pages)

    # Date / Header
    date_match = re.search(r'ИЗМЕНЕНИЯ\s+В\s+РАСПИСАНИИ\s+([^\n┌]+)', full_text)
    raw_header = date_match.group(1).strip() if date_match else ""

    parts = re.split(r'Зам\.\s*директора\s*по\s*УР', full_text, flags=re.IGNORECASE)
    table_part = parts[0]
    teachers_part = parts[1] if len(parts) > 1 else ""

    teacher_rooms = parse_teacher_rooms(teachers_part)

    # Strip box lines from table part
    clean_table = re.sub(r'[┌├└][─┬┴┼]+[┐┤┘]', '', table_part)
    cells = [c.strip() for c in clean_table.split('│')]

    group_replacements = {}
    current_group = None

    i = 0
    while i < len(cells):
        val = cells[i]
        if re.match(r'^\d{3,4}$', val):
            current_group = val

        if current_group in GROUP_ALIASES:
            if re.match(r'^(?:[1-9]|10)$', val):
                lesson_num = int(val)
                new_subj = cells[i+1] if i+1 < len(cells) else ""
                new_room = cells[i+2] if i+2 < len(cells) else ""
                new_teacher = cells[i+3] if i+3 < len(cells) else ""
                orig_subj = cells[i+4] if i+4 < len(cells) else ""
                orig_room = cells[i+5] if i+5 < len(cells) else ""
                orig_teacher = cells[i+6] if i+6 < len(cells) else ""

                if not re.match(r'^\d+$', new_subj):
                    group_replacements[lesson_num] = {
                        'new_subj': new_subj,
                        'new_room': new_room,
                        'new_teacher': new_teacher,
                        'orig_subj': orig_subj,
                        'orig_room': orig_room,
                        'orig_teacher': orig_teacher
                    }
        i += 1

    day_of_week = ""
    for d in ["ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ", "ПЯТНИЦА", "СУББОТА"]:
        if d in raw_header.upper():
            day_of_week = d.capitalize()
            break

    date_clean = ""
    dm = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', raw_header)
    if dm:
        date_clean = dm.group(1)

    return {
        'date_str': date_clean,
        'day_of_week': day_of_week,
        'raw_header': raw_header,
        'teacher_rooms': teacher_rooms,
        'group_replacements': group_replacements
    }
