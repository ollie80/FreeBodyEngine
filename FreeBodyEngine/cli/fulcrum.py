"""A small terminal based text editor for the FreeBodyEngine CLI."""

import curses
import os

def fulcrum_editor(stdscr, filepath):
    curses.curs_set(1)
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()
    text_lines = [""]

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            text_lines = f.read().splitlines()
        if not text_lines:
            text_lines = [""]

    cursor_y, cursor_x = 0, 0
    scroll_offset = 0 

    def save_file():
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(text_lines))
            status_msg = f"Saved to {filepath}"
        except Exception as e:
            status_msg = f"Error saving file: {e}"
        return status_msg

    status = "Press Ctrl+S to save, Ctrl+C to quit."

    while True:
        stdscr.clear()
        visible_height = max_y - 1

        if cursor_y < scroll_offset:
            scroll_offset = cursor_y
        elif cursor_y >= scroll_offset + visible_height:
            scroll_offset = cursor_y - visible_height + 1

        for idx in range(visible_height):
            line_index = scroll_offset + idx
            if line_index >= len(text_lines):
                break
            line = text_lines[line_index]
            stdscr.addstr(idx, 0, line[:max_x-1])

        stdscr.addstr(max_y - 1, 0, status[:max_x-1], curses.A_REVERSE)

        stdscr.move(cursor_y - scroll_offset, cursor_x)
        stdscr.refresh()

        key = stdscr.getch()

        if key == 3:  #ctrl+C
            break
        elif key == 19:  #ctrl+S 
            status = save_file()
        elif key in (curses.KEY_ENTER, 10, 13):
            current_line = text_lines[cursor_y]
            text_lines[cursor_y] = current_line[:cursor_x]
            text_lines.insert(cursor_y + 1, current_line[cursor_x:])
            cursor_y += 1
            cursor_x = 0
            
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if cursor_x > 0:
                line = text_lines[cursor_y]
                text_lines[cursor_y] = line[:cursor_x - 1] + line[cursor_x:]
                cursor_x -= 1
            elif cursor_y > 0:
                prev_line_len = len(text_lines[cursor_y - 1])
                text_lines[cursor_y - 1] += text_lines[cursor_y]
                del text_lines[cursor_y]
                cursor_y -= 1
                cursor_x = prev_line_len
        elif key == curses.KEY_UP and cursor_y > 0:
            cursor_y -= 1
            cursor_x = min(cursor_x, len(text_lines[cursor_y]))
        elif key == curses.KEY_DOWN and cursor_y < len(text_lines) - 1:
            cursor_y += 1
            cursor_x = min(cursor_x, len(text_lines[cursor_y]))
        elif key == curses.KEY_LEFT:
            if cursor_x > 0:
                cursor_x -= 1
            elif cursor_y > 0:
                cursor_y -= 1
                cursor_x = len(text_lines[cursor_y])
        elif key == curses.KEY_RIGHT:
            if cursor_x < len(text_lines[cursor_y]):
                cursor_x += 1
            elif cursor_y < len(text_lines) - 1:
                cursor_y += 1
                cursor_x = 0
        elif 32 <= key <= 126:
            line = text_lines[cursor_y]
            text_lines[cursor_y] = line[:cursor_x] + chr(key) + line[cursor_x:]
            cursor_x += 1

    stdscr.clear()

def fulcrum_handler(env, args):
    if len(args) > 0:
        path = os.path.join(env.path, args[0])
        try:
            curses.wrapper(fulcrum_editor, path)
        except KeyboardInterrupt:
            pass
    else:
        print("Usage: fulcrum <path>")
