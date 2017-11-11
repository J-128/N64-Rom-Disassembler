
import tkinter as tk
from tkinter import simpledialog, filedialog
import os
from function_defs import *
from disassembler import Disassembler, REGISTERS_ENCODE, BRANCH_INTS, JUMP_INTS

CONFIG_FILE = 'rom disassembler.config'

BRANCH_FUNCTIONS = ['BEQ', 'BEQL', 'BGEZ', 'BGEZAL', 'BGEZALL', 'BGEZL', 'BGTZ', 'BGTZL', 'BLEZ', 'BLEZL',
                    'BLTZ', 'BLTZAL', 'BLTZALL', 'BLTZL', 'BNEZ', 'BNEL', 'BNE', 'BC1F', 'BC1FL', 'BC1T', 'BC1TL']

JUMP_FUNCTIONS = ['J', 'JR', 'JAL', 'JALR']

# Disassembler, created when opening files
disasm = None

window = tk.Tk()
window.title('ROM Disassembler')
window.geometry('1337x810+550+50')

working_dir = os.path.dirname(os.path.realpath(__file__)) + '\\'
FRESH_APP_CONFIG = {
    'previous_base_location': working_dir,
    'previous_hack_location': working_dir,
    'scroll_amount': 8,
    'immediate_identifier': '$',
    'previous_navigation': 0,
    'game_address_mode': False
}

# Setup app_config either fresh or from file
if os.path.exists(CONFIG_FILE):
    try:
        config_in_file = unpickle_data(CONFIG_FILE)
        # Allows me to easily modify the app config items
        for key in FRESH_APP_CONFIG:
            if key not in config_in_file.keys():
                config_in_file[key] = FRESH_APP_CONFIG[key]
        for key in config_in_file:
            if key not in FRESH_APP_CONFIG.keys():
                del config_in_file[key]
        app_config = config_in_file.copy()
    except Exception as e:
        app_config = FRESH_APP_CONFIG.copy()
        simpledialog.messagebox._show('Error',
                                      'There was a problem loading the config file. '
                                      'Starting with default configuration.'
                                      '\n\nError: {}'.format(e))
else:
    app_config = FRESH_APP_CONFIG.copy()

'''
    A GUI with custom behaviour is required for user-friendliness.
    
    Displaying the whole file at once in a text box causes lag, so these text boxes will
      need to hold a small amount of data at a time in order to run smoothly.
      
    This can be done by maintain max_lines amount of lines at all times.
    
    Deviating from max_lines causes the list containing the data for the syntax checker
      to have a "shift". The syntax checker can't assume where, or whether or not, a shift
      has happened, so it needs the data to be processed before the checker receives it.
    
    The only times the amount of lines will change is when:
      - User has pressed: Enter
                          BackSpace (if cursor.line != 1 and cursor.column == 0)
                          Delete or Ctrl+D (if cursor.line != max_lines and cursor.column == end_of_column)
      - 1 or more highlighted (or selected) newlines are replaced (or "typed/pasted over")
      - Data containing 1 or more newlines is pasted into the text box
      
    Conditional management of each keypress is required to stop all of those problems from happening.
'''

address_text_box = tk.Text(window, font = 'Courier', state=tk.DISABLED)
base_file_text_box = tk.Text(window, font = 'Courier', state=tk.DISABLED)
hack_file_text_box = tk.Text(window, font = 'Courier', state=tk.DISABLED)
comments_text_box = tk.Text(window, font = 'Courier', state=tk.DISABLED)

ALL_TEXT_BOXES = [address_text_box,
                  base_file_text_box,
                  hack_file_text_box,
                  comments_text_box]


tag_config = {
              'function_end': 'light slate blue',
              'jump_to': 'LightBlue1',
              'branch': 'dark salmon',
              'jump': 'salmon',  # These colour names tho
              'jump_from': 'tomato',
              'bad': 'orange red',
              'out_of_range': 'DarkOrange',
              'target': 'turquoise',
              'liken': 'SeaGreen2',
              'nop': '#D0D0D0'
              }
[hack_file_text_box.tag_config(tag, background=tag_config[tag]) for tag in tag_config]

# [current_buffer_position, [(navigation, cursor_location, text_box_content, immediate_id, game_address_mode), ...]]
#                                                                          |------for hack_buffer only-----|
hack_buffer = [-1, []]
comments_buffer = [-1, []]
buffer_max = 20000

# {'decimal_address': [error_code, text_attempted_to_encode], ...}
user_errors = {}

max_lines = 42
navigation = 0


def clear_error(key):
    if isinstance(key, int):
        key = '{}'.format(key)
    if key in user_errors.keys():
        del user_errors[key]


def cursor_value(line, column):
    return '{}.{}'.format(line, column)


def get_cursor(handle, cursor_tag = tk.INSERT):
    cursor = handle.index(cursor_tag)
    dot = cursor.find('.')
    line = int(cursor[:dot])
    column = int(cursor[dot + 1:])
    return cursor, line, column


# To easily move cursor by x,y amount or floor/ceil the column
def modify_cursor(cursor, line_amount, column_amount, text):
    global max_lines
    # cursor value format:
    # '{line}.{column}'
    #  1-base  0-base
    if isinstance(text, str):
        text = text.split('\n')
    dot = cursor.find('.')
    line = int(cursor[:dot])
    column = int(cursor[dot + 1:])
    line = keep_within(line + line_amount, 1, len(text))
    line_length = len(text[line - 1])
    if isinstance(column_amount, int):
        column = keep_within(column + column_amount, 0, line_length)
    else:
        if column_amount == 'min':
            column = 0
        if column_amount == 'max':
            column = line_length
    return cursor_value(line, column), line, column


def geometry(geo):
    # geometry format:
    # '{width}x{height}+{x_pos}+{y_pos}'
    #                  |---optional---|
    #                  |-when setting-|
    mul_symbol = geo.find('x')
    plus_symbol_one = geo.find('+')
    plus_symbol_two = geo.find('+', plus_symbol_one + 1)

    window_w = int(geo[:mul_symbol])
    window_h = int(geo[mul_symbol + 1:plus_symbol_one])
    window_x = int(geo[plus_symbol_one + 1:plus_symbol_two])
    window_y = int(geo[plus_symbol_two + 1:])

    return window_w, window_h, window_x, window_y


def get_word_at(list, line, column):
    line_text = list[line - 1]
    lower_bound_punc = line_text.rfind('(', 0, column)
    if lower_bound_punc < 0:
        lower_bound_punc = line_text.rfind(' ', 0, column)
    upper_bound_punc = line_text.find(',', column)
    if upper_bound_punc < 0:
        upper_bound_punc = line_text.find(')', column)
    if upper_bound_punc < 0:
        upper_bound_punc = len(line_text)
    return list[line - 1][lower_bound_punc + 1: upper_bound_punc]


# Is called pretty much after every time the view is changed
prev_reg_target, prev_address_target, prev_cursor_location = '', 0, 0
def highlight_stuff():
    global prev_reg_target, prev_address_target, prev_cursor_location

    [hack_file_text_box.tag_remove(tag, '1.0', tk.END) for tag in tag_config]

    cursor, c_line, column = get_cursor(hack_file_text_box)
    text = hack_file_text_box.get('1.0', tk.END)[:-1].split('\n')
    targeting = get_word_at(text, c_line, column)

    if not prev_cursor_location:
        prev_cursor_location = navigation + c_line - 1

    try:
        jumps_from = disasm.jumps_to[str(prev_cursor_location)]
    except KeyError:
        jumps_from = []

    if prev_address_target or not column:
        c_line = 0

    for i in range(len(text)):
        line = i + 1
        line_text = text[i]
        this_word = line_text[:line_text.find(' ')]
        imm_id = text[i].find(app_config['immediate_identifier'])
        address = None
        navi = navigation + i

        # Highlight the end of each function
        if text[i] == 'JR RA':
            hack_file_text_box.tag_add('function_end',
                                       cursor_value(line, 0),
                                       cursor_value(line, 5))

        # Highlight branch functions
        elif this_word in BRANCH_FUNCTIONS:
            hack_file_text_box.tag_add('branch',
                                       cursor_value(line, 0),
                                       cursor_value(line, len(text[i])))
            if not c_line:
                address = prev_address_target
            elif line == c_line:
                address = text[i][imm_id + 1:]

        # Highlight jump functions
        elif this_word in JUMP_FUNCTIONS:
            hack_file_text_box.tag_add('jump',
                                       cursor_value(line, 0),
                                       cursor_value(line, len(text[i])))
            if not c_line:
                address = prev_address_target
            elif line == c_line and this_word in ['J', 'JAL']:
                address = text[i][imm_id + 1:]

        elif line_text == 'NOP':
            hack_file_text_box.tag_add('nop',
                                       cursor_value(line, 0),
                                       cursor_value(line, len(text[i])))

        # Highlight the target of jump or branch functions
        if address:
            if c_line:
                try:
                    # Raises error if user types non-numeric characters where an address/offset is
                    address = deci(address)
                except:
                    address = -1
                else:
                    if app_config['game_address_mode']:
                        address -= disasm.game_offset
                    address >>= 2
                    prev_address_target = address
            if address in range(navigation, navigation + max_lines):
                place = address - navigation
                hack_file_text_box.tag_add('target',
                                           cursor_value(place + 1, 0),
                                           cursor_value(place + 2, 0))

        # Highlight instructions in which jump to the cursors location
        if navi in jumps_from:
            hack_file_text_box.tag_add('jump_from',
                                       cursor_value(line, 0),
                                       cursor_value(line + 1, 0))

        # Highlight instructions in which are a target of any jump or branch
        # Because the disasm.jumps dict is so huge, a try/except works "exceptionally" faster than iterative methods
        try:
            a = disasm.jumps_to[str(navi)]

            # We only want to hit this line of code if str(navi) in disasm.jumps_to
            hack_file_text_box.tag_add('jump_to',
                                       cursor_value(line, 0),
                                       cursor_value(line + 1, 0))
        except KeyError:
            a = None

        # Highlight errors
        key = str(navi)
        if key in user_errors.keys():
            err_code = user_errors[key][0]
            hack_file_text_box.tag_add('bad' if err_code > -3 else 'out_of_range',
                                       cursor_value(i + 1, 0),
                                       cursor_value(i + 2, 0))
            
    # Highlight all of the same registers on screen if cursor is targeting one
    def highlight_targets(target):
        for i in range(len(text)):
            line = i + 1
            begin = 0
            while True:
                column = text[i].find(target, begin)
                word_at = get_word_at(text, line, column)
                if column >= 0:
                    if word_at[:1] != app_config['immediate_identifier']:
                        hack_file_text_box.tag_add('liken',
                                                   cursor_value(i + 1, column),
                                                   cursor_value(i + 1, column + len(target)))
                else:
                    break
                begin = column + 1

    # These conditions allow user to scroll out of view of the target without losing highlighting
    if targeting in REGISTERS_ENCODE:
        prev_reg_target = targeting
        highlight_targets(targeting)
    elif prev_reg_target:
        highlight_targets(prev_reg_target)


def reset_target():
    global prev_reg_target, prev_address_target, prev_cursor_location
    prev_reg_target, prev_address_target, prev_cursor_location = '', 0, 0


# The hacked text box syntax checker and change applier
def apply_hack_changes(ignore_slot = None):
    current_text = hack_file_text_box.get('1.0', tk.END)[:-1].upper()
    split_text = current_text.split('\n')
    for i in range(max_lines):
        navi = navigation + i
        if i == ignore_slot:
            continue
        is_hex_part = navi < 16
        string_key = '{}'.format(navi)
        if is_hex_part:
            without_spaces = split_text[i].replace(' ', '')
            try:
                int_of = deci(without_spaces)
            except:
                user_errors[string_key] = (-1, split_text[i])
                continue
            disasm.split_and_store_bytes(int_of, navi)
            clear_error(string_key)

        elif not split_text[i]:
            disasm.split_and_store_bytes(0, navi)
            hack_file_text_box.insert(cursor_value(i + 1, 0), 'NOP')

        elif split_text[i] != 'UNKNOWN/NOT AN INSTRUCTION':
            encoded_int = disasm.encode(split_text[i], navi)
            if encoded_int >= 0:
                disasm.split_and_store_bytes(encoded_int, navi)
                clear_error(string_key)
            else:
                user_errors[string_key] = (encoded_int, split_text[i])


# Disassembler.comments accumulator
def apply_comment_changes():
    current_text = comments_text_box.get('1.0', tk.END)[:-1]
    split_text = current_text.split('\n')
    for i in range(max_lines):
        navi = navigation + i
        string_key = '{}'.format(navi)
        if not split_text[i]:
            if string_key in disasm.comments.keys():
                del disasm.comments[string_key]
            continue
        disasm.comments[string_key] = split_text[i]


def buffer_append(buffer, tuple):
    # buffer[0] is the current buffer frame being displayed
    # buffer[1] is an array containing the buffer frames
    buffer_length = len(buffer[1])
    distance_from_end = (buffer_length - 1) - buffer[0]

    # This condition means the user is not currently at the end of the buffer (they have done some undo's)
    # so delete all buffer frames following the current one so that the current buffer frame is at the top
    if distance_from_end and buffer_length:
        buffer[1] = buffer[1][:-distance_from_end]
        buffer_length -= distance_from_end
    buffer[1].append(tuple)
    buffer[0] += 1

    # Start shifting buffer frames down and out of the buffer as the limit has been reached
    # Added diff slice in case buffer ever overflows
    diff = buffer_max - buffer[0]
    if diff < 0:
        buffer[0] -= diff
        buffer[1] = buffer[1][diff:]


# Puts the windows clipboard back when the user leaves focus
def replace_clipboard():
    global clipboard
    try:
        window.clipboard_get()
        clipboard = ''
    except:
        if clipboard:
            window.clipboard_append(clipboard)


# Custom keyboard events and textbox behaviour upon any keypress in text boxes
clipboard = ''
def keyboard_events(handle, max_char, event, buffer = None, hack_function = False):
    global clipboard
    if not disasm:
        return
    reset_target()
    joined_text = handle.get('1.0', tk.END)
    if joined_text.count('\n') == max_lines:
        joined_text = joined_text[:-1]
    split_text = joined_text.split('\n')

    cursor, line, column = get_cursor(handle)

    ctrl_held = bool(event.state & 0x0004)
    ctrl_d = ctrl_held and event.keysym == 'd'
    bad_bad_hotkey = ctrl_held and event.keysym in ['z', 't']
    if bad_bad_hotkey:
        # Messes with custom behaviour, so wait until after changes are made
        #   by bad hotkey, then restore text box to how it was before the hotkey
        window.after(0, lambda: (handle.delete('1.0', tk.END),
                                 handle.insert('1.0', joined_text),
                                 handle.mark_set(tk.INSERT, cursor),
                                 highlight_stuff()))
        return

    shift_held = bool(event.state & 0x0001)
    alt_held = bool(event.state & 0x0008) or bool(event.state & 0x0080)

    has_char = bool(event.char) and event.keysym != 'Escape' and not ctrl_held

    print(event.keysym)

    is_undoing = buffer and ctrl_held and event.keysym == 'comma'
    is_redoing = buffer and ctrl_held and event.keysym == 'period'
    is_cutting = ctrl_held and event.keysym == 'x'
    if is_cutting:
        asdf = None
    is_pasting = ctrl_held and event.keysym == 'v'
    is_copying = ctrl_held and event.keysym == 'c'
    is_deleting = ctrl_d or event.keysym == 'Delete'
    is_backspacing = event.keysym == 'BackSpace'
    is_returning = event.keysym == 'Return'

    selection_removable = has_char or is_pasting or is_cutting or is_deleting

    not_arrows = event.keysym not in ['Left', 'Up', 'Right', 'Down']
    vert_arrows = event.keysym in ['Up', 'Down']

    apply_function = apply_hack_changes if hack_function else lambda ignore_slot=None: apply_comment_changes()

    # Cause each modification of text box to snap-shot data in order to undo/redo
    if buffer and ((not (is_undoing or is_redoing) and has_char and not_arrows) or ctrl_d or is_pasting or is_cutting):
        buffer_frame = (navigation, cursor, joined_text,
                        app_config['immediate_identifier'],
                        app_config['game_address_mode'])\
                        if hack_function else \
                        (navigation, cursor, joined_text)
        buffer_append(buffer, buffer_frame)

    # Undoing and Redoing code
    if is_undoing or is_redoing:
        if buffer[0] == len(buffer[1]) - 1 and is_undoing:
            part = buffer[1][buffer[0]]
            if part[0] != navigation or part[2] != joined_text:
                buffer_frame = (navigation, cursor, joined_text,
                                app_config['immediate_identifier'],
                                app_config['game_address_mode']) \
                                if hack_function else \
                                (navigation, cursor, joined_text)
                buffer_append(buffer, buffer_frame)

        buffer[0] += 1 if is_redoing else -1
        if buffer[0] < 0:
            buffer[0] = 0
        elif buffer[0] > len(buffer[1]) - 1:
            buffer[0] = len(buffer[1]) - 1
        else:
            apply_hack_changes()
            apply_comment_changes()
            place = buffer[0]
            navigate_to(buffer[1][place][0])
            cursor = buffer[1][place][1]
            text_content = buffer[1][place][2]
            handle.delete('1.0', tk.END)
            handle.insert('1.0', text_content)
            handle.mark_set(tk.INSERT, cursor)

            if hack_function:
                immediate_id = buffer[1][place][3]
                game_address_mode = buffer[1][place][4]
                if immediate_id != app_config['immediate_identifier']:
                    app_config['immediate_identifier'] = immediate_id
                    pickle_data(app_config, CONFIG_FILE)
                    disasm.immediate_identifier = immediate_id
                if game_address_mode != app_config['game_address_mode']:
                    app_config['game_address_mode'] = game_address_mode
                    pickle_data(app_config, CONFIG_FILE)
                    disasm.game_address_mode = game_address_mode
            apply_hack_changes()
            apply_comment_changes()
            highlight_stuff()
        return

    # Copy/Paste and selection handling
    selection_line_mod = False
    try:
        selection_start, sel_start_line, sel_start_column = get_cursor(handle, tk.SEL_FIRST)
        selection_end, sel_end_line, sel_end_column = get_cursor(handle, tk.SEL_LAST)
        # Select whole columns if selecting multiple lines
        print(selection_start, selection_end)
        if sel_start_line != sel_end_line:
            # if sel_start_column == len(split_text[sel_start_line - 1]):
            #     selection_line_mod += 1
            #     selection_start, sel_start_line, sel_start_column = modify_cursor(selection_start, 1, 0, split_text)
            if sel_end_column == 0:
                selection_line_mod = True
                selection_end, sel_end_line, sel_end_column = modify_cursor(selection_end, -1, 0, split_text)
            selection_start, sel_start_line, sel_start_column = modify_cursor(selection_start, 0, 'min', split_text)
            selection_end, sel_end_line, sel_end_column = modify_cursor(selection_end, 0, 'max', split_text)
    except:
        selection_start, sel_start_line, sel_start_column = '1.0', 0, 0
        selection_end, sel_end_line, sel_end_column = '1.0', 0, 0

    has_selection = selection_start != selection_end
    selection_lines = sel_end_line - sel_start_line
    selection_function = has_selection and (selection_removable or is_copying)
    standard_key = not is_backspacing and not is_returning and has_char
    temp_cursor, _, __ = modify_cursor(selection_start, 0, -1, split_text)
    lower_outer_bound_selection_char = handle.get(temp_cursor)
    upper_outer_bound_selection_char = handle.get(selection_end)
    paste_text = ''
    lines_diff = 0

    # Because using mark_set() on SEL_FIRST or SEL_LAST seems to corrupt the widgets beyond repair at a windows level,
    # A work around with a custom clipboard is required in order for the code to be able to serve it's intended purpose
    if has_selection and not selection_lines and is_pasting and '\n' in clipboard:
        selection_start, sel_start_line, sel_start_column = modify_cursor(selection_start, 0, 'min', split_text)
        selection_end, sel_end_line, sel_end_column = modify_cursor(selection_end, 0, 'max', split_text)

    if selection_function:
        selection_text = handle.get(selection_start, selection_end)

        if is_copying or is_cutting:
            clipboard = selection_text
            # So that when user pastes, window clipboard won't override clipboard
            window.after(0, window.clipboard_clear)

        if selection_removable:
            handle.delete(selection_start, selection_end)
            lines_diff += selection_lines
            handle.mark_set(tk.INSERT, selection_start)

    if is_pasting:
        # If window clipboard has contents, contents to be drawn from there, else draw from clipboard
        # window clipboard having contents means user has copied data from an external source
        try:
            winnie_clip = window.clipboard_get()
            clipboard = winnie_clip
            window.clipboard_clear()
        except:
            winnie_clip = clipboard
        if winnie_clip:
            if '\n' in winnie_clip:
                # Ensure the text has within the maximum amount of lines and columns
                split_clip = winnie_clip.split('\n')
                line_boundary = max_lines - (sel_start_line if has_selection else line)
                split_clip = split_clip[:line_boundary + 1]
                split_clip = [i[:max_char] for i in split_clip]
                lines_diff -= len(split_clip) - 1
                winnie_clip = '\n'.join(split_clip)
                if not selection_function:
                    min_del, _, __ = modify_cursor(cursor, 0, 'min', split_text)
                    max_del, _, __ = modify_cursor(cursor, -lines_diff, 'max', split_text)
                    handle.delete(min_del, max_del)
                    lines_diff = 0
            paste_text = winnie_clip

    # Either clear lines which would be excess lines after the paste
    # Or add new lines to fill in what would be the gaps after the paste
    insertion_place = selection_start if has_selection else cursor
    if lines_diff > 0:
        handle.insert(insertion_place, '\n' * lines_diff)
    elif lines_diff < 0:
        temp_cursor, _, __ = modify_cursor(insertion_place, -lines_diff, 'max', split_text)
        handle.delete(insertion_place, temp_cursor)

    if is_pasting or is_cutting:
        def move_next(handle):
            move_amount = 1 if is_pasting else 0
            temp_cursor, _, __ = modify_cursor(handle.index(tk.INSERT), move_amount, 'max', handle.get('1.0', tk.END)[:-1])
            handle.mark_set(tk.INSERT, temp_cursor)
        handle.insert(insertion_place, paste_text)
        if not selection_line_mod or is_pasting:
            window.after(0, lambda: (apply_hack_changes(),
                                     apply_comment_changes(),
                                     move_next(handle),
                                     navigate_to(navigation)))
    # Copy/Paste end

    # Easier than recalculating for each condition in the copy/paste section
    cursor, line, column = get_cursor(handle)
    # selection_start, sel_start_line, sel_start_column, selection_end, sel_end_line, sel_end_column = selection_calc()
    # has_selection = selection_start != selection_end
    if selection_removable:
        selection_start, sel_start_line, sel_start_column, selection_end, sel_end_line, sel_end_column = 0,0,0,0,0,0
        has_selection = False
    joined_text = handle.get('1.0', tk.END)[:-1]
    split_text = joined_text.split('\n')

    nl_at_cursor = handle.get(cursor) == '\n'
    if has_selection:
        nl_at_cursor = nl_at_cursor or handle.get(selection_end) == '\n'
    # Make any key delete the final character of the line if word is about to wrap onto next line
    # Also validate all code except line currently editing
    if standard_key:
        apply_function(ignore_slot = line - 1)
        line_chars = len(split_text[line - 1])
        if line_chars > max_char - 1:
            handle.delete(cursor_value(line, max_char - 1), cursor_value(line, max_char))

    # Make delete do nothing if cursor precedes a new line
    # Make backspace act as left arrow if cursor at column 0 then validate code (ignoring the line if cursor not at column 0)
    elif ((is_backspacing and (column == 0 and line > 1)) or (is_deleting and nl_at_cursor and not shift_held)) and not has_selection:
        # if not selection_lines: # was needed to stop something but now is not?
        if is_deleting:
            apply_function(ignore_slot = (line - 1) if not sel_start_line else None)
        handle.insert(cursor,'\n')
        handle.mark_set(tk.INSERT, cursor)
        if is_backspacing:
            apply_function(ignore_slot = (line - 1) if not sel_start_line else None)

    # Make return send the cursor to the end of the next line and validate code
    elif is_returning:
        move_lines = -1 if line == max_lines else 0
        cursor, _, __ = modify_cursor(cursor, move_lines, 'max', split_text)
        handle.mark_set(tk.INSERT, cursor)
        handle.delete(cursor)
        new_cursor, _, __ = modify_cursor(cursor, 1, 'max', split_text)
        window.after(0, lambda: (apply_function(), handle.mark_set(tk.INSERT, new_cursor)))

    cursor, line, column = get_cursor(handle)
    split_text = handle.get('1.0', tk.END)[:-1].split('\n')
    print('selection, ',selection_start, selection_end)

    # Prevent delete or backspace from modifying textbox any further than the bounds of the selected text (if selected text is only on one line)
    if has_selection and not selection_lines:
        if (is_deleting and column != len(split_text[line - 1])) or (is_backspacing and column != 0):
            replace_char = lower_outer_bound_selection_char if is_backspacing else upper_outer_bound_selection_char
        elif (is_backspacing and column == 0) or (is_deleting and sel_end_column == len(split_text[sel_end_line - 1])):
            replace_char = '\n'
        else:
            replace_char = ''
        if not (is_pasting or is_returning):
            handle.insert(selection_start, replace_char)
            window.after(0, lambda: apply_function())
        if is_deleting:
            window.after(0, lambda: handle.mark_set(tk.INSERT, selection_start))

    # So the P on the cursor's NOP doesn't get removed when backspace happens
    elif has_selection and selection_lines and is_backspacing:
        handle.insert(cursor, 'P')

    if vert_arrows:
        apply_function()

    if selection_removable and selection_line_mod and (standard_key or is_cutting):
        def move_to():
            temp_cursor = get_cursor(handle)[0]
            handle.insert(temp_cursor, '\n')
            handle.mark_set(tk.INSERT, temp_cursor)
            apply_function()

        window.after(0, move_to)

    # The delays are necessary to solve complications for text modified by the key after this function fires
    window.after(0, highlight_stuff)


base_file_text_box.bind('<Key>', lambda event:
    keyboard_events(base_file_text_box, 31, event, buffer=False))

hack_file_text_box.bind('<Key>', lambda event:
    keyboard_events(hack_file_text_box, 31, event, buffer=hack_buffer, hack_function=True))

comments_text_box.bind('<Key>', lambda event:
    keyboard_events(comments_text_box, 59, event, buffer=comments_buffer))


# The button is destroyed and remade every time the user scrolls within it's view
change_rom_name_button = tk.Button()
def change_rom_name():
    if not disasm:
        return
    new_name = simpledialog.askstring('Change rom name', '20 Characters maximum')
    if new_name:
        if len(new_name) < 20:
            new_name += ' ' * (20 - len(new_name))
        elif len(new_name) > 20:
            new_name = new_name[:20]
        # new_name = new_name.upper()
        for i in range(20):
            disasm.hack_file[disasm.header_items['Rom Name'][0] + i] = ord(new_name[i])
        disasm.comments['9'] = new_name
        navigate_to(navigation)


def navigate_to(index):
    global navigation, change_rom_name_button, disasm
    if not disasm:
        return

    if change_rom_name_button:
        change_rom_name_button.destroy()
        change_rom_name_button = None

    shift_amount = navigation

    # Correct the navigation if traveling out of bounds, also calculate limits for file samples to display
    amount_words = disasm.file_length // 4
    navigation = index if index + max_lines < amount_words else amount_words - max_lines
    if navigation < 0:
        navigation = 0
    limit = navigation + max_lines if navigation + max_lines < amount_words else amount_words
    lines = limit - navigation

    shift_amount -= navigation

    # Sample bytes out of files
    file_nav = navigation * 4
    base_sample = disasm.base_file[file_nav:file_nav + ((limit if limit < max_lines else max_lines) * 4)]
    hack_sample = disasm.hack_file[file_nav:file_nav + ((limit if limit < max_lines else max_lines) * 4)]

    # Translate each 4 lot of bytes into separate integers
    ints_in_base_sample = ints_of_4_byte_aligned_region(base_sample)
    ints_in_hack_sample = ints_of_4_byte_aligned_region(hack_sample)

    # Create blank comments box, then fill with any comments that have been made (we don't store any blank comments)
    sample_comments = [''] * lines
    for i in range(lines):
        string_key = '{}'.format(navigation + i)
        if string_key in disasm.comments.keys():
            sample_comments[i] = disasm.comments[string_key]

    # Calculate what addresses to display in the address box, and disassemble ints into instructions, display header section as hex
    address_range = [extend_zeroes(hexi((i * 4) + (disasm.game_offset
                                                   if disasm.game_address_mode else 0)), 8) for i in range(navigation, limit)]
    base_disassembled = [disasm.decode(ints_in_base_sample[i], navigation + i) if navigation + i > 15 else \
                         hex_space(extend_zeroes(hexi(ints_in_base_sample[i]), 8)) \
                         for i in range(len(ints_in_base_sample))]
    hack_disassembled = [disasm.decode(ints_in_hack_sample[i], navigation + i) if navigation + i > 15 else \
                         hex_space(extend_zeroes(hexi(ints_in_hack_sample[i]), 8)) \
                         for i in range(len(ints_in_hack_sample))]

    # Replace disassembled data in the hack file with any errors the user has made
    for i in range(len(hack_disassembled)):
        string_key = '{}'.format(navigation + i)
        if string_key in user_errors.keys():
            hack_disassembled[i] = user_errors[string_key][1]

    # Display floating Rom Name Change button
    if disasm.header_items['Rom Name'][0] // 4 in range(navigation, limit):
        change_rom_name_button = tk.Button(window, text = 'Change', command = change_rom_name)
        y_offset = ((disasm.header_items['Rom Name'][0] // 4) - navigation) * 18
        change_rom_name_button.place(x = 965, y = 46 + y_offset, height = 20)

    # Update all 4 text boxes
    def update_text_box(handle, text):
        text = '\n'.join(text)
        cursor, line, column = get_cursor(handle)
        handle.delete('1.0', tk.END)
        handle.insert('1.0', text)

        new_line = line + shift_amount
        if new_line < 1 or new_line > max_lines:
            new_cursor_loc = cursor_value(keep_within(new_line, 1, max_lines), 0)
        else:
            new_cursor_loc, _, __ = modify_cursor(cursor, shift_amount, 0, text)

        handle.mark_set(tk.INSERT, new_cursor_loc)

    params = [[address_text_box, address_range],
              [base_file_text_box, base_disassembled],
              [hack_file_text_box, hack_disassembled],
              [comments_text_box, sample_comments]]
    [update_text_box(param[0], param[1]) for param in params]

    if prev_cursor_location in range(navigation, limit):
        line = prev_cursor_location - navigation
        temp_cursor, _, __ = modify_cursor('1.0', line, 'max', hack_file_text_box.get('1.0', tk.END)[:-1])
        hack_file_text_box.mark_set(tk.INSERT, temp_cursor)

    highlight_stuff()


def navigation_prompt():
    if not disasm:
        return
    address = simpledialog.askstring('Navigate to address', '')
    try:
        address = deci(address)
        if app_config['game_address_mode']:
            address -= disasm.game_offset
        address //= 4
    except:
        return
    apply_hack_changes()
    apply_comment_changes()
    reset_target()
    navigate_to(address)


def scroll_callback(event):
    global navigation, disasm
    if not disasm:
        return
    apply_hack_changes()
    apply_comment_changes()
    direction = -app_config['scroll_amount'] if event.delta > 0 else app_config['scroll_amount']
    navigate_to(navigation + direction)


def save_changes_to_file(save_as=False):
    global max_lines, disasm
    if not disasm:
        return False

    apply_hack_changes()
    apply_comment_changes()

    # Do not save changes if there are errors
    for key in user_errors:
        i = int(key)
        navigate_to(i - (max_lines // 2))
        highlight_stuff()
        return False

    if save_as:
        new_file_name = filedialog.asksaveasfilename(initialdir = app_config['previous_hack_location'],
                                                     title = 'Save as...')
        if not new_file_name:
            return False
        new_file_path = os.path.realpath(new_file_name)
        if new_file_path == disasm.base_folder + disasm.base_file_name:
            simpledialog.messagebox._show('Wait a sec', 'You shouldn\'t select the base file')
            return False
        new_dir = new_file_path[:new_file_path.rfind('\\') + 1]
        app_config['previous_hack_location'] = new_dir
        pickle_data(app_config, CONFIG_FILE)
        disasm.hack_file_name = new_file_name
        disasm.comments_file = new_file_name + '.comments'

    with open(disasm.comments_file, 'w') as file:
        file.write(dict_to_string(disasm.comments))

    with open(disasm.hack_folder + disasm.hack_file_name, 'wb') as file:
        file.write(disasm.hack_file)

    return True


def close_window(side = 'right'):
    global disasm
    if not disasm:
        window.destroy()
        return

    close_win_width = 270
    close_win_height = 45
    close_win_y_offset = 130

    win_w, win_h, win_x, win_y = geometry(window.geometry())

    placement_x = ((win_w if side == 'right' else close_win_width)  + win_x) - close_win_width
    placement_y = (close_win_y_offset + win_y) - close_win_height

    close_win_geo = '{}x{}+{}+{}'.format(close_win_width, close_win_height, placement_x, placement_y)

    close_win = tk.Tk()
    close_win.geometry(close_win_geo)
    close_win.title('Exit')
    label = tk.Label(close_win, text = 'Save work?').place(x = 150, y = 12)

    yes_button = tk.Button(close_win, text='Yes',command = lambda:\
        (save_changes_to_file(), window.destroy(), close_win.destroy()))
    no_button = tk.Button(close_win, text='No',command = lambda:\
        (window.destroy(), close_win.destroy()))

    yes_button.place(x=10, y=10, width=50)
    no_button.place(x=75, y=10, width=50)

    def cancel_close_win():
        global closing
        closing = False
        close_win.destroy()

    close_win.protocol('WM_DELETE_WINDOW', cancel_close_win)
    close_win.bind('<FocusOut>', lambda _: close_win.destroy())
    close_win.focus_force()
    close_win.mainloop()


def open_files(mode = ''):
    global disasm, change_rom_name_button

    if disasm:
        if not save_changes_to_file():
            return
        disasm = None
        [text_box.delete('1.0', tk.END) for text_box in ALL_TEXT_BOXES]
    else:
        [text_box.configure(state=tk.NORMAL) for text_box in ALL_TEXT_BOXES]

    if change_rom_name_button:
        change_rom_name_button.destroy()
        change_rom_name_button = None

    # Set data for rest of this function
    if mode == 'new':
        base_title = 'Select the original base rom'
        hack_title = 'Choose location and name for the new hacked rom'
        hack_dialog_function = filedialog.asksaveasfilename
    else:
        base_title = 'Select the base rom'
        hack_title = 'Select the hacked rom'
        hack_dialog_function = filedialog.askopenfilename

    # Obtain file locations from user input
    base_file_path = filedialog.askopenfilename(initialdir = app_config['previous_base_location'], title = base_title)
    if not base_file_path:
        return
    base_file_path = os.path.realpath(base_file_path)
    base_dir = base_file_path[:base_file_path.rfind('\\') + 1]

    hack_dir = base_dir if mode == 'new' else app_config['previous_hack_location']
    hack_file_path = hack_dialog_function(initialdir = hack_dir, title = hack_title)
    if not hack_file_path:
        return
    base_dot = base_file_path.rfind('.')
    file_extension = base_file_path[base_dot + 1:]
    if '.' not in hack_file_path:
        hack_file_path += '.' + file_extension
    else:
        hack_dot = hack_file_path.rfind('.')
        if hack_dot == len(hack_file_path) - 1:
            hack_file_path += file_extension
    hack_file_path = os.path.realpath(hack_file_path)
    hack_dir = hack_file_path[:hack_file_path.rfind('\\') + 1]

    if mode == 'new':
        if os.path.exists(hack_file_path):
            simpledialog.messagebox._show('Sorry', 'That file already exists')
            return
        else:
            with open(base_file_path, 'rb') as base_file:
                with open(hack_file_path, 'wb') as hack_file:
                    hack_file.write(base_file.read())

    timer_reset()

    # Remember dirs for next browse
    app_config['previous_base_location'] = base_dir
    app_config['previous_hack_location'] = hack_dir
    pickle_data(app_config, CONFIG_FILE)

    # Initialise disassembler with paths to the 2 files, apply saved settings from app_config
    try:
        disasm = Disassembler(base_file_path,
                              hack_file_path,
                              app_config['game_address_mode'],
                              app_config['immediate_identifier'])
    except Exception as e:
        simpledialog.messagebox._show('Error', e)
        base_file_text_box.delete('1.0', tk.END)
        hack_file_text_box.delete('1.0', tk.END)
        [text_box.configure(state=tk.DISABLED) for text_box in ALL_TEXT_BOXES]
        disasm = None
        return

    base_file_text_box.insert('1.0', 'Mapping out jumps...')
    hack_file_text_box.insert('1.0', 'Please wait')

    def rest_of_function():
        disasm.map_jumps()
        base_file_text_box.delete('1.0', tk.END)
        hack_file_text_box.delete('1.0', tk.END)

        # Navigate user to first line of code, start the undo buffer with the current data on screen
        navigate_to(0)
        buffer_append(hack_buffer, (navigation,
                                    cursor_value(1, 0),
                                    hack_file_text_box.get('1.0', tk.END)[:-1],
                                    app_config['immediate_identifier'],
                                    app_config['game_address_mode']))
        buffer_append(comments_buffer, (navigation,
                                        cursor_value(1, 0),
                                        comments_text_box.get('1.0', tk.END)[:-1]))
        timer_tick('Disasm init')

        # ints = ints_of_4_byte_aligned_region(disasm.hack_file)
        # timer_tick('Creating ints list')
        # for i in range(len(ints)):
        #     instruction = disasm.decode(ints[i], i)
        # timer_tick('Disassembling file')

    # Otherwise text boxes don't get updated to notify user of task
    window.after(1, rest_of_function)


def toggle_address_mode():
    apply_hack_changes()
    apply_comment_changes()
    buffer_append(hack_buffer, (navigation,
                                hack_file_text_box.index(tk.INSERT),
                                hack_file_text_box.get('1.0', tk.END)[:-1],
                                app_config['immediate_identifier'],
                                app_config['game_address_mode']))
    toggle_to = not app_config['game_address_mode']
    app_config['game_address_mode'] = toggle_to
    if disasm:
        disasm.game_address_mode = toggle_to
    pickle_data(app_config, CONFIG_FILE)
    navigate_to(navigation)


def change_immediate_id():
    accepted_symbols = ['<', '>', ':', ';', '\'', '"', '|', '{', '}', '[', ']',
                        '=', '+', '-', '_', '*', '&', '^', '%', '$', '#', '.',
                        '@', '!', '`', '~', '/', '?', '\\']
    symbol = simpledialog.askstring('Set immediate identifier symbol',
                                    'Must be one of {}'.format(' '.join(accepted_symbols)))
    if symbol and symbol[:1] in accepted_symbols:
        hack_text = hack_file_text_box.get('1.0', tk.END)[:-1]
        buffer_append(hack_buffer, (navigation,
                                    hack_file_text_box.index(tk.INSERT),
                                    hack_text,
                                    app_config['immediate_identifier'],
                                    app_config['game_address_mode']))
        hack_text.replace(app_config['immediate_identifier'], symbol[:1])
        hack_file_text_box.delete('1.0', tk.END)
        hack_file_text_box.insert('1.0', hack_text)
        for key in user_errors.keys():
            user_errors[key] = user_errors[key].replace(app_config['immediate_identifier'], symbol[:1])
        app_config['immediate_identifier'] = symbol[:1]
        if disasm:
            disasm.immediate_identifier = symbol[:1]
        pickle_data(app_config, CONFIG_FILE)


def set_scroll_amount():
    amount = simpledialog.askstring('Set scroll amount', 'Current: {}'.format(app_config['scroll_amount']))
    try:
        amount = deci(amount) if amount[:2] == '0x' else int(amount)
    except:
        return
    app_config['scroll_amount'] = amount
    pickle_data(app_config, CONFIG_FILE)


def help_box():
    message = '\n'.join([
        '----General Info----',
        'The base rom file is never modified, even if you try to make modifications to the textbox.',
        'It is simply there to reflect on if you need to see the original code at any point.',
        '',
        'In order to save any changes you have made, all errors must be resolved before the save feature will allow it.',
        'Trying to save while an error exists will result in your navigation shifting to the next error instead.',
        '',
        'The header part displays and edits as hex values.',
        '',
        'The comments file will be output to where your hacked rom is located.',
        'The comments file must always be located in the same folder as your hacked rom in order for it to load.',
        'You can also open the comments files with a text editor if required.',
        '',
        'When setting the scroll amount, use "0x" to specify a hexadecimal value, or leave it out to specify a decimal value.',
        '',
        '',
        '----Highlighting----',
        'Red: Error - Invalid syntax',
        'Orange: Error - Immediate value used beyond it\'s limit',
        'Pink: Jump functions',
        'Light Pink: Branch functions',
        'Light Purple: JR RA',
        'Light Green: Currently targeted register',
        'Light Cyan: Instructions which are targeted by selected jump or branch',
        'Dark Pink: Jumps or branches which target selected instruction',
        # Jump mapping needs fixing before it will be useful
        # 'Light Sky-Blue: Means there is a jump or branch somewhere in the assembly which targets the highlighted instruction',
        '',
        '',
        '----Keyboard----',
        'Ctrl+N: Open base rom and start new hacked file',
        'Ctrl+O: Open base rom and existing hacked rom',
        'Ctrl+S: Quick save',
        'Ctrl+J: Follow jump/branch at text insert cursor',
        'Ctrl+F: Find all jumps to function at text insert cursor',
        'F4: Navigate to address',
        'F5: Toggle mode which displays and handles addresses using the game\'s entry point',
        'Ctrl+{Comma} ("<" key): Undo',
        'Ctrl+{Fullstop} (">" key): Redo',
        '',
        'The hacked rom text box and comments text box have separate undo/redo buffers.',
        'Both buffers can hold up to 20,000 keystrokes worth of frames each.'
    ])
    simpledialog.messagebox._show('Help', message)


def about_box():
    message = '\n'.join([
        'Created by Mitchell Parry-Shaw with Python 3.5 during 2017 sometime.',
        'There really isn\'t much else to tell you. Sorry.'
    ])
    simpledialog.messagebox._show('Shoutouts to simpleflips', message)


def find_jumps():
    cursor, line, column = get_cursor(hack_file_text_box)
    navi = (line - 1) + navigation
    jumps = disasm.find_jumps(navi)
    # todo: make jump gui


def follow_jump():
    cursor, line, column = get_cursor(hack_file_text_box)
    navi = (line - 1) + navigation
    navi_4 = navi << 2
    int_word = ints_of_4_byte_aligned_region(disasm.hack_file[navi_4: navi_4 + 4])[0]
    opcode = (int_word & 0xFC000000) >> 26
    navi += 1  # Address calculated based on delay slot
    if opcode in JUMP_INTS:
        address = (int_word & 0x03FFFFFF) + (navi & 0x3C000000)
        navigate_to(address)
    elif opcode in BRANCH_INTS:
        address = sign_16_bit_value(int_word & 0xFFFF) + navi
        navigate_to(address)


def test_function():
    dictie = disasm.find_vector_instructions()
    asdf = None

menu_bar = tk.Menu(window)

file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label='Start new (Ctrl+N)', command=lambda: open_files('new'))
file_menu.add_command(label='Open existing (Ctrl+O)', command=lambda: open_files('existing'))
file_menu.add_separator()
file_menu.add_command(label='Save (Ctrl+S)', command=save_changes_to_file)
file_menu.add_command(label='Save as...', command=lambda: save_changes_to_file(True))
file_menu.add_separator()
file_menu.add_command(label='Exit', command=lambda: close_window('left'))
menu_bar.add_cascade(label='File', menu=file_menu)

tool_menu = tk.Menu(menu_bar, tearoff=0) # todo
tool_menu.add_command(label='Navigate (F4)', command=navigation_prompt)
# ----------------------------------------------------------------------------------
tool_menu.add_separator()
tool_menu.add_command(label='Test', command=test_function)
# ----------------------------------------------------------------------------------

menu_bar.add_cascade(label='Tools', menu=tool_menu)

opts_menu = tk.Menu(menu_bar, tearoff=0)
opts_menu.add_command(label='Toggle "game entry point" mode (F5)', command=toggle_address_mode)
opts_menu.add_command(label='Change immediate value identifier', command=change_immediate_id)
opts_menu.add_command(label='Set scroll amount', command=set_scroll_amount)
menu_bar.add_cascade(label='Options', menu=opts_menu)

help_menu = tk.Menu(menu_bar,tearoff=0)
help_menu.add_command(label='Help', command=help_box)
help_menu.add_command(label='About', command=about_box)
menu_bar.add_cascade(label='Help', menu=help_menu)

window.config(menu=menu_bar)

window.bind('<F4>', lambda e: navigation_prompt())
window.bind('<F5>', lambda e: toggle_address_mode())
window.bind('<Control-s>', lambda e: save_changes_to_file())
window.bind('<Control-n>', lambda e: open_files(mode='new'))
window.bind('<Control-o>', lambda e: open_files())
window.bind('<MouseWheel>', scroll_callback)
window.bind('<FocusOut>', lambda e: replace_clipboard())
window.bind('<Button-1>', lambda e: (reset_target(),
                                     apply_hack_changes(),
                                     apply_comment_changes(),
                                     highlight_stuff()) if disasm else None)
hack_file_text_box.bind('<Control-f>', lambda e: find_jumps())
hack_file_text_box.bind('<Control-j>', lambda e: follow_jump())

address_text_box.place(x=6, y=45, width=85, height=760)
base_file_text_box.place(x=95, y=45, width=315, height=760)
hack_file_text_box.place(x=414, y=45, width=315, height=760)
comments_text_box.place(x=733, y=45, width=597, height=760)

window.protocol('WM_DELETE_WINDOW', close_window)
window.mainloop()