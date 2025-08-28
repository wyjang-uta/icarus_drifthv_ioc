def handle_user_input(stdscr, running):
    key = stdscr.getch()
    if key == -1:
        return running, False
    if key == ord('s'):
        return True, False
    elif key == ord('p'):
        return False, False
    elif key == 17:
        return False, True
    return running, False
