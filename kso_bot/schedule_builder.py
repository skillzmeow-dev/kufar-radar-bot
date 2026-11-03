from typing import Dict, Optional, Tuple
from config import TEACHER_SUBJECTS
from schedule_data import REGULAR_SCHEDULE, DAY_NAMES

def resolve_room_for_lesson(
    lesson_num: int,
    subject: str,
    teacher: str,
    explicit_room: str,
    teacher_rooms: Dict[str, Dict[int, str]]
) -> Tuple[str, str]:
    """
    Resolves the room and teacher for a given lesson.
    Returns: (room_str, teacher_name)
    """
    if explicit_room and explicit_room.strip():
        return explicit_room.strip(), teacher

    # Determine teacher if not explicitly given
    subj_lower = subject.lower().strip()
    resolved_teacher = teacher.strip() if teacher else ""

    if not resolved_teacher:
        for t_name, subjs in TEACHER_SUBJECTS.items():
            if any(s in subj_lower for s in subjs):
                resolved_teacher = t_name
                break

    # Look up in teacher_rooms if teacher is known
    room = ""
    if resolved_teacher:
        # Match teacher in teacher_rooms (allowing partial match by surname)
        surname = resolved_teacher.split()[0].lower()
        for t_key, lessons_map in teacher_rooms.items():
            if surname in t_key.lower():
                if lesson_num in lessons_map:
                    room = lessons_map[lesson_num]
                break

    return room, resolved_teacher


def build_schedule_message(
    target_date_str: str,
    target_day_index: int, # 0=Пн, 1=Вт, ...
    parsed_substitutions: Optional[Dict] = None,
    last_update_info: str = ""
) -> str:
    """
    Constructs the formatted Telegram message for group 02-24.
    If parsed_substitutions is None, outputs the regular schedule with a notice.
    """
    day_name = DAY_NAMES[target_day_index] if 0 <= target_day_index < len(DAY_NAMES) else "День"

    # Header
    if parsed_substitutions:
        header = f"🗓 <b>Расписание на {day_name} ({target_date_str}):</b>\n"
    else:
        header = (
            f"⚠️ <b>Замены на {day_name} ({target_date_str}) ещё не опубликованы на Диске.</b>\n"
        )
        if last_update_info:
            header += f"🕒 <i>Последнее обновление на сайте: {last_update_info}</i>\n"
        header += f"\n📖 <b>Стандартное расписание на {day_name}:</b>\n"

    # Base schedule for this day
    base_schedule = REGULAR_SCHEDULE.get(target_day_index, {})
    if not base_schedule and target_day_index == 6:
        return f"🎉 <b>{day_name} ({target_date_str}) — Выходной день!</b>\nПар нет, отдыхаем."

    replacements = parsed_substitutions.get('group_replacements', {}) if parsed_substitutions else {}
    teacher_rooms = parsed_substitutions.get('teacher_rooms', {}) if parsed_substitutions else {}

    # All lesson numbers
    all_lessons = sorted(set(list(base_schedule.keys()) + list(replacements.keys())))
    if not all_lessons:
        return header + "\nПар нет по расписанию."

    lines = []
    for num in all_lessons:
        rep = replacements.get(num)
        base = base_schedule.get(num)

        if rep:
            # Substitution exists
            new_subj = rep.get('new_subj', '').strip()
            new_teacher = rep.get('new_teacher', '').strip()
            new_room_raw = rep.get('new_room', '').strip()
            orig_subj = rep.get('orig_subj', '').strip() or (base['subject'] if base else '')

            if 'урок снят' in new_subj.lower() or 'снят' in new_subj.lower():
                was_subj = f" (был: {orig_subj})" if orig_subj and orig_subj != '√' else ""
                lines.append(f"<b>{num}.</b> ❌ <s>Урок снят</s>{was_subj}")
            else:
                room, teacher = resolve_room_for_lesson(num, new_subj, new_teacher, new_room_raw, teacher_rooms)
                room_str = f" [каб. {room}]" if room else ""
                teacher_str = f" ({teacher})" if teacher else ""
                
                was_note = ""
                if orig_subj and orig_subj != '√' and orig_subj.lower() != new_subj.lower():
                    was_note = f"\n   └ <i>вместо: {orig_subj}</i>"

                lines.append(f"<b>{num}.</b> 🔄 <b>{new_subj}</b>{room_str}{teacher_str}{was_note}")
        elif base:
            # Regular lesson without replacement
            base_subj = base['subject']
            base_teacher = base.get('teacher', '')
            room, teacher = resolve_room_for_lesson(num, base_subj, base_teacher, "", teacher_rooms)
            room_str = f" [каб. {room}]" if room else ""
            teacher_str = f" ({teacher})" if teacher else ""
            lines.append(f"<b>{num}.</b> {base_subj}{room_str}{teacher_str}")

    return header + "\n" + "\n".join(lines)
