def time_to_seconds(note: str) -> int:
    if not note:
        return None
    split_note = note.split(":")
    if len(split_note) != 2:
        return None
    minutes = int(split_note[0])
    seconds = int(split_note[1])
    return (minutes * 60) + seconds


def parse_time_duration(time_str: str, default_duration: int) -> tuple[int, int]:
    if not time_str:
        return 0, default_duration

    split_note = time_str.split("-")
    if len(split_note) == 0:
        return 0, default_duration
    elif len(split_note) == 1:
        return time_to_seconds(split_note[0]), default_duration

    start = time_to_seconds(split_note[0])
    end = time_to_seconds(split_note[1])
    time = start + ((end - start) // 2)
    duration = end - start
    return time, duration
